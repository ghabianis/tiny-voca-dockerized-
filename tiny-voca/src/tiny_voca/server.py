"""Serve a persistent tiny-voca model and a small browser interface."""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import logging
import mimetypes
import os
from pathlib import Path
import threading
from urllib.parse import urlsplit

import soundfile as sf
import torch

from . import infer
from .text import NothingToPronounce

LOGGER = logging.getLogger("tiny_voca.server")
MAX_TEXT_LENGTH = 2000
MAX_REQUEST_BYTES = 16_384
WEB_DIR = Path(os.environ.get("TINY_VOCA_WEB_DIR", Path(__file__).resolve().parents[2] / "web" / "server-ui"))


def create_handler(model, web_dir=WEB_DIR):
    inference_lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def _send(self, status, content_type, body, headers=()):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for name, value in headers:
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)

        def _send_json(self, status, payload):
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self._send(status, "application/json; charset=utf-8", body)

        def do_GET(self):
            path = urlsplit(self.path).path
            if path == "/api/health":
                self._send_json(200, {
                    "ready": True,
                    "voices": list(model.config.speakers),
                    "sample_rate": model.config.sample_rate,
                })
                return

            asset = {
                "/": "index.html",
                "/app.css": "app.css",
                "/app.js": "app.js",
            }.get(path)
            if asset is None:
                self._send_json(404, {"error": "Not found"})
                return
            try:
                body = (web_dir / asset).read_bytes()
            except OSError:
                LOGGER.exception("Could not read web interface asset %s", asset)
                self._send_json(500, {"error": "Web interface is unavailable"})
                return
            self._send(200, mimetypes.guess_type(asset)[0] or "application/octet-stream", body)

        def do_POST(self):
            if urlsplit(self.path).path != "/api/speak":
                self._send_json(404, {"error": "Not found"})
                return

            content_length = self.headers.get("Content-Length")
            if content_length is None:
                self._send_json(411, {"error": "Content-Length is required"})
                return
            try:
                size = int(content_length)
            except ValueError:
                self._send_json(400, {"error": "Invalid Content-Length"})
                return
            if size < 0:
                self._send_json(400, {"error": "Invalid Content-Length"})
                return
            if size > MAX_REQUEST_BYTES:
                self._send_json(413, {"error": "Request is too large"})
                return

            try:
                payload = json.loads(self.rfile.read(size))
            except (json.JSONDecodeError, UnicodeDecodeError):
                self._send_json(400, {"error": "Request body must be valid JSON"})
                return
            if not isinstance(payload, dict):
                self._send_json(400, {"error": "Request body must be a JSON object"})
                return

            text = payload.get("text")
            voice = payload.get("voice", "F2")
            if not isinstance(text, str) or not text.strip():
                self._send_json(400, {"error": "Enter some text to speak"})
                return
            if len(text) > MAX_TEXT_LENGTH:
                self._send_json(413, {"error": f"Text must be {MAX_TEXT_LENGTH} characters or fewer"})
                return
            if voice not in model.config.speakers:
                self._send_json(400, {"error": f"Voice must be one of {', '.join(model.config.speakers)}"})
                return

            try:
                with inference_lock, torch.inference_mode():
                    wave, _ = infer.speak_text(model, text, voice)
                output = io.BytesIO()
                sf.write(output, wave.numpy(), model.config.sample_rate, format="WAV", subtype="PCM_16")
            except NothingToPronounce as error:
                self._send_json(422, {"error": str(error)})
                return
            except ValueError as error:
                self._send_json(422, {"error": str(error)})
                return
            except Exception:
                LOGGER.exception("Speech generation failed")
                self._send_json(500, {"error": "Speech generation failed; check the server logs"})
                return

            self._send(200, "audio/wav", output.getvalue(), (("Content-Disposition", 'inline; filename="speech.wav"'),))

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, default=Path(os.environ.get("TINY_VOCA_CHECKPOINT", "weights/tiny-voca.pt")))
    parser.add_argument("--host", default=os.environ.get("HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8000")))
    args = parser.parse_args()
    if not args.checkpoint.is_file():
        parser.error(f"checkpoint not found: {args.checkpoint}")

    if infer.FRONTEND_VARIABLE not in os.environ:
        infer.match_frontend(args.checkpoint)
    model = infer.load_model(args.checkpoint)
    server = ThreadingHTTPServer((args.host, args.port), create_handler(model))
    LOGGER.info("Model ready; listening at http://%s:%s", args.host, args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        LOGGER.info("Shutting down")
    finally:
        server.server_close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    main()
