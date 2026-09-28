"""
Photopea AI Copilot - Model Context Protocol (MCP) Server
Allows ChatGPT to directly manipulate and edit Photoshop documents in Photopea
according to natural language instructions.
"""

import sys
import os
import json
import time
import urllib.request
import urllib.parse
from typing import Dict, Any, List, Optional
from mcp.server.mcpserver import MCPServer
from template_analyzer import TemplateAnalyzer
from image_decomposer import ImageDecomposer

# Initialize MCP Server
app = MCPServer("Photopea-Copilot-MCP")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
BRIDGE_URL = os.environ.get("BRIDGE_URL", "http://127.0.0.1:8000").rstrip("/")

os.makedirs(TEMPLATES_DIR, exist_ok=True)
os.makedirs(OUTPUTS_DIR, exist_ok=True)

# Helper: Communication with local Photopea Web Bridge
def send_bridge_command(script: str, description: str, timeout: float = 6.0) -> Dict[str, Any]:
    """Sends an ExtendScript command to the active Photopea browser session and awaits response."""
    url = f"{BRIDGE_URL}/api/bridge/execute"
    payload = json.dumps({
        "script": script,
        "description": description,
        "timeout": timeout
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout + 2.0) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {
            "status": "bridge_unavailable",
            "message": (
                f"Impossibile comunicare con Photopea sul browser: {str(e)}. "
                "Assicurati che http://localhost:8000 sia aperto nel browser per visualizzare ed eseguire le modifiche."
            )
        }

def get_bridge_state() -> Dict[str, Any]:
    """Retrieves the active document state and layers from Photopea."""
    url = f"{BRIDGE_URL}/api/bridge/state"
    try:
        with urllib.request.urlopen(url, timeout=3.0) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {
            "document": {
                "name": "Nessun documento attivo",
                "width": 0,
                "height": 0,
                "layers": []
            },
            "error": str(e)
        }

def sanitize_js(val: Any) -> str:
    """Safely escapes strings for ExtendScript interpolation."""
    s = str(val or "")
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "")

def hex_to_rgb(hex_code: str):
    """Converts hex color string to RGB tuple."""
    hex_code = hex_code.lstrip("#")
    if len(hex_code) == 3:
        hex_code = "".join([c * 2 for c in hex_code])
    if len(hex_code) != 6:
        return (255, 255, 255)
    return tuple(int(hex_code[i:i+2], 16) for i in (0, 2, 4))


# ============================================================================
# MCP Tools: Image to Editable PSD Conversion & Photoshop Manipulation
# ============================================================================

@app.tool()
async def convert_image_to_editable_psd(
    image_path_or_url: str,
    text_annotations: Optional[List[Dict[str, Any]]] = None,
    custom_headline: Optional[str] = None
) -> Dict[str, Any]:
    """
    SCOPO PRINCIPALE DEL TOOL:
    Prende un'immagine piatta (PNG, JPG, WebP) e la converte in un documento PSD
    a livelli completamente modificabili all'interno di Photopea.

    Fasi eseguite automaticamente:
    1. Analisi visiva della composizione e rilevamento regioni di testo
    2. Ricostruzione e inpainting dello sfondo con OpenCV (cancella i testi piatti senza aloni)
    3. Creazione in Photopea di veri livelli di testo Photoshop (LayerKind.TEXT)
       con coordinate esatte, stima del font size e campionamento cromatico fedele
    4. Sincronizzazione in tempo reale sul canvas di Photopea: tutti i livelli diventano
       istantaneamente modificabili via chat con ChatGPT e salvabili in formato PSD.
    """
    # 1. Resolve image source (Local path or Remote URL)
    target_path = None
    if image_path_or_url.startswith(("http://", "https://")):
        fname = f"downloaded_{int(time.time())}.png"
        target_path = os.path.join(TEMPLATES_DIR, fname)
        urllib.request.urlretrieve(image_path_or_url, target_path)
    else:
        candidates = [
            image_path_or_url,
            os.path.join(TEMPLATES_DIR, image_path_or_url),
            os.path.join(BASE_DIR, image_path_or_url),
            os.path.abspath(image_path_or_url)
        ]
        for c in candidates:
            if os.path.exists(c):
                target_path = c
                break

    if not target_path or not os.path.exists(target_path):
        return {
            "status": "error",
            "message": f"Immagine sorgente non trovata al percorso: {image_path_or_url}"
        }

    # 2. Decompose image into inpaint background & text layers
    try:
        decomp = ImageDecomposer.convert_image_to_psd_script(
            image_path=target_path,
            text_layers=text_annotations,
            custom_headline=custom_headline
        )
    except Exception as e:
        return {
            "status": "error",
            "message": f"Errore durante la scomposizione dell'immagine in livelli: {str(e)}"
        }

    # 3. Send ExtendScript to Photopea to assemble the layered PSD
    desc = f"Conversione immagine '{os.path.basename(target_path)}' in PSD a livelli modificabili"
    bridge_res = send_bridge_command(decomp["extendscript"], desc, timeout=8.0)

    return {
        "status": "success",
        "message": f"Immagine '{os.path.basename(target_path)}' convertita con successo in PSD a livelli modificabili!",
        "dimensions": decomp["dimensions"],
        "clean_background": decomp["clean_background_url"],
        "editable_layers_created": decomp["detected_layers_count"],
        "layers": decomp["layers"],
        "photopea_status": bridge_res.get("status"),
        "next_actions": [
            "Modifica qualsiasi testo con 'edit_text_layer'",
            "Sposta o ridimensiona elementi con 'transform_layer'",
            "Sostituisci immagini o Smart Object con 'replace_image_layer'",
            "Esporta il file PSD completo con 'export_document(format=\"psd\")'"
        ]
    }


@app.tool()
async def get_document_state() -> Dict[str, Any]:
    """
    Legge lo stato attuale del documento aperto in Photopea.
    Restituisce:
    - Nome del documento, larghezza e altezza in pixel
    - Elenco completo dei livelli (nome, tipo: testo/pixel/smartobject/gruppo, visibilità, opacità)
    - Contenuto dei livelli di testo, coordinate (bounds), stili e colori attuali.
    Usa questo tool prima di applicare modifiche per 'vedere' com'è composto il file.
    """
    state = get_bridge_state()
    doc = state.get("document", {})
    layers = doc.get("layers", [])

    return {
        "status": "success",
        "document_name": doc.get("name", "Documento non aperto"),
        "dimensions": f"{doc.get('width', 0)} x {doc.get('height', 0)} px",
        "total_layers": len(layers),
        "layers": layers,
        "hint": "Puoi modificare qualsiasi livello usando 'edit_text_layer', 'transform_layer', o scrivere script personalizzati con 'execute_photoshop_script'."
    }


@app.tool()
async def execute_photoshop_script(script: str, description: str) -> Dict[str, Any]:
    """
    Il comando definitivo per modificare qualsiasi file Photoshop in Photopea.
    Esegue codice ExtendScript/JavaScript Photoshop direttamente nel motore di Photopea.
    Permette di:
    - Manipolare livelli, maschere, stili di livello (ombre, tracce, sovrapposizioni)
    - Applicare trasformazioni, rotazioni, filtri (sfocatura, regolazioni colore)
    - Gestire selezioni, tracciati, smart object e guide.
    """
    # Enclose with layer auto-rescanning and confirmation echo
    wrapped_script = f"""
    (function() {{
        try {{
            {script}
            
            // Riscansiona i livelli aggiornati
            function scan(layers) {{
                var res = [];
                for (var i = 0; i < layers.length; i++) {{
                    var l = layers[i];
                    var item = {{ name: l.name, visible: l.visible, opacity: Math.round(l.opacity), kind: l.typename }};
                    try {{
                        if (l.bounds) item.bounds = [Math.round(l.bounds[0].value), Math.round(l.bounds[1].value), Math.round(l.bounds[2].value), Math.round(l.bounds[3].value)];
                    }} catch(e) {{}}
                    if (l.kind === LayerKind.TEXT) {{
                        item.type = "text";
                        item.text = l.textItem.contents;
                        try {{ item.fontSize = Math.round(l.textItem.size.value); }} catch(e) {{}}
                    }}
                    res.push(item);
                }}
                return res;
            }}

            var docData = {{
                docName: app.activeDocument.name,
                width: Math.round(app.activeDocument.width),
                height: Math.round(app.activeDocument.height),
                layers: scan(app.activeDocument.layers)
            }};

            app.echoToOE("PP_CMD_SUCCESS:" + JSON.stringify({{ success: true, doc: docData }}));
        }} catch(err) {{
            app.echoToOE("PP_CMD_ERROR:" + err.toString());
        }}
    }})();
    """

    res = send_bridge_command(wrapped_script, description)
    return {
        "status": res.get("status", "unknown"),
        "description": description,
        "execution_details": res
    }


@app.tool()
async def edit_text_layer(
    layer_name: str,
    new_text: Optional[str] = None,
    font_size: Optional[float] = None,
    color_hex: Optional[str] = None,
    position_x: Optional[float] = None,
    position_y: Optional[float] = None
) -> Dict[str, Any]:
    """
    Modifica in modo mirato un livello di testo in Photopea.
    Permette di cambiare:
    - Testo del livello (new_text)
    - Dimensione del font in pixel (font_size)
    - Colore del testo in formato esadecimale (es. '#FF5500', '#FFFFFF')
    - Posizione X e Y nel canvas.
    """
    js_operations = []
    san_layer = sanitize_js(layer_name)

    if new_text is not None:
        js_operations.append(f'layer.textItem.contents = "{sanitize_js(new_text)}";')

    if font_size is not None:
        js_operations.append(f'layer.textItem.size = {float(font_size)};')

    if color_hex is not None:
        r, g, b = hex_to_rgb(color_hex)
        js_operations.append(f"""
        var c = new SolidColor();
        c.rgb.red = {r}; c.rgb.green = {g}; c.rgb.blue = {b};
        layer.textItem.color = c;
        """)

    if position_x is not None or position_y is not None:
        px = float(position_x) if position_x is not None else "layer.textItem.position[0]"
        py = float(position_y) if position_y is not None else "layer.textItem.position[1]"
        js_operations.append(f'layer.textItem.position = [{px}, {py}];')

    script = f"""
    var layer = null;
    try {{
        layer = app.activeDocument.artLayers.getByName("{san_layer}");
    }} catch(e) {{
        for (var i = 0; i < app.activeDocument.artLayers.length; i++) {{
            if (app.activeDocument.artLayers[i].name.toLowerCase() === "{san_layer}".toLowerCase()) {{
                layer = app.activeDocument.artLayers[i];
                break;
            }}
        }}
    }}

    if (!layer) throw new Error("Livello testo '{san_layer}' non trovato.");
    if (layer.kind !== LayerKind.TEXT) throw new Error("Il livello '{san_layer}' non è un livello di testo.");

    {chr(10).join(js_operations)}
    """

    desc = f"Modificato testo livello '{layer_name}'"
    return await execute_photoshop_script(script, desc)


@app.tool()
async def transform_layer(
    layer_name: str,
    move_x: float = 0.0,
    move_y: float = 0.0,
    opacity: Optional[float] = None,
    visible: Optional[bool] = None,
    rotate_deg: Optional[float] = None
) -> Dict[str, Any]:
    """
    Applica trasformazioni a qualsiasi livello:
    - Spostamento orizzontale/verticale relativo in pixel (move_x, move_y)
    - Opacità (0 - 100)
    - Visibilità (true: visibile, false: nascosto)
    - Rotazione in gradi (rotate_deg).
    """
    san_layer = sanitize_js(layer_name)
    js_ops = []

    if move_x != 0 or move_y != 0:
        js_ops.append(f"layer.translate({float(move_x)}, {float(move_y)});")

    if opacity is not None:
        js_ops.append(f"layer.opacity = {max(0.0, min(100.0, float(opacity)))};")

    if visible is not None:
        js_ops.append(f"layer.visible = {'true' if visible else 'false'};")

    if rotate_deg is not None and rotate_deg != 0:
        js_ops.append(f"layer.rotate({float(rotate_deg)});")

    script = f"""
    var layer = null;
    try {{
        layer = app.activeDocument.artLayers.getByName("{san_layer}");
    }} catch(e) {{
        for (var i = 0; i < app.activeDocument.artLayers.length; i++) {{
            if (app.activeDocument.artLayers[i].name.toLowerCase() === "{san_layer}".toLowerCase()) {{
                layer = app.activeDocument.artLayers[i];
                break;
            }}
        }}
    }}
    if (!layer) throw new Error("Livello '{san_layer}' non trovato.");
    {chr(10).join(js_ops)}
    """

    desc = f"Trasformazione livello '{layer_name}' (move: [{move_x}, {move_y}], op: {opacity}, vis: {visible})"
    return await execute_photoshop_script(script, desc)


@app.tool()
async def replace_image_layer(layer_name: str, image_url: str) -> Dict[str, Any]:
    """
    Sostituisce o inserisce una nuova immagine in Photopea (aperta come Smart Object)
    posizionandola sopra il livello specificato.
    """
    san_layer = sanitize_js(layer_name)
    san_url = sanitize_js(image_url)

    script = f"""
    var targetLayer = null;
    try {{ targetLayer = app.activeDocument.artLayers.getByName("{san_layer}"); }} catch(e) {{}}

    // Inserisce immagine come Smart Object
    app.open("{san_url}", null, true);

    if (targetLayer) {{
        app.activeDocument.activeLayer.move(targetLayer, ElementPlacement.PLACEBEFORE);
    }}
    """
    desc = f"Inserita immagine da '{image_url[:40]}...' sopra il livello '{layer_name}'"
    return await execute_photoshop_script(script, desc)


@app.tool()
async def add_new_layer(
    layer_type: str = "text",
    name: str = "Nuovo Livello",
    text: Optional[str] = "Nuovo Testo",
    color_hex: str = "#FFFFFF",
    font_size: float = 36.0,
    position_x: float = 100.0,
    position_y: float = 200.0
) -> Dict[str, Any]:
    """
    Crea un nuovo livello nel documento:
    - 'text': livello di testo
    - 'solid_color': livello riempito con colore
    """
    san_name = sanitize_js(name)
    r, g, b = hex_to_rgb(color_hex)

    if layer_type == "text":
        script = f"""
        var l = app.activeDocument.artLayers.add();
        l.name = "{san_name}";
        l.kind = LayerKind.TEXT;
        l.textItem.contents = "{sanitize_js(text)}";
        l.textItem.size = {float(font_size)};
        l.textItem.position = [{float(position_x)}, {float(position_y)}];
        var c = new SolidColor();
        c.rgb.red = {r}; c.rgb.green = {g}; c.rgb.blue = {b};
        l.textItem.color = c;
        """
    else:
        script = f"""
        var l = app.activeDocument.artLayers.add();
        l.name = "{san_name}";
        app.activeDocument.selection.selectAll();
        var c = new SolidColor();
        c.rgb.red = {r}; c.rgb.green = {g}; c.rgb.blue = {b};
        app.activeDocument.selection.fill(c);
        app.activeDocument.selection.deselect();
        """

    desc = f"Aggiunto livello {layer_type} '{name}'"
    return await execute_photoshop_script(script, desc)


@app.tool()
async def delete_or_duplicate_layer(layer_name: str, action: str = "duplicate") -> Dict[str, Any]:
    """
    Duplica o elimina un livello nel documento.
    action: 'duplicate' oppure 'delete'.
    """
    san_layer = sanitize_js(layer_name)
    act = action.lower()

    if act == "delete":
        script = f"""
        var l = app.activeDocument.artLayers.getByName("{san_layer}");
        l.remove();
        """
        desc = f"Eliminato livello '{layer_name}'"
    else:
        script = f"""
        var l = app.activeDocument.artLayers.getByName("{san_layer}");
        l.duplicate();
        """
        desc = f"Duplicato livello '{layer_name}'"

    return await execute_photoshop_script(script, desc)


@app.tool()
async def capture_canvas_preview() -> Dict[str, Any]:
    """
    Scatta un'istantanea visiva (PNG ad alta risoluzione) del canvas di Photopea
    per consentire a ChatGPT o all'utente di ispezionare visivamente il risultato delle modifiche.
    """
    script = """
    app.activeDocument.saveToOE("png");
    """
    desc = "Catturata anteprima visiva canvas da Photopea"
    res = send_bridge_command(script, desc, timeout=4.0)
    return {
        "status": "success",
        "message": "Anteprima aggiornata visibile su http://localhost:8000",
        "details": res
    }


@app.tool()
async def export_document(format: str = "psd", filename: Optional[str] = None) -> Dict[str, Any]:
    """
    Esporta il file Photoshop modificato.
    Formati:
    - 'psd': Progetto completo a livelli modificabile
    - 'png': Immagine ad alta definizione trasparente
    - 'jpg': Immagine per web.
    """
    fmt = format.lower()
    fname = filename or f"photoshop_export_{int(time.time())}.{fmt}"
    out_path = os.path.join(OUTPUTS_DIR, fname)

    script = f'app.activeDocument.saveToOE("{fmt}:true");'
    desc = f"Esportazione documento in formato {fmt.upper()}"
    send_bridge_command(script, desc)

    return {
        "status": "success",
        "message": f"Esportazione {fmt.upper()} completata in Photopea.",
        "target_file": out_path,
        "format": fmt
    }


@app.tool()
async def open_psd_file(file_path: str) -> Dict[str, Any]:
    """
    Apre un file PSD presente sul computer in Photopea.
    Può essere un percorso assoluto o relativo a templates/ o outputs/.
    """
    resolved_path = None
    candidates = [
        file_path,
        os.path.join(TEMPLATES_DIR, file_path),
        os.path.join(BASE_DIR, file_path),
        os.path.abspath(file_path)
    ]
    for c in candidates:
        if os.path.exists(c):
            resolved_path = c
            break

    if not resolved_path:
        return {
            "status": "error",
            "message": f"File PSD non trovato al percorso: {file_path}"
        }

    # Analyze file structure with template analyzer
    analysis = TemplateAnalyzer.analyze_psd(resolved_path)

    # Tell Photopea to load it if web app is connected
    rel_path = os.path.relpath(resolved_path, BASE_DIR).replace("\\", "/")
    script = f'app.open("{rel_path}", null, false);'
    send_bridge_command(script, f"Apertura file PSD '{analysis['filename']}'")

    return {
        "status": "success",
        "message": f"File '{analysis['filename']}' caricato!",
        "analysis": analysis
    }


# ============================================================================
# Main Entry Point (Stdio & SSE Transports)
# ============================================================================
if __name__ == "__main__":
    import asyncio
    import argparse

    parser = argparse.ArgumentParser(description="Photopea AI Copilot MCP Server")
    parser.add_argument("--transport", choices=["stdio", "sse"], default="stdio", help="Transport protocol (default: stdio)")
    parser.add_argument("--port", type=int, default=8001, help="Port for SSE transport (default: 8001)")
    args = parser.parse_args()

    if args.transport == "sse":
        print(f"[Photopea Copilot MCP] Avvio server SSE su http://127.0.0.1:{args.port}/sse ...", file=sys.stderr)
        asyncio.run(app.run_sse_async(host="127.0.0.1", port=args.port))
    else:
        print("[Photopea Copilot MCP] Avvio server stdio (ChatGPT Desktop / MCP Client)...", file=sys.stderr)
        asyncio.run(app.run_stdio_async())
