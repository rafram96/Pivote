"""
Guarda anti-divergencia de `backend/db/schema.sql`.

`schema.sql` NO es fuente de verdad: el código lo es. Quien crea las tablas de
verdad son dos constantes DDL —el schema `mef` del ETL y las 3 tablas del
respaldo lógico— y cada una se aplica sola, sin leer el archivo. El archivo
existe para poder leer el esquema completo de un vistazo y levantarlo a mano.

Justamente por eso puede mentir sin que nadie se entere: fue exactamente lo que
pasó entre 2026-06 y 2026-08 (sondeo B04 — declaraba 4 tablas y 2 vistas que el
código nunca creó). Estos tests comparan, SIN Postgres y sin red, los bloques
marcados `>>> ESPEJO` del archivo contra las constantes del código.

La comparación es textual y normalizada: se ignoran comentarios `--`, líneas en
blanco y diferencias de espaciado/indentación. Cualquier cambio real de DDL
(una columna, un índice, un CHECK) rompe el test hasta que el archivo lo
refleje. Límite conocido: esto NO valida que el SQL sea válido para PostgreSQL
ni que la BD desplegada coincida — para eso hace falta un PG real, y los tests
que lo usan están gateados por `PIVOTE_TEST_DB_URL`.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
SCHEMA_SQL = BACKEND / "db" / "schema.sql"

_RE_BLOQUE = re.compile(
    r"^--\s*>>>\s*ESPEJO:\s*(?P<origen>.+?)\s*>>>\s*$"
    r"(?P<cuerpo>.*?)"
    r"^--\s*<<<\s*FIN ESPEJO\s*<<<\s*$",
    re.MULTILINE | re.DOTALL,
)


def _normalizar(sql: str) -> str:
    """DDL comparable: sin comentarios de línea, sin blancos redundantes."""
    sin_comentarios = "\n".join(
        linea.split("--")[0] for linea in sql.splitlines()
    )
    return re.sub(r"\s+", " ", sin_comentarios).strip()


def _bloques() -> dict[str, str]:
    """Los bloques `>>> ESPEJO … <<<` del archivo, indexados por su origen."""
    texto = SCHEMA_SQL.read_text(encoding="utf-8")
    return {m.group("origen"): m.group("cuerpo") for m in _RE_BLOQUE.finditer(texto)}


# (origen declarado en el archivo, módulo, nombre de la constante)
ESPEJOS = [
    ("backend/scripts/actualizar_base_mef.py :: _DDL_PG",
     "scripts.actualizar_base_mef", "_DDL_PG"),
    ("backend/orquestador/repositorio_pg.py :: _DDL",
     "orquestador.repositorio_pg", "_DDL"),
]


def _ddl_del_codigo(modulo: str, constante: str) -> str:
    import importlib
    return getattr(importlib.import_module(modulo), constante)


@pytest.mark.parametrize("origen,modulo,constante", ESPEJOS,
                         ids=[e[0].split("::")[-1].strip() for e in ESPEJOS])
def test_schema_sql_espeja_el_ddl_del_codigo(origen, modulo, constante):
    """El bloque del archivo dice EXACTAMENTE lo que el código ejecuta."""
    bloques = _bloques()
    assert origen in bloques, (
        f"`db/schema.sql` no declara el bloque espejo de {origen}. "
        f"Bloques presentes: {sorted(bloques)}"
    )
    del_archivo = _normalizar(bloques[origen])
    del_codigo = _normalizar(_ddl_del_codigo(modulo, constante))
    assert del_archivo == del_codigo, (
        f"`db/schema.sql` divergió de {origen}.\n"
        f"El código es la fuente de verdad: actualiza el archivo, no al revés."
    )


def test_todos_los_ddl_del_codigo_estan_espejados():
    """Un DDL nuevo en el código sin bloque en el archivo también es divergencia."""
    declarados = set(_bloques())
    esperados = {origen for origen, _, _ in ESPEJOS}
    assert declarados == esperados, (
        f"bloques espejo del archivo: {sorted(declarados)} · esperados: {sorted(esperados)}"
    )


def test_schema_sql_no_resucita_las_vistas_fantasma():
    """Las tablas/vistas aspiracionales de B04 no vuelven a colarse como DDL.

    `base_datos`, `analisis`, `espejos`, `enriquecimientos` y `concursos` nunca
    existieron en una BD real; el archivo puede NOMBRARLAS en su prosa (explica
    por qué se fueron), pero no volver a crearlas.
    """
    lineas_ddl = [
        linea.split("--")[0]
        for linea in SCHEMA_SQL.read_text(encoding="utf-8").splitlines()
        if not linea.lstrip().startswith("--")
    ]
    ddl = "\n".join(lineas_ddl).upper()
    for fantasma in ("VIEW BASE_DATOS", "VIEW ANALISIS", "TABLE IF NOT EXISTS ESPEJOS",
                     "TABLE IF NOT EXISTS ENRIQUECIMIENTOS",
                     "TABLE IF NOT EXISTS CONCURSOS"):
        assert fantasma not in ddl, f"`db/schema.sql` volvió a declarar {fantasma}"
