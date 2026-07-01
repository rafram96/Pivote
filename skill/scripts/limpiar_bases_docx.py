"""Limpia unas bases OSCE en .docx quitando el texto TACHADO (w:strike/w:dstrike =
requisitos ELIMINADOS en la integración) y lo entrega como PDF, para que agent-bases
lea SOLO los requisitos vigentes.

En .docx la tacha es DATO ESTRUCTURADO (w:strike) → la limpieza es determinística,
a diferencia del PDF donde la tacha es una línea dibujada (ambigua). Por eso el .docx
se limpia con este script y el PDF se maneja por visión en el prompt de agent-bases.

Uso:   python scripts/limpiar_bases_docx.py <bases.docx> [salida.pdf]
Salida: imprime la ruta del PDF limpio en la ÚLTIMA línea de stdout.

Requiere: lxml. Para el PDF: Microsoft Word (Windows) o LibreOffice `soffice` (Linux).
"""
import platform
import subprocess
import sys
import zipfile
from pathlib import Path
from shutil import which

from lxml import etree

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _q(tag: str) -> str:
    return f"{{{W}}}{tag}"


def _es_tachado(r) -> bool:
    rpr = r.find(_q("rPr"))
    if rpr is None:
        return False
    for tag in ("strike", "dstrike"):
        e = rpr.find(_q(tag))
        if e is not None and (e.get(_q("val")) or "true") not in ("false", "0", "none"):
            return True
    return False


def _strip(xml_bytes: bytes):
    tree = etree.fromstring(xml_bytes)
    n = 0
    for r in list(tree.iter(_q("r"))):
        if _es_tachado(r):
            r.getparent().remove(r)
            n += 1
    return etree.tostring(tree, xml_declaration=True, encoding="UTF-8", standalone=True), n


def limpiar_docx(src: Path, dst_docx: Path) -> int:
    """Reescribe el .docx sin los runs tachados (document.xml + headers/footers)."""
    zin = zipfile.ZipFile(src)
    partes = [n for n in zin.namelist()
              if n.endswith(".xml") and (n == "word/document.xml"
                  or n.startswith("word/header") or n.startswith("word/footer"))]
    mod, total = {}, 0
    for n in partes:
        out, k = _strip(zin.read(n))
        if k or n == "word/document.xml":
            mod[n] = out
        total += k
    with zipfile.ZipFile(dst_docx, "w", zipfile.ZIP_DEFLATED) as zout:
        for it in zin.infolist():
            zout.writestr(it, mod.get(it.filename, zin.read(it.filename)))
    zin.close()
    return total


def _a_pdf_word(docx: Path, pdf: Path) -> bool:
    """Windows + Microsoft Word vía PowerShell COM (sin depender de pywin32)."""
    d, p = str(docx), str(pdf)
    ps = (
        '$w = New-Object -ComObject Word.Application; $w.Visible=$false; $w.DisplayAlerts=0; '
        'try { $doc = $w.Documents.Open("' + d + '", $false, $true); '
        '$doc.ExportAsFixedFormat("' + p + '", 17); $doc.Close($false) } '
        'finally { $w.Quit() }'
    )
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                   capture_output=True, text=True)
    return pdf.exists()


def _a_pdf_soffice(docx: Path, pdf: Path) -> bool:
    """Linux/Cowork (o Windows con LibreOffice) vía soffice headless."""
    exe = next((c for c in ("soffice", "libreoffice") if which(c)), None)
    if not exe:
        return False
    subprocess.run([exe, "--headless", "--convert-to", "pdf", "--outdir",
                    str(pdf.parent), str(docx)], capture_output=True, text=True)
    gen = pdf.parent / (docx.stem + ".pdf")   # soffice nombra <stem>.pdf en outdir
    if gen != pdf and gen.exists():
        gen.replace(pdf)
    return pdf.exists()


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("uso: python scripts/limpiar_bases_docx.py <bases.docx> [salida.pdf]")
    src = Path(sys.argv[1]).resolve()
    if not src.exists():
        sys.exit(f"no existe: {src}")
    pdf = (Path(sys.argv[2]).resolve() if len(sys.argv) > 2
           else src.with_name(src.stem + "_limpio.pdf"))
    tmp_docx = src.with_name(src.stem + "_limpio.docx")

    n = limpiar_docx(src, tmp_docx)
    print(f"tachados removidos: {n}", file=sys.stderr)

    ok = _a_pdf_word(tmp_docx, pdf) if platform.system() == "Windows" else False
    if not ok:
        ok = _a_pdf_soffice(tmp_docx, pdf)
    if not ok:
        sys.exit("no pude convertir a PDF: instala Microsoft Word (Windows) o "
                 "LibreOffice `soffice` (Linux/Cowork).")
    print(pdf)   # ÚLTIMA línea = ruta del PDF limpio que debe leer agent-bases


if __name__ == "__main__":
    main()
