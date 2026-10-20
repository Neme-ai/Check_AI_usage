"""Authenticated loopback-only receiver for the user's Chrome extension."""
import hmac
import json
import re
import secrets
import time
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from PySide6.QtCore import QThread, Signal
from usage_core import PROVIDERS, read_json, write_json, window

PORT = 18765

def validate_snapshot(data, now=None):
    now = time.time() if now is None else now
    if not isinstance(data, dict) or data.get("provider") not in PROVIDERS:
        raise ValueError("Invalid provider")
    observed = data.get("observed_at")
    if isinstance(observed, bool) or not isinstance(observed, (int, float)) or not now-120 <= observed <= now+10:
        raise ValueError("Stale observation")
    if data.get("status") != "ok":
        statuses = {"unrecognized": "页面未识别 · 请在 Chrome 中核验", "closed": "监控页已关闭 · 请从扩展重新打开", "offline": "页面加载失败 · 保留旧值", "wrong_page": "监控标签页已离开用量页面"}
        if data.get("status") not in statuses:
            raise ValueError("Invalid status")
        return data["provider"], {"status": statuses[data["status"]]}, observed
    raw = data.get("windows")
    if not isinstance(raw, list) or not 1 <= len(raw) <= 16:
        raise ValueError("Missing windows")
    rows, keys = [], set()
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("Invalid window")
        key = item.get("key")
        if key not in ("primary_window", "secondary_window", "five_hour", "seven_day") or key in keys:
            raise ValueError("Unknown or duplicate window")
        if data["provider"] == "codex" and key not in ("primary_window", "secondary_window"):
            raise ValueError("Mismatched provider")
        if data["provider"] == "claude" and key not in ("five_hour", "seven_day"):
            raise ValueError("Mismatched provider")
        keys.add(key)
        seconds = 18000 if key in ("primary_window", "five_hour") else 604800
        row = window(key, "5 小时" if seconds == 18000 else "每周", item.get("used"), item.get("reset_at"), seconds)
        if not row:
            raise ValueError("Invalid percentage")
        reset_text = item.get("reset_text", "")
        row["reset_text"] = reset_text[:160] if isinstance(reset_text, str) else ""
        rows.append(row)
    return data["provider"], {"windows": rows, "updated_at": observed, "status": "正常", "source": "Chrome 官方用量页"}, observed

class ExtensionBridge(QThread):
    update = Signal(str, dict)
    note = Signal(str)

    def __init__(self, root, port=PORT):
        super().__init__()
        self.port = port
        config = read_json(root / "extension-bridge.json", {})
        token = config.get("token") if isinstance(config, dict) else None
        self.token = token if isinstance(token, str) and len(token) == 43 else secrets.token_urlsafe(32)
        write_json(root / "extension-bridge.json", {"token": self.token, "port": port})
        self.refresh_generation = time.time_ns()
        self.last_observed = {}
        self.server = None
        self.state_lock = threading.Lock()

    def command(self, name, provider=None):
        if name == "quit":
            self.requestInterruption()
        elif name == "refresh":
            self.refresh_generation += 1

    def run(self):
        bridge = self
        class Handler(BaseHTTPRequestHandler):
            def setup(self):
                super().setup()
                self.connection.settimeout(3)

            def log_message(self, *args):
                pass

            def origin_allowed(self):
                origin = self.headers.get("Origin", "")
                return not origin or bool(re.fullmatch(r"chrome-extension://[a-p]{32}", origin))

            def authorized(self):
                return (self.headers.get("Host") == f"127.0.0.1:{bridge.port}"
                        and self.origin_allowed()
                        and hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + bridge.token))

            def respond(self, status, data):
                encoded = json.dumps(data).encode()
                self.send_response(status)
                origin = self.headers.get("Origin", "")
                if origin and self.origin_allowed():
                    self.send_header("Access-Control-Allow-Origin", origin)
                    self.send_header("Vary", "Origin")
                self.send_header("Content-Type", "application/json")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def do_OPTIONS(self):
                if not self.origin_allowed() or self.headers.get("Host") != f"127.0.0.1:{bridge.port}":
                    self.respond(403, {"ok": False})
                    return
                self.send_response(204)
                self.send_header("Access-Control-Allow-Origin", self.headers.get("Origin", ""))
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
                self.end_headers()

            def do_GET(self):
                if not self.authorized():
                    self.respond(403, {"ok": False})
                elif self.path == "/poll":
                    self.respond(200, {"ok": True, "refresh": str(bridge.refresh_generation)})
                else:
                    self.respond(404, {"ok": False})

            def do_POST(self):
                if not self.authorized():
                    self.respond(403, {"ok": False})
                    return
                if self.path != "/usage":
                    self.respond(404, {"ok": False})
                    return
                try:
                    size = int(self.headers.get("Content-Length", "0"))
                    if not 0 < size <= 16384:
                        raise ValueError()
                    data = json.loads(self.rfile.read(size))
                    key, update, observed = validate_snapshot(data)
                    with bridge.state_lock:
                        if observed < bridge.last_observed.get(key, 0):
                            raise ValueError()
                        bridge.last_observed[key] = observed
                        bridge.update.emit(key, update)
                    self.respond(200, {"ok": True})
                except (ValueError, OSError, TypeError):
                    self.respond(400, {"ok": False, "error": "invalid_or_stale_data"})

        try:
            self.server = ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
            self.port = self.server.server_port
            self.server.daemon_threads = True
            self.server.timeout = .25
            while not self.isInterruptionRequested():
                self.server.handle_request()
        except OSError:
            self.note.emit("本机扩展连接端口无法启动，请检查是否运行了另一份监控器。")
        finally:
            if self.server:
                self.server.server_close()
