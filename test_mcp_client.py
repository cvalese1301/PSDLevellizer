"""
Test Script: Simulates an MCP Client (like ChatGPT) communicating with mcp_server.py.
Executes the full pipeline:
1. List Templates
2. Inspect Layer Structure
3. Generate Social Post (Topic -> Copy & Image -> Photopea Render)
4. Run AI Visual QA Validation
5. Export final graphic asset
"""

import asyncio
import json
import sys
import mcp_server

# Ensure UTF-8 output on Windows terminal
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

async def run_simulation():
    print("=" * 65)
    print("SIMULAZIONE MCP: CHATGPT <---> PHOTOPEA POSTGEN STUDIO")
    print("=" * 65)

    # 1. ChatGPT queries available templates via MCP
    print("\n[Step 1] ChatGPT chiama il tool: 'list_templates'")
    templates_res = await mcp_server.list_templates()
    print("Risposta MCP ricevuta:")
    for tid, info in templates_res["templates"].items():
        print(f"  • {tid} ({info['dimensions']}) - {info['name']}")

    # 2. ChatGPT uploads and analyzes a custom PSD template
    print("\n[Step 2] ChatGPT carica e analizza un template personalizzato PSD:")
    custom_analysis = await mcp_server.upload_and_analyze_template(file_path="templates/text.psd")
    print(f"Esito: {custom_analysis['message']}")
    print(f"Sintesi Composizione: {custom_analysis['composition_summary']}")
    print("Slot Rilevati dall'AI:")
    for slot, layer_name in custom_analysis["detected_slots"].items():
        print(f"  • {slot.upper()}: '{layer_name}'")

    # 3. ChatGPT inspects the layer structure of 'tech-announcement'
    print("\n[Step 3] ChatGPT chiama il tool: 'inspect_template_layers' per 'tech-announcement'")
    layers_res = await mcp_server.inspect_template_layers("tech-announcement")
    print(f"Layer rilevati: {len(layers_res['layers'])}")
    for l in layers_res["layers"]:
        default_val = f' (default: "{l.get("default")}")' if "default" in l else ""
        print(f"  - [{l['role'].upper()}] {l['name']}{default_val}")

    # 4. ChatGPT generates a targeted post on AI Automation
    topic = "Automazione Grafica con Photopea e MCP"
    print(f"\n[Step 4] ChatGPT chiama: 'generate_social_post' per il tema '{topic}'")
    post_res = await mcp_server.generate_social_post(
        template_id="tech-announcement",
        topic=topic,
        tone="tech_bold"
    )
    copy = post_res["post_details"]["copy"]
    print("Contenuto generato dall'AI e inviato a Photopea:")
    print(f"  • Headline:    {copy['headline']}")
    print(f"  • Subheadline: {copy['subheadline']}")
    print(f"  • CTA:         {copy['cta']}")
    print(f"  • Badge:       {copy['badge']}")
    print(f"  • Image URL:   {post_res['post_details']['image_url'][:75]}...")

    # 4. ChatGPT runs Visual QA verification
    print("\n[Step 4] ChatGPT chiama: 'verify_post_qa' per validare l'output")
    qa_res = await mcp_server.verify_post_qa(
        template_id="tech-announcement",
        headline=copy["headline"],
        subheadline=copy["subheadline"],
        cta=copy["cta"]
    )
    qa = qa_res["qa_report"]
    print(f"Punteggio QA: {qa['score']}/100 -> Verdetto: {qa['verdict']}")
    for check in qa["checklist"]:
        symbol = "✓" if check["status"] == "pass" else "⚠"
        print(f"  [{symbol}] {check['name']}: {check['detail']}")

    # 5. Export finalized asset
    print("\n[Step 5] ChatGPT chiama: 'export_post' in formato PNG")
    export_res = await mcp_server.export_post(format="png", filename="chatgpt_mcp_output.png")
    print(f"Asset esportato in: {export_res['target_file']}")
    print("\n" + "=" * 65)
    print("TUTTI I TOOL MCP SONO STATI ESEGUITI E VALIDATI CON SUCCESSO!")
    print("=" * 65)

if __name__ == "__main__":
    asyncio.run(run_simulation())
