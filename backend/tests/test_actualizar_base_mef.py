"""Pruebas offline del ETL serving-first del MEF."""
from __future__ import annotations

import csv
import json
import os
import sys
import uuid
from types import SimpleNamespace
from pathlib import Path

import pytest

from resolucion.base_mef import BaseMef
from scripts import actualizar_base_mef as etl
from scripts.actualizar_base_mef import FUENTES, _procesar


BASE = {
    "CODIGO_UNICO": "",
    "CODIGO_SNIP": "",
    "NOMBRE_INVERSION": "MEJORAMIENTO DEL HOSPITAL PROVINCIAL",
    "ESTADO": "VIABLE",
    "SITUACION": "EN EJECUCION",
    "ENTIDAD": "GOBIERNO REGIONAL DE PRUEBA",
    "NIVEL": "GOBIERNO REGIONAL",
    "SECTOR": "SALUD",
    "FUNCION": "SALUD",
    "TIPO_INVERSION": "PROYECTO DE INVERSION",
    "DES_TIPOLOGIA": "HOSPITALES",
    "DES_MODALIDAD": "ADMINISTRACION INDIRECTA",
    "MONTO_VIABLE": "123456.78",
    "COSTO_ACTUALIZADO": "234567.89",
    "FECHA_REGISTRO": "2024-01-02",
    "FECHA_VIABILIDAD": "2024-02-03",
    "EXPEDIENTE_TECNICO": "SI",
    "NOMBRE_OPMI": "OPMI REGIONAL",
    "NOMBRE_UF": "UF REGIONAL",
    "NOMBRE_UEI": "UEI REGIONAL",
    "NOMBRE_UEP": "UEP REGIONAL",
    "UBIGEO": "000000",
    "DEPARTAMENTO": "PRUEBA",
    "PROVINCIA": "PRUEBA",
    "DISTRITO": "PRUEBA",
}


class PostgresFake:
    def __init__(self):
        self.filas = []
        self.meta = None
        self.publicada = False
        self.retener = None

    def insertar(self, valores):
        self.filas.append(valores)

    def validar(self, meta):
        assert len(self.filas) == meta["identidades"]
        self.meta = meta

    def publicar(self):
        self.publicada = True

    def purgar(self, retener):
        self.retener = retener


def _ejecutar(entrada, salida, **kwargs):
    pg = PostgresFake()
    meta = _procesar(entrada, salida, pg=pg, **kwargs)
    return meta, pg


def _escribir(ruta: Path, fila: dict) -> None:
    with ruta.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(fila))
        w.writeheader()
        w.writerow(fila)


@pytest.fixture
def fuentes(tmp_path):
    entrada = tmp_path / "entrada"
    salida = tmp_path / "salida"
    entrada.mkdir()
    for i, (archivo, _) in enumerate(FUENTES, start=1):
        fila = dict(BASE)
        fila["CODIGO_UNICO"] = str(2_000_000 + i)
        fila["CODIGO_SNIP"] = str(100_000 + i)
        if archivo == "INVERSIONES_DESACTIVADAS.csv":
            fila["COD_SNIP"] = fila.pop("CODIGO_SNIP")
            fila["NOM_OPMI"] = fila.pop("NOMBRE_OPMI")
            fila["NOM_UF"] = fila.pop("NOMBRE_UF")
            fila["NOM_UEI"] = fila.pop("NOMBRE_UEI")
            fila["NOM_UEP"] = fila.pop("NOMBRE_UEP")
        _escribir(entrada / archivo, fila)
    return entrada, salida


def test_publica_manifest_y_carga_postgres_enriquecida(fuentes):
    entrada, salida = fuentes
    meta, pg = _ejecutar(
        entrada, salida, min_union=3, min_por_fuente=1,
        identificador="carga-prueba",
    )

    manifest = json.loads((salida / "manifest.json").read_text(encoding="utf-8"))
    activa = salida / manifest["ruta"]
    assert manifest["load_id"] == "carga-prueba"
    assert meta["filas_total"] == 3
    assert meta["identidades"] == 3
    assert (activa / "inversiones.csv.gz").is_file()
    assert (activa / "entidades_publicas.csv").is_file()
    assert pg.publicada is True
    assert pg.retener == 2
    fila = next(f for f in pg.filas if f[1] == "2000003")
    assert fila[15] == "SALUD"  # sector
    assert str(fila[20]) == "123456.78"  # monto viable
    assert fila[25] == "OPMI REGIONAL"


def test_aliases_nom_entran_al_catalogo(fuentes):
    entrada, salida = fuentes
    _ejecutar(
        entrada, salida, min_union=3, min_por_fuente=1,
        identificador="aliases",
    )
    activa = salida / "cargas" / "aliases"
    texto = (activa / "entidades_publicas.csv").read_text(encoding="utf-8")
    assert "OPMI REGIONAL" in texto
    assert "UF REGIONAL" in texto
    assert "UEI REGIONAL" in texto
    assert "UEP REGIONAL" in texto


def test_gate_fallido_conserva_manifest_anterior(fuentes):
    entrada, salida = fuentes
    _ejecutar(
        entrada, salida, min_union=3, min_por_fuente=1,
        identificador="buena",
    )
    anterior = (salida / "manifest.json").read_text(encoding="utf-8")

    with pytest.raises(ValueError, match="validación FALLIDA"):
        _ejecutar(
            entrada, salida, min_union=99, min_por_fuente=1,
            identificador="mala",
        )

    assert (salida / "manifest.json").read_text(encoding="utf-8") == anterior
    assert not (salida / "cargas" / "mala").exists()


def test_base_detecta_nueva_carga_sin_reiniciar(fuentes):
    entrada, salida = fuentes
    _ejecutar(
        entrada, salida, min_union=3, min_por_fuente=1,
        identificador="20260729T010000Z-primera",
    )
    base = BaseMef(salida)
    primera = base.buscar_candidatos("HOSPITAL PROVINCIAL")
    assert primera
    assert primera[0]["entidad"] == "GOBIERNO REGIONAL DE PRUEBA"

    for archivo, _ in FUENTES:
        ruta = entrada / archivo
        with ruta.open(encoding="utf-8-sig", newline="") as f:
            fila = next(csv.DictReader(f))
        fila["ENTIDAD"] = "NUEVA ENTIDAD PUBLICA"
        _escribir(ruta, fila)
    _ejecutar(
        entrada, salida, min_union=3, min_por_fuente=1,
        identificador="20260729T020000Z-segunda",
    )

    segunda = base.buscar_candidatos("HOSPITAL PROVINCIAL")
    assert segunda
    assert segunda[0]["entidad"] == "NUEVA ENTIDAD PUBLICA"


def test_base_enriquece_desde_postgres_sin_cargar_ram(fuentes):
    entrada, salida = fuentes
    _ejecutar(
        entrada, salida, min_union=3, min_por_fuente=1,
        identificador="carga-pg",
    )

    def consulta(load_id, codigo):
        assert load_id == "carga-pg"
        if codigo == "__health__":
            return None
        if codigo != "2000001":
            return None
        return {
            "cui": codigo,
            "snip": "100001",
            "nombre": "MEJORAMIENTO DEL HOSPITAL PROVINCIAL",
            "estado_dataset": "ACTIVO",
            "situacion": "EN EJECUCION",
            "entidad": "GOBIERNO REGIONAL DE PRUEBA",
            "sector": "SALUD",
            "monto_viable": "123456.78",
        }

    base = BaseMef(salida, consulta_pg=consulta)
    ficha = base.existe_cui("2000001")
    assert ficha["sector"] == "SALUD"
    assert ficha["monto_viable"] == "123456.78"
    assert base._cargada is False
    assert base.existe_cui("9999999") is None
    assert base._cargada is False


def test_drift_bloquea_caida_brusca_de_fuente(fuentes):
    entrada, salida = fuentes
    _ejecutar(
        entrada, salida, min_union=3, min_por_fuente=1,
        identificador="20260729T010000Z-completa",
    )
    archivo = entrada / "DETALLE_INVERSIONES.csv"
    with archivo.open(encoding="utf-8-sig", newline="") as f:
        campos = list((csv.DictReader(f).fieldnames or []))
    with archivo.open("w", encoding="utf-8-sig", newline="") as f:
        csv.DictWriter(f, fieldnames=campos).writeheader()

    with pytest.raises(ValueError, match="caída de volumen"):
        _ejecutar(
            entrada, salida, min_union=0, min_por_fuente=0,
            identificador="20260729T020000Z-corta",
        )


def test_descarga_reintenta_y_no_publica_parcial(tmp_path, monkeypatch):
    llamadas = 0
    esperas = []

    class Respuesta:
        def __init__(self, falla=False):
            self.falla = falla

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def raise_for_status(self):
            if self.falla:
                raise RuntimeError("503 temporal")

        def iter_content(self, chunk_size):
            yield b"csv-valido"

    def get(*_args, **_kwargs):
        nonlocal llamadas
        llamadas += 1
        return Respuesta(falla=llamadas == 1)

    monkeypatch.setattr(etl, "MIN_BYTES_DESCARGA", 1)
    monkeypatch.setitem(sys.modules, "requests", SimpleNamespace(get=get))
    etl._descargar(tmp_path, reintentos=3, espera=esperas.append)

    assert llamadas == len(FUENTES) + 1
    assert len(esperas) == 1
    assert all((tmp_path / archivo).read_bytes() == b"csv-valido"
               for archivo, _ in FUENTES)
    assert not list(tmp_path.glob("*.parcial"))


def test_lock_impide_dos_actualizaciones_simultaneas(tmp_path):
    with etl._bloqueo_exclusivo(tmp_path):
        with pytest.raises(RuntimeError, match="ya existe"):
            with etl._bloqueo_exclusivo(tmp_path):
                pytest.fail("el segundo lock no debía adquirirse")


@pytest.mark.skipif(
    not os.getenv("PIVOTE_TEST_PG_DSN"),
    reason="requiere PostgreSQL de integración explícito",
)
def test_carga_postgres_real_y_publica_puntero(fuentes):
    import psycopg

    entrada, salida = fuentes
    dsn = os.environ["PIVOTE_TEST_PG_DSN"]
    load_id = f"pytest-{uuid.uuid4().hex}"
    with etl.CargaPostgres(dsn, load_id) as pg:
        meta = _procesar(
            entrada, salida, pg=pg, min_union=3, min_por_fuente=1,
            identificador=load_id,
        )

    with psycopg.connect(dsn) as con:
        fila = con.execute(
            """SELECT sector, monto_viable::text, opmi
               FROM mef.investments WHERE load_id = %s AND cui = '2000003'""",
            (load_id,),
        ).fetchone()
        activa = con.execute(
            "SELECT load_id FROM mef.active_load WHERE singleton"
        ).fetchone()[0]
    assert meta["identidades"] == 3
    assert fila == ("SALUD", "123456.78", "OPMI REGIONAL")
    assert activa == load_id
