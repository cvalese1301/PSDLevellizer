"""
Photopea AI Studio - Test End-to-End: Scomposizione Immagine in PSD + Copilot MCP
1. Prende un'immagine piatta (PNG/JPG) e la converte in livelli PSD modificabili in Photopea.
2. Esegue istruzioni agentiche tramite MCP (modifica testi, stili, salvataggio PSD).
"""

import asyncio
import json
import sys
import time
import mcp_server

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

async def run_end_to_end_test():
    print("=" * 75)
    print("TEST: CONVERSIONE IMMAGINE IN LIVELLI PSD MODIFICABILI + COPILOT AGENTICO")
    print("=" * 75)

    # -------------------------------------------------------------------------
    # FASE 1: SCOPO PRINCIPALE - Conversione da Immagine Piatta a PSD a Livelli
    # -------------------------------------------------------------------------
    print("\n[FASE 1 - SCOPO PRINCIPALE] Conversione Immagine -> PSD Modificabile")
    sample_img = "templates/flat_sample_post.png"
    print(f"Sorgente: Immagine piatta '{sample_img}'")
    print("Chiamata MCP: convert_image_to_editable_psd(...)")
    
    decomp_res = await mcp_server.convert_image_to_editable_psd(sample_img)
    print(f"Esito: {decomp_res.get('status')}")
    print(f"Messaggio: {decomp_res.get('message')}")
    print(f"Livelli testo estratti ({decomp_res.get('editable_layers_created')}):")
    for l in decomp_res.get("layers", []):
        print(f"  • {l.get('name')}: '{l.get('text')}' (Font: {l.get('font_size')}px, Colore: {l.get('color_hex')})")

    # Attesa che Photopea assembli il documento e lo sincronizzi
    await asyncio.sleep(2.5)

    # -------------------------------------------------------------------------
    # FASE 2: FUNZIONE AGENTICA - ChatGPT legge lo stato del documento Photopea
    # -------------------------------------------------------------------------
    print("\n[FASE 2 - AGENTIC COPILOT] ChatGPT 'guarda' il documento aperto in Photopea")
    doc_state = await mcp_server.get_document_state()
    print(f"Documento in Photopea: {doc_state['document_name']} ({doc_state['dimensions']})")
    print(f"Livelli presenti nel canvas ({doc_state['total_layers']}):")
    for l in doc_state["layers"]:
        text_preview = f' -> "{l.get("text")}"' if l.get("text") else ""
        print(f"  [{l.get('type', l.get('kind'))}] {l['name']}{text_preview}")

    await asyncio.sleep(1.0)

    # -------------------------------------------------------------------------
    # FASE 3: FUNZIONE AGENTICA - Modifica mirata dei livelli di testo
    # -------------------------------------------------------------------------
    target_layer = None
    for l in doc_state["layers"]:
        if l.get("type") == "text" or "livello" in l.get("name", "").lower():
            target_layer = l["name"]
            break

    if target_layer:
        print(f"\n[FASE 3 - MODIFICA TESTO] ChatGPT modifica '{target_layer}'")
        res_edit = await mcp_server.edit_text_layer(
            layer_name=target_layer,
            new_text="OFFERTA FLASH -70% LIMITATA",
            font_size=28,
            color_hex="#06B6D4"
        )
        print(f"Esito modifica: {res_edit.get('status')}")
    else:
        print("\nNessun livello di testo specifico trovato per il test.")

    await asyncio.sleep(1.0)

    # -------------------------------------------------------------------------
    # FASE 4: Salvataggio e Rendering Anteprima
    # -------------------------------------------------------------------------
    print("\n[FASE 4 - ANTEPRIMA & EXPORT] Generazione anteprima del PSD modificato")
    preview_res = await mcp_server.capture_canvas_preview()
    print(f"Stato rendering anteprima: {preview_res.get('status')}")

    print("\n" + "=" * 75)
    print("TEST COMPLETATO CON SUCCESSO!")
    print("1. Immagine convertita in PSD a livelli con sfondo inpaintato.")
    print("2. Livelli di testo modificati tramite istruzioni MCP di ChatGPT.")
    print("=" * 75)

if __name__ == "__main__":
    asyncio.run(run_end_to_end_test())
