import http.client
import json
import tempfile
import time
import unittest
from pathlib import Path
from extension_bridge import ExtensionBridge, validate_snapshot

def sample():
    return {"provider": "codex", "status": "ok", "observed_at": time.time(),
            "windows": [{"key": "primary_window", "used": 30, "reset_at": 1900000000}]}

class BridgeTests(unittest.TestCase):
    def test_requires_fresh_correct_provider_and_finite_quota(self):
        data = sample()
        key, state, observed = validate_snapshot(data)
        self.assertEqual(state["windows"][0]["remaining"], 70)
        for change in ({"observed_at": time.time()-200}, {"provider": "other"}, {"status": "invented"}):
            with self.assertRaises(ValueError):
                validate_snapshot(dict(data, **change))
        data["windows"][0]["used"] = float("nan")
        with self.assertRaises(ValueError):
            validate_snapshot(data)

    def test_error_keeps_last_success_timestamp_and_values(self):
        _, update, _ = validate_snapshot({"provider": "claude", "status": "closed", "observed_at": time.time()})
        self.assertNotIn("windows", update)
        self.assertNotIn("updated_at", update)

    def test_loopback_token_origin_and_replay_checks(self):
        with tempfile.TemporaryDirectory() as folder:
            worker = ExtensionBridge(Path(folder), port=0)
            worker.start()
            deadline = time.time()+5
            while not worker.port and time.time()<deadline:
                time.sleep(.01)
            self.assertGreater(worker.port, 0)
            def request(method, path, data=None, token=None, origin=None):
                connection = http.client.HTTPConnection("127.0.0.1", worker.port, timeout=3)
                headers={"Authorization": "Bearer " + (token or "wrong"), "Content-Type": "application/json"}
                if origin:
                    headers["Origin"] = origin
                connection.request(method, path, json.dumps(data) if data else None, headers)
                response=connection.getresponse()
                result=(response.status, response.read())
                connection.close()
                return result
            try:
                self.assertEqual(request("GET", "/poll")[0],403)
                self.assertEqual(request("GET", "/poll",token=worker.token,origin="https://evil.example")[0],403)
                self.assertEqual(request("GET", "/poll",token=worker.token,origin="chrome-extension://"+"a"*32)[0],200)
                data=sample()
                self.assertEqual(request("POST", "/usage",data,worker.token)[0],200)
                data["observed_at"]-=5
                self.assertEqual(request("POST", "/usage",data,worker.token)[0],400)
                data=sample()
                data["windows"]*=2
                self.assertEqual(request("POST", "/usage",data,worker.token)[0],400)
            finally:
                worker.command("quit")
                self.assertTrue(worker.wait(3000))

if __name__ == "__main__":
    unittest.main()
