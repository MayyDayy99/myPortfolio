"""ComfyUI bridge (CONTRACTS §8, comfyui-bridge skill).

This module is a 1:1 copy of the ``ComfyClient`` canon from
``.claude/skills/comfyui-bridge/SKILL.md`` plus the high-level
:func:`generate_image` entry point that the ``generate_image`` job handler
calls. The ComfyUI process runs natively on the macOS host (Metal GPU, ADR-2);
the container reaches it at ``http://host.docker.internal:8188`` (env
``COMFYUI_URL``). Output is fetched via ``/history`` + ``/view`` (ADR-5).

Error messages are Hungarian (UI/operator facing); identifiers and comments are
English (CLAUDE.md #9). The node ids to patch (positive prompt, KSampler seed,
SaveImage) are read from the workflow's ``*.meta.json`` sidecar, never hardcoded.
"""

from __future__ import annotations

import copy
import json
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

import websocket  # websocket-client package (ADR-7: Apache-2.0)

from app.config import get_settings

# --------------------------------------------------------------------------- #
# Hungarian error messages (skill "Hibakezelés" section) — verbatim.
# --------------------------------------------------------------------------- #
COMFY_UNREACHABLE = (
    "A ComfyUI nem érhető el — fut a Macen? (8188-as port; "
    "runbook: docs/04, 6. pont)"
)


class ComfyError(RuntimeError):
    """Raised on any ComfyUI bridge failure, carrying a Hungarian message."""


# --------------------------------------------------------------------------- #
# Canonical client (comfyui-bridge skill — copied 1:1 in structure).
# --------------------------------------------------------------------------- #
class ComfyClient:
    """Headless ComfyUI client: submit prompt, await over WS, fetch PNG."""

    def __init__(self, base_url: str):
        self.base = base_url.rstrip("/")  # http://host.docker.internal:8188
        self.ws_base = self.base.replace("http", "ws", 1)

    def load_workflow(self, path: str) -> dict:
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def generate(
        self,
        workflow: dict,
        *,
        prompt_text: str,
        seed: int,
        prompt_node: str,
        seed_node: str,
        timeout_s: int = 300,
    ) -> bytes:
        wf = copy.deepcopy(workflow)
        wf[prompt_node]["inputs"]["text"] = prompt_text  # positive prompt node
        wf[seed_node]["inputs"]["seed"] = seed  # KSampler node
        client_id = str(uuid.uuid4())

        req = urllib.request.Request(
            f"{self.base}/prompt",
            data=json.dumps({"prompt": wf, "client_id": client_id}).encode(),
            headers={"Content-Type": "application/json"},
        )
        prompt_id = json.loads(urllib.request.urlopen(req, timeout=15).read())["prompt_id"]

        ws = websocket.WebSocket()
        ws.connect(f"{self.ws_base}/ws?clientId={client_id}", timeout=timeout_s)
        try:
            while True:
                msg = ws.recv()
                if isinstance(msg, str):
                    m = json.loads(msg)
                    if (
                        m.get("type") == "executing"
                        and m["data"].get("node") is None
                        and m["data"].get("prompt_id") == prompt_id
                    ):
                        break  # done
        finally:
            ws.close()

        hist = json.loads(
            urllib.request.urlopen(f"{self.base}/history/{prompt_id}", timeout=15).read()
        )[prompt_id]
        images = [
            im
            for node in hist["outputs"].values()
            for im in node.get("images", [])
        ]
        if not images:
            # Empty images: no SaveImage node, or the run failed ComfyUI-side.
            # Surface the history status so the operator can debug (skill rule).
            status = hist.get("status")
            raise ComfyError(
                "A ComfyUI futás nem adott vissza képet — "
                f"history status: {status!r} (prompt_id: {prompt_id})."
            )
        img = images[0]
        q = urllib.parse.urlencode(
            {
                "filename": img["filename"],
                "subfolder": img["subfolder"],
                "type": img["type"],
            }
        )
        return urllib.request.urlopen(f"{self.base}/view?{q}", timeout=30).read()


# --------------------------------------------------------------------------- #
# Workflow meta loader: node ids live in the `*.meta.json` sidecar (CONTRACTS
# §8/§16), never hardcoded.
# --------------------------------------------------------------------------- #
def _load_meta(meta_path: Path) -> dict:
    """Read the node-id sidecar; raise a Hungarian error if it is malformed."""

    try:
        meta = json.loads(Path(meta_path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ComfyError(
            f"A workflow meta-fájl hiányzik: {meta_path}. "
            "Ez tartalmazza a prompt/seed/save node-azonosítókat."
        ) from exc
    except json.JSONDecodeError as exc:
        raise ComfyError(
            f"A workflow meta-fájl hibás JSON: {meta_path} ({exc})."
        ) from exc

    missing = [k for k in ("prompt_node", "seed_node", "save_node") if k not in meta]
    if missing:
        raise ComfyError(
            "A workflow meta-fájlból hiányzik a node-azonosító: "
            f"{', '.join(missing)} ({meta_path})."
        )
    return meta


# --------------------------------------------------------------------------- #
# High-level entry point — the `generate_image` job handler calls this.
# --------------------------------------------------------------------------- #
def generate_image(
    *,
    prompt_text: str,
    seed: int,
    out_path: Path,
    workflow_path: Path,
    meta_path: Path,
    base_url: str | None = None,
) -> None:
    """Generate one image with ComfyUI and write the PNG bytes to ``out_path``.

    The positive-prompt and KSampler-seed node ids come from ``meta_path``; the
    ``save_node`` id is validated to exist in the workflow. Connection failures
    are re-raised as :class:`ComfyError` with the canonical Hungarian message.

    Runtime code writes ONLY under the data dir (CLAUDE.md #7); the caller passes
    an ``out_path`` rooted there.
    """

    resolved_base = base_url or get_settings().comfyui_url
    client = ComfyClient(resolved_base)

    workflow = client.load_workflow(str(workflow_path))
    meta = _load_meta(Path(meta_path))

    save_node = meta["save_node"]
    if save_node not in workflow:
        raise ComfyError(
            f"A workflow nem tartalmazza a megadott SaveImage node-ot: "
            f"{save_node!r} ({workflow_path})."
        )

    try:
        png_bytes = client.generate(
            workflow,
            prompt_text=prompt_text,
            seed=seed,
            prompt_node=meta["prompt_node"],
            seed_node=meta["seed_node"],
        )
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as exc:
        # ConnectionRefused / timeout on /prompt (or any socket-level failure
        # reaching ComfyUI) -> canonical Hungarian "not reachable" message.
        raise ComfyError(COMFY_UNREACHABLE) from exc
    except websocket.WebSocketException as exc:
        raise ComfyError(COMFY_UNREACHABLE) from exc

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(png_bytes)
