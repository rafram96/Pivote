"""Chequeo en vivo del CUI/SNIP 133630 (caso Hermilio Valdizán — Item 02
Obras Complementarias). Responde 3 preguntas:

  1. ¿Cuántos registros devuelve InfoObras para 133630 y cuáles son sus
     códigos/estados/fechas? (¿está el tercero, el de obras complementarias?)
  2. ¿Qué clave trae realmente el "Código InfoObras"? (bug del Excel: "—")
  3. Para cada registro, ¿qué rango de valorizaciones tiene? ¿alguno solapa
     el periodo del certificado 10/06/2016 → 15/05/2017?
"""
import sys, json
from pathlib import Path
from datetime import date

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/

from scraping.infoobras import (  # noqa: E402
    _crear_session, _extraer_datos_ejecucion, _procesar_avances,
    _parse_timestamp_json, _estado_obra,
)
from resolucion.cui import ConsultaInfoObras  # noqa: E402

CERT_INI, CERT_FIN = date(2016, 6, 10), date(2017, 5, 15)


def rango_valorizaciones(session, obra_id):
    try:
        datos = _extraer_datos_ejecucion(session, obra_id)
        avs = _procesar_avances(datos.get("lAvances", []))
        fechas = [date(a.anio, a.mes, 1) for a in avs if getattr(a, "anio", 0) and getattr(a, "mes", 0)]
        if not fechas:
            return None, None, 0
        return min(fechas), max(fechas), len(fechas)
    except Exception as e:
        return f"ERR {e!r}", None, 0


def solapa(ini, fin):
    if not isinstance(ini, date) or not isinstance(fin, date):
        return "?"
    return "SÍ" if (max(ini, CERT_INI) <= min(fin, CERT_FIN)) else "no"


def main():
    obras = ConsultaInfoObras().por_codigo("133630")
    print(f"\n=== 133630 devolvió {len(obras)} registro(s) ===\n")
    if not obras:
        print("Sin resultados.")
        return

    # Pregunta 2: ¿qué claves trae cada registro?
    print(">>> CLAVES del primer registro (para ver dónde vive el Código InfoObras):")
    print(sorted(obras[0].keys()))
    for clave in ("codigoObra", "codigoInfobras", "codInfobras", "CodigoInfobras"):
        print(f"    {clave!r:18} -> {obras[0].get(clave)!r}")
    print()

    session = _crear_session()
    print(">>> REGISTROS (código / estado / fechas cabecera / valorizaciones):\n")
    for o in obras:
        cid = o.get("codigoObra")
        est = _estado_obra(o)
        fi = _parse_timestamp_json(o.get("fechaIniObra"))
        ff = _parse_timestamp_json(o.get("fechaFinObra"))
        vi, vf, nv = rango_valorizaciones(session, cid)
        print(f"  Código {cid} | {est:12} | cabecera {fi} → {ff}")
        print(f"      nombre: {(o.get('nombrObra') or '')[:80]}")
        print(f"      monto:  {o.get('montoObraSoles')}  dpto: {o.get('nombrDepartamento')}")
        print(f"      valorizaciones: {nv} avances, rango {vi} → {vf}  | solapa cert? {solapa(vi, vf)}")
        print()

    print(f"Periodo del certificado: {CERT_INI} → {CERT_FIN}")


if __name__ == "__main__":
    main()
