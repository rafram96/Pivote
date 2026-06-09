"""
validar_espejo.py — Valida un JSON espejo contra el schema Pydantic.

Lo usa el orquestador de la skill: tras consolidar (o tras cada subagente), corre
este validador. Si falla, reintenta el subagente correspondiente pasándole los
errores concretos (texto que imprime este script).

Uso:
    python validar_espejo.py <ruta_json>
Salida: "OK · ..." y exit 0 si valida; o el detalle de errores y exit 1.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # para importar schemas/

from pydantic import ValidationError  # noqa: E402
from schemas.espejo import JsonEspejo  # noqa: E402


def validar(ruta: Path) -> int:
    try:
        data = json.loads(ruta.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: no se pudo leer/parsear JSON: {e}")
        return 1

    try:
        esp = JsonEspejo.model_validate(data)
    except ValidationError as e:
        print(f"INVÁLIDO · {len(e.errors())} error(es):")
        for err in e.errors():
            loc = ".".join(str(x) for x in err["loc"])
            print(f"  - [{loc}] {err['msg']}")
        return 1

    nprof = len(esp.profesionales)
    nexp = sum(len(p.experiencias) for p in esp.profesionales)
    print(f"OK · espejo válido · {nprof} profesionales · {nexp} experiencias · "
          f"postor_exp={len(esp.postor.experiencia_postor)} · "
          f"factores={len(esp.resumen_evaluacion.factores)}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python validar_espejo.py <ruta_json>", file=sys.stderr)
        raise SystemExit(2)
    raise SystemExit(validar(Path(sys.argv[1])))
