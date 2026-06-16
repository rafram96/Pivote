"""
Auditoría en vivo de los cruces SUNAT (punto 2 de "qué falta").

Verifica contra RUCs reales del concurso:
  • consultar_ruc()            → insumo de ALT04 (fecha de inscripción/constitución)
  • consultar_representantes() → insumo de ALT12 (firmante ≠ representante legal)
  • diagnosticar_html_sunat()  → que un RUC inexistente NO se confunda con rotura

Recordatorio del cableado actual (hallazgo de esta auditoría):
  - ALT04 SÍ está cableada (EtapaSunatReal: fecha_inscripcion > fecha_inicial).
  - ALT12 NO está cableada: el helper consultar_representantes existe y los tests
    lo cubren, pero ninguna etapa lo invoca ni setea firmante_facultado_sunat.

Datos públicos (consulta RUC SUNAT), solo lectura.

Uso:
    python tools/auditar_sunat.py 20489650674 20607105615
    python tools/auditar_sunat.py            # usa el set por defecto del demo
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "backend"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from scraping.sunat import (  # noqa: E402
    _crear_session_sunat,
    consultar_representantes,
    consultar_ruc,
)

# Empresas (RUC 20…) extraídas del espejo del demo (4816fbdf3bea).
DEFAULT = [
    "20489650674", "20551741134", "20573023481", "20600789911",
    "20607105615",  # ← la que dio estructura_desconocida en el run
]


def auditar(ruc: str, sess) -> None:
    print(f"\n{'='*70}\nRUC {ruc}")
    emp = consultar_ruc(ruc, session=sess)
    if emp is None:
        print("  consultar_ruc → None (ver diagnóstico en el log de arriba)")
    else:
        print(f"  razón social      : {emp.razon_social}")
        print(f"  fecha inscripción : {emp.fecha_inscripcion}   ← insumo ALT04")
        print(f"  inicio actividades: {emp.fecha_inicio_actividades}")
        print(f"  estado/condición  : {emp.estado} / {emp.condicion}")
        # Chequeo sintético ALT04: ¿dispararía contra un inicio de experiencia dado?
        if emp.fecha_inscripcion:
            for ini in ("2015-01-01", "2020-01-01"):
                from datetime import date
                y, m, d = map(int, ini.split("-"))
                dispara = emp.fecha_inscripcion > date(y, m, d)
                print(f"    ALT04 si exp. inicia {ini}: "
                      f"{'DISPARA (constituida después)' if dispara else 'no dispara'}")

    reps = consultar_representantes(ruc, session=sess)
    print(f"  representantes legales (insumo ALT12): {len(reps)}")
    for r in reps[:4]:
        print(f"    · {r.tipo_documento} {r.nro_documento} — {r.nombre} ({r.cargo})")


def main() -> int:
    rucs = sys.argv[1:] or DEFAULT
    sess = _crear_session_sunat()
    print(f"Auditando {len(rucs)} RUC(s) contra SUNAT en vivo…")
    for ruc in rucs:
        try:
            auditar(ruc, sess)
        except Exception as ex:  # noqa: BLE001
            print(f"  ERROR {ruc}: {ex!r}")
    sess.close()
    print(f"\n{'='*70}\nListo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
