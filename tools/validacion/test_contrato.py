"""
test_contrato.py — Test de contrato del JSON espejo: Pydantic vs zod.

Corre los fixtures de espejo COMPLETO por los dos validadores del contrato
(backend/schemas/espejo.py y skill/schemas/espejo.js) y falla si:
  a) algún fixture es inválido para alguno de los dos, o
  b) los veredictos divergen (uno acepta lo que el otro rechaza).

La divergencia es el bug caro: un espejo que la skill valida OK en la PC del
ingeniero pero que el backend rechaza en ingesta (o viceversa).

Los espejos se DESCUBREN, no se apuntan: los fixtures viejos hardcodeados
(fixtures/trujillo, new_format) se movieron/perdieron y dejaron el test roto.
Ahora corre contra todo `backend/datos_pivote/<job>/espejo.json` (jobs reales,
presentes en local y en el server) + cualquier `*espejo*.json` de `fixtures/`
que exista.

Uso:
    python tools/validacion/test_contrato.py
Salida: tabla de veredictos; exit 0 solo si todo OK y sin divergencias.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "backend"))

from pydantic import ValidationError  # noqa: E402
from schemas.espejo import JsonEspejo  # noqa: E402


def _descubrir_fixtures() -> list[Path]:
    vistos = []
    vistos += sorted((RAIZ / "backend/datos_pivote").glob("*/espejo.json"))
    # espejos sueltos en fixtures/ (si los hay); se excluyen las BD de
    # experiencias (otra forma: sin postor ni resumen, no son el contrato)
    vistos += sorted(p for p in (RAIZ / "fixtures").rglob("*espejo*.json")
                     if "bd_experiencias" not in p.name)
    return vistos


FIXTURES = _descubrir_fixtures()
VALIDADOR_JS = RAIZ / "skill/scripts/validar_espejo.js"


def veredicto_pydantic(ruta: Path) -> tuple[bool, str]:
    data = json.loads(ruta.read_text(encoding="utf-8"))
    try:
        m = JsonEspejo.model_validate(data)
    except ValidationError as e:
        primeros = "; ".join(
            f"[{'.'.join(str(x) for x in err['loc'])}] {err['msg']}" for err in e.errors()[:3]
        )
        return False, f"{e.error_count()} error(es): {primeros}"
    nexp = sum(len(p.experiencias) for p in m.profesionales)
    return True, f"{len(m.profesionales)} prof · {nexp} exp"


def veredicto_zod(ruta: Path) -> tuple[bool, str]:
    r = subprocess.run(
        ["node", str(VALIDADOR_JS), str(ruta)],
        capture_output=True, text=True, encoding="utf-8", cwd=RAIZ,
    )
    salida = (r.stdout or r.stderr).strip().splitlines()
    resumen = salida[0] if salida else "(sin salida)"
    detalle = "; ".join(s.strip() for s in salida[1:4])
    return r.returncode == 0, resumen if r.returncode == 0 else f"{resumen} {detalle}"


def main() -> int:
    if not FIXTURES:
        print("⚠ sin espejos que probar (ni jobs en datos_pivote ni fixtures)")
        return 1
    fallas = 0
    for fixture in FIXTURES:
        ok_py, msg_py = veredicto_pydantic(fixture)
        ok_js, msg_js = veredicto_zod(fixture)
        nombre = fixture.relative_to(RAIZ)
        print(f"=== {nombre}")
        print(f"  pydantic: {'OK' if ok_py else 'INVÁLIDO'} · {msg_py}")
        print(f"  zod     : {'OK' if ok_js else 'INVÁLIDO'} · {msg_js}")
        if ok_py != ok_js:
            print("  ✗ DIVERGENCIA: los validadores no coinciden")
            fallas += 1
        elif not ok_py:
            print("  ✗ ambos rechazan el fixture")
            fallas += 1

    print()
    if fallas:
        print(f"CONTRATO ROTO · {fallas} problema(s)")
        return 1
    print("CONTRATO OK · ambos validadores aceptan los mismos espejos")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
