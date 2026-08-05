"""
Comprobar A MANO el candado de identidad CUI↔proceso SEACE (T-004 F5).

No es un test automatizado: es la herramienta para que una persona vea, en
lenguaje de evaluador, POR QUÉ el sistema dio (o no dio) por verificados los
documentos de un proceso. Cada señal se imprime con sus dos lados y su
resultado, para poder discutirla.

Tres modos:

  caso    Un certificado inventado o real contra un CUI. Consulta los procesos
          del CUI y evalúa el candado contra el proceso que el selector elige.

  replay  Un job ya corrido de `datos_pivote/`: recorre sus experiencias y
          resume en qué estado del candado queda cada una.

  cruces  (T-011) Sobre un job ya corrido: aplica las DOS reglas de fechas
          —inicio vs firma del contrato, término vs aprobación del expediente—
          y resume cuántas cuadran, cuántas no y cuántas se abstienen y por qué.
          Con `--excel RUTA` regenera además el entregable para ver la hoja
          «Cronología de expedientes» (sin tocar el original).

La red solo se toca con `--vivo`. Sin esa bandera todo sale de la caché local
(`datos_pivote/referencia/seace_procesos/`), así que la comprobación es
repetible y funciona sin internet una vez descargados los procesos.

Ejemplos:

    venv/Scripts/python backend/scripts/probar_candado_seace.py caso \\
        --cui 2337618 --vivo \\
        --entidad "GOBIERNO REGIONAL DE JUNIN" \\
        --ruc-emisor 20263373058 --emisor "INSTITUTO DE CONSULTORIA S.A." \\
        --inicio 2021-10-01 --fin 2023-10-11

    venv/Scripts/python backend/scripts/probar_candado_seace.py replay 7e9306a321ac

    venv/Scripts/python backend/scripts/probar_candado_seace.py cruces 7e9306a321ac
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from validacion.candado_seace import (  # noqa: E402
    CONFIRMADO, CONTRADICE, POR_CONFIRMAR, evaluar_candado, resumen_proceso,
    rotulo,
)

SIMBOLO = {"a_favor": "[+]", "en_contra": "[-]", "sin_dato": "[ ]"}
TITULO_SENAL = {
    "entidad": "Entidad que contrató",
    "adjudicatario": "Empresa que emitió el certificado",
    "objeto": "Objeto del proceso",
    "temporal": "Fechas",
    "monto": "Monto (señal de apoyo)",
}


# ── Caché de procesos por CUI ────────────────────────────────────────────────

def _dir_cache() -> Path:
    from config import data_dir
    return data_dir() / "referencia" / "seace_procesos"


def procesos_de(cui: str, vivo: bool) -> tuple[list | None, str]:
    """(procesos, procedencia). `None` = no se pudo saber (no es lo mismo que
    «el CUI no tiene procesos», que es una lista vacía)."""
    cache = _dir_cache() / f"{str(cui).strip()}.json"
    if not vivo:
        if not cache.exists():
            return None, (
                f"no hay copia local de los procesos del CUI {cui}.\n"
                f"    Ejecuta una vez el mismo comando agregando  --vivo  "
                f"y queda guardado para las siguientes corridas.")
        try:
            return json.loads(cache.read_text(encoding="utf-8")), "copia local"
        except (OSError, ValueError):
            return None, f"la copia local del CUI {cui} está ilegible; usa --vivo"
    from scraping.seace_abierto import procesos_por_cui
    try:
        procesos = procesos_por_cui(cui)
    except Exception as e:  # noqa: BLE001 — el CLI nunca muestra un traceback
        return None, f"la fuente de datos abiertos falló ({type(e).__name__})"
    if procesos is None:
        return None, "la fuente de datos abiertos no respondió; reintentar"
    cache.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache.with_suffix(".json.part")
    tmp.write_text(json.dumps(procesos, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, cache)
    return procesos, "consulta en vivo (guardada en la copia local)"


# ── Impresión ────────────────────────────────────────────────────────────────

def _linea(texto: str = "") -> None:
    print(texto)


def _consola_utf8() -> None:
    """La consola de Windows llega en cp1252 y revienta con «→» o «·».
    Se fuerza UTF-8 con reemplazo: un acento mal pintado es un detalle, un
    traceback en la cara del usuario no."""
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            pass


def imprimir_candado(candado, sangria: str = "  ") -> None:
    veredicto = {CONFIRMADO: "VERIFICADO", POR_CONFIRMAR: "POR CONFIRMAR",
                 CONTRADICE: "NO COINCIDE"}.get(candado.resultado, candado.resultado)
    _linea(f"{sangria}VEREDICTO: {veredicto}")
    _linea(f"{sangria}{rotulo(candado.resultado)}")
    _linea(f"{sangria}{candado.motivo}")
    _linea()
    _linea(f"{sangria}Señales evaluadas:")
    for s in candado.senales:
        titulo = TITULO_SENAL.get(s.nombre, s.nombre)
        _linea(f"{sangria}  {SIMBOLO.get(s.sentido, '[?]')} {titulo}")
        for trozo in _envolver(s.detalle, 88):
            _linea(f"{sangria}      {trozo}")
    _linea()
    _linea(f"{sangria}A favor: {len(candado.a_favor)} señal(es) fuerte(s) · "
           f"En contra: {len(candado.en_contra)}")


def _envolver(texto: str, ancho: int) -> list[str]:
    palabras, lineas, actual = str(texto or "").split(), [], ""
    for p in palabras:
        if len(actual) + len(p) + 1 > ancho and actual:
            lineas.append(actual)
            actual = p
        else:
            actual = f"{actual} {p}".strip()
    if actual:
        lineas.append(actual)
    return lineas or [""]


# ── Modo `caso` ──────────────────────────────────────────────────────────────

def modo_caso(a) -> int:
    from scraping.seace_abierto import clasificar_proceso, seleccionar_proceso

    _linea("=" * 92)
    _linea(f"CANDADO SEACE · CUI {a.cui} · se busca un proceso de {a.tipo}")
    _linea("=" * 92)
    _linea("Datos del certificado que se está evaluando:")
    _linea(f"  Entidad contratante : {a.entidad or '(no declarada en el certificado)'}")
    _linea(f"  Emisor              : {a.emisor or '(no declarado)'}"
           f"{f'  ·  RUC {a.ruc_emisor}' if a.ruc_emisor else ''}")
    _linea(f"  Periodo declarado   : {a.inicio or '?'} a {a.fin or '?'}")
    if a.monto:
        _linea(f"  Monto declarado     : S/ {float(a.monto):,.2f}")
    _linea()

    procesos, procedencia = procesos_de(a.cui, a.vivo)
    if procesos is None:
        _linea(f"No se pudo evaluar: {procedencia}")
        return 2
    _linea(f"Procesos publicados para el CUI ({procedencia}): {len(procesos)}")
    for p in procesos:
        t, _saldo = clasificar_proceso(p)
        titulo = ((p.get("tender") or {}).get("title") or p.get("ocid") or "")
        _linea(f"    - {titulo[:62]:<62} → {t}")
    _linea()

    periodo = None
    ini, fin = _fecha(a.inicio), _fecha(a.fin)
    if ini and fin:
        periodo = (ini, fin)
    seleccion = seleccionar_proceso(procesos, a.tipo, periodo=periodo)
    elegido = seleccion.get("elegido")
    if elegido is None:
        _linea("NO HAY PROCESO QUE VERIFICAR")
        _linea(f"  {seleccion.get('motivo')}")
        _linea("  El Excel dirá «No se encontró un proceso del tipo correspondiente "
               "a la experiencia»")
        _linea("  y no se promoverá ningún documento. No es un error del sistema: es "
               "lo que publica la fuente.")
        return 0

    resumen = resumen_proceso(elegido)
    resumen["tipo"] = clasificar_proceso(elegido)[0]
    _linea(f"Proceso elegido: {resumen.get('nomenclatura') or elegido.get('ocid')}")
    _linea(f"  Motivo de la elección : {seleccion.get('motivo')}")
    _linea(f"  Entidad convocante    : {resumen.get('entidad_convocante') or '—'}")
    _linea(f"  Adjudicatario (RUC)   : "
           f"{', '.join(resumen.get('rucs_adjudicatarios') or []) or '—'}")
    _linea(f"  Firma del contrato    : {resumen.get('fecha_firma') or '—'}")
    _linea(f"  Vigencia              : {resumen.get('vigencia_inicio') or '—'} a "
           f"{resumen.get('vigencia_fin') or '—'}")
    if resumen.get("monto"):
        _linea(f"  Monto del proceso     : S/ {resumen['monto']:,.2f}")
    _linea()
    _linea("-" * 92)
    candado = evaluar_candado(resumen, {
        "entidad_contratante": a.entidad,
        "entidad_emisora": a.emisor,
        "ruc_emisor": a.ruc_emisor,
        "tipo_experiencia": a.tipo,
        "fecha_inicial": a.inicio,
        "fecha_final": a.fin,
        "monto_contrato_soles": a.monto,
    })
    imprimir_candado(candado)
    _linea("-" * 92)
    _linea("Recordatorio: el candado NO bloquea la descarga. Los documentos del "
           "proceso van igual")
    _linea("al ZIP como sustento; lo que cambia es el rótulo de confianza del Excel "
           "y del índice.")
    return 0


def _fecha(v):
    from datetime import datetime
    try:
        return datetime.strptime(str(v or "")[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


# ── Modo `replay` ────────────────────────────────────────────────────────────

def modo_replay(a) -> int:
    from config import data_dir
    from scraping.seace_abierto import clasificar_proceso

    carpeta = data_dir() / a.job
    espejo_f, enr_f = carpeta / "espejo.json", carpeta / "enriquecimiento.json"
    if not enr_f.exists():
        _linea(f"No existe el job {a.job} en {data_dir()} "
               f"(falta enriquecimiento.json).")
        return 2
    enr = json.loads(enr_f.read_text(encoding="utf-8"))
    espejo = (json.loads(espejo_f.read_text(encoding="utf-8"))
              if espejo_f.exists() else {})

    # Certificado por experiencia, desde el espejo (el enriquecimiento no lo trae).
    certs: dict[str, dict] = {}
    for i, prof in enumerate(espejo.get("profesionales") or [], start=1):
        n_prof = prof.get("n_prof") or i
        for e in prof.get("experiencias") or []:
            certs[f"{n_prof}:{e.get('n')}"] = e

    _linea("=" * 92)
    _linea(f"REPLAY DEL CANDADO SEACE · job {a.job}")
    _linea(f"Concurso: {(espejo.get('_meta') or {}).get('concurso') or '—'}")
    _linea("=" * 92)

    conteo = {CONFIRMADO: 0, POR_CONFIRMAR: 0, CONTRADICE: 0}
    sin_proceso: dict[str, int] = {}
    sin_cache: set[str] = set()
    detalle: list[tuple[str, str, str]] = []
    cache_procesos: dict[str, list | None] = {}

    for clave in sorted(enr, key=_orden_clave):
        if ":" not in str(clave):
            continue
        seace = (enr[clave] or {}).get("seace")
        if not isinstance(seace, dict):
            continue
        estado = seace.get("estado")
        if estado != "seleccionado":
            sin_proceso[estado] = sin_proceso.get(estado, 0) + 1
            continue
        cui = str(seace.get("cui") or "")
        if cui not in cache_procesos:
            cache_procesos[cui] = procesos_de(cui, a.vivo)[0]
        procesos = cache_procesos[cui]
        if procesos is None:
            sin_cache.add(cui)
            continue
        elegido = next((p for p in procesos if p.get("ocid") == seace.get("ocid")), None)
        if elegido is None:
            sin_cache.add(cui)
            continue
        resumen = resumen_proceso(elegido)
        resumen["tipo"] = clasificar_proceso(elegido)[0]
        cert = certs.get(clave) or {}
        candado = evaluar_candado(resumen, {
            "entidad_contratante": cert.get("entidad_contratante"),
            "entidad_emisora": cert.get("entidad_emisora"),
            "ruc_emisor": cert.get("ruc_emisor"),
            "tipo_experiencia": seace.get("proceso_objeto"),
            "fecha_inicial": cert.get("fecha_inicial"),
            "fecha_final": cert.get("fecha_final"),
            "monto_contrato_soles": cert.get("monto_contrato_soles"),
        })
        conteo[candado.resultado] = conteo.get(candado.resultado, 0) + 1
        detalle.append((clave, candado.resultado,
                        ", ".join(s.nombre for s in candado.a_favor) or "ninguna"))

    total_con_proceso = sum(conteo.values())
    _linea(f"Experiencias con proceso SEACE elegido: {total_con_proceso}")
    _linea(f"  VERIFICADO    (confirmado)   : {conteo[CONFIRMADO]}")
    _linea(f"  POR CONFIRMAR (insuficiente) : {conteo[POR_CONFIRMAR]}")
    _linea(f"  NO COINCIDE   (contradice)   : {conteo[CONTRADICE]}")
    _linea()
    if sin_proceso:
        _linea("Experiencias SIN proceso que verificar (no llegan al candado):")
        textos = {
            "sin_tipo": "el CUI no publica un proceso del tipo de la experiencia",
            "sin_procesos": "el CUI no figura en datos abiertos (cobertura 2018+)",
            "fuente_no_disponible": "la fuente no respondió en esa corrida",
        }
        for estado, n in sorted(sin_proceso.items(), key=lambda x: -x[1]):
            _linea(f"  {n:>3}  {textos.get(estado, estado)}")
        _linea()
    if sin_cache:
        _linea(f"Sin copia local de procesos para {len(sin_cache)} CUI "
               f"({', '.join(sorted(sin_cache))}).")
        _linea("  Corre una vez con --vivo para descargarlos.")
        _linea()
    if a.detalle and detalle:
        _linea("Detalle por experiencia (profesional:experiencia):")
        for clave, res, favor in detalle:
            _linea(f"  {clave:>7}  {res:<14} señales a favor: {favor}")
    return 0


def _orden_clave(k):
    try:
        a, b = str(k).split(":")
        return (0, int(a), int(b))
    except (ValueError, TypeError):
        return (1, 0, 0)


# ── Modo `cruces` (T-011) ────────────────────────────────────────────────────

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


def _certificados_por_clave(espejo: dict) -> dict:
    certs: dict[str, dict] = {}
    for i, prof in enumerate(espejo.get("profesionales") or [], start=1):
        n_prof = prof.get("n_prof") or i
        for e in prof.get("experiencias") or []:
            certs[f"{n_prof}:{e.get('n')}"] = e
    return certs


def _completar_candado(enr: dict, certs: dict, vivo: bool) -> tuple[int, set]:
    """Rellena `seace.proceso` y `seace.candado` de un job corrido ANTES de F5,
    usando la copia local de los procesos del CUI. No escribe nada en disco: el
    job queda intacto y el replay es repetible. Devuelve (completados, CUIs sin
    copia local)."""
    from scraping.seace_abierto import clasificar_proceso
    cache: dict[str, list | None] = {}
    completados, sin_cache = 0, set()
    for clave, bloque in enr.items():
        if ":" not in str(clave) or not isinstance(bloque, dict):
            continue
        seace = bloque.get("seace")
        if not isinstance(seace, dict) or seace.get("estado") != "seleccionado":
            continue
        if seace.get("candado"):
            continue
        cui = str(seace.get("cui") or "")
        if cui not in cache:
            cache[cui] = procesos_de(cui, vivo)[0]
        procesos = cache[cui] or []
        elegido = next((p for p in procesos if p.get("ocid") == seace.get("ocid")), None)
        if elegido is None:
            sin_cache.add(cui)
            continue
        resumen = resumen_proceso(elegido)
        resumen["tipo"] = clasificar_proceso(elegido)[0]
        cert = certs.get(clave) or {}
        seace["proceso"] = resumen
        seace["fecha_suscripcion"] = resumen.get("fecha_firma")
        seace["vigencia"] = [resumen.get("vigencia_inicio"),
                             resumen.get("vigencia_fin")]
        seace["candado"] = evaluar_candado(resumen, {
            "entidad_contratante": cert.get("entidad_contratante"),
            "entidad_emisora": cert.get("entidad_emisora"),
            "ruc_emisor": cert.get("ruc_emisor"),
            "tipo_experiencia": seace.get("proceso_objeto"),
            "fecha_inicial": cert.get("fecha_inicial"),
            "fecha_final": cert.get("fecha_final"),
            "monto_contrato_soles": cert.get("monto_contrato_soles"),
        }).como_dict()
        completados += 1
    return completados, sin_cache


def modo_cruces(a) -> int:
    """Replay OFFLINE de las dos reglas de fechas sobre un job ya corrido."""
    from reglas.cruces_fechas import (
        COINCIDE, DISPARA, POR_CONFIRMAR, PREGUNTA_REGLA, REGLA_INICIO,
        REGLA_TERMINO, TOLERANCIA_DIAS_APROBACION, TOLERANCIA_DIAS_INICIO,
        cruces_de_experiencia,
    )

    espejo, enr, carpeta = _cargar_job(a.job)
    if enr is None:
        _linea(f"No existe el job {a.job} en {carpeta.parent} "
               f"(falta enriquecimiento.json).")
        return 2
    certs = _certificados_por_clave(espejo)

    _linea("=" * 92)
    _linea(f"CRUCES DE FECHAS CONTRATO / EXPEDIENTE vs CERTIFICADO · job {a.job}")
    _linea(f"Concurso: {(espejo.get('_meta') or {}).get('concurso') or '—'}")
    _linea("=" * 92)
    _linea("Dos preguntas por experiencia:")
    _linea(f"  A. {PREGUNTA_REGLA[REGLA_INICIO]}")
    _linea(f"     (se admite un desfase de hasta {TOLERANCIA_DIAS_INICIO} días "
           f"por la entrega de terreno u orden de inicio)")
    _linea(f"  B. {PREGUNTA_REGLA[REGLA_TERMINO]}  — solo expedientes técnicos")
    _linea(f"     (se admiten hasta {TOLERANCIA_DIAS_APROBACION} días por el "
           f"cierre administrativo)")
    _linea()

    completados, sin_cache = _completar_candado(enr, certs, a.vivo)
    if completados:
        _linea(f"El job es anterior al candado de identidad: se reconstruyó la "
               f"identidad de {completados} proceso(s)")
        _linea("desde la copia local de los datos abiertos. El job en disco NO "
               "se modifica.")
        _linea()
    if sin_cache:
        _linea(f"Sin copia local de procesos para {len(sin_cache)} CUI "
               f"({', '.join(sorted(sin_cache))}).")
        _linea("  Corre una vez con --vivo para descargarlos.")
        _linea()

    conteo = {REGLA_INICIO: {DISPARA: 0, COINCIDE: 0, POR_CONFIRMAR: 0},
              REGLA_TERMINO: {DISPARA: 0, COINCIDE: 0, POR_CONFIRMAR: 0}}
    razones: dict[str, dict[str, int]] = {REGLA_INICIO: {}, REGLA_TERMINO: {}}
    detalle: list[tuple] = []
    total_exp = 0

    for clave in sorted(certs, key=_orden_clave):
        total_exp += 1
        cruces = cruces_de_experiencia(enr.get(clave) or {}, certs[clave])
        for c in cruces:
            conteo[c.regla][c.resultado] = conteo[c.regla].get(c.resultado, 0) + 1
            if c.resultado == POR_CONFIRMAR:
                r = _razon_corta(c.motivo)
                razones[c.regla][r] = razones[c.regla].get(r, 0) + 1
            if c.resultado == DISPARA or a.detalle:
                detalle.append((clave, c))

    _linea(f"Experiencias del análisis: {total_exp}")
    _linea()
    for regla, titulo in ((REGLA_INICIO, "A · inicio declarado vs firma del contrato"),
                          (REGLA_TERMINO, "B · término declarado vs aprobación del expediente")):
        c = conteo[regla]
        evaluadas = sum(c.values())
        _linea(f"REGLA {titulo}")
        _linea(f"  Se pronunció sobre        : {evaluadas} experiencia(s)")
        _linea(f"  CUADRA (la fecha calza)   : {c[COINCIDE]}")
        _linea(f"  NO CUADRA (a revisar)     : {c[DISPARA]}")
        _linea(f"  POR VERIFICAR (se abstuvo): {c[POR_CONFIRMAR]}")
        for razon, n in sorted(razones[regla].items(), key=lambda x: -x[1]):
            for i, trozo in enumerate(_envolver(razon, 78)):
                _linea(f"      {f'{n:>3}  ' if i == 0 else '     '}{trozo}")
        _linea()

    if detalle:
        _linea("-" * 92)
        _linea("Detalle (profesional:experiencia):")
        for clave, c in detalle:
            marca = {DISPARA: "[!]", COINCIDE: "[+]", POR_CONFIRMAR: "[ ]"}
            _linea(f"  {marca.get(c.resultado, '[?]')} {clave:>7}  "
                   f"{'A' if c.regla == REGLA_INICIO else 'B'}  "
                   f"declarado {c.fecha_declarada or '—'} · documento "
                   f"{c.fecha_fuente or '—'}")
            for trozo in _envolver(c.motivo, 84):
                _linea(f"          {trozo}")
        _linea()

    _linea("Recordatorio: una abstención NO es un incumplimiento. Cuando la "
           "fuente no existe o no")
    _linea("se pudo confirmar que corresponda a este certificado, la celda dice "
           "POR VERIFICAR.")

    if a.excel:
        return _regenerar_con_cronologia(espejo, enr, carpeta, a.excel)
    return 0


def modo_cruce_caso(a) -> int:
    """Un caso INVENTADO, sin red y sin job: las dos reglas de fechas sobre datos
    que la persona escribe en la línea de comandos. Sirve para ver el mecanismo
    completo —incluida la regla del expediente, que un job puede no ejercitar—
    y para discutir los umbrales con números en la mano."""
    from reglas.cruces_fechas import (
        PREGUNTA_REGLA, REGLA_INICIO, TITULO_REGLA,
        evaluar_inicio_vs_contrato, evaluar_termino_vs_aprobacion,
    )

    proceso = {
        "entidad_convocante": a.entidad_proceso or a.entidad,
        "rucs_adjudicatarios": [a.ruc_adjudicatario or a.ruc_emisor or ""],
        "fecha_firma": a.firma,
        "vigencia_inicio": a.firma,
        "vigencia_fin": a.fin,
        "nomenclatura": "PROCESO DE PRUEBA",
        "tipo": a.tipo,
    }
    certificado = {
        "entidad_contratante": a.entidad,
        "entidad_emisora": a.emisor,
        "ruc_emisor": a.ruc_emisor,
        "tipo_experiencia": a.tipo,
        "fecha_inicial": a.inicio,
        "fecha_final": a.fin,
        "monto_contrato_soles": None,
    }
    candado = evaluar_candado(proceso, certificado)
    enr = {"seace": {"estado": "seleccionado", "cui": "0000000",
                     "proceso_objeto": a.tipo, "proceso": proceso,
                     "fecha_suscripcion": a.firma,
                     "candado": candado.como_dict()}}
    if a.aprobacion_et:
        enr["aprobacion_expediente"] = {"fecha": a.aprobacion_et,
                                        "nombre": "Resolución de aprobación (prueba)"}
        enr["verificacion_expediente"] = {
            "verificado_en_mef": True,
            "contratista": {"valor": a.emisor or "(emisor)",
                            "veredicto": "no_verificable" if a.mef_no_coincide else "ok"},
            "resolucion": {"numero": "N° 000-PRUEBA", "veredicto": "ok"},
        }

    _linea("=" * 92)
    _linea("CRUCES DE FECHAS · caso de prueba (sin red, sin job)")
    _linea("=" * 92)
    _linea(f"  Periodo declarado en el certificado : {a.inicio} a {a.fin}")
    _linea(f"  Firma del contrato del proceso      : {a.firma or '—'}")
    _linea(f"  Aprobación del expediente           : {a.aprobacion_et or '—'}")
    _linea()
    _linea(f"Identidad del proceso (candado F5): {candado.resultado.upper()} — "
           f"{len(candado.a_favor)} señal(es) a favor, {len(candado.en_contra)} en contra.")
    _linea()

    cruces = [evaluar_inicio_vs_contrato(enr["seace"], certificado),
              evaluar_termino_vs_aprobacion(enr, certificado)]
    for c in cruces:
        if c is None:
            _linea("REGLA B · no aplica: la experiencia no es de expediente técnico "
                   "(usa --aprobacion-et para ejercitarla).")
            _linea()
            continue
        letra = "A" if c.regla == REGLA_INICIO else "B"
        _linea(f"REGLA {letra} · {TITULO_REGLA[c.regla]}")
        _linea(f"  {PREGUNTA_REGLA[c.regla]}  →  {c.respuesta}")
        if c.dias is not None:
            _linea(f"  Diferencia día-exacta: {c.dias} día(s)")
        for trozo in _envolver(c.motivo, 88):
            _linea(f"      {trozo}")
        _linea()
    _linea("Recordatorio: POR VERIFICAR nunca es un incumplimiento — es el "
           "sistema absteniéndose.")
    return 0


def _razon_corta(motivo: str) -> str:
    """Primera oración del motivo — agrupa las abstenciones por causa real."""
    t = str(motivo or "").strip()
    corte = t.find(": ")
    if 0 < corte < 160:
        t = t[corte + 2:]
    punto = t.find(". ")
    if punto > 0:
        t = t[:punto]
    return t[:200].rstrip(" .") + "."


def _regenerar_con_cronologia(espejo: dict, enr: dict, carpeta, salida) -> int:
    """Regenera el Excel del job en OTRA ruta, con la hoja «Cronología de
    expedientes». No sobrescribe el entregable original."""
    from pathlib import Path

    from entregables import mapear_certificados, regenerar_excel_final
    from entregables.excel_final import HOJA_CRONOLOGIA

    salida = Path(salida).resolve()
    certs = mapear_certificados(carpeta.parent, carpeta.name)
    _linea()
    _linea("-" * 92)
    _linea(f"Regenerando el Excel en {salida} …")
    regenerar_excel_final(espejo, enr, salida, certificados=certs)
    import openpyxl
    wb = openpyxl.load_workbook(salida, read_only=True)
    hojas = wb.sheetnames
    wb.close()
    _linea(f"  Hojas del libro: {len(hojas)}")
    _linea(f"  La hoja «{HOJA_CRONOLOGIA}» "
           f"{'SÍ está' if HOJA_CRONOLOGIA in hojas else 'NO está'} "
           f"(es la última: {hojas[-1]}).")
    return 0 if HOJA_CRONOLOGIA in hojas else 1


# ── Entrada ──────────────────────────────────────────────────────────────────

def main(argv=None) -> int:
    _consola_utf8()
    p = argparse.ArgumentParser(
        description="Comprobar a mano el candado de identidad CUI↔proceso SEACE.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__)
    sub = p.add_subparsers(dest="modo", required=True)

    c = sub.add_parser("caso", help="un certificado contra un CUI")
    c.add_argument("--cui", required=True)
    c.add_argument("--tipo", default="supervision",
                   choices=["supervision", "expediente", "ejecucion", "preinversion"],
                   help="tipo de proceso que corresponde a la experiencia")
    c.add_argument("--entidad", help="entidad contratante que declara el certificado")
    c.add_argument("--emisor", help="razón social que emite el certificado")
    c.add_argument("--ruc-emisor", dest="ruc_emisor")
    c.add_argument("--inicio", help="inicio del profesional (AAAA-MM-DD)")
    c.add_argument("--fin", help="término del profesional (AAAA-MM-DD)")
    c.add_argument("--monto", type=float, help="monto en soles que declara el certificado")
    c.add_argument("--vivo", action="store_true",
                   help="consultar los datos abiertos (por defecto usa la copia local)")
    c.set_defaults(func=modo_caso)

    r = sub.add_parser("replay", help="recorrer un job ya corrido")
    r.add_argument("job", help="id del job en datos_pivote (ej. 7e9306a321ac)")
    r.add_argument("--vivo", action="store_true")
    r.add_argument("--detalle", action="store_true",
                   help="listar el resultado de cada experiencia")
    r.set_defaults(func=modo_replay)

    x = sub.add_parser("cruces",
                       help="T-011 · cruces de fechas contrato/expediente ↔ "
                            "certificado sobre un job ya corrido")
    x.add_argument("job", help="id del job en datos_pivote (ej. 7e9306a321ac)")
    x.add_argument("--vivo", action="store_true",
                   help="consultar los datos abiertos si falta la copia local")
    x.add_argument("--detalle", action="store_true",
                   help="listar TODAS las experiencias, no solo las que no cuadran")
    x.add_argument("--excel", metavar="RUTA",
                   help="además, regenerar el Excel del job en esa ruta para ver "
                        "la hoja «Cronología de expedientes» (no toca el original)")
    x.set_defaults(func=modo_cruces)

    y = sub.add_parser("cruce-caso",
                       help="T-011 · las dos reglas de fechas sobre un caso "
                            "inventado (sin red y sin job)")
    y.add_argument("--inicio", required=True, help="inicio declarado (AAAA-MM-DD)")
    y.add_argument("--fin", required=True, help="término declarado (AAAA-MM-DD)")
    y.add_argument("--firma", help="firma del contrato del proceso (AAAA-MM-DD)")
    y.add_argument("--tipo", default="supervision",
                   choices=["supervision", "expediente", "ejecucion", "preinversion"])
    y.add_argument("--entidad", help="entidad contratante del certificado")
    y.add_argument("--entidad-proceso", dest="entidad_proceso",
                   help="entidad convocante del proceso (por defecto, la misma)")
    y.add_argument("--emisor", help="razón social que emite el certificado")
    y.add_argument("--ruc-emisor", dest="ruc_emisor")
    y.add_argument("--ruc-adjudicatario", dest="ruc_adjudicatario",
                   help="RUC del adjudicatario del proceso (por defecto, el del emisor)")
    y.add_argument("--aprobacion-et", dest="aprobacion_et",
                   help="fecha de la resolución que aprobó el expediente "
                        "(AAAA-MM-DD) — activa la regla B")
    y.add_argument("--mef-no-coincide", dest="mef_no_coincide", action="store_true",
                   help="simular que el MEF NO confirma al proyectista (la regla "
                        "B debe abstenerse)")
    y.set_defaults(func=modo_cruce_caso)

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
