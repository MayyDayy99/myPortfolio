"""Tests for the ComfyUI bridge (CONTRACTS §8). NO real ComfyUI.

A tiny threaded ``http.server`` impersonates ComfyUI's ``/prompt``, ``/history``
and ``/view`` HTTP endpoints; the websocket "wait for completion" step is
replaced with a fake ``websocket.WebSocket`` via monkeypatch (http.server can't
speak the WS protocol). We assert that:

* :func:`generate_image` writes a real PNG and parses the SaveImage node output;
* a refused connection raises the canonical Hungarian "ComfyUI nem érhető el".
"""

from __future__ import annotations

import json
import struct
import threading
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from app.pipeline import comfy

_WORKFLOWS = Path(__file__).resolve().parents[2] / "workflows"
_WORKFLOW_PATH = _WORKFLOWS / "item-image.json"
_META_PATH = _WORKFLOWS / "item-image.meta.json"

_PROMPT_ID = "test-prompt-id-0001"
_FILENAME = "item-image_00001_.png"
_SUBFOLDER = ""
_TYPE = "output"


def _make_png_bytes() -> bytes:
    """Build a minimal valid 1x1 RGBA PNG (signature + IHDR + IDAT + IEND)."""

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)  # 1x1, 8-bit, RGBA
    raw = b"\x00" + b"\xff\x00\x00\xff"  # one filter byte + one red pixel
    idat = zlib.compress(raw)
    return sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


_PNG = _make_png_bytes()


class _FakeComfyHandler(BaseHTTPRequestHandler):
    """Minimal stand-in for the ComfyUI HTTP API.

    Set the class attribute ``empty_images = True`` (via a subclass) to make
    ``/history`` return an output node with no images, exercising the
    empty-images error branch.
    """

    empty_images = False

    def log_message(self, *args):  # silence the server's stderr logging
        return

    def _send_json(self, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        if urlparse(self.path).path == "/prompt":
            length = int(self.headers.get("Content-Length", 0))
            self.rfile.read(length)  # drain the body
            self._send_json({"prompt_id": _PROMPT_ID})
        else:
            self.send_error(404)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == f"/history/{_PROMPT_ID}":
            images = (
                []
                if self.empty_images
                else [
                    {
                        "filename": _FILENAME,
                        "subfolder": _SUBFOLDER,
                        "type": _TYPE,
                    }
                ]
            )
            self._send_json(
                {
                    _PROMPT_ID: {
                        "status": {"completed": not self.empty_images},
                        "outputs": {"9": {"images": images}},
                    }
                }
            )
        elif parsed.path == "/view":
            qs = parse_qs(parsed.query)
            assert qs.get("filename") == [_FILENAME]
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(_PNG)))
            self.end_headers()
            self.wfile.write(_PNG)
        else:
            self.send_error(404)


class _FakeWebSocket:
    """Drop-in for ``websocket.WebSocket``: yields the 'execution done' frame."""

    def __init__(self) -> None:
        self._sent = False

    def connect(self, url: str, timeout: float | None = None) -> None:  # noqa: ARG002
        self._url = url

    def recv(self) -> str:
        # First a noise frame, then the terminal "executing / node=None" frame.
        if not self._sent:
            self._sent = True
            return json.dumps({"type": "status", "data": {"status": {}}})
        return json.dumps(
            {"type": "executing", "data": {"node": None, "prompt_id": _PROMPT_ID}}
        )

    def close(self) -> None:
        pass


class _EmptyImagesHandler(_FakeComfyHandler):
    """Handler variant whose /history returns no images."""

    empty_images = True


def _serve(handler_cls):
    """Start a daemon HTTP server on an ephemeral port; return (server, base)."""

    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, thread, f"http://{host}:{port}"


@pytest.fixture
def comfy_server():
    """Run the fake ComfyUI HTTP server on an ephemeral localhost port."""

    server, thread, base = _serve(_FakeComfyHandler)
    try:
        yield base
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture
def comfy_server_empty():
    """Fake ComfyUI whose /history returns an output node with no images."""

    server, thread, base = _serve(_EmptyImagesHandler)
    try:
        yield base
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_generate_image_writes_png(
    comfy_server: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Replace the websocket with a fake that immediately reports completion.
    monkeypatch.setattr(comfy.websocket, "WebSocket", _FakeWebSocket)

    out_path = tmp_path / "out" / "generated.png"
    comfy.generate_image(
        prompt_text="egy barátságos tehén egy mezőn",
        seed=123,
        out_path=out_path,
        workflow_path=_WORKFLOW_PATH,
        meta_path=_META_PATH,
        base_url=comfy_server,
    )

    # The PNG from the SaveImage node output was downloaded and written.
    assert out_path.is_file()
    data = out_path.read_bytes()
    assert data == _PNG
    assert data.startswith(b"\x89PNG\r\n\x1a\n")


def test_refused_connection_raises_hungarian(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Point at a closed port so the POST /prompt connection is refused.
    # 127.0.0.1:1 is not listening; urlopen raises URLError(ConnectionRefused).
    monkeypatch.setattr(comfy.websocket, "WebSocket", _FakeWebSocket)

    with pytest.raises(comfy.ComfyError) as excinfo:
        comfy.generate_image(
            prompt_text="bármi",
            seed=1,
            out_path=tmp_path / "nope.png",
            workflow_path=_WORKFLOW_PATH,
            meta_path=_META_PATH,
            base_url="http://127.0.0.1:1",
        )

    assert "A ComfyUI nem érhető el" in str(excinfo.value)
    # The output file must not have been created on failure.
    assert not (tmp_path / "nope.png").exists()


def test_empty_images_reports_status(
    comfy_server_empty: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """An empty `images` list surfaces the history status (skill rule)."""

    monkeypatch.setattr(comfy.websocket, "WebSocket", _FakeWebSocket)

    with pytest.raises(comfy.ComfyError) as excinfo:
        comfy.generate_image(
            prompt_text="x",
            seed=1,
            out_path=tmp_path / "x.png",
            workflow_path=_WORKFLOW_PATH,
            meta_path=_META_PATH,
            base_url=comfy_server_empty,
        )
    msg = str(excinfo.value)
    assert "nem adott vissza képet" in msg
    # The history status is included in the log message for debugging.
    assert "status" in msg
    assert not (tmp_path / "x.png").exists()
