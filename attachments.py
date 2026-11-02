"""attachments.py - safely read what a user attaches to a chat message.

  * Documents (.pdf .docx .txt): type is checked by file extension AND by the
    file's real contents ("magic bytes"), size is capped, text is extracted in
    memory. Nothing is written to disk and the uploaded file name is never used
    as a path, so path-traversal tricks have nothing to attack.
  * Photos and camera pictures: checked, shrunk, and re-encoded. Re-encoding
    removes hidden metadata such as GPS location.
  * Voice: converted to text on this computer with the Whisper speech model
    (package faster-whisper). Audio is not sent to any online service.

Everything that can go wrong raises AttachmentError with a message that is safe
and understandable to show to the user.
"""
import base64
import io
import os
import re
import zipfile
from typing import NamedTuple

MAX_FILE_BYTES = 5 * 1024 * 1024        # Word/text documents and photos
MAX_PDF_BYTES = 25 * 1024 * 1024         # PDFs may be larger
MAX_AUDIO_BYTES = 10 * 1024 * 1024
MAX_DOC_CHARS = 12_000                  # about 3,000 tokens: what fits in the model's reading window
MAX_PDF_PAGES = 50
MAX_IMAGE_PIXELS = 40_000_000
IMAGE_EDGE = 1024
DOC_TYPES = (".pdf", ".docx", ".txt")
IMAGE_TYPES = (".png", ".jpg", ".jpeg", ".webp")


class AttachmentError(Exception):
    """A problem with an attachment, written for the end user."""


class Document(NamedTuple):
    name: str
    text: str
    truncated: bool
    size: int


class Photo(NamedTuple):
    name: str
    b64: str          # JPEG, resized, metadata removed, base64 text (what the vision model receives)
    size: int


def safe_name(name: str) -> str:
    """Display-only file name: no folders, no control characters, no markdown symbols."""
    name = os.path.basename(str(name or "").replace("\\", "/"))
    name = re.sub(r"[\x00-\x1f\x7f]", "", name)
    name = re.sub(r"[`*_\[\]<>~#|$:]", "-", name).strip(" .-")
    return (name[:60] or "file")


def _check_size(data: bytes, max_bytes: int = MAX_FILE_BYTES) -> None:
    if not data:
        raise AttachmentError("That file is empty.")
    if len(data) > max_bytes:
        raise AttachmentError(f"That file is larger than {max_bytes // (1024 * 1024)} MB.")


# ------------------------------------------------------------------ documents
def _pdf_text(data: bytes) -> str:
    if not data.startswith(b"%PDF-"):
        raise AttachmentError("That file is not a real PDF.")
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise AttachmentError("PDF support needs a package. Run: pip install pypdf") from exc
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise AttachmentError("Password-protected PDFs are not supported.")
        parts = [(page.extract_text() or "") for page in reader.pages[:MAX_PDF_PAGES]]
    except AttachmentError:
        raise
    except Exception as exc:
        raise AttachmentError("That PDF could not be read. It may be damaged.") from exc
    return "\n".join(parts)


def _docx_text(data: bytes) -> str:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
        info = archive.getinfo("word/document.xml")
    except (zipfile.BadZipFile, KeyError) as exc:
        raise AttachmentError("That file is not a real Word (.docx) document.") from exc
    if info.file_size > 30 * 1024 * 1024:                       # guards against "zip bombs"
        raise AttachmentError("That Word document is too large to read safely.")
    try:
        from docx import Document as WordDocument
    except ImportError as exc:
        raise AttachmentError("Word support needs a package. Run: pip install python-docx") from exc
    try:
        doc = WordDocument(io.BytesIO(data))
        lines = [p.text for p in doc.paragraphs]
        for table in doc.tables:
            for row in table.rows:
                lines.append(" | ".join(cell.text.strip() for cell in row.cells))
    except Exception as exc:
        raise AttachmentError("That Word document could not be read.") from exc
    return "\n".join(lines)


def _txt_text(data: bytes) -> str:
    if b"\x00" in data[:4096]:
        raise AttachmentError("That does not look like a plain text file.")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def read_document(name: str, data: bytes, max_chars: int = MAX_DOC_CHARS) -> Document:
    """Validate a document and return its text (cut to `max_chars`)."""
    shown = safe_name(name)
    ext = os.path.splitext(shown.lower())[1]
    if ext not in DOC_TYPES:
        raise AttachmentError("Documents must be PDF, Word (.docx) or text (.txt) files.")
    _check_size(data, MAX_PDF_BYTES if ext == ".pdf" else MAX_FILE_BYTES)
    text = {".pdf": _pdf_text, ".docx": _docx_text, ".txt": _txt_text}[ext](data)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        raise AttachmentError("No readable text was found. A scanned document needs OCR, which is not supported yet.")
    return Document(shown, text[:max_chars], len(text) > max_chars, len(data))


# --------------------------------------------------------------------- photos
def read_photo(name: str, data: bytes) -> Photo:
    """Validate a picture, shrink it, strip its metadata, and return it ready for the vision model."""
    shown = safe_name(name)
    _check_size(data)
    try:
        from PIL import Image, ImageOps
    except ImportError as exc:
        raise AttachmentError("Photo support needs a package. Run: pip install pillow") from exc
    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    try:
        image = Image.open(io.BytesIO(data))
        if image.format not in ("PNG", "JPEG", "WEBP"):
            raise AttachmentError("Photos must be PNG, JPG or WEBP pictures.")
        if image.width * image.height > MAX_IMAGE_PIXELS:
            raise AttachmentError("That picture has too many pixels.")
        image = ImageOps.exif_transpose(image).convert("RGB")
        image.thumbnail((IMAGE_EDGE, IMAGE_EDGE))
        out = io.BytesIO()
        image.save(out, format="JPEG", quality=85)             # a fresh file: original metadata is gone
    except AttachmentError:
        raise
    except Exception as exc:
        raise AttachmentError("That picture could not be read. It may be damaged.") from exc
    return Photo(shown, base64.b64encode(out.getvalue()).decode("ascii"), len(data))


# ---------------------------------------------------------- generic file check
VAULT_TYPES = DOC_TYPES + IMAGE_TYPES


def validate_file(name: str, data: bytes, max_bytes: int = MAX_FILE_BYTES):
    """Check that a file is really what its extension says. Returns (clean_name, extension).
    Nothing is extracted or executed; the contents are only inspected."""
    shown = safe_name(name)
    ext = os.path.splitext(shown.lower())[1]
    if ext not in VAULT_TYPES:
        raise AttachmentError("Allowed types: PDF, Word (.docx), text (.txt), PNG, JPG and WEBP.")
    if not data:
        raise AttachmentError("That file is empty.")
    effective_limit = MAX_PDF_BYTES if ext == ".pdf" else max_bytes
    if len(data) > effective_limit:
        raise AttachmentError(f"That file is larger than {effective_limit // (1024 * 1024)} MB.")
    if ext == ".pdf":
        if not data.startswith(b"%PDF-"):
            raise AttachmentError("That file is not a real PDF.")
    elif ext == ".docx":
        try:
            info = zipfile.ZipFile(io.BytesIO(data)).getinfo("word/document.xml")
        except (zipfile.BadZipFile, KeyError) as exc:
            raise AttachmentError("That file is not a real Word (.docx) document.") from exc
        if info.file_size > 30 * 1024 * 1024:
            raise AttachmentError("That Word document is too large to handle safely.")
    elif ext == ".txt":
        if b"\x00" in data[:4096]:
            raise AttachmentError("That does not look like a plain text file.")
    else:
        try:
            from PIL import Image
            Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
            image = Image.open(io.BytesIO(data))
            if image.format not in ("PNG", "JPEG", "WEBP"):
                raise AttachmentError("Pictures must be PNG, JPG or WEBP.")
            if image.width * image.height > MAX_IMAGE_PIXELS:
                raise AttachmentError("That picture has too many pixels.")
            image.verify()
        except AttachmentError:
            raise
        except Exception as exc:
            raise AttachmentError("That picture could not be read. It may be damaged.") from exc
    return shown, ext


# ---------------------------------------------------------------------- voice
_WHISPER = None


def whisper_model_name() -> str:
    return os.getenv("MINDMATE_WHISPER_MODEL", "") or "base"


def transcribe_audio(data: bytes) -> str:
    """Turn a voice recording into text on this computer."""
    global _WHISPER
    if not data:
        raise AttachmentError("The recording is empty.")
    if len(data) > MAX_AUDIO_BYTES:
        raise AttachmentError("That recording is too long. Keep it under a few minutes.")
    if _WHISPER is None:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise AttachmentError("Voice needs a speech package. Run: pip install faster-whisper") from exc
        try:
            _WHISPER = WhisperModel(whisper_model_name(), device="cpu", compute_type="int8")
        except Exception as exc:
            raise AttachmentError(
                "The speech model could not be loaded. The first use downloads it, so check your internet connection."
            ) from exc
    try:
        segments, _info = _WHISPER.transcribe(io.BytesIO(data), beam_size=1, vad_filter=True)
        text = " ".join(segment.text.strip() for segment in segments).strip()
    except Exception as exc:
        raise AttachmentError("The recording could not be turned into text.") from exc
    if not text:
        raise AttachmentError("I could not hear any words in that recording.")
    return text
