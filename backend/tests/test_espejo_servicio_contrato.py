import json
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from schemas.espejo import JsonEspejo


def _espejo(servicio):
    return {
        "_meta": {"analisis_id": "parity", "servicio_esperado": servicio},
        "postor": {},
        "profesionales": [{"n_prof": 1, "cargo": "X",
                            "experiencias": [{"n": 1, "servicio_declarado": servicio}]}],
    }


def test_servicio_evidencia_pagina_estricta_y_legacy():
    JsonEspejo.model_validate(_espejo(None))
    JsonEspejo.model_validate(_espejo({"tipo": "otro", "texto": None,
                                       "pagina_pdf": None, "fuente": None}))
    with pytest.raises(ValidationError):
        JsonEspejo.model_validate(_espejo({"tipo": "otro", "pagina_pdf": True}))
    with pytest.raises(ValidationError):
        JsonEspejo.model_validate(_espejo({"tipo": "otro", "pagina_pdf": "1"}))


def test_servicio_valido_pasa_pydantic_y_zod(tmp_path):
    ruta = tmp_path / "espejo.json"
    ruta.write_text(json.dumps(_espejo({"tipo": "ejecucion_obra",
                                        "texto": "Residente de obra",
                                        "pagina_pdf": 1,
                                        "fuente": "certificado"})), encoding="utf-8")
    JsonEspejo.model_validate(json.loads(ruta.read_text(encoding="utf-8")))
    raiz = Path(__file__).resolve().parents[2]
    proceso = subprocess.run(
        ["node", str(raiz / "skill/scripts/validar_espejo.js"), str(ruta)],
        cwd=raiz, capture_output=True, text=True, encoding="utf-8",
    )
    assert proceso.returncode == 0, proceso.stdout + proceso.stderr
