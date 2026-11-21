import asyncio
import pytest
from unittest.mock import patch
from homeassistant import config_entries
from homeassistant.const import CONF_USERNAME
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er, device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.proscenic_m7 import api as api_mod
from custom_components.proscenic_m7.const import DOMAIN, CONF_SERIAL
from fake_cloud import FakeCloud



@pytest.fixture
async def cloud():
    c = FakeCloud(); await c.start()
    api_mod.HEARTBEAT_INTERVAL = 0.2; api_mod.POLL_INTERVAL = 0.5
    orig = api_mod.ProscenicClient.__init__.__defaults__
    api_mod.ProscenicClient.__init__.__defaults__ = (c.base,)
    try:
        yield c
    finally:
        api_mod.ProscenicClient.__init__.__defaults__ = orig
        await c.stop()


async def _wait(hass, cond, t=6):
    for _ in range(int(t / 0.05)):
        await hass.async_block_till_done()
        if cond(): return True
        await asyncio.sleep(0.05)
    return False


async def test_config_flow(hass, cloud):
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert r["type"] == FlowResultType.FORM
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_USERNAME: "bad@x.de", CONF_SERIAL: "SN123"})
    assert r["errors"] == {"base": "invalid_auth"}
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_USERNAME: "u@x.de", CONF_SERIAL: "BAD"})
    assert r["errors"] == {"base": "invalid_serial"}
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {CONF_USERNAME: "u@x.de", CONF_SERIAL: "SN123"})
    assert r["type"] == FlowResultType.CREATE_ENTRY
    assert r["data"] == {CONF_USERNAME: "u@x.de", CONF_SERIAL: "SN123"}   # kein Token gespeichert
    await hass.async_block_till_done()
    # zweite Einrichtung derselben Seriennummer wird abgelehnt
    r2 = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    r2 = await hass.config_entries.flow.async_configure(r2["flow_id"], {CONF_USERNAME: "u@x.de", CONF_SERIAL: "SN123"})
    assert r2["type"] == FlowResultType.ABORT
    for e in hass.config_entries.async_entries(DOMAIN):
        await hass.config_entries.async_unload(e.entry_id)
    await hass.async_block_till_done()


async def test_entities(hass, cloud):
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_USERNAME: "u@x.de", CONF_SERIAL: "SN123"}, unique_id="SN123")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    ereg = er.async_get(hass)
    ids = {e.translation_key: e.entity_id for e in er.async_entries_for_config_entry(ereg, entry.entry_id)}
    print("ENTITIES:", ids)
    assert set(ids) == {"status", "battery", "cleaned_area", "clean_time", "total_area",
                        "total_time", "error", "problem", "robot_online", "robot",
                        "deep_clean", "empty_dust"}

    assert await _wait(hass, lambda: hass.states.get(ids["battery"]).state == "79")
    st = lambda k: hass.states.get(ids[k])
    assert st("status").state == "dormant"
    assert st("status").attributes["mode"] == "dormant"
    assert st("error").state == "side_brush"
    assert st("error").attributes["error_codes"] == [-2402]
    assert st("problem").state == "on"
    assert st("robot_online").state == "on"
    assert float(st("clean_time").state) == pytest.approx(2115 / 60, abs=0.1)   # Minuten
    assert float(st("total_time").state) == pytest.approx(834939 / 3600, abs=0.1)   # Stunden
    assert st("cleaned_area").state == "28"
    assert st("battery").attributes["device_class"] == "battery"

    # Zustandswechsel kommt per Push/Poll an
    cloud.status = dict(cloud.status, mode="sweep", elec=60, errorState=[])
    assert await _wait(hass, lambda: st("status").state == "cleaning")
    assert st("battery").state == "60" and st("problem").state == "off" and st("error").state == "none"

    # Unbekannter Modus -> unknown, roher Wert bleibt als Attribut
    cloud.status = dict(cloud.status, mode="neuermodus")
    assert await _wait(hass, lambda: st("status").state == "unknown")
    assert st("status").attributes["mode"] == "neuermodus"

    # Geraet
    dreg = dr.async_get(hass)
    if hasattr(dreg, "async_get_device_by_identifier"):   # neuere HA-Versionen
        dev = dreg.async_get_device_by_identifier((DOMAIN, "SN123"), entry.entry_id)
    else:
        dev = dreg.async_get_device(identifiers={(DOMAIN, "SN123")})
    assert dev and dev.manufacturer == "Proscenic" and dev.model == "M7 Pro"

    # Cloud faellt aus -> Entitaeten nicht verfuegbar
    for w in list(cloud.writers): w.close()
    await cloud.stop()
    assert await _wait(hass, lambda: st("battery").state == "unavailable", 10)

    # sauberes Entladen beendet den Hintergrund-Task
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_commands(hass, cloud):
    from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
    entry = MockConfigEntry(domain=DOMAIN, data={CONF_USERNAME: "u@x.de", CONF_SERIAL: "SN123"}, unique_id="SN123")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    ereg = er.async_get(hass)
    ents = {e.translation_key: e.entity_id for e in er.async_entries_for_config_entry(ereg, entry.entry_id)}
    vac = ents["robot"]
    print("VAC:", vac, "BUTTONS:", ents["deep_clean"], ents["empty_dust"])
    assert await _wait(hass, lambda: hass.states.get(vac).state == "idle")
    assert hass.states.get(vac).attributes["fan_speed"] == "quiet"
    assert hass.states.get(vac).attributes["fan_speed_list"] == ["quiet", "standard", "powerful"]

    async def call(domain, service, **data):
        n = len(cloud.commands)
        await hass.services.async_call(domain, service, data, blocking=True)
        assert len(cloud.commands) == n + 1, "genau ein Befehl erwartet"
        return cloud.commands[-1]

    def check(cmd, path, body):
        assert cmd["path"] == path, cmd
        assert cmd["username"] == "u@x.de"
        assert cmd["token"] == "AbCdEfGh01234567"
        assert cmd["ctype"] == "application/x-www-form-urlencoded"
        assert cmd["body"] == body, cmd

    # Exakt die Werte aus rest_commands.yaml des Pakets
    check(await call("vacuum", "start", entity_id=vac), "/instructions/cmd21005/SN123", "cleanMode=sweepOnly")
    check(await call("button", "press", entity_id=ents["deep_clean"]), "/instructions/cmd21005_2/SN123", "cleanMode=depthTotalClean")
    check(await call("button", "press", entity_id=ents["empty_dust"]), "/instructions/cmd/SN123",
          '{"dInfo":{"userId":"u@x.de"},"data":{"cmd":"startDustCenter","value":0},"infoType":21024};')
    check(await call("vacuum", "pause", entity_id=vac), "/instructions/SN123/21017", "mode=pause")
    check(await call("vacuum", "return_to_base", entity_id=vac), "/instructions/SN123/21012", "charge=start")
    check(await call("vacuum", "set_fan_speed", entity_id=vac, fan_speed="powerful"), "/instructions/SN123/21022", "setMode=strong")
    check(await call("vacuum", "set_fan_speed", entity_id=vac, fan_speed="standard"), "/instructions/SN123/21022", "setMode=auto")
    check(await call("vacuum", "set_fan_speed", entity_id=vac, fan_speed="quiet"), "/instructions/SN123/21022", "setMode=quiet")
    check(await call("vacuum", "send_command", entity_id=vac, command="deep_clean"), "/instructions/cmd21005_2/SN123", "cleanMode=depthTotalClean")

    # Pausiert -> start setzt fort
    cloud.status = dict(cloud.status, mode="pause")
    assert await _wait(hass, lambda: hass.states.get(vac).state == "paused")
    check(await call("vacuum", "start", entity_id=vac), "/instructions/SN123/21017", "pauseOrContinue=continue")

    # Saugt / Rueckfahrt / Fehler
    for mode, expected in (("sweep", "cleaning"), ("tocharge", "returning"), ("fullcharge", "docked"), ("fault", "error")):
        cloud.status = dict(cloud.status, mode=mode)
        assert await _wait(hass, lambda: hass.states.get(vac).state == expected), (mode, hass.states.get(vac).state)

    # Unbekannter Befehl / unbekannte Saugstaerke
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call("vacuum", "send_command", {"entity_id": vac, "command": "format_c"}, blocking=True)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call("vacuum", "set_fan_speed", {"entity_id": vac, "fan_speed": "turbo"}, blocking=True)

    # Abgelaufener Token: ein Retry mit frischem Token
    cloud.expire_once = 1
    tokens = cloud.token_calls
    n = len(cloud.commands)
    await hass.services.async_call("vacuum", "pause", {"entity_id": vac}, blocking=True)
    assert len(cloud.commands) == n + 2 and cloud.token_calls == tokens + 1

    # Cloud meldet Fehlercode -> HomeAssistantError
    cloud.fail_code = 500
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call("vacuum", "pause", {"entity_id": vac}, blocking=True)
    cloud.fail_code = 0

    # Nach einem Befehl wird der Status zeitnah neu abgefragt
    before = cloud.status_requests
    await hass.services.async_call("vacuum", "pause", {"entity_id": vac}, blocking=True)
    assert await _wait(hass, lambda: cloud.status_requests > before, 8)

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
