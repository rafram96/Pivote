"""
Comprobar A MANO el bloque R de resiliencia de las descargas (issue #81).

No es un test automatizado: es la herramienta para VER, sobre un job real o
sobre una simulación offline, las cuatro cosas que cambiaron.

Cuatro modos:

  notas      Los textos de las notas SEACE (las que lee un evaluador dentro de
             la carpeta de la experiencia) de un job ya corrido: qué dice hoy
             cada nota en disco y qué dirá la próxima corrida. Con `--salida`
             escribe un ZIP chiquito con SOLO las notas regeneradas.

  informes   Las experiencias donde la obra SÍ publica informes de control pero
             ninguno cae en el periodo del certificado: antes decían «sin
             documentos publicados (0 disponibles)». Con `--zip` regenera el
             ZIP de esas experiencias (en otra ruta) para leer su índice.

  reintento  Simulación offline del reintento selectivo: una sección revienta,
             la caché queda PARCIAL, el segundo pedido rehace solo esa sección
             y la promueve a completa. Sin red y sin tocar ningún job.

  part       Planta una carpeta `.part` huérfana en una caché de mentira y
             comprueba que la corrida siguiente la recoge.

NINGÚN modo escribe en un job real y NINGUNO toca la red.

Ejemplos:

    venv/Scripts/python backend/scripts/probar_cache_descargas.py notas 7e9306a321ac
    venv/Scripts/python backend/scripts/probar_cache_descargas.py informes 7e9306a321ac
    venv/Scripts/python backend/scripts/probar_cache_descargas.py reintento
    venv/Scripts/python backend/scripts/probar_cache_descargas.py part
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from orquestador.descargas_seace import (  # noqa: E402
    DOCUMENTOS_SEACE, NOTA_SEACE_DESCARGA_FALLIDA, nota_seace_ausencia,
)


def _linea(texto: str = "") -> None:
    print(texto)


def _consola_utf8() -> None:
    """La consola de Windows llega en cp1252 y revienta con «→» o «·»."""
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            pass


def _cargar_job(job: str):
    """(espejo, enriquecimiento, carpeta) de un job de `datos_pivote/`."""
    from config import data_dir
    carpeta = data_dir() / job
    espejo_f, enr_f = carpeta / "espejo.json", carpeta / "enriquecimiento.json"
    if not enr_f.exists():
        return None, None, carpeta
    enr = json.loads(enr_f.read_text(encoding="utf-8"))
    espejo = (json.loads(espejo_f.read_text(encoding="utf-8"))
              if espejo_f.exists() else {})
    return espejo, enr, carpeta


def _claves_ordenadas(enr: dict) -> list[tuple[int, int, dict]]:
    salida = []
    for clave, bloque in (enr or {}).items():
        if ":" not in str(clave) or not isinstance(bloque, dict):
            continue
        try:
            np_, ne = (int(x) for x in str(clave).split(":"))
        except ValueError:
            continue
        salida.append((np_, ne, bloque))
    return sorted(salida)


# ── Modo `notas` (R3, textos SEACE) ──────────────────────────────────────────

def modo_notas(a) -> int:
    espejo, enr, carpeta = _cargar_job(a.job)
    if enr is None:
        _linea(f"No hay enriquecimiento.json en {carpeta}")
        return 2
    descargas = carpeta / "descargas"
    filas, por_estado = [], {}
    for np_, ne, bloque in _claves_ordenadas(enr):
        seace = bloque.get("seace") if isinstance(bloque.get("seace"), dict) else None
        if not seace:
            continue
        estado = seace.get("estado")
        for _clave_doc, nombre, etiqueta in DOCUMENTOS_SEACE:
            for sufijo in ("NO_DISPONIBLE", "ERROR"):
                # también los nombres históricos `SEACE_0…` de jobs viejos
                candidatas = [descargas / f"P{np_}_E{ne}" / f"{nombre}_{sufijo}.txt"]
                candidatas += sorted((descargas / f"P{np_}_E{ne}").glob(
                    f"SEACE_*{nombre}_{sufijo}.txt")) if (
                    descargas / f"P{np_}_E{ne}").is_dir() else []
                for ruta in candidatas:
                    if not ruta.is_file():
                        continue
                    viejo = ruta.read_text(encoding="utf-8", errors="replace").strip()
                    nuevo = (NOTA_SEACE_DESCARGA_FALLIDA if sufijo == "ERROR"
                             and estado == "seleccionado"
                             else nota_seace_ausencia(estado))
                    filas.append((np_, ne, etiqueta, ruta.name, estado, viejo, nuevo))
                    por_estado.setdefault((estado, sufijo, nuevo), []).append(
                        f"P{np_}/E{ne}")

    _linea(f"Job {a.job} · notas SEACE en disco: {len(filas)}")
    _linea()
    if not filas:
        _linea("Este job no tiene notas SEACE (ninguna experiencia quedó sin "
               "documento del proceso).")
        return 0
    for (estado, sufijo, nuevo), donde in sorted(
            por_estado.items(), key=lambda x: (-len(x[1]), str(x[0][0]))):
        viejos = sorted({f[5] for f in filas
                         if f[4] == estado and f[3].endswith(f"{sufijo}.txt")})
        experiencias = list(dict.fromkeys(donde))
        _linea(f"■ estado «{estado}» · nota {sufijo} · {len(donde)} archivo(s) "
               f"en {len(experiencias)} experiencia(s)")
        _linea(f"  en: {', '.join(experiencias[:8])}"
               + (f" … (+{len(experiencias) - 8})" if len(experiencias) > 8 else ""))
        for v in viejos:
            _linea(f"  ANTES : {v}")
        _linea(f"  AHORA : {nuevo}")
        _linea()

    if a.salida:
        salida = Path(a.salida)
        salida.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(salida, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for np_, ne, _etiqueta, nombre, _estado, _viejo, nuevo in filas:
                zf.writestr(f"P{np_}_E{ne}/{nombre}", nuevo + "\n")
        _linea(f"ZIP con las {len(filas)} notas REGENERADAS: {salida}")
        _linea("(solo las notas: ningún PDF, para poder abrirlo al instante)")
    return 0


# ── Modo `informes` (R3, informes fuera del periodo) ─────────────────────────

def _informes_publicados_por_obra(enr: dict, descargas: Path) -> dict[str, int]:
    """Inventario de informes de control por obra, reconstruido de lo que hay en
    disco: la unión de los informes materializados en TODAS las experiencias de
    esa obra. Los jobs corridos antes de la issue #81 no guardaron el inventario
    en el manifiesto; este recuento lo repone para poder mirarlo a mano."""
    vistos: dict[str, set[str]] = {}
    for np_, ne, bloque in _claves_ordenadas(enr):
        obra = bloque.get("obra") if isinstance(bloque.get("obra"), dict) else {}
        obra_id = (obra or {}).get("obra_id")
        if not obra_id:
            continue
        carpeta = descargas / f"P{np_}_E{ne}" / "Informes de control"
        if carpeta.is_dir():
            vistos.setdefault(str(obra_id), set()).update(
                p.name for p in carpeta.iterdir() if p.is_file())
    return {obra: len(nombres) for obra, nombres in vistos.items()}


def modo_informes(a) -> int:
    from entregables.zip_infoobras import _estado_seccion_legible

    espejo, enr, carpeta = _cargar_job(a.job)
    if enr is None:
        _linea(f"No hay enriquecimiento.json en {carpeta}")
        return 2
    descargas = carpeta / "descargas"
    publicados = _informes_publicados_por_obra(enr, descargas)
    afectadas = []
    for np_, ne, bloque in _claves_ordenadas(enr):
        manifiesto = (bloque.get("descargas_reales")
                      if isinstance(bloque.get("descargas_reales"), dict) else {})
        seccion = (manifiesto.get("secciones") or {}).get("Informes de control")
        if not isinstance(seccion, dict) or seccion.get("estado") != "sin_documentos":
            continue
        obra = bloque.get("obra") if isinstance(bloque.get("obra"), dict) else {}
        n = publicados.get(str((obra or {}).get("obra_id")), 0)
        if not n:
            continue
        antes = _estado_seccion_legible(seccion, "Informes de control")
        ahora = _estado_seccion_legible({**seccion, "publicados": n},
                                        "Informes de control")
        afectadas.append((np_, ne, (obra or {}).get("obra_id"), n, antes, ahora))

    _linea(f"Job {a.job} · experiencias donde la obra publica informes de control "
           f"pero NINGUNO cae en el periodo del certificado: {len(afectadas)}")
    _linea()
    for np_, ne, obra_id, n, antes, ahora in afectadas:
        _linea(f"■ P{np_}/E{ne} · obra {obra_id} · {n} informe(s) publicado(s) "
               f"por la obra, 0 en el periodo")
        _linea(f"  ANTES : SECCIÓN Informes de control: {antes}")
        _linea(f"  AHORA : SECCIÓN Informes de control: {ahora}")
        _linea()
    if not afectadas:
        _linea("Ninguna: en este job no se da el caso (o el job no tiene "
               "descargas en disco).")
        return 0

    if a.zip:
        return _zip_de_muestra(a, espejo, enr, descargas, publicados, afectadas)
    _linea("Con --zip P1_E1,P1_E2 se regenera el ZIP de esas experiencias (en "
           "otra ruta) para leer el índice completo.")
    return 0


def _zip_de_muestra(a, espejo, enr, descargas, publicados, afectadas) -> int:
    """ZIP acotado a unas pocas experiencias, con el manifiesto ya repuesto, para
    leer el índice REAL (mismo generador que el entregable) sin empaquetar el
    job entero."""
    from entregables import construir_zip_infoobras

    pedidas = set()
    for parte in str(a.zip).split(","):
        parte = parte.strip().upper().removeprefix("P")
        if "_E" in parte:
            np_, ne = parte.split("_E")
            pedidas.add((int(np_), int(ne)))
    if not pedidas:
        _linea("--zip espera algo como P1_E1,P1_E2")
        return 2

    enr_muestra: dict = {}
    for np_, ne, bloque in _claves_ordenadas(enr):
        if (np_, ne) not in pedidas:
            continue
        copia = json.loads(json.dumps(bloque))
        manifiesto = copia.get("descargas_reales")
        obra = copia.get("obra") if isinstance(copia.get("obra"), dict) else {}
        n = publicados.get(str((obra or {}).get("obra_id")), 0)
        if isinstance(manifiesto, dict) and n:
            seccion = (manifiesto.get("secciones") or {}).get("Informes de control")
            if isinstance(seccion, dict) and seccion.get("estado") == "sin_documentos":
                seccion["publicados"] = n
        enr_muestra[f"{np_}:{ne}"] = copia

    profesionales = []
    for prof in espejo.get("profesionales") or []:
        exps = [e for e in (prof.get("experiencias") or [])
                if (prof.get("n_prof"), e.get("n")) in pedidas]
        if exps:
            profesionales.append({**prof, "experiencias": exps})
    espejo_muestra = {**espejo, "profesionales": profesionales}
    mapa = {clave: descargas / f"P{clave[0]}_E{clave[1]}" for clave in pedidas
            if (descargas / f"P{clave[0]}_E{clave[1]}").is_dir()}

    salida = Path(a.salida or (Path.home() / "Downloads" /
                               f"indice_{a.job}_muestra.zip"))
    construir_zip_infoobras(espejo_muestra, mapa, salida,
                            enriquecimiento=enr_muestra)
    with zipfile.ZipFile(salida) as zf:
        indice = zf.read("indice.txt").decode("utf-8")
    _linea(f"ZIP de muestra: {salida}")
    _linea("── indice.txt ──────────────────────────────────────────────")
    _linea(indice)
    return 0


# ── Modo `reintento` (R1) ────────────────────────────────────────────────────

def modo_reintento(a) -> int:
    from orquestador.descargas_infoobras import (
        CacheDescargasInfoObras, secciones_en_error,
    )

    raiz = Path(tempfile.mkdtemp(prefix="pivote-r1-"))
    try:
        cache = CacheDescargasInfoObras(raiz / "cache_obras")
        pedidos: list = []

        def primera(destino: Path, pendientes=None) -> dict:
            pedidos.append(pendientes)
            (destino / "Valorizaciones" / "2020-01 ENERO").mkdir(parents=True)
            (destino / "Valorizaciones" / "2020-01 ENERO" / "val.pdf").write_bytes(
                b"%PDF valorizacion")
            (destino / "Datos de cierre").mkdir()
            (destino / "Datos de cierre" / "acta.pdf").write_bytes(b"%PDF acta")
            return {
                "secciones": {
                    "InfoObras": {"esperados": 1, "descargados": 1},
                    "Datos de cierre": {"esperados": 1, "descargados": 1},
                    "Informes de control": {"error": True},
                },
                "avisos": ["Informes de control: la consulta no pudo completarse."],
                "informes_anios": [],
            }

        def reintento(destino: Path, pendientes=None) -> dict:
            pedidos.append(pendientes)
            carpeta = destino / "Informes de control"
            carpeta.mkdir(parents=True, exist_ok=True)
            (carpeta / "2020 - I-01.pdf").write_bytes(b"%PDF informe")
            return {
                "secciones": {"Informes de control": {"esperados": 1, "descargados": 1}},
                "informes_anios": [2020],
            }

        _linea("PASADA 1 — el portal se cae en «Informes de control»")
        uno = cache.obtener(74266, descargar=primera)
        entrada = raiz / "cache_obras" / "74266"
        _linea(f"  secciones caídas      : {', '.join(secciones_en_error(uno.estado))}")
        _linea(f"  marca publicada       : "
               f"{'.completa' if (entrada / '.completa').exists() else '.parcial'}")
        _linea(f"  corpus sano en disco  : "
               f"{sorted(p.name for p in entrada.iterdir() if p.is_dir())}")
        _linea("  → el error NO se congela: la entrada queda reintentable.")
        _linea()

        _linea("PASADA 2 — el portal responde")
        dos = cache.obtener(74266, descargar=reintento)
        _linea(f"  se pidió a la fuente   : "
               f"{sorted(pedidos[1]) if pedidos[1] else 'todo'}")
        _linea(f"  secciones caídas       : "
               f"{', '.join(secciones_en_error(dos.estado)) or '(ninguna)'}")
        _linea(f"  marca publicada        : "
               f"{'.completa' if (entrada / '.completa').exists() else '.parcial'}")
        _linea(f"  valorización de la 1ª pasada intacta: "
               f"{(entrada / 'Valorizaciones/2020-01 ENERO/val.pdf').is_file()}")
        _linea(f"  informe descargado ahora           : "
               f"{(entrada / 'Informes de control/2020 - I-01.pdf').is_file()}")
        _linea(f"  estado fusionado                   : "
               f"{json.dumps(dos.estado['secciones'], ensure_ascii=False)}")
        _linea()

        _linea("PASADA 3 — caché ya completa: no se vuelve a la fuente")
        tres = cache.obtener(
            74266,
            descargar=lambda _d, _p=None: (_ for _ in ()).throw(
                AssertionError("no debería consultarse")))
        _linea(f"  cache_hit: {tres.cache_hit}   ·   consultas totales a la "
               f"fuente: {len(pedidos)} (1 completa + 1 selectiva)")
        return 0
    finally:
        shutil.rmtree(raiz, ignore_errors=True)


# ── Modo `part` (R4) ─────────────────────────────────────────────────────────

def modo_part(a) -> int:
    from orquestador.descargas_infoobras import CacheDescargasInfoObras

    raiz = Path(tempfile.mkdtemp(prefix="pivote-r4-"))
    try:
        cache = CacheDescargasInfoObras(raiz / "cache_obras")
        cache.obtener(74266, descargar=lambda destino, _p=None: (
            (destino / "Valorizaciones").mkdir(parents=True),
            (destino / "Valorizaciones" / "val.pdf").write_bytes(b"%PDF"),
            {"secciones": {"InfoObras": {"esperados": 1, "descargados": 1}}})[-1])
        huerfano = raiz / "cache_obras" / f".74266.{'0a1b2c3d' * 4}.part"
        (huerfano / "Valorizaciones").mkdir(parents=True)
        (huerfano / "Valorizaciones" / "a medias.pdf").write_bytes(b"%PDF a medias")
        _linea(f"Carpeta huérfana plantada: {huerfano.name}")
        _linea(f"  contenido: {[p.name for p in huerfano.rglob('*') if p.is_file()]}")
        recolectadas = cache.recolectar_temporales()
        _linea(f"Recolectadas en la corrida siguiente: {recolectadas}")
        _linea(f"  ¿sigue existiendo?      : {huerfano.exists()}")
        _linea(f"  caché válida intacta    : "
               f"{(raiz / 'cache_obras/74266/.completa').is_file()} "
               f"(+ {(raiz / 'cache_obras/74266/Valorizaciones/val.pdf').is_file()} "
               f"su documento)")
        _linea(f"Segunda pasada (nada que recoger): "
               f"{cache.recolectar_temporales()}")
        return 0
    finally:
        shutil.rmtree(raiz, ignore_errors=True)


# ── Entrada ──────────────────────────────────────────────────────────────────

def main(argv=None) -> int:
    _consola_utf8()
    p = argparse.ArgumentParser(
        description="Comprobar a mano la resiliencia de la caché de descargas.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__)
    sub = p.add_subparsers(dest="modo", required=True)

    n = sub.add_parser("notas", help="textos de las notas SEACE de un job")
    n.add_argument("job", help="id del job en datos_pivote (ej. 7e9306a321ac)")
    n.add_argument("--salida", metavar="RUTA.zip",
                   help="además, escribir un ZIP con las notas regeneradas")
    n.set_defaults(func=modo_notas)

    i = sub.add_parser("informes",
                       help="informes de control publicados pero fuera del periodo")
    i.add_argument("job", help="id del job en datos_pivote (ej. 7e9306a321ac)")
    i.add_argument("--zip", metavar="P1_E1,P1_E2",
                   help="regenerar el ZIP de esas experiencias para leer el índice")
    i.add_argument("--salida", metavar="RUTA.zip",
                   help="ruta del ZIP de muestra (por defecto, Downloads)")
    i.set_defaults(func=modo_informes)

    r = sub.add_parser("reintento",
                       help="simulación offline del reintento selectivo")
    r.set_defaults(func=modo_reintento)

    t = sub.add_parser("part", help="carpeta .part huérfana plantada y recolectada")
    t.set_defaults(func=modo_part)

    a = p.parse_args(argv)
    try:
        return a.func(a)
    except KeyboardInterrupt:
        _linea("\nInterrumpido.")
        return 130
    except Exception as e:  # noqa: BLE001 — nunca un traceback en la cara
        _linea(f"\nNo se pudo completar la comprobación: {type(e).__name__}: {e}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
