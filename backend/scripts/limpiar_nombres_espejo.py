"""Limpia el campo `nombre` de los profesionales en espejos YA generados: separa
nombre / dni / notas (las corridas viejas metían todo dentro de `nombre`).

Idempotente: si el nombre ya está limpio, no toca nada. Útil para que los jobs de
prueba se vean limpios en el panel sin re-correr la skill. Las extracciones nuevas
ya salen separadas (ver agent-propuesta-profesional + schema con `dni`).

Uso:   python -m scripts.limpiar_nombres_espejo            # toda la carpeta de datos
       python -m scripts.limpiar_nombres_espejo <job_id>   # solo ese job
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402 — carga el .env de la raíz
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_RE_DNI = re.compile(r"DNI\s*[:.]?\s*(\d{6,8})", re.I)
_RE_DNI_TRAILING = re.compile(r"\s*\(\s*DNI\s*[:.]?\s*\d{6,8}\s*\)\s*$", re.I)


def separar(nombre: str) -> tuple[str, str | None, str | None]:
    """`nombre` sucio → (nombre_limpio, dni, nota). El nombre limpio es el texto
    antes del primer paréntesis; el DNI es el primer número de 6-8 dígitos tras
    'DNI'; la nota es el resto del paréntesis (sin el '(DNI …)' final si solo era eso)."""
    if not nombre:
        return nombre, None, None
    limpio = re.split(r"\s*\(", nombre, 1)[0].strip()
    if limpio == nombre.strip():           # sin paréntesis → ya limpio
        return nombre.strip(), None, None
    resto = nombre[len(limpio):].strip()
    mdni = _RE_DNI.search(resto)
    dni = mdni.group(1) if mdni else None
    # ¿el resto era SOLO "(DNI 12345678)"? entonces no hay nota
    if re.fullmatch(r"\(\s*DNI\s*[:.]?\s*\d{6,8}\s*\)", resto, re.I):
        nota = None
    else:
        nota = _RE_DNI_TRAILING.sub("", resto).strip(" ()") or None
    return limpio, dni, nota


def limpiar_espejo(ruta: Path) -> int:
    d = json.loads(ruta.read_text(encoding="utf-8"))
    cambios = 0
    for p in d.get("profesionales", []):
        nombre = p.get("nombre")
        limpio, dni, nota = separar(nombre or "")
        if limpio == (nombre or "").strip() and dni is None and nota is None:
            continue  # ya limpio
        p["nombre"] = limpio
        if dni and not p.get("dni"):
            p["dni"] = dni
        if nota:
            notas = p.get("notas") or []
            if nota not in notas:
                notas.append(nota)
            p["notas"] = notas
        cambios += 1
    if cambios:
        ruta.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
    return cambios


def main(job_id: str | None) -> None:
    dd = config.data_dir()
    patron = f"{job_id}.espejo.json" if job_id else "*.espejo.json"
    archivos = sorted(dd.glob(patron))
    tot_files = tot_profs = 0
    for f in archivos:
        n = limpiar_espejo(f)
        if n:
            tot_files += 1
            tot_profs += n
            print(f"  {f.name}: {n} profesionales limpiados", flush=True)
    print(f"[limpiar] {tot_files} espejos modificados · {tot_profs} profesionales "
          f"(de {len(archivos)} archivos)", flush=True)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
