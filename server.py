"""
Photopea AI Copilot - Unified Web & Bridge Server
Runs the web interface on http://localhost:8000, embeds Photopea,
and acts as a high-speed real-time bridge between ChatGPT (via MCP) and Photopea.
"""

import os
import sys
import json
import time
import asyncio
from typing import Dict, Any, Optional

from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, FileResponse
from starlette.staticfiles import StaticFiles
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
OUTPUTS_DIR = os.path.join(BASE_DIR, "outputs")
os.makedirs(TEMPLATES_DIR, exist_ok=True)
os.makedirs(OUTPUTS_DIR, exist_ok=True)

# In-memory Bridge State for real-time ChatGPT <-> Photopea synchronization
class PhotopeaBridge:
    def __init__(self):
        self.pending_command: Optional[Dict[str, Any]] = None
        self.last_command_id: int = 0
        self.command_results: Dict[str, Any] = {}
        self.active_document: Dict[str, Any] = {
            "name": "Nessun documento",
            "width": 0,
            "height": 0,
            "layers": []
        }
        self.last_preview_path: Optional[str] = None
        self.action_history: list = []

    def queue_command(self, script: str, description: str, timeout: float = 6.0) -> Dict[str, Any]:
        self.last_command_id += 1
        cmd_id = f"cmd_{self.last_command_id}_{int(time.time() * 1000)}"
        cmd = {
            "id": cmd_id,
            "script": script,
            "description": description,
            "created_at": time.time(),
            "status": "pending"
        }
        self.pending_command = cmd
        self.action_history.append({
            "id": cmd_id,
            "description": description,
            "timestamp": time.time(),
            "status": "in_progress"
        })
        return cmd

    def resolve_command(self, cmd_id: str, result: Dict[str, Any]):
        self.command_results[cmd_id] = result
        if self.pending_command and self.pending_command.get("id") == cmd_id:
            self.pending_command = None
        
        # Update action history
        for item in self.action_history:
            if item.get("id") == cmd_id:
                item["status"] = "completed"
                item["result"] = result
                break

bridge = PhotopeaBridge()

# ============================================================================
# API Endpoints for Browser <-> Server Bridge
# ============================================================================

async def api_get_pending_command(request: Request):
    """The browser polls this endpoint to receive scripts ordered by ChatGPT via MCP."""
    if bridge.pending_command:
        cmd = bridge.pending_command
        return JSONResponse(cmd)
    return JSONResponse({"status": "idle"})

async def api_post_command_result(request: Request):
    """The browser sends back the execution confirmation or error from Photopea."""
    try:
        data = await request.json()
        cmd_id = data.get("id")
        if cmd_id:
            bridge.resolve_command(cmd_id, data)
        return JSONResponse({"status": "acknowledged"})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=400)

async def api_update_layers(request: Request):
    """The browser updates the server whenever the document layers change in Photopea."""
    try:
        data = await request.json()
        bridge.active_document = {
            "name": data.get("docName", "Documento"),
            "width": data.get("width", 1080),
            "height": data.get("height", 1080),
            "layers": data.get("layers", []),
            "updated_at": time.time()
        }
        return JSONResponse({"status": "ok", "layers_count": len(bridge.active_document["layers"])})
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=400)

async def api_get_state(request: Request):
    """Returns the full state of the active document and recent history."""
    return JSONResponse({
        "document": bridge.active_document,
        "pending_command": bridge.pending_command,
        "history": bridge.action_history[-10:]
    })

async def api_send_command_and_wait(request: Request):
    """
    Called by MCP Server: queues an ExtendScript command, waits for Photopea
    to execute it via the browser, and returns the result to ChatGPT.
    """
    try:
        data = await request.json()
        script = data.get("script", "")
        desc = data.get("description", "Azione Photopea")
        timeout = float(data.get("timeout", 5.0))

        cmd = bridge.queue_command(script, desc, timeout)
        cmd_id = cmd["id"]

        # Wait for resolution
        start_time = time.time()
        while time.time() - start_time < timeout:
            if cmd_id in bridge.command_results:
                res = bridge.command_results.pop(cmd_id)
                return JSONResponse({
                    "status": "success",
                    "id": cmd_id,
                    "description": desc,
                    "result": res,
                    "active_document": bridge.active_document
                })
            await asyncio.sleep(0.1)

        # Timeout reached
        return JSONResponse({
            "status": "pending_or_timeout",
            "id": cmd_id,
            "message": "Comando inviato alla coda di Photopea. Se il browser è aperto su http://localhost:8000 verrà eseguito a breve.",
            "active_document": bridge.active_document
        })
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

from image_decomposer import ImageDecomposer

async def api_convert_image_to_psd(request: Request):
    """Handles uploading an image and converting it into editable PSD layers in Photopea."""
    try:
        form = await request.form()
        file_item = form.get("file")
        if not file_item:
            return JSONResponse({"status": "error", "message": "Nessuna immagine fornita"}, status_code=400)

        filename = getattr(file_item, "filename", f"input_{int(time.time())}.png")
        saved_path = os.path.join(TEMPLATES_DIR, filename)
        contents = await file_item.read()
        with open(saved_path, "wb") as f:
            f.write(contents)

        # Run decomposition with full base_url
        base_url = str(request.base_url).rstrip("/")
        decomp = ImageDecomposer.convert_image_to_psd_script(saved_path, base_url=base_url)

        # Queue script to Photopea
        bridge.queue_command(
            decomp["extendscript"],
            f"Conversione immagine '{filename}' in livelli PSD modificabili",
            timeout=8.0
        )

        return JSONResponse({
            "status": "success",
            "message": f"Immagine '{filename}' scomposta in {decomp['detected_layers_count']} livelli modificabili!",
            "decomposition": decomp
        })
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

async def api_convert_sample(request: Request):
    """Converts the built-in sample flat post into editable PSD layers in Photopea."""
    try:
        sample_path = os.path.join(TEMPLATES_DIR, "flat_sample_post.png")
        if not os.path.exists(sample_path):
            return JSONResponse({"status": "error", "message": "Immagine di esempio non trovata"}, status_code=404)

        base_url = str(request.base_url).rstrip("/")
        decomp = ImageDecomposer.convert_image_to_psd_script(sample_path, base_url=base_url)
        bridge.queue_command(
            decomp["extendscript"],
            "Conversione Immagine Demo ('flat_sample_post.png') in PSD a livelli modificabili",
            timeout=8.0
        )
        return JSONResponse({
            "status": "success",
            "message": f"Immagine demo scomposta in {decomp['detected_layers_count']} livelli modificabili!",
            "decomposition": decomp
        })
    except Exception as e:
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

async def api_upload_psd(request: Request):
    """Handles uploading a custom PSD file."""
    form = await request.form()
    file_item = form.get("file")
    if not file_item:
        return JSONResponse({"status": "error", "message": "Nessun file ricevuto"}, status_code=400)

    filename = getattr(file_item, "filename", f"upload_{int(time.time())}.psd")
    out_path = os.path.join(TEMPLATES_DIR, filename)
    contents = await file_item.read()
    with open(out_path, "wb") as f:
        f.write(contents)

    return JSONResponse({
        "status": "success",
        "filename": filename,
        "file_path": out_path,
        "size_bytes": len(contents)
    })

# Routes Configuration
routes = [
    Route("/api/bridge/execute", api_send_command_and_wait, methods=["POST"]),
    Route("/api/bridge/pending", api_get_pending_command, methods=["GET"]),
    Route("/api/bridge/result", api_post_command_result, methods=["POST"]),
    Route("/api/bridge/layers", api_update_layers, methods=["POST"]),
    Route("/api/bridge/state", api_get_state, methods=["GET"]),
    Route("/api/convert-image", api_convert_image_to_psd, methods=["POST"]),
    Route("/api/convert-sample", api_convert_sample, methods=["POST", "GET"]),
    Route("/api/upload-psd", api_upload_psd, methods=["POST"]),
    Mount("/", app=StaticFiles(directory=BASE_DIR, html=True), name="static")
]

middleware = [
    Middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
]

app = Starlette(debug=True, routes=routes, middleware=middleware)

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    host = "0.0.0.0"
    print(f"[Photopea Copilot] Avvio Web & Bridge Server su http://{host}:{port} ...", file=sys.stderr)
    uvicorn.run("server:app", host=host, port=port, log_level="info")
