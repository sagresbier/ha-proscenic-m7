import asyncio, sys, logging
import aiohttp
import importlib.util
# api.py ohne HA-Paket laden (kein __init__ -> keine HA-Importe)
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("api", ROOT / "custom_components" / "proscenic_m7" / "api.py")
api = importlib.util.module_from_spec(spec); spec.loader.exec_module(api)
api.HEARTBEAT_INTERVAL = 0.2; api.POLL_INTERVAL = 0.5; api.READ_TIMEOUT = 2
api.MIN_BACKOFF = 0.3
sys.path.insert(0, str(ROOT / "tests"))
from fake_cloud import FakeCloud, TOKEN, encrypt

async def wait_for(cond, t=5):
    for _ in range(int(t / 0.05)):
        if cond(): return True
        await asyncio.sleep(0.05)
    return False

async def main():
    # Entschluesselung Rundlauf
    assert api.decrypt_payload(encrypt({"a": 1}, TOKEN), TOKEN) == '{"a": 1}'
    assert api.decrypt_payload("%%%", TOKEN) is None
    print("decrypt ok")

    cloud = FakeCloud(); await cloud.start()
    async with aiohttp.ClientSession() as s:
        # Validierung
        await api.ProscenicClient(s, "u@x.de", "SN123", cloud.base).async_validate()
        for user, sn, exc in (("wrong@x.de", "SN123", api.AuthError), ("u@x.de", "BAD", api.InvalidSerial)):
            try:
                await api.ProscenicClient(s, user, sn, cloud.base).async_validate()
                raise SystemExit("keine Exception fuer %s" % user)
            except exc: pass
        dead = api.ProscenicClient(s, "u@x.de", "SN123", "http://127.0.0.1:9")
        try: await dead.async_validate(); raise SystemExit("sollte fehlschlagen")
        except api.CannotConnect: pass
        print("validate ok")

        # Dauerbetrieb
        c = api.ProscenicClient(s, "u@x.de", "SN123", cloud.base)
        events = []
        c.set_callback(lambda: events.append(c.snapshot()))
        task = asyncio.create_task(c.run())
        assert await wait_for(lambda: c.status.get("elec") == 79), "kein Status"
        assert c.connected and c.robot_online is True
        assert c.status["mode"] == "dormant" and c.status["errorState"] == [-2402]
        print("status ok:", c.status["mode"], c.status["elec"])

        # Aenderung wird beim naechsten Poll uebernommen
        cloud.status = dict(cloud.status, mode="sweep", elec=60, errorState=[])
        assert await wait_for(lambda: c.status.get("mode") == "sweep"), "Update fehlt"
        assert c.status["elec"] == 60
        print("update ok")

        # Verbindungsabbruch -> Reconnect mit neuem Login
        logins = cloud.logins; tokens = cloud.token_calls
        cloud.drop_next = True
        assert await wait_for(lambda: not c.connected, 3), "Abbruch nicht erkannt"
        assert await wait_for(lambda: c.connected, 6), "kein Reconnect"
        assert cloud.logins == logins + 1 and cloud.token_calls == tokens + 1
        assert await wait_for(lambda: cloud.status_requests > 0)
        print("reconnect ok (neuer Token geholt)")

        # Cloud komplett weg -> Client bleibt am Leben und meldet nicht verbunden
        await cloud.stop()
        assert await wait_for(lambda: not c.connected, 5)
        assert c.robot_online is None
        assert not task.done()
        print("cloud weg ok, Task lebt")
        task.cancel()
        try: await task
        except asyncio.CancelledError: pass
    print("ALLE API-TESTS OK")

logging.basicConfig(level=logging.WARNING)


async def test_api():
    await main()


if __name__ == "__main__":
    asyncio.run(main())
