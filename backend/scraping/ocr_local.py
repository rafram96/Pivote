"""
OCR local determinístico para documentos oficiales (resoluciones del MEF, actas).

Mismo motor que usa la skill en la máquina del cliente (Tesseract, español,
`--psm 1` con detección de orientación), pero corriendo en el servidor: CPU,
cero tokens, reproducible. El backend NUNCA llama a una IA en la nube (ADR-001);
leer un PDF escaneado con Tesseract no rompe esa regla.

Uso: `texto_pdf(ruta)` devuelve `(texto, fuente, paginas)` donde `fuente` es
`capa` (el PDF traía texto), `ocr` (se reconoció) o `sin_texto` (ni capa ni
Tesseract disponible). Nunca lanza por falta de Tesseract: el consumidor decide
qué hacer con `sin_texto`. Import perezoso de PyMuPDF (ya es dependencia dura
del backend por los certificados embebidos).
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_CANDIDATOS_WINDOWS = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
)
_TESSDATA_LINUX = (
    "/usr/share/tesseract-ocr/5/tessdata",
    "/usr/share/tesseract-ocr/4.00/tessdata",
    "/usr/share/tesseract-ocr/tessdata",
    "/usr/share/tessdata",
)
_MODELOS = ("spa.traineddata", "osd.traineddata")
MIN_CHARS_CAPA = 300      # menos que esto en las primeras páginas = escaneo


def find_tesseract() -> Optional[str]:
    cmd = shutil.which("tesseract")
    if cmd:
        return cmd
    return next((r for r in _CANDIDATOS_WINDOWS if os.path.exists(r)), None)


def ensure_tessdata(tess: str, out_dir: Optional[str] = None) -> bool:
    """Garantiza `spa` + `osd` (necesarios para `--psm 1`). Primero busca junto al
    binario o en las rutas del sistema; si faltan, los copia/descarga a un
    directorio privado y fija TESSDATA_PREFIX. Devuelve si quedaron disponibles."""
    cands: list[str] = []
    env = os.environ.get("TESSDATA_PREFIX")
    if env:
        cands.append(env)
    cands.append(os.path.join(os.path.dirname(tess), "tessdata"))
    cands.extend(_TESSDATA_LINUX)
    for d in cands:
        if d and all(os.path.isfile(os.path.join(d, f)) for f in _MODELOS):
            os.environ["TESSDATA_PREFIX"] = d
            return True
    prefix = os.path.join(out_dir or tempfile.gettempdir(), "_tessdata")
    os.makedirs(prefix, exist_ok=True)
    for d in cands:
        if d and os.path.isdir(d):
            for nombre in os.listdir(d):
                if nombre.endswith(".traineddata"):
                    destino = os.path.join(prefix, nombre)
                    if not os.path.exists(destino):
                        try:
                            shutil.copyfile(os.path.join(d, nombre), destino)
                        except OSError:
                            pass
            break
    for modelo in ("spa", "osd"):
        destino = os.path.join(prefix, f"{modelo}.traineddata")
        if os.path.isfile(destino) and os.path.getsize(destino) > 1_000_000:
            continue
        for url in (
            f"https://github.com/tesseract-ocr/tessdata_fast/raw/main/{modelo}.traineddata",
            f"https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/{modelo}.traineddata",
        ):
            try:
                urllib.request.urlretrieve(url, destino)
                if os.path.getsize(destino) > 1_000_000:
                    break
            except (OSError, urllib.error.URLError):
                pass
    os.environ["TESSDATA_PREFIX"] = prefix
    return all(os.path.isfile(os.path.join(prefix, f)) for f in _MODELOS)


def disponible() -> bool:
    return find_tesseract() is not None


def _ocr_imagen(tess: str, imagen: str, timeout: float = 120.0) -> str:
    r = subprocess.run(
        [tess, imagen, "stdout", "-l", "spa", "--psm", "1"],
        capture_output=True, text=True, encoding="utf-8", errors="ignore",
        timeout=timeout, env={**os.environ, "OMP_THREAD_LIMIT": "1"},
    )
    return r.stdout or ""


def texto_pdf(ruta, max_pag: int = 4, dpi: int = 150,
              tess: Optional[str] = None) -> tuple[str, str, int]:
    """Texto de las primeras `max_pag` páginas de un PDF.

    Devuelve `(texto, fuente, paginas_totales)`. Prefiere la capa de texto; si
    es un escaneo y hay Tesseract, reconoce página a página (imágenes temporales
    que se borran). Sin Tesseract → `("", "sin_texto", n)`.
    """
    import fitz  # PyMuPDF (dependencia dura del backend)

    doc = fitz.open(str(ruta))
    n = min(len(doc), max_pag)
    capa = " ".join(doc[i].get_text() for i in range(n))
    if len(capa.strip()) >= MIN_CHARS_CAPA:
        return capa, "capa", len(doc)
    tess = tess or find_tesseract()
    if not tess:
        return "", "sin_texto", len(doc)
    ensure_tessdata(tess, str(Path(ruta).parent))
    partes: list[str] = []
    for i in range(n):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            img = tmp.name
        try:
            doc[i].get_pixmap(dpi=dpi).save(img)
            partes.append(_ocr_imagen(tess, img))
        except (OSError, subprocess.SubprocessError) as ex:  # una página mala no tumba el documento
            logger.debug("ocr página %d de %s: %s", i + 1, ruta, ex)
        finally:
            try:
                os.remove(img)
            except OSError:
                pass
    texto = " ".join(partes)
    return texto, ("ocr" if texto.strip() else "sin_texto"), len(doc)
