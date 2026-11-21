import json
from http.server import ThreadingHTTPServer
from pathlib import Path
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import torch

from tiny_voca import server


class FakeModel:
    class config:
        speakers = ("F2", "M2")
        sample_rate = 24000


class ServerTests(unittest.TestCase):
    def setUp(self):
        handler = server.create_handler(FakeModel(), Path(__file__).resolve().parents[1] / "web" / "server-ui")
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.httpd.server_port}"

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join()

    def post(self, payload):
        request = Request(
            self.url + "/api/speak",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        return urlopen(request)

    def test_speak_returns_a_wav(self):
        with patch.object(server.infer, "speak_text", return_value=(torch.zeros(240), [])) as speak:
            response = self.post({"text": "Hello there", "voice": "M2"})

        self.assertEqual(response.status, 200)
        self.assertEqual(response.headers.get_content_type(), "audio/wav")
        self.assertEqual(response.read()[:4], b"RIFF")
        speak.assert_called_once_with(unittest.mock.ANY, "Hello there", "M2")

    def test_invalid_voice_is_rejected_without_running_the_model(self):
        with patch.object(server.infer, "speak_text") as speak:
            with self.assertRaises(HTTPError) as error:
                self.post({"text": "Hello there", "voice": "unknown"})

        self.assertEqual(error.exception.code, 400)
        with error.exception as response:
            self.assertIn("F2, M2", response.read().decode())
        speak.assert_not_called()

    def test_health_and_interface_are_served(self):
        with urlopen(self.url + "/api/health") as response:
            health = json.loads(response.read())
        with urlopen(self.url + "/") as response:
            page = response.read().decode()

        self.assertEqual(health["voices"], ["F2", "M2"])
        self.assertIn("Generate speech", page)


if __name__ == "__main__":
    unittest.main()
