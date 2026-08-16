import tempfile
import unittest
from pathlib import Path

from skill.scripts import ocr_propuesta as ocr


class OcrPropuestaTest(unittest.TestCase):
    def test_tesseract_usa_osd(self):
        cmd = ocr.comando_tesseract("tesseract", "pagina.png")
        self.assertEqual(cmd[-2:], ["--psm", "1"])

    def test_multiimagen_conserva_jpg_png_y_descarta_smask_ppm(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            rutas = []
            for nombre, tamano in (
                ("img-414-000.jpg", 3000),
                ("img-414-001.png", 2500),
                ("img-414-002.jpg", 100),
                ("img-414-003.ppm", 5000),
            ):
                ruta = base / nombre
                ruta.write_bytes(b"x" * tamano)
                rutas.append(str(ruta))
            self.assertEqual(
                [Path(x).name for x in ocr.imagenes_utiles(rutas)],
                ["img-414-000.jpg", "img-414-001.png"],
            )

    def test_reporta_paginas_vacias_o_cortas(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "p0001.txt").write_text("texto suficientemente largo para pasar", encoding="utf-8")
            (base / "p0002.txt").write_text("logo", encoding="utf-8")
            (base / "p0003.txt").write_text("", encoding="utf-8")
            self.assertEqual(ocr.paginas_bajo_umbral(tmp, 3, minimo=10), [2, 3])


if __name__ == "__main__":
    unittest.main()
