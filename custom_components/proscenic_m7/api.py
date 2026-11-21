"""Client fuer die alte Proscenic-Cloud (Proscenic-Home-App, mobile.proscenic.com.de).

Ablauf (aus der Proscenic-Home-App 1.5.5 abgeleitet und gegen die echte Cloud getestet):
  1. POST /appInit/getToken            -> frischer Token (nur Benutzername noetig)
  2. POST /appInit/getSockAddr         -> IP/Port des Push-Servers
  3. TCP verbinden, Login (infoType 70001), Heartbeat alle 6 s (70003)
  4. POST /instructions/cmd20001/{sn}  -> Roboter schickt Status (infoType 20001)
Nachrichten sind JSON, mit "#\\t#" abgeschlossen. Bei "encrypt":1 ist "data" Base64 und
AES-128/ECB-verschluesselt, der Schluessel ist der Token.

Der Token wird nie geloggt oder gespeichert.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
from collections.abc import Callable
from typing import Any

import aiohttp
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://mobile.proscenic.com.de"
TERMINATOR = b"#\t#"
HEARTBEAT_INTERVAL = 6
POLL_INTERVAL = 20
READ_TIMEOUT = 30
CONNECT_TIMEOUT = 15
HTTP_TIMEOUT = aiohttp.ClientTimeout(total=15)
MIN_BACKOFF = 5
MAX_BACKOFF = 120


# Befehle, 1:1 aus den funktionierenden rest_commands des Pakets andker87/Proscenic-M7-PRO.
# {sn} = Seriennummer, {user} = Benutzername. Body wird als application/x-www-form-urlencoded gesendet.
COMMANDS: dict[str, tuple[str, str]] = {
    "clean": ("/instructions/cmd21005/{sn}", "cleanMode=sweepOnly"),
    "deep_clean": ("/instructions/cmd21005_2/{sn}", "cleanMode=depthTotalClean"),
    "empty_dust": (
        "/instructions/cmd/{sn}",
        '{{"dInfo":{{"userId":"{user}"}},"data":{{"cmd":"startDustCenter","value":0}},"infoType":21024}};',
    ),
    "pause": ("/instructions/{sn}/21017", "mode=pause"),
    "continue": ("/instructions/{sn}/21017", "pauseOrContinue=continue"),
    "charge": ("/instructions/{sn}/21012", "charge=start"),
    "fan_quiet": ("/instructions/{sn}/21022", "setMode=quiet"),
    "fan_standard": ("/instructions/{sn}/21022", "setMode=auto"),
    "fan_powerful": ("/instructions/{sn}/21022", "setMode=strong"),
}


class ProscenicError(Exception):
    """Basisfehler."""


class CannotConnect(ProscenicError):
    """Cloud nicht erreichbar oder unerwartete Antwort."""


class AuthError(ProscenicError):
    """Benutzername unbekannt, kein Token erhalten."""


class InvalidSerial(ProscenicError):
    """Keine Serveradresse fuer diese Seriennummer."""


def decrypt_payload(b64: str, key: str) -> str | None:
    """Entschluesselt ein Feld "data" (AES-128/ECB, PKCS7, Schluessel = Token).

    Hinter dem JSON haengt laut App-Code ein zusaetzliches Byte, daher wird bis zur
    letzten schliessenden Klammer abgeschnitten.
    """
    try:
        raw = base64.b64decode(b64)
        decryptor = Cipher(algorithms.AES(key.encode()), modes.ECB()).decryptor()
        out = decryptor.update(raw) + decryptor.finalize()
    except (ValueError, TypeError):
        return None
    if out:
        pad = out[-1]
        if 1 <= pad <= 16:
            out = out[:-pad]
    text = out.decode("utf-8", "replace")
    end = text.rfind("}")
    return text[: end + 1] if end >= 0 else None


class ProscenicClient:
    """Haelt die Push-Verbindung und stellt den letzten Status bereit."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        username: str,
        serial: str,
        base_url: str = BASE_URL,
    ) -> None:
        self._session = session
        self._username = username
        self._serial = serial
        self._base_url = base_url.rstrip("/")
        self._callback: Callable[[], None] | None = None
        self.status: dict[str, Any] = {}
        self.robot_online: bool | None = None
        self.connected = False
        self._token: str | None = None

    def set_callback(self, callback: Callable[[], None]) -> None:
        """Wird bei jeder Aenderung aufgerufen."""
        self._callback = callback

    def snapshot(self) -> dict[str, Any]:
        """Kopie des aktuellen Zustands fuer die Entitaeten."""
        return {
            "connected": self.connected,
            "robot_online": self.robot_online,
            "status": dict(self.status),
        }

    def _notify(self) -> None:
        if self._callback is not None:
            self._callback()

    # ---------------------------------------------------------------- HTTP
    async def _request(
        self,
        method: str,
        path: str,
        token: str | None = None,
        form: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        raw_body: str | None = None,
    ) -> dict[str, Any]:
        headers = {}
        if token:
            headers["token"] = token
        if raw_body is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        try:
            async with self._session.request(
                method,
                self._base_url + path,
                headers=headers,
                data=raw_body if raw_body is not None else form,
                params=params,
                timeout=HTTP_TIMEOUT,
            ) as resp:
                body = await resp.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
            raise CannotConnect(f"{path}: {err}") from err
        if not isinstance(body, dict):
            raise CannotConnect(f"{path}: unerwartete Antwort")
        return body

    async def async_get_token(self) -> str:
        """Frischen Token holen (wie die App, ohne Passwort)."""
        body = await self._request(
            "POST", "/appInit/getToken", form={"username": self._username}
        )
        token = (body.get("data") or {}).get("token")
        if body.get("code") != 0 or not token:
            raise AuthError(f"getToken code={body.get('code')}")
        return str(token)

    async def async_get_socket_addr(self, token: str) -> tuple[str, int]:
        body = await self._request(
            "POST",
            "/appInit/getSockAddr",
            token=token,
            form={"username": self._username, "sn": self._serial},
        )
        try:
            addr = body["data"]["addr_list"][0]
            return str(addr["ip"]), int(addr["port"])
        except (KeyError, IndexError, TypeError, ValueError) as err:
            if body.get("code") == 102:
                raise AuthError("Token abgelehnt") from err
            raise InvalidSerial(f"getSockAddr code={body.get('code')}") from err

    async def async_request_status(self, token: str) -> None:
        """Stoesst eine Statusmeldung (infoType 20001) an."""
        await self._request(
            "POST",
            f"/instructions/cmd20001/{self._serial}",
            token=token,
            params={"username": self._username},
        )

    async def async_command(self, name: str) -> None:
        """Sendet einen Steuerbefehl aus COMMANDS. Bei abgelaufenem Token einmal mit neuem Token."""
        path, body = COMMANDS[name]
        path = path.format(sn=self._serial)
        body = body.format(user=self._username)
        for attempt in (1, 2):
            token = self._token if attempt == 1 and self._token else await self.async_get_token()
            result = await self._request(
                "POST",
                path,
                token=token,
                params={"username": self._username},
                raw_body=body,
            )
            code = result.get("code")
            if code == 0:
                return
            if code == 102 and attempt == 1:
                self._token = None  # abgelaufen -> naechster Versuch holt einen neuen
                continue
            raise ProscenicError(f"Befehl {name}: code={code} msg={result.get('msg')}")

    async def async_refresh(self) -> None:
        """Statusmeldung sofort anstossen (z. B. nach einem Befehl)."""
        if self._token:
            try:
                await self.async_request_status(self._token)
            except ProscenicError as err:
                _LOGGER.debug("Statusabfrage fehlgeschlagen: %s", err)

    async def async_validate(self) -> None:
        """Prueft Benutzername und Seriennummer (fuer den Config-Flow)."""
        token = await self.async_get_token()
        await self.async_get_socket_addr(token)

    # -------------------------------------------------------------- Socket
    async def run(self) -> None:
        """Dauerschleife mit Reconnect und Backoff. Zum Beenden Task canceln."""
        backoff = MIN_BACKOFF
        loop = asyncio.get_running_loop()
        while True:
            started = loop.time()
            try:
                await self._session_once()
            except asyncio.CancelledError:
                raise
            except ProscenicError as err:
                _LOGGER.warning("Proscenic-Cloud: %s", err)
            except (OSError, asyncio.TimeoutError, ConnectionError) as err:
                _LOGGER.warning("Proscenic-Verbindung unterbrochen: %s", err)
            except Exception:  # noqa: BLE001 - die Schleife darf nie sterben
                _LOGGER.exception("Unerwarteter Fehler in der Proscenic-Verbindung")
            finally:
                if self.connected or self.robot_online is not None:
                    self.connected = False
                    self.robot_online = None
                    self._notify()
            if loop.time() - started > 60:
                backoff = MIN_BACKOFF
            _LOGGER.debug("Neuer Verbindungsversuch in %s s", backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, MAX_BACKOFF)

    async def _send(self, writer: asyncio.StreamWriter, info_type: int, data: dict) -> None:
        msg = json.dumps({"infoType": info_type, "data": data}, separators=(",", ":"))
        writer.write(msg.encode() + TERMINATOR)
        await writer.drain()

    async def _session_once(self) -> None:
        token = await self.async_get_token()
        self._token = token
        host, port = await self.async_get_socket_addr(token)
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), CONNECT_TIMEOUT
        )
        tasks: list[asyncio.Task] = []
        try:
            await self._send(writer, 70001, {"sn": self._serial, "token": token})
            tasks.append(asyncio.create_task(self._heartbeat(writer, token)))
            tasks.append(asyncio.create_task(self._poller(writer, token)))
            self.connected = True
            self._notify()
            _LOGGER.debug("Mit Proscenic-Push-Server verbunden")
            buf = b""
            while True:
                chunk = await asyncio.wait_for(reader.read(65536), READ_TIMEOUT)
                if not chunk:
                    raise ConnectionError("Server hat die Verbindung geschlossen")
                buf += chunk
                while TERMINATOR in buf:
                    raw, buf = buf.split(TERMINATOR, 1)
                    self._handle(raw, token)
        finally:
            for task in tasks:
                task.cancel()
            writer.close()
            self._token = None

    async def _heartbeat(self, writer: asyncio.StreamWriter, token: str) -> None:
        try:
            while True:
                await asyncio.sleep(HEARTBEAT_INTERVAL)
                await self._send(writer, 70003, {"token": token, "sn": self._serial})
        except (OSError, ConnectionError):
            return  # der Lese-Loop bemerkt den Abbruch

    async def _poller(self, writer: asyncio.StreamWriter, token: str) -> None:
        await asyncio.sleep(1)
        while True:
            try:
                await self.async_request_status(token)
            except ProscenicError as err:
                _LOGGER.debug("Statusabfrage fehlgeschlagen: %s", err)
            await asyncio.sleep(POLL_INTERVAL)

    def _handle(self, raw: bytes, token: str) -> None:
        text = raw.decode("utf-8", "replace").strip()
        if not text:
            return
        if '"infoType":70003' in text:
            # Heartbeat-Antwort ist kein gueltiges JSON (Token ohne Anfuehrungszeichen)
            online = '"online":true' in text
            if online != self.robot_online:
                self.robot_online = online
                self._notify()
            return
        try:
            msg = json.loads(text)
        except ValueError:
            _LOGGER.debug("Nicht lesbare Nachricht ignoriert")
            return
        if not isinstance(msg, dict):
            return
        if msg.get("encrypt") == 1:
            decrypted = decrypt_payload(str(msg.get("data", "")), token)
            if decrypted is None:
                _LOGGER.debug("Entschluesselung fehlgeschlagen")
                return
            try:
                inner = json.loads(decrypted)
            except ValueError:
                return
        else:
            inner = msg.get("data")
        if not isinstance(inner, dict):
            return
        if inner.get("infoType") == 20001 and isinstance(inner.get("data"), dict):
            self.status = inner["data"]
            self._notify()
