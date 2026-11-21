"""Fake der Proscenic-Cloud: HTTP (aiohttp) + TCP-Push-Server."""
import asyncio, base64, json
from aiohttp import web
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

TOKEN = "AbCdEfGh01234567"
TERM = b"#\t#"

def encrypt(obj, key):
    plain = json.dumps(obj).encode() + b"\n"          # Extra-Byte wie in der echten Cloud
    pad = 16 - len(plain) % 16
    plain += bytes([pad]) * pad
    enc = Cipher(algorithms.AES(key.encode()), modes.ECB()).encryptor()
    return base64.b64encode(enc.update(plain) + enc.finalize()).decode()

class FakeCloud:
    def __init__(self, serial="SN123", user="u@x.de"):
        self.serial, self.user = serial, user
        self.status = {"mode": "dormant", "subMode": "null", "elec": 79, "cleanArea": 28,
                       "cleanTime": 2115, "workNoisy": "quiet", "allArea": 11125, "allTime": 834939, "errorState": [-2402]}
        self.status_requests = 0
        self.logins = 0
        self.drop_next = False
        self.writers = []
        self.token_calls = 0
        self.commands = []          # aufgezeichnete Steuerbefehle
        self.expire_once = 0        # naechste N Befehle mit Code 102 beantworten
        self.fail_code = 0          # != 0: Befehle mit diesem Code beantworten

    async def start(self):
        self.tcp = await asyncio.start_server(self._tcp, "127.0.0.1", 0)
        self.port = self.tcp.sockets[0].getsockname()[1]
        app = web.Application()
        app.add_routes([
            web.post("/appInit/getToken", self._token),
            web.post("/appInit/getSockAddr", self._addr),
            web.post("/instructions/cmd20001/{sn}", self._cmd20001),
            web.post("/instructions/cmd21005/{sn}", self._command),
            web.post("/instructions/cmd21005_2/{sn}", self._command),
            web.post("/instructions/cmd/{sn}", self._command),
            web.post("/instructions/{sn}/{code}", self._command),
        ])
        self.runner = web.AppRunner(app); await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", 0); await site.start()
        self.http_port = site._server.sockets[0].getsockname()[1]
        self.base = f"http://127.0.0.1:{self.http_port}"

    async def stop(self):
        for w in self.writers: w.close()
        self.tcp.close(); await self.runner.cleanup()

    async def _token(self, req):
        self.token_calls += 1
        form = await req.post()
        if form.get("username") != self.user:
            return web.json_response({"code": 1, "msg": "no user", "data": {}})
        return web.json_response({"code": 0, "msg": "OK", "data": {"token": TOKEN}})

    async def _addr(self, req):
        if req.headers.get("token") != TOKEN:
            return web.json_response({"code": 102, "msg": "token expired", "data": {}})
        form = await req.post()
        if form.get("sn") != self.serial:
            return web.json_response({"code": 0, "msg": "OK", "data": {}})
        return web.json_response({"code": 0, "msg": "OK",
                                  "data": {"addr_list": [{"ip": "127.0.0.1", "port": self.port}]}})

    async def _cmd20001(self, req):
        assert req.headers.get("token") == TOKEN
        assert req.query.get("username") == self.user
        self.status_requests += 1
        for w in list(self.writers):
            msg = {"encrypt": 1, "data": encrypt({"infoType": 20001, "data": self.status}, TOKEN)}
            w.write(json.dumps(msg).encode() + TERM)
            # dazwischen eine andere verschluesselte Nachricht (Karte), muss ignoriert werden
            msg2 = {"encrypt": 1, "data": encrypt({"infoType": 20002, "data": {"map": "x"}}, TOKEN)}
            w.write(json.dumps(msg2).encode() + TERM)
        return web.json_response({"code": 0, "msg": "OK", "data": None})

    async def _command(self, req):
        body = (await req.read()).decode()
        self.commands.append({
            "path": req.path, "username": req.query.get("username"),
            "token": req.headers.get("token"), "ctype": req.headers.get("Content-Type"), "body": body,
        })
        if self.expire_once > 0:
            self.expire_once -= 1
            return web.json_response({"code": 102, "msg": "token expired", "data": None})
        if req.headers.get("token") != TOKEN:
            return web.json_response({"code": 102, "msg": "token expired", "data": None})
        if self.fail_code:
            return web.json_response({"code": self.fail_code, "msg": "robot offline", "data": None})
        return web.json_response({"code": 0, "msg": "OK", "data": None})

    async def _tcp(self, reader, writer):
        self.writers.append(writer)
        buf = b""
        try:
            while True:
                chunk = await reader.read(4096)
                if not chunk: break
                buf += chunk
                while TERM in buf:
                    raw, buf = buf.split(TERM, 1)
                    m = json.loads(raw)
                    if m["infoType"] == 70001:
                        assert m["data"]["token"] == TOKEN and m["data"]["sn"] == self.serial
                        self.logins += 1
                        writer.write(json.dumps({"encrypt": 0, "data": {"infoType": 70001, "data": {"expire": False}}}).encode() + TERM)
                    elif m["infoType"] == 70003:
                        if self.drop_next:
                            self.drop_next = False
                            writer.close(); return
                        # echte Cloud: Token ohne Anfuehrungszeichen -> kein gueltiges JSON
                        writer.write(('{"encrypt":0,"data":{"infoType":70003,"data":{"online":true,"expire":false,"token":%s}}}' % TOKEN).encode() + TERM)
                    await writer.drain()
        except (ConnectionError, asyncio.CancelledError):
            pass
        finally:
            if writer in self.writers: self.writers.remove(writer)
