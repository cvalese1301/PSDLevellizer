"""
Image to Editable PSD Decomposer Engine
Takes a flat raster image (PNG, JPG, WebP), isolates text and graphic regions,
inpaints the clean background using OpenCV, and constructs a fully layered,
editable Photoshop PSD inside Photopea with real text layers (LayerKind.TEXT).
"""

import os
import time
import math
import json
import urllib.parse
from typing import Dict, Any, List, Optional, Tuple
import cv2
import numpy as np
from PIL import Image

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DECOMPOSED_DIR = os.path.join(BASE_DIR, "outputs", "decomposed")
os.makedirs(DECOMPOSED_DIR, exist_ok=True)

class ImageDecomposer:
    """
    Deconstructs flattened images into clean background + editable text layers + graphic elements.
    """

    @staticmethod
    def sample_text_color(img_rgb: np.ndarray, bbox: Tuple[int, int, int, int]) -> str:
        """
        Samples the dominant high-contrast text color inside the bounding box.
        Returns a hex color string like '#FFFFFF' or '#FFCC00'.
        """
        x, y, w, h = bbox
        h_img, w_img = img_rgb.shape[:2]
        x1 = max(0, x)
        y1 = max(0, y)
        x2 = min(w_img, x + w)
        y2 = min(h_img, y + h)

        if x2 <= x1 or y2 <= y1:
            return "#FFFFFF"

        crop = img_rgb[y1:y2, x1:x2]
        # Flatten pixels and find dominant color or brightest/darkest based on variance
        pixels = crop.reshape(-1, 3)
        mean_col = pixels.mean(axis=0)

        # Check corners to find background color estimate
        corners = [crop[0, 0], crop[0, -1], crop[-1, 0], crop[-1, -1]]
        bg_estimate = np.mean(corners, axis=0)

        # Find pixel farthest in distance from the background estimate
        diffs = np.linalg.norm(pixels - bg_estimate, axis=1)
        max_idx = np.argmax(diffs)
        text_pixel = pixels[max_idx]

        hex_color = f"#{int(text_pixel[0]):02X}{int(text_pixel[1]):02X}{int(text_pixel[2]):02X}"
        return hex_color

    @classmethod
    def detect_text_regions_cv(cls, img_bgr: np.ndarray) -> List[Dict[str, Any]]:
        """
        Uses OpenCV morphological operations and contour analysis to locate text blocks
        in images where OCR or AI annotations are not yet provided.
        """
        h_img, w_img = img_bgr.shape[:2]
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

        # Gradient to highlight edges of letters
        grad_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
        grad_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
        grad = cv2.convertScaleAbs(cv2.sqrt(grad_x**2 + grad_y**2))
        _, grad_thresh = cv2.threshold(grad, 35, 255, cv2.THRESH_BINARY)

        # Morphological dilation to group letters into words and lines
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (14, 4))
        dilated = cv2.dilate(grad_thresh, kernel, iterations=2)

        # Find contours
        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        detected = []
        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)

        for c in contours:
            x, y, w, h = cv2.boundingRect(c)
            # Filter noise and whole image contours
            if w > 25 and h > 8 and (w * h) < (w_img * h_img * 0.45):
                color_hex = cls.sample_text_color(img_rgb, (x, y, w, h))
                estimated_font_size = max(16, int(h * 0.85))
                detected.append({
                    "id": f"text_{len(detected) + 1}",
                    "name": f"Livello_Testo_{len(detected) + 1}",
                    "bounds": [int(x), int(y), int(x + w), int(y + h)],
                    "width": int(w),
                    "height": int(h),
                    "font_size": estimated_font_size,
                    "color_hex": color_hex,
                    "text": f"Testo Rilevato {len(detected) + 1}"
                })

        # Sort top-to-bottom
        detected.sort(key=lambda item: item["bounds"][1])
        return detected

    @classmethod
    def detect_text_regions_ocr(cls, image_path: str, img_bgr: np.ndarray) -> List[Dict[str, Any]]:
        """
        Uses Windows native OCR to extract exact text content and bounding boxes.
        """
        import subprocess
        script_path = os.path.join(BASE_DIR, "win_ocr.ps1")
        if not os.path.exists(script_path):
            return []

        try:
            cmd = ["powershell", "-ExecutionPolicy", "Bypass", "-File", script_path, "-ImagePath", image_path]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=8.0)
            if res.returncode != 0 or not res.stdout.strip():
                return []

            data = json.loads(res.stdout.strip())
            if not isinstance(data, list) or len(data) == 0:
                return []

            img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
            detected = []
            for idx, item in enumerate(data):
                text = str(item.get("Text", "")).strip()
                if not text:
                    continue
                x = int(item.get("X", 0))
                y = int(item.get("Y", 0))
                w = int(item.get("Width", 10))
                h = int(item.get("Height", 10))

                color_hex = cls.sample_text_color(img_rgb, (x, y, w, h))
                estimated_font_size = max(18, int(h * 3.0))

                clean_snippet = "".join([c if c.isalnum() else "_" for c in text])[:24].strip("_")
                layer_name = f"Livello_{clean_snippet}" if clean_snippet else f"Livello_Testo_{idx + 1}"

                detected.append({
                    "id": f"text_ocr_{idx + 1}",
                    "name": layer_name,
                    "bounds": [x, y, x + w, y + h],
                    "width": w,
                    "height": h,
                    "font_size": estimated_font_size,
                    "color_hex": color_hex,
                    "text": text
                })

            detected.sort(key=lambda item: item["bounds"][1])
            return detected
        except Exception as e:
            return []

    @classmethod
    def inpaint_clean_background(
        cls,
        img_bgr: np.ndarray,
        regions: List[Dict[str, Any]],
        output_clean_bg_path: str
    ) -> str:
        """
        Removes the text/element regions from the image using OpenCV inpainting,
        producing a pristine background layer without flattened ghost texts.
        """
        h_img, w_img = img_bgr.shape[:2]
        mask = np.zeros((h_img, w_img), dtype=np.uint8)

        # Add dilated bounding boxes of text regions to the inpainting mask
        for r in regions:
            bounds = r.get("bounds", [0, 0, 0, 0])
            x1, y1, x2, y2 = bounds
            w = max(1, x2 - x1)
            h = max(1, y2 - y1)
            # Generous padding to cover ascenders, descenders, and shadows
            pad_x = max(6, int(w * 0.05))
            pad_y = max(8, int(h * 0.25))
            x1 = max(0, x1 - pad_x)
            y1 = max(0, y1 - pad_y)
            x2 = min(w_img, x2 + pad_x)
            y2 = min(h_img, y2 + pad_y)
            cv2.rectangle(mask, (x1, y1), (x2, y2), 255, -1)

        # Inpaint with Navier-Stokes / Telea method
        inpainted = cv2.inpaint(img_bgr, mask, inpaintRadius=6, flags=cv2.INPAINT_TELEA)

        # Save clean background image
        cv2.imwrite(output_clean_bg_path, inpainted)
        return output_clean_bg_path

    @classmethod
    def convert_image_to_psd_script(
        cls,
        image_path: str,
        text_layers: Optional[List[Dict[str, Any]]] = None,
        custom_headline: Optional[str] = None,
        base_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Main pipeline: Takes an image, isolates text and background,
        and generates the ExtendScript to construct the layered PSD inside Photopea.
        """
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"Immagine non trovata: {image_path}")

        img_bgr = cv2.imread(image_path)
        if img_bgr is None:
            raise ValueError(f"Impossibile leggere l'immagine: {image_path}")

        h_img, w_img = img_bgr.shape[:2]
        timestamp = int(time.time() * 1000)
        base_name = os.path.splitext(os.path.basename(image_path))[0]
        clean_bg_filename = f"{base_name}_clean_bg_{timestamp}.png"
        clean_bg_path = os.path.join(DECOMPOSED_DIR, clean_bg_filename)

        # Priority: 1. AI custom annotations -> 2. Windows native OCR -> 3. OpenCV CV detector
        if text_layers:
            detected = text_layers
        else:
            detected = cls.detect_text_regions_ocr(image_path, img_bgr)
            if not detected:
                detected = cls.detect_text_regions_cv(img_bgr)

        # If custom headline is requested, apply to first text layer
        if custom_headline and detected:
            detected[0]["text"] = custom_headline

        # Inpaint background to erase flat text
        cls.inpaint_clean_background(img_bgr, detected, clean_bg_path)

        # Relative or absolute URL for Photopea to load background image
        if base_url:
            clean_bg_rel_url = f"{base_url.rstrip('/')}/outputs/decomposed/{clean_bg_filename}"
        else:
            clean_bg_rel_url = f"/outputs/decomposed/{clean_bg_filename}"

        # Generate Photopea ExtendScript
        extendscript_lines = [
            f'// Auto-generated Photopea PSD Builder for: {base_name}',
            f'var doc = app.documents.add({w_img}, {h_img}, 72, "{base_name}_Layered", NewDocumentMode.RGB, DocumentFill.TRANSPARENT);',
            '',
            '// 1. Load Inpainted Clean Background Layer',
            f'app.open("{clean_bg_rel_url}", null, true);',
            'app.activeDocument.activeLayer.name = "Clean_Background";',
            ''
        ]

        # Add each detected text as a true editable Photoshop TextLayer
        for idx, t in enumerate(detected):
            layer_name = t.get("name", f"Testo_{idx + 1}")
            text_val = t.get("text", f"Testo {idx + 1}").replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
            font_size = float(t.get("font_size", 32))
            bounds = t.get("bounds", [50, 100 + (idx * 60), 400, 150 + (idx * 60)])
            pos_x = bounds[0]
            # In Photoshop ExtendScript, text baseline position is near bottom of bounding box
            pos_y = bounds[1] + int(font_size * 0.9)

            color_hex = t.get("color_hex", "#FFFFFF").lstrip("#")
            if len(color_hex) == 6:
                r, g, b = tuple(int(color_hex[i:i+2], 16) for i in (0, 2, 4))
            else:
                r, g, b = (255, 255, 255)

            extendscript_lines.extend([
                f'// Layer {idx + 1}: {layer_name}',
                'var tl = doc.artLayers.add();',
                f'tl.name = "{layer_name}";',
                'tl.kind = LayerKind.TEXT;',
                f'tl.textItem.contents = "{text_val}";',
                f'tl.textItem.size = {font_size};',
                f'tl.textItem.position = [{pos_x}, {pos_y}];',
                'var tc = new SolidColor();',
                f'tc.rgb.red = {r}; tc.rgb.green = {g}; tc.rgb.blue = {b};',
                'tl.textItem.color = tc;',
                ''
            ])

        extendscript_lines.extend([
            '// Rescan and export',
            'app.activeDocument.saveToOE("png");',
            f'app.echoToOE("PP_CMD_SUCCESS:" + JSON.stringify({{ decomposed: true, layers_count: {len(detected) + 1} }}));'
        ])

        full_script = "\n".join(extendscript_lines)

        return {
            "status": "success",
            "source_image": os.path.abspath(image_path),
            "dimensions": {"width": w_img, "height": h_img},
            "clean_background_file": clean_bg_path,
            "clean_background_url": clean_bg_rel_url,
            "detected_layers_count": len(detected),
            "layers": detected,
            "extendscript": full_script
        }
