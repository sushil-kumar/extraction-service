import fitz  # PyMuPDF
import pytesseract
from PIL import Image, ImageOps
import io
import logging

logger = logging.getLogger(__name__)

def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Try native text extraction first (fast, free, works for digitally-generated PDFs)."""
    try:
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        text = "\n".join(page.get_text() for page in doc)
        doc.close()
        return text.strip()
    except Exception as e:
        logger.error(f"PDF text extraction failed: {e}")
        return ""

def pdf_to_image_bytes(file_bytes: bytes, page_num: int = 0) -> bytes:
    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        page = doc.load_page(page_num)
        pix = page.get_pixmap(dpi=300)  # higher DPI helps Tesseract accuracy
        return pix.tobytes("png")

def ocr_image_bytes(image_bytes: bytes) -> str:
    """Free OCR via Tesseract — used for scanned PDFs and uploaded images."""
    try:
        image = Image.open(io.BytesIO(image_bytes))
        # Normalize contrast and scale small scanned text before OCR.
        image = ImageOps.autocontrast(image.convert("L"))
        image = image.resize((image.width * 2, image.height * 2), Image.Resampling.LANCZOS)

        candidates = [
            pytesseract.image_to_string(image, config="--psm 6"),
            pytesseract.image_to_string(image, config="--psm 11"),
        ]
        return max((text.strip() for text in candidates), key=len, default="")
    except Exception as e:
        logger.error(f"Tesseract OCR failed: {e}")
        return ""

def get_document_text(file_bytes: bytes, content_type: str) -> str:
    """Single entry point: returns best-effort free-tier text for any supported type."""
    if content_type == "application/pdf":
        text = extract_text_from_pdf(file_bytes)
        if text:
            return text
        # Scanned PDF — render and OCR every page, not just the first one.
        try:
            with fitz.open(stream=file_bytes, filetype="pdf") as doc:
                page_text = []
                for page in doc:
                    pix = page.get_pixmap(dpi=300)
                    page_text.append(ocr_image_bytes(pix.tobytes("png")))
                return "\n\n".join(text for text in page_text if text).strip()
        except Exception as e:
            logger.error(f"Scanned PDF OCR failed: {e}")
            return ""

    elif content_type in ("image/jpeg", "image/png", "image/webp"):
        return ocr_image_bytes(file_bytes)

    return ""