#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Compara el léxico de privadas ANTIGUO contra el vigente sobre espejos locales.

Sin red y sin escribir nada en las carpetas de datos: solo LEE `espejo.json` y,
si existe, `enriquecimiento.json` de cada job para responder dos preguntas:

  1. ¿qué experiencias cambian de clasificación con `_es_experiencia_privada`?
  2. ¿alguna experiencia HOY RESUELTA con CUI pasa a privada? (eso sería una
     regresión: `_checkpoint_naturaleza` la degradaría a revisión).

El criterio ANTIGUO se reconstruye aplicando `_RE_PRIVADA` (el léxico educativo,
que no cambió) sobre proyecto + entidad_contratante + objeto — que es
literalmente lo que hacía la versión previa de `_es_experiencia_privada`.

Uso (los datos del cliente viven fuera del repo; se pasa la ruta):

    python backend/scripts/comparar_lexico_privadas.py <carpeta_datos_pivote> [--detalle]

No imprime nombres, RUC ni CUI de terceros salvo con `--detalle`, que es para
inspección local del desarrollador y nunca debe pegarse en el repo.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from resolucion.cui import (  # noqa: E402
    _RE_PRIVADA, _es_experiencia_privada, _texto_cliente,
)


def _privada_antigua(exp: dict) -> bool:
    """Criterio histórico: solo el léxico educativo sobre los mismos campos."""
    return bool(_RE_PRIVADA.search(_texto_cliente(exp)))


def _resuelta_con_cui(enr: dict, n_prof, n_exp) -> bool:
    """True si el enriquecimiento guardado resolvió un CUI para esa experiencia
    (incluye el caso multiobra: alguna sub-obra con CUI). El `estado` no se
    persiste en `enriquecimiento.json`: el CUI presente ES la resolución."""
    r = enr.get(f"{n_prof}:{n_exp}")
    if not isinstance(r, dict):
        return False
    if r.get("cui"):
        return True
    return any(isinstance(s, dict) and s.get("cui")
               for s in (r.get("sub_obras") or []))


def _cargar(ruta: Path) -> dict:
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except Exception:
        return {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("datos", help="carpeta con un subdirectorio por job")
    ap.add_argument("--detalle", action="store_true",
                    help="imprime el texto de cada cambio (uso local)")
    args = ap.parse_args()

    raiz = Path(args.datos)
    if not raiz.is_dir():
        print(f"no es una carpeta: {raiz}")
        return 2

    tot = Counter()
    regresiones: list[tuple] = []
    nuevas: list[tuple] = []

    for espejo_ruta in sorted(raiz.glob("*/espejo.json")):
        job = espejo_ruta.parent.name
        espejo = _cargar(espejo_ruta)
        if not espejo:
            continue
        enr = _cargar(espejo_ruta.parent / "enriquecimiento.json")
        tipo = (espejo.get("_meta") or {}).get("tipo_evaluacion")
        n_job = Counter()
        for prof in espejo.get("profesionales") or []:
            for exp in prof.get("experiencias") or []:
                antes, ahora = _privada_antigua(exp), _es_experiencia_privada(exp)
                n_job["exp"] += 1
                if antes == ahora:
                    continue
                clave = (job, prof.get("n_prof"), exp.get("n"))
                if ahora:
                    n_job["nuevas_privadas"] += 1
                    nuevas.append((*clave, _texto_cliente(exp)[:160]))
                    if _resuelta_con_cui(enr, prof.get("n_prof"), exp.get("n")):
                        n_job["regresiones"] += 1
                        regresiones.append((*clave, _texto_cliente(exp)[:160]))
                else:
                    n_job["dejan_de_ser_privadas"] += 1
                    nuevas.append((*clave, "[-] " + _texto_cliente(exp)[:160]))
        tot.update(n_job)
        print(f"{job}  tipo={tipo or '-'}  exp={n_job['exp']}  "
              f"nuevas_privadas={n_job['nuevas_privadas']}  "
              f"dejan_de_ser_privadas={n_job['dejan_de_ser_privadas']}  "
              f"regresiones(resueltas con CUI)={n_job['regresiones']}")

    print("\n== TOTAL ==")
    print(f"experiencias leídas: {tot['exp']}")
    print(f"pasan a privada:     {tot['nuevas_privadas']}")
    print(f"dejan de ser privada:{tot['dejan_de_ser_privadas']}")
    print(f"REGRESIONES (hoy resueltas con CUI y ahora privadas): {tot['regresiones']}")

    if args.detalle:
        print("\n== cambios ==")
        for fila in nuevas:
            print("  ", fila)
        if regresiones:
            print("\n== regresiones ==")
            for fila in regresiones:
                print("  ", fila)

    return 1 if tot["regresiones"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
