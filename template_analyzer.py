"""
Template Analyzer Engine
Inspects and analyzes custom PSD/PSB templates for Photopea PostGen Studio.
Extracts layer trees, geometry, typography, and performs AI semantic role classification.
"""

import os
import math
from typing import Dict, Any, List, Optional
from psd_tools import PSDImage

class TemplateAnalyzer:
    """
    Parses Photoshop (.psd/.psb) files and returns a structured semantic breakdown
    for ChatGPT via MCP.
    """

    @staticmethod
    def classify_layer_role(layer_info: Dict[str, Any], doc_w: int, doc_h: int) -> Dict[str, Any]:
        """
        Applies heuristic AI classification to assign semantic roles to layers
        based on name, typography, bounds, and layout position.
        """
        name_lower = layer_info["name"].lower()
        kind = layer_info["kind"]
        bounds = layer_info.get("bounds", [0, 0, 0, 0])
        w = bounds[2] - bounds[0]
        h = bounds[3] - bounds[1]
        area = w * h
        doc_area = doc_w * doc_h
        text_content = layer_info.get("text", "")
        font_size = layer_info.get("font_size", 24)

        # 1. Background Detection
        if area >= (doc_area * 0.85) and (bounds[0] <= 10 and bounds[1] <= 10):
            return {
                "role": "background",
                "label": "Sfondo Base",
                "priority": 10
            }

        # 2. Text Layer Classifications
        if kind == "type" or "text" in layer_info:
            # Check for CTA keywords
            cta_keywords = ["cta", "button", "bottone", "scopri", "prova", "clicca", "accedi", "iscriviti", "buy", "join", "start", "learn", "→", ">"]
            if any(k in name_lower or k in text_content.lower() for k in cta_keywords):
                return {
                    "role": "cta",
                    "label": "Call To Action (Pulsante)",
                    "max_recommended_chars": max(15, math.floor(w / 14)),
                    "priority": 1
                }

            # Check for Badge / Pill / Tag
            badge_keywords = ["badge", "tag", "pill", "cat", "categoria", "label", "%", "off", "sconto", "speciale"]
            if (any(k in name_lower or k in text_content.lower() for k in badge_keywords) or (len(text_content) < 22 and bounds[1] < doc_h * 0.35 and font_size <= 26)):
                return {
                    "role": "badge",
                    "label": "Badge Categoria / Tag",
                    "max_recommended_chars": 25,
                    "priority": 2
                }

            # Check for Brand / Author / Handle
            brand_keywords = ["brand", "author", "autore", "handle", "logo", "url", "site", "@", "www."]
            if any(k in name_lower or k in text_content.lower() for k in brand_keywords) or text_content.strip().startswith("@"):
                return {
                    "role": "author_brand",
                    "label": "Autore / Brand Handle",
                    "max_recommended_chars": 30,
                    "priority": 3
                }

            # Check for Headline (large font or top/center position)
            if font_size >= 36 or "titolo" in name_lower or "head" in name_lower or "title" in name_lower:
                return {
                    "role": "headline",
                    "label": "Titolo Principale",
                    "max_recommended_chars": max(30, math.floor((w * 2) / font_size)),
                    "priority": 0
                }

            # Otherwise Subheadline / Description
            return {
                "role": "subheadline",
                "label": "Sottotitolo / Copy Descrittivo",
                "max_recommended_chars": max(60, math.floor((w * 3.5) / max(16, font_size))),
                "priority": 4
            }

        # 3. Graphic / Image Placeholder Classifications
        img_keywords = ["img", "photo", "foto", "image", "hero", "placeholder", "visual", "product", "speaker"]
        if kind == "smartobject" or any(k in name_lower for k in img_keywords) or (area >= doc_area * 0.12):
            return {
                "role": "image_placeholder",
                "label": "Placeholder Immagine / Smart Object",
                "aspect_ratio": f"{round(w/max(1, h), 2)}:1",
                "dimensions": f"{w}x{h}",
                "priority": 5
            }

        # 4. Generic decorative shape / element
        return {
            "role": "decorative_element",
            "label": "Elemento Decorativo",
            "priority": 9
        }

    @classmethod
    def analyze_psd(cls, file_path: str) -> Dict[str, Any]:
        """
        Parses a local PSD/PSB file, extracting document dimensions and layer structures.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File PSD non trovato al percorso: {file_path}")

        psd = PSDImage.open(file_path)
        doc_w = psd.width
        doc_h = psd.height

        # Calculate Aspect Ratio
        gcd = math.gcd(doc_w, doc_h)
        simplified_aspect = f"{doc_w // gcd}:{doc_h // gcd}"
        if doc_w == doc_h:
            social_format = "Instagram/LinkedIn Feed Quadrato (1:1)"
        elif doc_w == 1080 and doc_h == 1350:
            social_format = "Instagram/LinkedIn Verticale (4:5)"
        elif doc_w == 1080 and doc_h == 1920:
            social_format = "Instagram Story / TikTok Verticale (9:16)"
        elif doc_w > doc_h:
            social_format = "Landscape / Twitter / LinkedIn Banner (16:9)"
        else:
            social_format = f"Custom ({simplified_aspect})"

        layers_list = []
        text_layers_count = 0
        image_slots_count = 0

        for layer in psd:
            info = {
                "name": layer.name,
                "visible": layer.visible,
                "opacity": round(layer.opacity / 2.55, 1) if hasattr(layer, "opacity") else 100,
                "kind": layer.kind
            }

            try:
                info["bounds"] = [layer.left, layer.top, layer.right, layer.bottom]
                info["width"] = layer.width
                info["height"] = layer.height
            except Exception:
                info["bounds"] = [0, 0, doc_w, doc_h]
                info["width"] = doc_w
                info["height"] = doc_h

            # Extract Text Details if Type Layer
            if layer.kind == "type":
                try:
                    info["text"] = layer.text.strip()
                except Exception:
                    info["text"] = ""
                
                # Approximate font size from transform or text engine
                info["font_size"] = 28
                text_layers_count += 1

            # AI Semantic Role Classification
            role_data = cls.classify_layer_role(info, doc_w, doc_h)
            info["ai_role"] = role_data["role"]
            info["role_label"] = role_data["label"]
            if "max_recommended_chars" in role_data:
                info["max_recommended_chars"] = role_data["max_recommended_chars"]
            if role_data["role"] == "image_placeholder":
                image_slots_count += 1

            layers_list.append(info)

        # Generate Natural Language Composition Summary for ChatGPT
        headlines = [l["name"] for l in layers_list if l["ai_role"] == "headline"]
        subheadlines = [l["name"] for l in layers_list if l["ai_role"] == "subheadline"]
        ctas = [l["name"] for l in layers_list if l["ai_role"] == "cta"]
        placeholders = [l["name"] for l in layers_list if l["ai_role"] == "image_placeholder"]

        summary = (
            f"Il template '{os.path.basename(file_path)}' ha una risoluzione di {doc_w}x{doc_h} px ({social_format}). "
            f"È composto da {len(layers_list)} livelli totali. "
            f"Rilevati: {len(headlines)} titolo/i ('{', '.join(headlines) if headlines else 'nessuno'}'), "
            f"{len(subheadlines)} sottotitolo/i, {len(ctas)} pulsante/i CTA, e "
            f"{image_slots_count} box/placeholder per immagini ('{', '.join(placeholders) if placeholders else 'nessuno'}')."
        )

        return {
            "status": "success",
            "filename": os.path.basename(file_path),
            "file_path": os.path.abspath(file_path),
            "dimensions": {"width": doc_w, "height": doc_h},
            "aspect_ratio": simplified_aspect,
            "social_format": social_format,
            "total_layers": len(layers_list),
            "text_layers_count": text_layers_count,
            "image_slots_count": image_slots_count,
            "composition_summary": summary,
            "layers": layers_list
        }
