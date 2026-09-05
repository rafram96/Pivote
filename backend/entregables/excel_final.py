"""
Excel FINAL enriquecido — el entregable del backend (formato definitivo
confirmado por el cliente 2026-06-10):

  1. Hoja **CLAUDE** — la extracción/evaluación (5 partes, igual al de la skill).
  2. Hoja **Base de Datos** — todas las experiencias consolidadas (25 columnas:
     postor/profesional, emisor, fechas, días/Paso 5, y los veredictos), con
     auto-filtro, color de fondo por profesional (convención de la skill
     `propuestas` de Manuel) y verde/rojo en las columnas de pregunta.
  3. **Una hoja por profesional** con el CUADRO DE HITOS de sus experiencias:
     periodo certificado → paralizaciones de la obra (InfoObras) → tramos
     efectivos → resumen brutos/paralizados/traslapes/EFECTIVOS (Paso 5,
     calculado con `reglas.calculo` — el mismo motor con goldens de las hojas
     manuales JEFE/Estructura).

Las paralizaciones llegan del enriquecimiento (etapa INFOOBRAS); si una
experiencia no las tiene, su cuadro muestra brutos = efectivos.
"""
from __future__ import annotations

import calendar
import hashlib
import io
import json
import logging
import re
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import openpyxl
from openpyxl.comments import Comment
from openpyxl.worksheet.pagebreak import Break
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

import entregables.cronologia as cronologia
from entregables.leyenda_gantt import COLORES_GANTT, MARCAS_GANTT, NOTAS_GANTT
from entregables.certeza import (
    BUCKET_CONFIRMADO, BUCKET_INFERIDO, BUCKET_PRIVADA, BUCKET_SIN_IDENTIFICAR,
    COLOR_INFERIDO, COLOR_PRIVADA, COLOR_SIN_IDENTIFICAR, COLOR_VERIFICADO,
    alertas_experiencia, bucket_certeza, clasificar_identificacion,
    es_provisional, fuente_mef, normalizar_motivo_fuente,
)
from reglas import (
    anios, dias_efectivos_profesional, dias_inclusivos, periodo_fechas,
    restar_paralizaciones,
)
from schemas.cargo import etiqueta_hoja
from scripts.generar_excel import (
    AL_HEAD, AL_WRAP, BORDER, F_BOLD, F_CELL, F_HEAD, F_PARTE, F_PROF,
    FILL_BACKEND, FILL_CLAUDE, FILL_HEAD, FILL_PARTE, FILL_PEND, FILL_PROF,
    FILL_SUPUESTO, FMT_DEC, FMT_FECHA, FMT_INT, _fill_veredicto, _sin_jerga,
    conciliar_conclusion, construir_hoja_evaluacion, fecha_excel,
)

logger = logging.getLogger(__name__)

Paralizaciones = dict[tuple[int, int], list[tuple[date, date]]]

# Paleta de fondos por profesional para la hoja Base de Datos (suaves, ciclan)
_PALETA_PROF = ["D7E9F7", "DCEFE8", "F8E1D5", "E1E8F5", "E8ECEF", "D5E9E7",
                "F1DDD3", "DDE6F0"]

# Amarillo FUERTE (FFFF00) — SOLO para lo que la leyenda de las hojas P promete:
# dato del certificado, valorización dentro del periodo, separadores y el
# encabezado CERT. Todo lo que significa «por verificar» usa el amarillo SUAVE
# (`FILL_PEND`, FFF2CC), que es el que la leyenda declara como tal. Antes ambos
# sentidos compartían el mismo FFFF00 y la leyenda mentía: un candado SEACE sin
# confirmar se veía idéntico a una fecha declarada por el postor.
FILL_VALOR = PatternFill("solid", fgColor="FFFF00")
# Veredicto de la verificación de expedientes (MEF) → texto de evaluador (sin jerga)
_VER_TXT = {"ok": "✔ Coincide", "no_verificable": "Por confirmar",
            "discrepancia": "✗ Discrepancia"}
# Rojo: meses PARALIZADOS en la tabla de valorizaciones (la obra estuvo parada → no
# cuentan para la experiencia; el ingeniero los marcaba así, a mano e incompleto).
F_CELL_ROJO = Font(size=9, color="FF0000")
# Amarillo separador: 2 filas (A:Z) entre experiencias en la hoja por profesional
FILL_SEP = PatternFill("solid", fgColor="FFFF00")
# Semántico para el cuadro del emisor (SUNAT): rojo = anomalía (ALT04), verde = ok.
FILL_ALERTA = PatternFill("solid", fgColor="F4CCCC")
FILL_OK = PatternFill("solid", fgColor="D9EAD3")
# Advertencia de revisión: rojo FUERTE, no el rosa del cuadro del emisor. Comparte
# franja (F:K) con el bloque de la obra que va justo debajo y tiene que ganarle a
# simple vista — si se lee como una nota más, el aviso no sirve para nada.
FILL_AVISO = PatternFill("solid", fgColor="FF9999")
F_AVISO = Font(bold=True, size=10, color="7F0000")
# Sistema de color del ingeniero en las hojas por profesional:
#   amarillo = declarado / dentro del periodo · cyan = efectivo verificado (Paso 5)
#   naranja = excluido (paralización / sin valorización) · azules = jerarquía de marco.
FILL_EFECTIVO = PatternFill("solid", fgColor="00FFFF")     # cyan: días efectivos
FILL_CERT = PatternFill("solid", fgColor="FFFF00")         # amarillo: encabezado CERT N°X
F_CERT = Font(bold=True, size=10, color="15212E")
FILL_DATOS = PatternFill("solid", fgColor="1F4E78")        # azul oscuro: header del recap
F_DATOS = Font(bold=True, size=10, color="FFFFFF")
FILL_RECAP = PatternFill("solid", fgColor="DDEBF7")        # azul claro: etiquetas del recap
# Certeza de identificación (PARTE 5 de expedientes): `entregables.certeza`
# devuelve el HEX y aquí se traduce al relleno YA existente, para que la leyenda
# del entregable siga siendo verdad (verde=verificado, violeta=inferido,
# amarillo suave=por verificar, gris=fuera del registro público).
_FILL_CERTEZA = {
    COLOR_VERIFICADO: FILL_OK,
    COLOR_INFERIDO: FILL_SUPUESTO,
    COLOR_SIN_IDENTIFICAR: FILL_PEND,
    COLOR_PRIVADA: FILL_PARTE,
}
FMT_SOLES = '#,##0.00'
# El avance físico de InfoObras ya viene en escala de porcentaje (38.36 = 38.36%).
# El formato nativo '0.00%' de Excel multiplica ×100 (mostraría 3836.00%), así que
# usamos el '%' como literal para no reescalar.
FMT_PCT = '0.00"%"'

_MES_ES = {1: "ENERO", 2: "FEBRERO", 3: "MARZO", 4: "ABRIL", 5: "MAYO",
           6: "JUNIO", 7: "JULIO", 8: "AGOSTO", 9: "SEPTIEMBRE",
           10: "OCTUBRE", 11: "NOVIEMBRE", 12: "DICIEMBRE"}

# Acciones por defecto cuando el item de revisión no trae la suya. Genéricas a
# propósito: pedir "pegar el CUI" sin saber que el problema ES el CUI manda al
# evaluador a arreglar algo que puede estar bien.
_ACCION_GENERICA = "revisar esta experiencia en el panel"
# En el bloque sin obra el diagnóstico sí es de identidad (no hubo cruce), así que
# ahí la acción por defecto puede ser concreta.
_ACCION_SIN_OBRA = "confirmar la obra o pegar el CUI correcto en el panel"

# El entregable lo lee un Comité que NO usa el panel: una acción redactada para
# el operador del backend ("elegir candidato", "pegar el CUI") es una fuga de
# interfaz que además le pide algo que no puede hacer. Se traduce al gesto
# documental equivalente en el momento de pintarla.
_ACCION_SIN_PANEL = {
    "elegir candidato o pegar CUI":
        "Confirmar con el certificado y, si existe, el contrato del expediente",
    "elegir el RUC correcto en el panel": "confirmar el RUC del emisor",
}


def _accion_visible(accion) -> Optional[str]:
    """Traduce la acción del item de revisión a lenguaje de evaluador."""
    if accion is None:
        return None
    texto = str(accion)
    for jerga, claro in _ACCION_SIN_PANEL.items():
        texto = texto.replace(jerga, claro)
    return texto


def _rotulo_candado_seace(resultado) -> Optional[str]:
    """Rótulo de confianza del candado SEACE (T-004 F5), con la fuente única en
    `validacion/candado_seace.py`. Devuelve `None` para un job anterior a F5
    (sin el campo `candado`): el bloque se dibuja como siempre y nada rompe."""
    from validacion.candado_seace import rotulo
    return rotulo(resultado)


def _mayus_inicial(texto) -> str:
    """Primera letra en mayúscula SIN tocar el resto: `str.capitalize()` bajaría
    los veredictos que el motor escribe en mayúsculas ("NO CUMPLE pero…")."""
    t = str(texto or "").strip()
    return (t[0].upper() + t[1:]) if t else t


def _motivo_accion(v) -> tuple[str, Optional[str]]:
    """Motivo y acción sugerida de una entrada de `revisiones`.

    Los ItemRevision los crean 4 etapas distintas y cada uno trae SU acción
    (`accion_sugerida`): pegar un CUI, verificar una fecha del certificado,
    reintentar el portal… Se acepta también un str suelto — el marcador
    "[PRIVADA]" y las llamadas que solo pasan el motivo."""
    if isinstance(v, dict):
        return str(v.get("motivo") or ""), _accion_visible(v.get("accion_sugerida"))
    if isinstance(v, (tuple, list)):
        return (str(v[0] if v else ""),
                _accion_visible(v[1] if len(v) > 1 else None))
    return str(v or ""), None


def _es_ruta_privada(v) -> bool:
    """La marca identifica la ruta privada, esté resuelta o pendiente SUNAT."""
    motivo, _ = _motivo_accion(v)
    return motivo.startswith(("[PRIVADA]", "[PRIVADA_PENDIENTE]"))


def _es_privada_pendiente(v) -> bool:
    motivo, _ = _motivo_accion(v)
    return motivo.startswith("[PRIVADA_PENDIENTE]")


def _es_revision_efectiva(v) -> bool:
    """Solo una privada con RUC SUNAT identificado deja de ser provisional."""
    return bool(v) and (not _es_ruta_privada(v) or _es_privada_pendiente(v))


def completar_revisiones_privadas(revisiones: dict, enriquecimiento: Optional[dict]) -> dict:
    """Añade la ruta privada al mapa del Excel y distingue SUNAT verificado.

    La identificación mínima es un RUC inequívoco. Un nombre sin coincidencia o
    con varios candidatos conserva los días como provisionales y recibe una
    etiqueta explícita; no se convierte silenciosamente en un fallo de backend.
    """
    for clave, datos in (enriquecimiento or {}).items():
        if (not isinstance(datos, dict)
                or str(datos.get("via") or "").upper() != "PRIVADA"
                or ":" not in clave or clave.startswith("prof:")):
            continue
        np_, ne = (int(x) for x in clave.split(":"))
        if (np_, ne) in revisiones:
            continue
        sunat = datos.get("sunat") or {}
        if sunat.get("ruc"):
            revisiones[(np_, ne)] = "[PRIVADA]"
        elif sunat.get("ambiguo"):
            revisiones[(np_, ne)] = (
                "[PRIVADA_PENDIENTE] SUNAT devolvió varias coincidencias para el emisor",
                "confirmar el RUC correcto entre los candidatos de SUNAT y revisar el certificado",
            )
        else:
            revisiones[(np_, ne)] = (
                "[PRIVADA_PENDIENTE] SUNAT no pudo identificar al emisor privado",
                "confirmar la razón social o el RUC en el certificado y reintentar SUNAT",
            )
    return revisiones


def _mes_en_rango(anio: int, mes: int, ini: Optional[date], fin: Optional[date]) -> bool:
    """True si el mes (anio, mes) solapa con el periodo del certificado [ini, fin]."""
    if not (ini and fin and anio and mes):
        return False
    m_ini = date(anio, mes, 1)
    m_fin = date(anio, mes, calendar.monthrange(anio, mes)[1])
    return m_ini <= fin and m_fin >= ini


def _fecha_iso(v) -> Optional[date]:
    if isinstance(v, date):
        return v
    if isinstance(v, str) and len(v) == 10:
        try:
            return date.fromisoformat(v)
        except ValueError:
            return None
    return None


def reconciliar_resultados_profesionales(espejo: dict,
                                         enriquecimiento: Optional[dict]) -> dict[int, dict]:
    """Reconstruye el resultado efectivo que comparten API y Excel.

    Los jobs anteriores a la separación de rutas pueden conservar en
    ``prof:N`` paralizaciones o avisos de InfoObras que ya no aplican a una
    experiencia de expediente o privada. El entregable nuevo ya presentaba
    esas rutas correctamente por experiencia, pero el resumen seguía leyendo
    el agregado histórico. Se recalcula solo con datos persistidos, sin red y
    sin modificar el resolver.
    """
    from orquestador.etapas_reales import _minimo_exigido
    from resolucion.cui import (TIPO_EXPEDIENTES, es_expediente_exp,
                                tipo_evaluacion_del_espejo)
    from validacion.recalculo import fechas_calculo, regla_periodos_de

    enriquecimiento = enriquecimiento or {}
    tipo_evaluacion = tipo_evaluacion_del_espejo(espejo)   # ADR-010
    # La correccion historica se activa solo cuando la convocatoria declaro su
    # tipo. Un espejo antiguo sin tipo no se reclasifica por texto ni por CUI.
    if tipo_evaluacion == TIPO_EXPEDIENTES:
        from entregables.expedientes import reconciliar_expedientes
        return reconciliar_expedientes(espejo, enriquecimiento)
    regla_periodos = regla_periodos_de(espejo)             # #93 · mes completo si lo dicen las bases
    salida: dict[int, dict] = {}
    for prof in (espejo or {}).get("profesionales", []):
        np_ = prof.get("n_prof")
        periodos: list[tuple[date, date]] = []
        paral_por_idx: dict[int, list[tuple[date, date]]] = {}
        sin_verificar: list[int] = []
        cobertura_baja: list[int] = []
        privadas_pendientes: list[int] = []
        fechas_invalidas: list[int] = []

        for exp in prof.get("experiencias", []):
            ne = exp.get("n")
            # Mismas fechas que usa el pipeline: cierta, o borde mensual si las
            # bases lo autorizan. Leer solo el ISO completo descartaba en silencio
            # los certificados con mes y año (dos profesionales bajo el mínimo).
            ini, fin, _deducida = fechas_calculo(exp, regla_periodos)
            if not (ini and fin) or fin < ini:
                if exp.get("fecha_inicial") or exp.get("fecha_final"):
                    fechas_invalidas.append(ne)
                continue

            idx = len(periodos)
            periodos.append((ini, fin))
            datos_exp = enriquecimiento.get(f"{np_}:{ne}") or {}
            privada = str(datos_exp.get("via") or "").upper() == "PRIVADA"
            expediente = es_expediente_exp(exp, tipo_evaluacion)

            # La ejecución física no descuenta tiempo de un expediente y las
            # fuentes públicas no aplican a una obra privada.
            if not (privada or expediente):
                paral_crudo = [periodo_fechas(x)
                               for x in datos_exp.get("paralizaciones", [])]
                paral = [(a, b) for a, b in paral_crudo if b >= a]
                if paral:
                    paral_por_idx[idx] = paral

            if privada:
                if not (datos_exp.get("sunat") or {}).get("ruc"):
                    privadas_pendientes.append(ne)
                continue
            if datos_exp.get("sin_verificar"):
                sin_verificar.append(ne)
            if not expediente and datos_exp.get("cobertura_baja") is not None:
                cobertura_baja.append(ne)

        anterior = dict(enriquecimiento.get(f"prof:{np_}") or {})
        for campo in ("cumple_backend", "veredicto_provisional", "cobertura_baja"):
            anterior.pop(campo, None)
        if not periodos:
            salida[np_] = anterior
            continue

        res = dias_efectivos_profesional(periodos, paral_por_idx)
        anios_ef = round(anios(res.dias_efectivos), 2)
        datos = {
            **anterior,
            "dias_brutos": res.dias_brutos,
            "dias_paralizados": res.dias_paralizados,
            "dias_traslape": res.dias_traslape,
            "dias_efectivos": res.dias_efectivos,
            "anios_efectivos": anios_ef,
        }
        exigido = _minimo_exigido(prof.get("requisitos"))
        if exigido:
            minimo_dias, minimo_texto = exigido
            datos.update(
                minimo_dias=minimo_dias,
                minimo_texto=minimo_texto,
                minimo_anios=(minimo_dias // 365 if minimo_dias % 365 == 0
                               else round(minimo_dias / 365, 2)),
            )
            if res.dias_efectivos < minimo_dias:
                datos["cumple_backend"] = (
                    f"NO CUMPLE — {res.dias_efectivos} días efectivos "
                    f"({anios_ef} años) contra un mínimo de {minimo_texto}")

        provisionales = sorted(set(sin_verificar + cobertura_baja
                                   + privadas_pendientes + fechas_invalidas))
        if provisionales:
            datos["veredicto_provisional"] = provisionales
            if cobertura_baja:
                datos["cobertura_baja"] = cobertura_baja
            causas = []
            if sin_verificar:
                causas.append("no se pudo consultar la obra en InfoObras")
            if cobertura_baja:
                causas.append("la obra encontrada casi no cubre el periodo del certificado "
                              "(puede ser la obra equivocada)")
            if privadas_pendientes:
                causas.append("SUNAT no identificó inequívocamente al emisor privado")
            if fechas_invalidas:
                causas.append("hay una fecha del certificado sin leer")
            exps = ", ".join(map(str, provisionales))
            minimo = datos.get("minimo_texto", datos.get("minimo_anios", "sin dato"))
            datos["cumple_backend"] = (
                f"POR VERIFICAR — {res.dias_efectivos} días efectivos PROVISIONALES "
                f"({anios_ef} años) contra un mínimo de {minimo}: en la(s) "
                f"experiencia(s) {exps}, {'; '.join(causas)}. La ausencia de datos NO "
                "invalida la experiencia; confirmar la evidencia antes de concluir.")
        salida[np_] = datos
    return salida


def _ddmmaa(v) -> str:
    """Fecha (ISO o date) como dd/mm/aa para los cuadros del emisor; '—' si no hay."""
    f = _fecha_iso(v)
    return f.strftime("%d/%m/%y") if f else "—"


# ── Certificados embebidos (Fase 2) ──────────────────────────────────────────
# Ancho de despliegue de la imagen del cert (px). A 130 DPI una página pesa
# ~100 KB JPEG; un análisis típico suma pocos MB.
_CERT_ANCHO_PX = 760


def _render_cert_pages(cert_pdf, dpi=130, q=70, max_pag=12):
    """Renderiza cada página del PDF del certificado a JPEG → [(bytes, ancho, alto)].
    El PDF ya viene con la página principal primero (lo ordena la skill). PyMuPDF
    se importa perezoso para no exigirlo cuando no hay certificados que embeber."""
    import fitz
    out = []
    with fitz.open(str(cert_pdf)) as doc:
        m = fitz.Matrix(dpi / 72, dpi / 72)
        for page in list(doc)[:max_pag]:
            pix = page.get_pixmap(matrix=m)
            out.append((pix.tobytes("jpg", jpg_quality=q), pix.width, pix.height))
    return out


def _factor_a_pdf_valido(pdf) -> bool:
    """Rechaza un recorte con texto que claramente pertenece a otro factor.
    Un escaneo sin capa de texto se conserva: no hay evidencia para descartarlo."""
    import fitz
    with fitz.open(str(pdf)) as doc:
        texto = " ".join(p.get_text("text") for p in doc).upper().strip()
    if not texto:
        return True
    return bool(re.search(r"FACTOR\s*A\b|EXPERIENCIA\s+DEL\s+PERSONAL\s+CLAVE|EXPERIENCIA\s+ADICIONAL", texto))


def _mapear_dir_certs(cdir) -> dict:
    """Mapea una carpeta `certs/` de PDFs recortados por la skill →
    `{(n_prof, n_exp | "TDR" | "ANEXO" | "FACTOR"): Path}`:

      · `P{n}_E{m}.pdf`   constancia de la experiencia (página principal primero)
      · `P{n}_TDR.pdf`    requisito del cargo en las bases        (mejora A)
      · `P{n}_ANEXO.pdf`  Anexo 16 declarado y firmado            (mejora A)
      · `P{n}_FACTOR.pdf` página del Cuadro de Factores (4.2 A)   (issue #32)

    El recorte del FACTOR es la MISMA página para todos; la skill la replica por
    profesional para que no haga falta una clave global (el ingest solo acepta
    `P*`, y `generar_excel_final` reparte los certs filtrando por `n_prof`). Las
    claves de tag no colisionan con las experiencias (ahí `n_exp` es int)."""
    certs: dict = {}
    cdir = Path(cdir)
    if not cdir.is_dir():
        return certs
    for f in cdir.glob("P*_E*.pdf"):
        try:
            np_, ne = f.stem[1:].split("_E")
            certs[(int(np_), int(ne))] = f
        except ValueError:
            continue
    for tag in ("TDR", "ANEXO", "FACTOR"):
        for f in cdir.glob(f"P*_{tag}.pdf"):
            try:
                certs[(int(f.stem[1:].split("_")[0]), tag)] = f
            except ValueError:
                continue
    return certs


def mapear_certificados(dir_base, job_id) -> dict:
    """Los certificados del job, en el layout del repositorio (`{job_id}/certs/`),
    listos para pasarle a `generar_excel_final`."""
    return _mapear_dir_certs(Path(dir_base) / str(job_id) / "certs")


# ── Hoja 2 · Base de Datos ───────────────────────────────────────────────────

_BD_HEAD = ["CARGO AL QUE POSTULA", "N° PROF", "PROFESIONAL", "N° COLEGIATURA",
            "N° EXP", "ENTIDAD / EMPRESA EMISORA", "PROYECTO U OBRA", "CUI",
            "TIPO DOC", "NOMBRE DEL EMISOR", "CARGO DEL EMISOR",
            "FECHA INICIAL", "FECHA FINAL", "FECHA EMISIÓN", "FOLIO",
            "DÍAS", "MESES", "AÑOS", "CARGO QUE OCUPÓ",
            "¿CARGO EN BASES?", "¿ANT. COLEGIAT.?", "¿INCLUYE COVID?",
            "¿TRASLAPE?", "¿TIPO DE OBRA SOLICITADO?", "OBSERVACIONES"]
_BD_WIDTHS = [34, 8, 26, 18, 7, 32, 44, 10, 14, 24, 20, 12, 12, 12, 10,
              8, 8, 8, 26, 12, 12, 11, 11, 16, 44]
# Columnas de veredicto → verde/rojo semántico (pos = SÍ bueno; neg = SÍ malo).
# ¿COVID? (22) queda informativo, sin color.
_BD_VERDICTS = {20: "pos", 21: "neg", 23: "neg", 24: "pos"}


def construir_hoja_base_datos(ws, espejo: dict, cuis: Optional[dict] = None,
                              revisiones: Optional[dict] = None) -> int:
    """Construye la hoja "Base de Datos". Devuelve el nº de filas de datos."""
    for i, w in enumerate(_BD_WIDTHS, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w

    for i, h in enumerate(_BD_HEAD, start=1):
        c = ws.cell(1, i, h)
        c.font, c.fill, c.border, c.alignment = F_HEAD, FILL_HEAD, BORDER, AL_HEAD
    ws.row_dimensions[1].height = 30

    cuis = cuis or {}
    revisiones = revisiones or {}
    r = 2
    for idx, prof in enumerate(espejo.get("profesionales", [])):
        fill = PatternFill("solid", fgColor=_PALETA_PROF[idx % len(_PALETA_PROF)])
        for e in prof.get("experiencias", []):
            sup = set(prof.get("supuestos") or []) | set(e.get("supuestos") or [])
            privada = _es_ruta_privada(
                revisiones.get((prof.get("n_prof"), e.get("n"))))
            observaciones = e.get("observaciones")
            if privada:
                pendiente = _es_privada_pendiente(
                    revisiones.get((prof.get("n_prof"), e.get("n"))))
                ruta = (("REVISIÓN — RUTA PRIVADA / SUNAT PENDIENTE. " if pendiente
                         else "OBRA PRIVADA — SUNAT IDENTIFICADO. ")
                        + "InfoObras, MEF y SEACE no aplican. La ruta de "
                          "verificación es SUNAT y la revisión documental del certificado.")
                observaciones = f"{ruta} · {observaciones}" if observaciones else ruta
            valores = [
                prof.get("cargo"), prof.get("n_prof"), prof.get("nombre"),
                prof.get("colegiatura"), e.get("n"), e.get("entidad_emisora"),
                e.get("proyecto"), cuis.get((prof.get("n_prof"), e.get("n"))) or e.get("cui"), e.get("tipo_documento"),
                e.get("nombre_emisor"), e.get("cargo_emisor"),
                fecha_excel(e.get("fecha_inicial")), fecha_excel(e.get("fecha_final")),
                fecha_excel(e.get("fecha_emision")), e.get("folio"),
                e.get("dias"), e.get("meses"), e.get("anios"), e.get("cargo_ocupado"),
                e.get("cargo_bases_valido"), (e.get("anterior_colegiatura")
                                               if e.get("anterior_colegiatura") not in (None, "")
                                               else "POR VERIFICAR"),
                e.get("incluye_covid"), e.get("traslape"), e.get("tipo_obra_valido"),
                observaciones,
            ]
            # #55: las celdas las lee el evaluador — la jerga interna (⟦crudo⟧,
            # agent-*, campos del schema) se reescribe igual que en la hoja CLAUDE
            valores = [_sin_jerga(v) for v in valores]
            for i, v in enumerate(valores, start=1):
                c = ws.cell(r, i, v)
                c.font, c.border, c.alignment, c.fill = F_CELL, BORDER, AL_WRAP, fill
                if i in (12, 13, 14) and isinstance(v, date):
                    c.number_format = FMT_FECHA
                if i == 16 and isinstance(v, (int, float)):
                    c.number_format = FMT_INT
                if i in (17, 18) and isinstance(v, (int, float)):
                    c.number_format = FMT_DEC
                # veredicto: el verde/rojo pinta ENCIMA del color por profesional
                if i in _BD_VERDICTS:
                    vf = _fill_veredicto(v, _BD_VERDICTS[i])
                    if vf:
                        c.fill = vf
                campos_bd = {
                    1: "cargo", 3: "nombre", 4: "colegiatura",
                    6: "entidad_emisora", 7: "proyecto", 8: "cui",
                    9: "tipo_documento", 10: "nombre_emisor", 11: "cargo_emisor",
                    12: "fecha_inicial", 13: "fecha_final", 14: "fecha_emision",
                    15: "folio", 19: "cargo_ocupado", 20: "cargo_bases_valido",
                    21: "anterior_colegiatura", 22: "incluye_covid",
                    23: "traslape", 24: "tipo_obra_valido",
                }
                if campos_bd.get(i) in sup and v not in (None, ""):
                    c.fill = FILL_SUPUESTO
                if i == 8 and (prof.get("n_prof"), e.get("n")) in cuis:
                    c.comment = Comment(
                        "CUI identificado por el sistema durante el cruce con InfoObras; "
                        "no necesariamente estaba escrito en el certificado.",
                        "Pivote",
                    )
            r += 1

    ws.auto_filter.ref = f"A1:{get_column_letter(len(_BD_HEAD))}{max(r - 1, 1)}"
    ws.freeze_panes = "A2"
    return r - 2


# ── Hoja · Cronología de expedientes (T-011) ─────────────────────────────────
#
# Hoja ADICIONAL. Las hojas del formato congelado (decisión del cliente
# 2026-06-10: CLAUDE, Base de Datos y una por profesional) no se tocan: esta se
# agrega AL FINAL del libro. Un job sin datos del proceso ni del expediente la
# genera igual, con la nota que dice por qué está vacía — nunca en silencio.

HOJA_CRONOLOGIA = "Cronología de expedientes"

_CRON_HEAD = ["PROFESIONAL", "N° EXP", "PROYECTO U OBRA", "CUI",
              "DESDE (declarado)", "HASTA (declarado)", "FIRMA DEL CONTRATO",
              "APROBACIÓN DEL EXPEDIENTE",
              "¿EMPEZÓ DESPUÉS DE FIRMADO EL CONTRATO?",
              "¿TERMINÓ ANTES DE APROBARSE EL EXPEDIENTE?",
              "QUÉ DICE EL CRUCE"]
_CRON_WIDTHS = [26, 7, 44, 10, 13, 13, 15, 17, 20, 20, 76]
_NCOL_CRON = len(_CRON_HEAD)

_CRON_INTRO = (
    "Esta hoja contrasta lo que declara cada certificado con las fechas que "
    "publican las fuentes oficiales: la firma del contrato del proceso "
    "(datos abiertos del Estado) y la resolución que aprobó el expediente "
    "técnico (MEF / InfoObras). Nada de lo que aquí figure descalifica por sí "
    "solo una experiencia: cuando la fuente no existe o no se pudo confirmar "
    "que corresponda a este certificado, la celda dice POR VERIFICAR — la falta "
    "de información nunca cuenta en contra del postor.")

_CRON_LEYENDA = ("Colores: verde = la fecha declarada calza con el documento · "
                 "rojo = incoherencia a revisar · amarillo = por verificar · "
                 "violeta = dato deducido (no consta escrito, se dedujo del "
                 "documento).")


_CRON_SIN_FUENTE_B = "POR VERIFICAR — sin fuente pública localizada"

# ── Sección 2 · línea de tiempo por profesional (concursos de EXPEDIENTES) ──
#
# En un concurso de expedientes la tabla comparativa (una fila por experiencia,
# once columnas de texto) obligaba al Comité a reconstruir mentalmente el orden
# de las experiencias y a buscar los traslapes a mano. Lo que decide es CUÁNTO
# tiempo acredita el profesional y CUÁNTO de ese tiempo está pisado o sin
# identificar: eso se ve de un golpe en una línea de tiempo y no en una tabla.
# La tabla se conserva tal cual para los concursos de OBRAS, donde el contraste
# fila a fila contra el contrato sigue siendo la lectura natural.
COLOR_TRASLAPE = "F4B183"                                   # naranja: dos periodos pisados
FILL_TRASLAPE = PatternFill("solid", fgColor=COLOR_TRASLAPE)

_GANTT_TITULO = "2 · LÍNEA DE TIEMPO POR PROFESIONAL"

_GANTT_ROTULO_EJE = "PERÍODO DECLARADO"
_GANTT_SIN_PERIODOS = ("Sin periodos computables: el certificado no consigna "
                       "fechas con las que se pueda dibujar una línea de tiempo.")

#: Las marcas C/R/≈ van ENCIMA de la barra: fuente pequeña y negrita para que se
#: lean sobre el relleno de certeza sin taparlo.
F_MARCA = Font(bold=True, size=8, color="15212E")

_GANTT_ESCALA = {cronologia.GRANO_MES: "Eje: meses",
                 cronologia.GRANO_TRIMESTRE: "Eje: trimestres",
                 cronologia.GRANO_ANIO: "Eje: años"}


def _num(*valores) -> int:
    """El primer valor numérico de la lista (0 si no hay ninguno)."""
    for v in valores:
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return int(v)
    return 0


def _veredicto_gantt(prof: dict, datos: dict) -> str:
    """CUMPLE / NO CUMPLE / POR VERIFICAR, leído de `cumple_backend`.

    `cumple_backend` lo redacta `reconciliar_resultados_profesionales` y ya cita
    los mismos días que imprime la cabecera del bloque; aquí solo se extrae la
    palabra. Cuando el reconciliado NO dictó nada (no hay incidencias) se decide
    con el mínimo exigido: sin mínimo declarado en las bases no hay contra qué
    comparar y la respuesta honesta es POR VERIFICAR.
    """
    texto = str(prof.get("cumple_backend") or datos.get("cumple_backend") or "")
    cabeza = _sin_jerga(texto).strip().upper()
    for etiqueta in ("NO CUMPLE", "POR VERIFICAR", "CUMPLE"):
        if cabeza.startswith(etiqueta):
            return etiqueta
    minimo = datos.get("minimo_dias")
    if isinstance(minimo, int) and minimo > 0:
        return ("CUMPLE" if _num(datos.get("dias_efectivos")) >= minimo
                else "NO CUMPLE")
    return "POR VERIFICAR"


def _rotulo_cruces(p: dict) -> str:
    """Respuestas completas y estructuradas; el motivo sigue en comentario."""
    return (f"\nInicio frente al contrato: {p.get('resp_a') or 'POR VERIFICAR'}\n"
            f"Término frente a aprobación: {p.get('resp_b') or 'POR VERIFICAR'}")


def _alto_rotulo_gantt(texto: str, ancho: int = 38) -> int:
    """Altura estimada contando saltos explícitos y envoltura del rótulo."""
    lineas = sum(max(1, -(-len(linea) // ancho))
                 for linea in str(texto or "").splitlines())
    return max(22, lineas * 13 + 4)


def _bloques_linea_de_tiempo(espejo: dict, fichas: dict,
                             tipo_evaluacion: Optional[str],
                             resultados: Optional[dict] = None) -> list[dict]:
    """Un bloque por profesional, ya resuelto: eje, filas, traslapes y totales.

    Todo lo que decide QUÉ se dibuja se resuelve aquí, con las fuentes únicas
    del backend, y el pintado de más abajo se limita a colocarlo:

      · periodos → `validacion.recalculo.fechas_calculo` con la regla de las
        bases (`regla_periodos_de`), la MISMA que usa la PARTE 5, para no
        descartar en silencio los certificados con mes y año;
      · días E/T → `reconciliar_resultados_profesionales` (o el
        `total_backend` que ese mismo reconciliado ya dejó en el espejo);
      · color → `certeza.clasificar_identificacion`;
      · reglas A/B → `presentacion_cruces` (viajan como comentario de la celda).
    """
    from validacion.recalculo import fechas_calculo, regla_periodos_de

    regla = regla_periodos_de(espejo)
    if resultados is None:
        enriquecimiento = {
            f"{np_}:{ne}": fx for (np_, ne), fx in fichas.items()
            if isinstance(fx, dict)
        }
        resultados = reconciliar_resultados_profesionales(espejo, enriquecimiento)
    bloques: list[dict] = []

    profesionales = sorted((espejo or {}).get("profesionales", []) or [],
                           key=lambda p: _num(p.get("n_prof")))
    for prof in profesionales:
        np_ = prof.get("n_prof")
        datos = resultados.get(np_) or {}
        total = prof.get("total_backend") if isinstance(
            prof.get("total_backend"), dict) else {}
        dias_ef = _num(total.get("dias_efectivos"), datos.get("dias_efectivos"))
        dias_tr = _num(total.get("dias_traslape"), datos.get("dias_traslape"))
        dias_dec = _num(total.get("dias_declarados"), datos.get("dias_brutos"))

        crudas: list[dict] = []
        periodos: list[tuple[date, date]] = []
        hitos: list[Optional[date]] = []
        for e in prof.get("experiencias", []) or []:
            fx = fichas.get((np_, e.get("n"))) or {}
            ini, fin, deducida = fechas_calculo(e, regla)
            if not (ini and fin) or fin < ini:
                ini = fin = None
            else:
                periodos.append((ini, fin))
            firma = cronologia.hito_firma(fx)
            resolucion = cronologia.hito_resolucion(fx)
            hitos += [firma, resolucion]
            p = presentacion_cruces(e, fx, tipo_evaluacion)
            crudas.append({
                "n": e.get("n"), "proyecto": p["proyecto"] or e.get("proyecto"),
                "cui": p["cui"], "inicio": ini, "fin": fin,
                "deducida": bool(deducida and (ini or fin)),
                "firma": firma, "resolucion": resolucion,
                "cruces": p,
                "color": clasificar_identificacion(e, fx)["color"],
                "comentario": _sin_jerga(
                    "¿Empezó después de firmado el contrato? "
                    f"{p['resp_a']}\n"
                    "¿Terminó antes de aprobarse el expediente? "
                    f"{p['resp_b']}\n{p['motivo'] or '—'}"),
            })

        rango = cronologia.rango_eje(periodos, hitos)
        eje = cronologia.construir_eje(*rango) if rango else []
        grano = cronologia.granularidad(*rango) if rango else cronologia.GRANO_MES

        # Orden de lectura: por fecha de inicio; las que no tienen fechas
        # computables van al final, para que la escalera de barras no se rompa.
        crudas.sort(key=lambda f: (f["inicio"] is None, f["inicio"] or date.min,
                                   _num(f["n"])))

        filas: list[dict] = []
        for f in crudas:
            celdas = cronologia.indices_periodo(eje, f["inicio"], f["fin"])
            marcas: dict[int, list[str]] = {}
            # A/B procede de `presentacion_cruces`; el motivo completo queda en
            # comentario, pero el estado nunca queda oculto tras un clic.
            notas: list[str] = [_rotulo_cruces(f["cruces"])]
            if not celdas:
                notas.append(cronologia.NOTA_SIN_FECHAS)
            elif f["deducida"]:
                marcas.setdefault(celdas[0], []).append(cronologia.MARCA_MES)
                notas.append(cronologia.NOTA_MES_COMPLETO)
            for marca, valor in ((cronologia.MARCA_FIRMA, f["firma"]),
                                 (cronologia.MARCA_RESOLUCION, f["resolucion"])):
                if not valor:
                    continue
                i = cronologia.indice_unidad(eje, valor)
                if i is None:
                    notas.append(cronologia.nota_hito_fuera(marca, valor))
                else:
                    marcas.setdefault(i, []).append(marca)
            rotulo = cronologia.rotulo_experiencia(f["n"], f["proyecto"],
                                                   f["cui"], notas)
            rotulo = rotulo.replace(" · \nInicio frente al contrato:",
                                    "\nInicio frente al contrato:")
            filas.append({
                "rotulo": rotulo,
                "celdas": celdas, "color": f["color"],
                "marcas": cronologia.marcas_de_columna(marcas),
                "comentario": f["comentario"],
            })

        traslapes = cronologia.unidades_con_traslape(eje, periodos)
        bloques.append({
            "n_prof": np_,
            "cabecera": (f"PROFESIONAL {np_} · {prof.get('nombre') or '—'} · "
                         f"{prof.get('cargo') or '—'} · {dias_ef} días efectivos "
                         f"({dias_tr} de traslape) · "
                         f"{_veredicto_gantt(prof, datos)}"),
            "escala": _GANTT_ESCALA.get(grano, ""),
            "eje": eje, "filas": filas, "traslapes": traslapes,
            "rotulo_traslapes": ("Traslapes · Sin traslapes" if not dias_tr
                                 else f"Traslapes · {dias_tr} días de traslape"),
            "total": (f"Total: {dias_dec} días declarados · {dias_tr} traslape · "
                      f"{dias_ef} efectivos"),
        })
    return bloques


def _pintar_linea_de_tiempo(ws, bloques: list[dict], fila: int,
                            ncols: int) -> tuple[int, int]:
    """Vuelca los bloques ya resueltos en la hoja. Devuelve `(filas, fila)`."""
    total_filas = 0
    for b in bloques:
        # Separación visual antes de TODOS los profesionales, incluido el
        # primero; no agrega datos ni altera los totales.
        fila += 1
        ws.row_breaks.append(Break(id=fila - 1))
        ws.merge_cells(start_row=fila, start_column=1, end_row=fila,
                       end_column=ncols)
        c = ws.cell(fila, 1, _sin_jerga(b["cabecera"]))
        c.font, c.fill = F_CERT, FILL_CERT
        c.alignment = Alignment(vertical="center", wrap_text=True)
        ws.row_dimensions[fila].height = _alto_rotulo_gantt(b["cabecera"])
        fila += 1

        eje = b["eje"]
        if not eje:
            ws.merge_cells(start_row=fila, start_column=1, end_row=fila,
                           end_column=ncols)
            c = ws.cell(fila, 1, _GANTT_SIN_PERIODOS)
            c.font, c.fill, c.alignment = F_CELL, FILL_PEND, AL_WRAP
            fila += 1
            for f in b["filas"]:
                cr = ws.cell(fila, 1, _sin_jerga(f["rotulo"]))
                cr.font, cr.border = F_CELL, BORDER
                cr.alignment = Alignment(vertical="center", wrap_text=True)
                if f["comentario"]:
                    cr.comment = Comment(f["comentario"], "Pivote")
                ws.row_dimensions[fila].height = _alto_rotulo_gantt(cr.value)
                fila += 1
                total_filas += 1
            fila += 1
            continue

        # Cabecera 1: los años, combinados sobre sus unidades.
        c = ws.cell(fila, 1, b["escala"])
        c.font, c.alignment = F_BOLD, AL_HEAD
        fila_anios = fila
        fila_anios_alta = False
        for i0, i1, anio in cronologia.tramos_de_anio(eje):
            if i1 > i0:
                ws.merge_cells(start_row=fila, start_column=2 + i0,
                               end_row=fila, end_column=2 + i1)
            ca = ws.cell(fila, 2 + i0, anio)
            alineacion = (Alignment(horizontal="center", vertical="center",
                                    text_rotation=90)
                          if i0 == i1 else AL_HEAD)
            ca.font, ca.fill, ca.border, ca.alignment = (F_HEAD, FILL_HEAD,
                                                         BORDER, alineacion)
            ca.number_format = "0"
            fila_anios_alta |= i0 == i1
        ws.row_dimensions[fila_anios].height = 36 if fila_anios_alta else 14
        fila += 1

        # Cabecera 2: la unidad (letra del mes, «T1»… o vacío en años).
        c = ws.cell(fila, 1, _GANTT_ROTULO_EJE)
        c.font, c.alignment = F_BOLD, AL_HEAD
        for i, u in enumerate(eje):
            cu = ws.cell(fila, 2 + i, u.etiqueta or None)
            cu.font, cu.fill, cu.border, cu.alignment = (F_HEAD, FILL_HEAD,
                                                         BORDER, AL_HEAD)
        ws.row_dimensions[fila].height = 14
        fila += 1

        for f in b["filas"]:
            cr = ws.cell(fila, 1, _sin_jerga(f["rotulo"]))
            cr.font, cr.border = F_CELL, BORDER
            cr.alignment = Alignment(vertical="center", wrap_text=True)
            if f["comentario"]:
                # Las respuestas de las dos reglas y su motivo NO se pierden al
                # retirar la tabla comparativa: viajan aquí, a un clic del
                # rótulo de la experiencia.
                cr.comment = Comment(f["comentario"], "Pivote")
            relleno = _FILL_CERTEZA.get(f["color"]) or FILL_PEND
            for i in f["celdas"]:
                cb = ws.cell(fila, 2 + i)
                cb.fill, cb.border = relleno, BORDER
            for i, marca in f["marcas"].items():
                cm = ws.cell(fila, 2 + i, marca)
                cm.font, cm.border, cm.alignment = F_MARCA, BORDER, AL_HEAD
            ws.row_dimensions[fila].height = _alto_rotulo_gantt(cr.value)
            fila += 1
            total_filas += 1

        ct = ws.cell(fila, 1, b["rotulo_traslapes"])
        ct.font, ct.border = F_BOLD, BORDER
        ct.alignment = Alignment(vertical="center", wrap_text=True)
        for i in sorted(b["traslapes"]):
            cx = ws.cell(fila, 2 + i)
            cx.fill, cx.border = FILL_TRASLAPE, BORDER
        ws.row_dimensions[fila].height = _alto_rotulo_gantt(ct.value)
        fila += 1

        ws.merge_cells(start_row=fila, start_column=1, end_row=fila,
                       end_column=ncols)
        ctot = ws.cell(fila, 1, b["total"])
        ctot.font, ctot.fill = F_BOLD, FILL_EFECTIVO
        ctot.alignment = Alignment(vertical="center", wrap_text=True)
        ws.row_dimensions[fila].height = _alto_rotulo_gantt(ctot.value)
        fila += 2

    return total_filas, fila

# Formato de fecha de los cruces: año de CUATRO dígitos. Aquí se comparan
# periodos declarados contra documentos oficiales y un `29/05/18` obliga a
# adivinar el siglo justo donde el año es el dato que importa.
FMT_FECHA_LARGA = "dd/mm/yyyy"


def _cron_dato(v) -> str:
    return _sin_jerga(v) if isinstance(v, str) and v.strip() else "—"


def _cron_cruce(cruces, regla) -> Optional[dict]:
    for c in cruces or []:
        if isinstance(c, dict) and c.get("regla") == regla:
            return c
    return None


def _tipo_evaluacion_espejo(espejo: Optional[dict]) -> Optional[str]:
    """`_meta.tipo_evaluacion` normalizado (ADR-010) o None. Import diferido: el
    resolver importa a su vez utilidades de este paquete."""
    from resolucion.cui import tipo_evaluacion_del_espejo
    return tipo_evaluacion_del_espejo(espejo)


def _tipo_experiencia(e: dict, fx: dict, tipo_evaluacion: Optional[str] = None) -> str:
    # ADR-010: el tipo declarado del concurso manda sobre la lectura del texto.
    # Es el mismo criterio con que el backend enrutó la verificación, así la
    # cronología no contradice a la ficha (un expediente enrutado como tal no
    # puede decir «NO APLICA» por perder la palabra en el nombre).
    from resolucion.cui import TIPO_EXPEDIENTES, TIPO_OBRAS, normalizar_tipo_evaluacion
    declarado = normalizar_tipo_evaluacion(tipo_evaluacion)
    if declarado == TIPO_EXPEDIENTES:
        return "expediente"
    if declarado == TIPO_OBRAS:
        return "ejecucion"
    explicito = str(fx.get("tipo_experiencia") or e.get("tipo_experiencia") or "").lower()
    texto = " ".join((explicito, str(e.get("proyecto") or ""))).lower()
    if re.search(r"expediente\s+t[eé]cnico|estudio\s+definitivo", texto):
        return "expediente"
    if re.search(r"preinversi[oó]n|perfil|factibilidad", texto):
        return "preinversion"
    if re.search(r"ejecuci[oó]n\s+de\s+obra|residente\s+de\s+obra|obra\s+ejecutada", texto):
        return "ejecucion"
    if explicito in {"expediente", "preinversion", "ejecucion", "supervision"}:
        return explicito
    return "indeterminada"


def presentacion_cruces(e: dict, fx: Optional[dict],
                        tipo_evaluacion: Optional[str] = None) -> dict:
    """Los cruces de UNA experiencia, ya traducidos a lo que se pinta.

    `tipo_evaluacion` es el parámetro del concurso (ADR-010, `_meta`); cuando
    viene, decide si la experiencia es de expediente u obra por encima del texto.

    ⚠ FUENTE ÚNICA de la presentación: la consumen la hoja «Cronología de
    expedientes» (vista de conjunto del Comité) **y** el bloque por profesional
    de cada hoja P. Si un texto, una fecha o un color cambia, cambia en los dos
    sitios a la vez — que es exactamente lo que se pidió al aprobar el híbrido.
    Las decisiones siguen viviendo en `reglas/cruces_fechas.py`; aquí solo se
    traducen a celdas.
    """
    from reglas.cruces_fechas import REGLA_INICIO, REGLA_TERMINO, RESPUESTA

    fx = fx or {}
    tipo = _tipo_experiencia(e, fx, tipo_evaluacion)
    via = str(fx.get("via") or "").upper()
    if via == "PRIVADA" or (tipo == "expediente" and via == "NA"):
        pendiente = bool(fx.get("privada_pendiente"))
        rotulo_a = ("REVISIÓN — RUTA PRIVADA / SUNAT PENDIENTE" if pendiente
                    else "FUENTE PÚBLICA NO APLICA — OBRA PRIVADA")
        rotulo_b = (_CRON_SIN_FUENTE_B + "; revisar el sustento privado"
                    if tipo == "expediente" else
                    ("POR VERIFICAR — tipo de experiencia no determinado"
                     if tipo == "indeterminada" else
                     "NO APLICA — la regla corresponde a expedientes técnicos"))
        return {
            "n_exp": e.get("n"), "proyecto": e.get("proyecto"), "cui": None,
            "proceso": None, "inicio": fecha_excel(e.get("fecha_inicial")),
            "fin": fecha_excel(e.get("fecha_final")), "firma": None,
            "aprobacion": None, "resp_a": rotulo_a,
            "resp_b": rotulo_b, "aplica_b": tipo != "ejecucion",
            "inferida": False,
            "motivo": (("SUNAT aún no identificó inequívocamente al emisor. "
                        if pendiente else "") +
                       "InfoObras, MEF y SEACE no aplican. La ruta de "
                       "verificación es SUNAT y la revisión documental del "
                       "certificado."),
        }
    cruces = fx.get("cruces_fechas") or []
    ca = _cron_cruce(cruces, REGLA_INICIO) or {}
    cb = _cron_cruce(cruces, REGLA_TERMINO)
    seace = fx.get("seace") if isinstance(fx.get("seace"), dict) else {}
    proceso = seace.get("proceso") or {}
    firma = (ca.get("fecha_fuente") or proceso.get("fecha_firma")
             or seace.get("fecha_suscripcion"))
    aprobacion = (cb or {}).get("fecha_fuente")
    motivos = [x.get("motivo") for x in (ca, cb) if x and x.get("motivo")]
    if tipo == "expediente":
        motivos = [normalizar_motivo_fuente(m) for m in motivos]
    return {
        "n_exp": e.get("n"),
        "proyecto": fx.get("obra_nombre") or e.get("proyecto"),
        "cui": fx.get("cui") or e.get("cui"),
        "proceso": (proceso.get("nomenclatura") or seace.get("codigoconvocatoria")
                    or None),
        "inicio": fecha_excel(e.get("fecha_inicial")),
        "fin": fecha_excel(e.get("fecha_final")),
        "firma": fecha_excel(firma),
        "aprobacion": fecha_excel(aprobacion),
        "resp_a": RESPUESTA.get(ca.get("resultado"), "POR VERIFICAR"),
        "resp_b": (RESPUESTA.get(cb.get("resultado"), "POR VERIFICAR") if cb else
                   (_CRON_SIN_FUENTE_B if tipo == "expediente" else
                    ("POR VERIFICAR — tipo de experiencia no determinado"
                     if tipo == "indeterminada" else
                     "NO APLICA — la regla corresponde a expedientes técnicos"))),
        "aplica_b": cb is not None or tipo in {"expediente", "indeterminada"},
        "inferida": bool(cb and cb.get("inferida") and aprobacion),
        "motivo": _sin_jerga(" ".join(str(m) for m in motivos)),
    }


def _pintar_respuesta(celda, respuesta: str, aplica: bool = True) -> None:
    """Verde / rojo / amarillo de una respuesta de cruce (SÍ es lo bueno). El
    «no aplica» va SIN color: amarillo significa «por verificar», y una
    supervisión no tiene nada que verificar contra la aprobación de un
    expediente."""
    f = _fill_veredicto(respuesta, "pos") if aplica else None
    if f:
        celda.fill = f


def _cron_proyectos(espejo: dict, fichas: dict) -> list[dict]:
    """Un bloque de ficha por PROYECTO (no por experiencia): varias experiencias
    del mismo CUI comparten contrato, aprobación y modificaciones. La clave es el
    CUI cuando existe; si no, el nombre del proyecto — dos proyectos sin CUI y
    con el mismo nombre son, para el evaluador, el mismo proyecto."""
    orden: list[str] = []
    por_clave: dict[str, dict] = {}
    for prof in espejo.get("profesionales", []):
        for e in prof.get("experiencias", []):
            fx = fichas.get((prof.get("n_prof"), e.get("n"))) or {}
            cui = str(fx.get("cui") or e.get("cui") or "").strip()
            nombre = fx.get("obra_nombre") or e.get("proyecto") or ""
            clave = cui or str(nombre)
            if not clave:
                continue
            if clave not in por_clave:
                orden.append(clave)
                por_clave[clave] = {"cui": cui, "nombre": nombre, "seace": None,
                                    "aprobacion": None, "verificacion": None,
                                    "modificaciones": [], "experiencias": 0,
                                    "via": fx.get("via"),
                                    "privada_pendiente": fx.get("privada_pendiente")}
            bloque = por_clave[clave]
            bloque["experiencias"] += 1
            bloque["nombre"] = bloque["nombre"] or nombre
            seace = fx.get("seace")
            if isinstance(seace, dict) and seace.get("estado") == "seleccionado":
                bloque["seace"] = bloque["seace"] or seace
            if fx.get("aprobacion_expediente"):
                bloque["aprobacion"] = bloque["aprobacion"] or fx["aprobacion_expediente"]
            if fx.get("verificacion_expediente"):
                bloque["verificacion"] = bloque["verificacion"] or fx["verificacion_expediente"]
            if fx.get("modificaciones_plazo") and not bloque["modificaciones"]:
                bloque["modificaciones"] = fx["modificaciones_plazo"]
    return [por_clave[c] for c in orden]


def _configurar_impresion_cronologia(ws, ncols: int, nfilas: int) -> None:
    """Impresión de la cronología con el rango real y sin columnas de relleno."""
    ultima = get_column_letter(max(1, ncols))
    ws.print_area = f"A1:{ultima}{max(1, nfilas)}"
    ws.freeze_panes = "B1"
    ws.sheet_properties.pageSetUpPr.fitToPage = False
    ws.page_setup.orientation = ws.ORIENTATION_LANDSCAPE
    ws.page_setup.paperSize = ws.PAPERSIZE_A3
    ws.page_setup.fitToWidth = None
    ws.page_setup.fitToHeight = None
    anchos = [ws.column_dimensions[get_column_letter(i)].width or 8
              for i in range(1, ncols + 1)]
    ancho_estimado_pt = sum(anchos) * 5.25 + ncols * 0.75
    ancho_papel_pt = 420 / 25.4 * 72 - (0.25 + 0.25) * 72
    ws.page_setup.scale = max(10, min(100, int(0.95 * ancho_papel_pt / ancho_estimado_pt * 100)))
    ws.page_margins.left = 0.25
    ws.page_margins.right = 0.25
    ws.page_margins.top = 0.45
    ws.page_margins.bottom = 0.45
    ws.print_options.horizontalCentered = False
    ws.print_title_rows = "$1:$1"
def construir_hoja_cronologia(ws, espejo: dict, fichas: Optional[dict] = None) -> int:
    """Hoja «Cronología de expedientes». Devuelve el nº de filas comparadas.

    Dos partes: (1) una ficha por proyecto — contrato del proceso, resolución de
    aprobación del expediente y modificaciones de plazo conocidas; (2) según el
    tipo de concurso:

      · EXPEDIENTES → «2 · LÍNEA DE TIEMPO POR PROFESIONAL»: un bloque tipo Gantt
        por profesional, con el color de certeza en cada barra, los hitos del MEF
        (C/R) sobre la barra y la fila de traslapes. Las respuestas de las dos
        reglas no se pierden: viajan como COMENTARIO de la celda del rótulo.
      · OBRAS (o tipo no declarado) → la tabla comparativa de siempre, una fila
        por experiencia.
    """
    from resolucion.cui import TIPO_EXPEDIENTES
    fichas = fichas or {}
    tipo_evaluacion = _tipo_evaluacion_espejo(espejo)          # ADR-010
    linea_de_tiempo = tipo_evaluacion == TIPO_EXPEDIENTES

    bloques: list[dict] = []
    if linea_de_tiempo:
        # La rejilla de la línea de tiempo manda sobre los anchos de la hoja: A
        # es el rótulo y de B en adelante van las unidades del eje, todas
        # estrechas. La sección 1 sigue combinando A:C (etiqueta) y D:última
        # (valor), así que se garantiza un mínimo de columnas para que ese valor
        # conserve un ancho legible aunque el eje sea corto.
        bloques = _bloques_linea_de_tiempo(espejo, fichas, tipo_evaluacion)
        eje_max = max([len(b["eje"]) for b in bloques] or [0])
        _NCOL = max(1 + eje_max, cronologia.MIN_COLUMNAS)
        ws.column_dimensions["A"].width = cronologia.ANCHO_ROTULO
        for i in range(2, _NCOL + 1):
            ws.column_dimensions[get_column_letter(i)].width = cronologia.ANCHO_UNIDAD
    else:
        _NCOL = _NCOL_CRON
        for i, w in enumerate(_CRON_WIDTHS, start=1):
            ws.column_dimensions[get_column_letter(i)].width = w

    r = 1

    def _ancho_columnas(desde: int, hasta: int) -> float:
        return sum(ws.column_dimensions[get_column_letter(i)].width or 8
                   for i in range(desde, hasta + 1)) * 0.8

    def _alto_con_ancho(texto, desde: int, hasta: int, minimo: int = 18) -> int:
        if not linea_de_tiempo:
            return minimo
        ancho = max(18, _ancho_columnas(desde, hasta))
        lineas = sum(max(1, -(-len(linea) // int(ancho)))
                     for linea in str(texto or "").splitlines())
        return max(minimo, lineas * 14 + 4)

    def banda(texto, font=F_PARTE, fill=FILL_PARTE, alto=20):
        nonlocal r
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=_NCOL)
        # También los títulos: el nombre del proyecto viene del espejo y puede
        # arrastrar marcas del consolidador (#55).
        c = ws.cell(r, 1, _sin_jerga(texto))
        c.font, c.fill, c.alignment = font, fill, Alignment(vertical="center",
                                                            wrap_text=True)
        if linea_de_tiempo:
            ws.row_dimensions[r].height = max(alto, _alto_con_ancho(texto, 1, _NCOL))
        else:
            ws.row_dimensions[r].height = alto
        r += 1

    def parrafo(texto, fill=None, filas=None):
        nonlocal r
        texto = _sin_jerga(texto)
        if linea_de_tiempo:
            alto = _alto_con_ancho(texto, 1, _NCOL)
            n = max(filas or 1, -(-alto // 14))
        else:
            n = filas or max(1, -(-len(texto) // 190))
        ws.merge_cells(start_row=r, start_column=1, end_row=r + n - 1,
                       end_column=_NCOL)
        c = ws.cell(r, 1, texto)
        c.font, c.alignment = F_CELL, AL_WRAP
        if fill:
            c.fill = fill
        for k in range(n):
            ws.row_dimensions[r + k].height = 14
        r += n

    def campo(etiqueta, valor, fill=None):
        """Etiqueta (A:C) + valor (D:K) — la rejilla de las fichas por proyecto."""
        nonlocal r
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=3)
        cl = ws.cell(r, 1, etiqueta)
        cl.font, cl.border, cl.alignment = F_BOLD, BORDER, AL_WRAP
        ws.merge_cells(start_row=r, start_column=4, end_row=r, end_column=_NCOL)
        cv = ws.cell(r, 4, _cron_dato(valor))
        cv.font, cv.border, cv.alignment = F_CELL, BORDER, AL_WRAP
        if fill:
            cv.fill = fill
        if linea_de_tiempo:
            ws.row_dimensions[r].height = max(
                _alto_con_ancho(etiqueta, 1, 3),
                _alto_con_ancho(valor, 4, _NCOL))
        r += 1

    banda("CRONOLOGÍA DE EXPEDIENTES Y CONTRATOS", F_DATOS, FILL_DATOS, 24)
    parrafo(_CRON_INTRO)
    parrafo(_CRON_LEYENDA)
    r += 1

    proyectos = _cron_proyectos(espejo, fichas)
    con_hito = [p for p in proyectos if p["seace"] or p["aprobacion"] or p["verificacion"]]

    banda(f"1 · FICHA POR PROYECTO ({len(con_hito)} de {len(proyectos)} con "
          f"documentos publicados)")
    if not con_hito:
        parrafo("Sin procesos verificables: ninguno de los proyectos de esta "
                "propuesta tiene un proceso de contratación en los datos abiertos "
                "del Estado (la cobertura empieza en 2018) ni una aprobación de "
                "expediente publicada. No es un defecto de la propuesta ni del "
                "análisis: es lo que las fuentes publican. Los periodos declarados "
                "se evalúan con el resto del expediente, sin este contraste.",
                FILL_PEND, filas=3)
    for p in con_hito:
        r += 1
        titulo = str(p["nombre"] or "Proyecto sin nombre")
        if p["cui"]:
            titulo += f"  ·  CUI {p['cui']}"
        titulo += f"  ·  {p['experiencias']} experiencia(s)"
        banda(titulo, F_CERT, FILL_CERT, 18)
        seace = p["seace"] or {}
        proceso = seace.get("proceso") or {}
        candado = seace.get("candado") if isinstance(seace.get("candado"), dict) else {}
        if seace:
            campo("Proceso de contratación", proceso.get("nomenclatura")
                  or seace.get("codigoconvocatoria"))
            campo("Entidad que convocó", proceso.get("entidad_convocante"))
            campo("Fecha de firma del contrato", _ddmmaa_larga(proceso.get("fecha_firma")
                                                               or seace.get("fecha_suscripcion")))
            vig = seace.get("vigencia") or [proceso.get("vigencia_inicio"),
                                            proceso.get("vigencia_fin")]
            campo("Vigencia del contrato",
                  f"{_ddmmaa_larga(vig[0] if vig else None)} a "
                  f"{_ddmmaa_larga(vig[1] if vig and len(vig) > 1 else None)}")
            rot = _rotulo_candado_seace(candado.get("resultado"))
            if rot:
                campo("¿El proceso corresponde a este certificado?", rot,
                      None if candado.get("resultado") == "confirmado" else FILL_PEND)
        elif str(p.get("via") or "").upper() == "PRIVADA":
            campo("Proceso de contratación",
                  ("REVISIÓN — RUTA PRIVADA / SUNAT PENDIENTE" if
                   p.get("privada_pendiente") else
                   "NO APLICA — obra privada; la ruta es SUNAT y revisión documental"),
                  FILL_PEND if p.get("privada_pendiente") else None)
        else:
            campo("Proceso de contratación",
                  "No figura en los datos abiertos del Estado (cobertura desde 2018)",
                  FILL_PEND)
        res = ((p["verificacion"] or {}).get("resolucion")) or {}
        aprob = p["aprobacion"] or {}
        if res or aprob:
            campo("Resolución que aprobó el expediente",
                  res.get("numero") or res.get("documento") or aprob.get("nombre"))
            f_aprob, fuente, inferida = _fecha_aprobacion_proyecto(p)
            campo("Fecha de la aprobación", _ddmmaa_larga(f_aprob),
                  FILL_SUPUESTO if (f_aprob and inferida) else
                  (None if f_aprob else FILL_PEND))
            if fuente:
                campo("De dónde sale esa fecha", fuente)
        mods = p["modificaciones"] or []
        if mods and not linea_de_tiempo:
            for m in mods:
                if not isinstance(m, dict):
                    continue
                partes = [str(m.get("tipo") or "Modificación de plazo")]
                if m.get("dias_aprobados"):
                    partes.append(f"{m['dias_aprobados']} días")
                if m.get("causal"):
                    partes.append(str(m["causal"]))
                if m.get("fecha_aprobacion"):
                    partes.append(f"aprobada el {_ddmmaa_larga(m['fecha_aprobacion'])}")
                if m.get("fecha_fin"):
                    partes.append(f"nuevo fin {_ddmmaa_larga(m['fecha_fin'])}")
                campo("Modificación de plazo", " · ".join(partes))
        else:
            campo("Modificaciones de plazo",
                  "InfoObras no registra modificaciones de plazo para este proyecto")

    r += 2
    if linea_de_tiempo:
        # La leyenda va UNA sola vez, antes del primer profesional: es la clave
        # de lectura de todos los bloques, no de cada uno.
        banda(_GANTT_TITULO)
        banda("LEYENDA — COLORES Y MARCAS")
        for color, significado in COLORES_GANTT:
            parrafo(significado, PatternFill("solid", fgColor=color))
        for _marca, significado in MARCAS_GANTT:
            parrafo(significado)
        for nota in NOTAS_GANTT:
            parrafo(nota, FILL_PEND)
        r += 1
        filas, ultima = _pintar_linea_de_tiempo(ws, bloques, r, _NCOL)
        _configurar_impresion_cronologia(ws, _NCOL, ultima)
        return filas

    banda("2 · TABLA COMPARATIVA — periodo declarado frente a los hitos documentales")
    for i, h in enumerate(_CRON_HEAD, start=1):
        c = ws.cell(r, i, h)
        c.font, c.fill, c.border, c.alignment = F_HEAD, FILL_HEAD, BORDER, AL_HEAD
    ws.row_dimensions[r].height = 40
    fila_head = r
    r += 1

    filas = 0
    for prof in espejo.get("profesionales", []):
        for e in prof.get("experiencias", []):
            p = presentacion_cruces(e, fichas.get((prof.get("n_prof"), e.get("n"))),
                                    tipo_evaluacion)
            valores = [prof.get("nombre"), p["n_exp"], p["proyecto"], p["cui"],
                       p["inicio"], p["fin"], p["firma"], p["aprobacion"],
                       p["resp_a"], p["resp_b"], p["motivo"]]
            for i, v in enumerate(valores, start=1):
                c = ws.cell(r, i, _sin_jerga(v) if isinstance(v, str) else v)
                c.font, c.border, c.alignment = F_CELL, BORDER, AL_WRAP
                if i in (5, 6, 7, 8):
                    # Fecha REAL con formato de fecha; sin dato, el guion. Sin
                    # esto la celda mostraba el `AAAA-MM-DD 00:00:00` crudo que
                    # la auditoría marcó en el resto del libro.
                    if isinstance(v, date):
                        c.number_format = FMT_FECHA_LARGA
                    elif v in (None, ""):
                        c.value = "—"
            _pintar_respuesta(ws.cell(r, 9), p["resp_a"])
            _pintar_respuesta(ws.cell(r, 10), p["resp_b"], p["aplica_b"])
            # Violeta = fecha deducida (la aprobación sale del nombre del archivo).
            if p["inferida"]:
                ws.cell(r, 8).fill = FILL_SUPUESTO
            filas += 1
            r += 1

    if not filas:
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=_NCOL_CRON)
        c = ws.cell(r, 1, "No hay experiencias que comparar.")
        c.font, c.fill, c.border, c.alignment = F_CELL, FILL_PEND, BORDER, AL_WRAP
        r += 1
    else:
        ws.auto_filter.ref = (f"A{fila_head}:"
                              f"{get_column_letter(_NCOL_CRON)}{r - 1}")
    return filas


def _ddmmaa_larga(v) -> str:
    """Fecha como dd/mm/aaaa para los textos de la cronología; '—' si no hay.
    Con año de 4 dígitos a propósito: la ficha se lee sola, fuera de una tabla
    con formato de celda."""
    f = _fecha_iso(v)
    return f.strftime("%d/%m/%Y") if f else "—"


def _fecha_aprobacion_proyecto(bloque: dict):
    """`(fecha, fuente, inferida)` de la aprobación del expediente del proyecto,
    con la MISMA precedencia que usa la regla (una sola fuente de verdad)."""
    from reglas.cruces_fechas import fecha_aprobacion_expediente
    return fecha_aprobacion_expediente({
        "aprobacion_expediente": bloque.get("aprobacion"),
        "verificacion_expediente": bloque.get("verificacion"),
    })


# ── Hojas por profesional · cuadro de hitos ──────────────────────────────────

_HITO_HEAD = ["HITO", "DESDE", "HASTA", "DÍAS"]


def _xl(v):
    """Valor seguro para una celda: list/tuple → '; '.join, dict → 'k: v; …', el
    resto tal cual. El espejo permite `requisitos`/`total` como record(any), así que
    un campo válido puede llegar como lista y openpyxl NO escribe listas en celdas
    (ValueError 'Cannot convert [...] to Excel'). Coercer evita tumbar el Excel."""
    if isinstance(v, (list, tuple)):
        return "; ".join(str(x) for x in v)
    if isinstance(v, dict):
        return "; ".join(f"{k}: {val}" for k, val in v.items())
    return _sin_jerga(v)


def _conclusion_expedientes(prof: dict, dias_ef: int, traslape: int,
                            dias_inferidos: int, dias_sin_identificar: int,
                            hay_provisional: bool) -> str:
    """Conclusión del profesional en un concurso de EXPEDIENTES.

    UNA sola fuente de verdad: los días efectivos que acaba de imprimir la
    PARTE 5 — que son los de `reconciliar_resultados_profesionales`. Reglas:

    · Si el backend ya dictó `cumple_backend` (NO CUMPLE o POR VERIFICAR), esa
      línea manda tal cual: ya cita el mismo número.
    · Si no lo dictó, se redacta aquí desde los días efectivos y el mínimo. Un
      «CUMPLE» heredado del evaluador NUNCA sobrevive a unos días efectivos por
      debajo del mínimo (caso real P9: la hoja decía «CUMPLE — 574 días» con un
      mínimo de 24 meses, porque tabla y conclusión contaban cosas distintas).
    · Siempre se dice cuántos de esos días dependen de un CUI inferido o de una
      experiencia sin identificar: es la información que la tabla acaba de
      desglosar y la que decide si el veredicto se puede firmar.
    """
    from orquestador.etapas_reales import _minimo_exigido

    exigido = _minimo_exigido(prof.get("requisitos"))
    minimo_dias, minimo_texto = exigido if exigido else (
        None, prof.get("minimo_exigido_backend"))
    anios_ef = round(anios(dias_ef), 2)
    base = _sin_jerga(prof.get("cumple_backend") or "") or None
    bajo_minimo = bool(minimo_dias) and dias_ef < minimo_dias

    if base and (bajo_minimo or not base.strip().upper().startswith("CUMPLE")):
        texto = base
    elif minimo_dias is None:
        texto = (f"POR VERIFICAR — {dias_ef} días efectivos ({anios_ef} años) "
                 f"tras descontar {traslape} días de traslape; las bases no "
                 f"consignan un mínimo con el que compararlos")
    elif bajo_minimo:
        texto = (f"NO CUMPLE — {dias_ef} días efectivos ({anios_ef} años) tras "
                 f"descontar {traslape} días de traslape, contra un mínimo de "
                 f"{minimo_texto} ({minimo_dias} días)")
    else:
        texto = (f"CUMPLE — {dias_ef} días efectivos ({anios_ef} años) tras "
                 f"descontar {traslape} días de traslape, contra un mínimo de "
                 f"{minimo_texto} ({minimo_dias} días)")

    dependientes = []
    if dias_inferidos:
        dependientes.append(f"{dias_inferidos} días corresponden a identificación "
                            f"inferida por nombre")
    if dias_sin_identificar:
        dependientes.append(f"{dias_sin_identificar} días corresponden a expedientes "
                            f"sin identificar")
    texto = texto.rstrip().rstrip(".")     # `cumple_backend` ya trae su punto final
    if dependientes:
        texto += (". Antes de descontar traslapes, " + " y ".join(dependientes)
                  + "; la identificación no acredita por sí sola el tiempo ni el cargo")
    else:
        texto += (". La identificación del expediente no acredita por sí sola el "
                  "tiempo ni el cargo")
    return texto + "."


def construir_hoja_profesional(
    ws, prof: dict, paralizaciones: Paralizaciones,
    cuis: Optional[dict] = None,
    fichas: Optional[dict] = None,
    revisiones: Optional[dict] = None,
    sunat: Optional[dict] = None,
    certificados: Optional[dict] = None,
    tipo_evaluacion: Optional[str] = None,   # ADR-010 · `_meta.tipo_evaluacion`
    regla_periodos: str = "no_definida",     # #93 · `reglas_evaluacion.periodos_sin_dia`
    bloque_gantt: Optional[dict] = None,
) -> None:
    from resolucion.cui import TIPO_EXPEDIENTES, normalizar_tipo_evaluacion
    from validacion.recalculo import fechas_calculo

    es_exp_prof = normalizar_tipo_evaluacion(tipo_evaluacion) == TIPO_EXPEDIENTES
    cuis = cuis or {}
    fichas = fichas or {}
    revisiones = revisiones or {}
    sunat = sunat or {}
    certificados = certificados or {}
    # A:D hitos · F:K obra+valorizaciones · M:P emisor SUNAT · R:U histórico SUNAT
    # (los dos cuadros del emisor van pegados) · W:Z representante de obra
    anchos = {"A": 52, "B": 14, "C": 14, "D": 10, "E": 2,
              "F": 5, "G": 18, "H": 14, "I": 18, "J": 14, "K": 13, "L": 2,
              "M": 16, "N": 12, "O": 18, "P": 12, "Q": 2,
              "R": 17, "S": 12, "T": 12, "U": 14, "V": 2,
              "W": 17, "X": 12, "Y": 22, "Z": 14}
    for col, w in anchos.items():
        ws.column_dimensions[col].width = w
    n_prof = prof.get("n_prof")
    r = 1

    # ancho útil (caracteres aprox.) de la banda combinada A:D, para envolver
    # títulos largos sin truncarlos.
    _ancho_banda = sum({"A": 52, "B": 14, "C": 14, "D": 10}.values())

    def banda(texto, font=F_PROF, fill=FILL_PROF, h=20):
        nonlocal r
        texto = _sin_jerga(texto)
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=4)
        c = ws.cell(r, 1, texto)
        c.font, c.fill = font, fill
        c.alignment = Alignment(vertical="center", wrap_text=True)
        # altura proporcional al nº de líneas que ocupará el texto envuelto
        lineas = max(1, -(-len(str(texto)) // _ancho_banda))  # ceil
        ws.row_dimensions[r].height = max(h, lineas * 15 + 4)
        r += 1

    def fila(hito, desde, hasta, dias_v, *, bold=False, fill=None):
        nonlocal r
        valores = [_sin_jerga(hito), _sin_jerga(desde), _sin_jerga(hasta), dias_v]
        for i, v in enumerate(valores, start=1):
            c = ws.cell(r, i, v)
            c.font = F_BOLD if bold else F_CELL
            c.border, c.alignment = BORDER, AL_WRAP
            if i in (2, 3) and isinstance(v, date):
                c.number_format = FMT_FECHA   # presentación dd/mm/yy
            if i == 4 and isinstance(v, (int, float)):
                c.number_format = FMT_INT
            if v not in (None, "") and fill is not None:
                c.fill = fill
        r += 1

    def render_obra(top: int, fx: dict, ini, fin) -> int:
        """Ficha de la obra + TODAS sus valorizaciones, en columnas F:J desde la
        fila `top`. Resalta en amarillo los meses dentro del periodo del
        certificado. Devuelve la última fila usada."""
        rr = top
        # ADR-010 · el CAMINO con que el backend enrutó la experiencia decide qué es
        # esta ficha: la obra que este cargo supervisó/ejecutó, o el proyecto cuyo
        # EXPEDIENTE elaboró (y cuya construcción posterior es solo contexto).
        from resolucion.cui import TIPO_EXPEDIENTES, normalizar_tipo_evaluacion
        es_exped = (fx.get("camino") == "expediente"
                    or normalizar_tipo_evaluacion(tipo_evaluacion) == TIPO_EXPEDIENTES)
        ws.merge_cells(start_row=rr, start_column=6, end_row=rr, end_column=10)
        c = ws.cell(rr, 6, ("PROYECTO CUYO EXPEDIENTE TÉCNICO ELABORÓ ESTE CARGO "
                            "(InfoObras / MEF)" if es_exped else
                            "OBRA EN INFOOBRAS (origen del análisis)"))
        c.font, c.fill, c.alignment = F_HEAD, FILL_HEAD, AL_HEAD
        rr += 1

        def kv(label, value, fmt=None):
            nonlocal rr
            ws.merge_cells(start_row=rr, start_column=6, end_row=rr, end_column=7)
            cl = ws.cell(rr, 6, label); cl.font, cl.border = F_BOLD, BORDER
            cl.alignment = Alignment(vertical="top", wrap_text=True)
            ws.merge_cells(start_row=rr, start_column=8, end_row=rr, end_column=10)
            cv = ws.cell(rr, 8, value); cv.font, cv.border, cv.alignment = F_CELL, BORDER, AL_WRAP
            if fmt and isinstance(value, (int, float, date)):
                cv.number_format = fmt
            # H:J ≈ 46 caracteres y una celda COMBINADA no auto-ajusta su alto en
            # Excel: el nombre de obra (150+ car.) se vería como una sola línea
            # cortada. Solo AUMENTA la altura (no pisa la de otras bandas de la fila).
            if isinstance(value, str) and len(value) > 46:
                alto = (-(-len(value) // 46)) * 13 + 4
                ws.row_dimensions[rr].height = max(ws.row_dimensions[rr].height or 15, alto)
            rr += 1

        # PRIMERO el nombre: es lo único que deja auditar de un vistazo si la obra
        # emparejada es la del certificado. Sin él, un CUI mal resuelto (un hospital
        # de otra región) pasa inadvertido detrás de un código y un monto correctos.
        kv("Nombre del proyecto" if es_exped else "Nombre de la obra",
           _sin_jerga(fx.get("obra_nombre") or "— (InfoObras no devolvió el nombre)"))
        # #63: un CUI puede tener varios registros de obra (plan de contingencia,
        # obra principal, saldos, ET) — cuando los hay, la ficha lo DECLARA para
        # que el evaluador sepa que se eligió uno entre varios (caso LaFora: el
        # ing. llegó a esa verdad por Datos Generales del portal; se la damos aquí).
        if (fx.get("registros_cui") or 0) > 1:
            kv("Registros bajo este CUI",
               f"{fx['registros_cui']} obras relacionadas — se usó la de la fase "
               "del certificado (ver nombre arriba)")
        kv("Código InfoObras", fx.get("codigo_infoobras") or "—")
        kv("CUI", fx.get("cui") or "—")
        if not es_exped:
            kv("Estado de obra", _sin_jerga(fx.get("estado") or "—"))
            kv("Monto informado en la ficha (S/)", fx.get("monto") if fx.get("monto") is not None else "—", FMT_SOLES)
            kv("Inicio de obra", _fecha_iso(fx.get("fecha_inicio")) or "—", FMT_FECHA)
            kv("Fin de obra", _fecha_iso(fx.get("fecha_fin")) or "—", FMT_FECHA)
        inventario = fx.get("inventario_documental") or {}
        documentos = inventario.get("documentos") if isinstance(inventario, dict) else None
        if isinstance(documentos, list):
            # Para un expediente no cuentan las valorizaciones de la construcción.
            n_encontrados = len({str(d.get("id") or d.get("url") or i)
                                 for i, d in enumerate(documentos)
                                 if isinstance(d, dict)
                                 and not (es_exped and d.get("tipo") == "valorizacion")})
        elif isinstance(fx.get("documentos_encontrados"), int) and not es_exped:
            n_encontrados = fx["documentos_encontrados"]
        elif es_exped:
            n_encontrados = 0
        else:
            n_encontrados = sum(int(v.get("docs") or 0)
                                for v in (fx.get("valorizaciones") or [])
                                if isinstance(v, dict))
        texto_encontrados = ("No se encontraron documentos" if n_encontrados == 0 else
                             "1 archivo encontrado" if n_encontrados == 1 else
                             f"{n_encontrados} archivos encontrados")
        kv("Documentos encontrados", texto_encontrados)
        rr += 1

        # Un expediente no tiene valorizaciones propias: las de la construcción
        # posterior no se listan ni disparan controles de acumulado/monto/fechas.
        vals_crudas = [] if es_exped else (fx.get("valorizaciones") or [])
        vals, vistas = [], set()
        for v in vals_crudas:
            huella = json.dumps(v, sort_keys=True, default=str, ensure_ascii=False)
            if huella not in vistas:
                vistas.add(huella)
                vals.append(v)
        vals.sort(key=lambda v: (v.get("anio") or 0, v.get("mes") or 0), reverse=True)
        if len(vals_crudas) != len(vals):
            kv("Control de datos", f"Se ocultaron {len(vals_crudas) - len(vals)} fila(s) "
               "duplicada(s) idéntica(s) del portal; el JSON de origen se conserva.")
        acumulados = [v.get("valorizado_real") for v in reversed(vals)
                      if isinstance(v.get("valorizado_real"), (int, float))]
        retrocesos = sum(b < a for a, b in zip(acumulados, acumulados[1:]))
        if retrocesos:
            kv("Control de acumulados", f"⚠ El acumulado retrocede en {retrocesos} mes(es); "
               "se muestra tal como lo publicó InfoObras y requiere revisión.")
        max_val = max(acumulados, default=None)
        monto = fx.get("monto")
        if isinstance(monto, (int, float)) and max_val and max(monto, max_val) / max(min(monto, max_val), 1) >= 5:
            kv("Control de monto", "⚠ El monto de la ficha difiere materialmente de la última "
               "valorización; podría corresponder al contrato de supervisión.")
        fin_obra = _fecha_iso(fx.get("fecha_fin"))
        meses_posteriores = [v for v in vals if fin_obra and v.get("anio") and v.get("mes")
                             and date(v["anio"], v["mes"], 1) > date(fin_obra.year, fin_obra.month, 1)]
        if meses_posteriores:
            kv("Control de fechas", "⚠ Hay valorizaciones posteriores al fin de obra informado. "
               "El cálculo usa la ventana de valorizaciones; confirmar si el fin fue ampliado.")
        verif = fx.get("verificacion_expediente")
        aprob = fx.get("aprobacion_expediente")
        # EXPEDIENTE técnico: la experiencia es de ELABORACIÓN del expediente, no de
        # ejecución de obra. En su MISMO lugar (mismo formato, distinta info) va la
        # verificación: contrato/contratista/resolución del MEF + aprobación InfoObras.
        # La decisión la toma el CAMINO con que el backend enrutó la experiencia
        # (ADR-010: parámetro del concurso), no la existencia de datos en el MEF:
        # antes, un expediente cuyo CUI no tenía contrato publicado caía a pintar
        # las valorizaciones de la CONSTRUCCIÓN como si fuera obra (caso real, 5-sep).
        # `es_exped` se calculó al inicio de la ficha.
        if verif or aprob or es_exped:
            ws.merge_cells(start_row=rr, start_column=6, end_row=rr, end_column=11)
            c = ws.cell(rr, 6, "EXPEDIENTE TÉCNICO — verificación (no hay valorizaciones: "
                               "este cargo elaboró el expediente, no ejecutó la obra)")
            c.font, c.fill = F_PARTE, FILL_PARTE
            c.alignment = Alignment(vertical="center", wrap_text=True)
            rr += 1
            if not verif and not aprob:
                situacion_mef = fuente_mef(fx)
                ws.merge_cells(start_row=rr, start_column=6, end_row=rr, end_column=11)
                c = ws.cell(rr, 6, " · ".join(x for x in (
                    situacion_mef.get("contrato"), situacion_mef.get("resolucion"),
                    "Los datos de ejecución no acreditan la elaboración del expediente."
                ) if x and x != "—"))
                c.font, c.fill, c.alignment = F_CELL, FILL_PEND, AL_WRAP
                ws.row_dimensions[rr].height = 42
                rr += 1
            if aprob:   # respaldo por la "Aprobación del proyecto" de InfoObras
                f = aprob.get("fecha")
                fm = f"{f[8:10]}/{f[5:7]}/{f[0:4]}" if f and len(f) == 10 else None
                msg = ("Aprobación del proyecto (InfoObras)" + (f" — {fm}" if fm else "")
                       + (f" · {aprob['nombre']}" if aprob.get("nombre") else ""))
                ws.merge_cells(start_row=rr, start_column=6, end_row=rr, end_column=11)
                c = ws.cell(rr, 6, msg); c.font, c.alignment, c.fill = F_CELL, AL_WRAP, FILL_VALOR
                rr += 1
            if verif:   # contraste contra el MEF (Banco de Inversiones)
                ct, cn = verif.get("contratista") or {}, verif.get("contrato") or {}
                rs = verif.get("resolucion") or {}
                _f = cn.get("fecha")
                _ffmt = f"{_f[8:10]}/{_f[5:7]}/{_f[0:4]}" if _f and len(_f) == 10 else None

                def _fila(label, valor, veredicto=None, fmt=None):
                    nonlocal rr
                    ws.merge_cells(start_row=rr, start_column=6, end_row=rr, end_column=7)
                    cl = ws.cell(rr, 6, label); cl.font, cl.border = F_BOLD, BORDER
                    ws.merge_cells(start_row=rr, start_column=8, end_row=rr, end_column=9)
                    cv = ws.cell(rr, 8, valor if valor not in (None, "") else "—")
                    cv.font, cv.border, cv.alignment = F_CELL, BORDER, AL_WRAP
                    if fmt and isinstance(valor, (int, float)):
                        cv.number_format = fmt
                    ws.merge_cells(start_row=rr, start_column=10, end_row=rr, end_column=11)
                    cver = ws.cell(rr, 10, _VER_TXT.get(veredicto, "") if veredicto else "")
                    cver.font, cver.border, cver.alignment = F_CELL, BORDER, AL_HEAD
                    if veredicto == "ok":
                        cver.fill = FILL_VALOR
                    rr += 1

                ws.merge_cells(start_row=rr, start_column=6, end_row=rr, end_column=11)
                c = ws.cell(rr, 6, "VERIFICACIÓN SEACE / MEF (Banco de Inversiones)")
                c.font, c.fill = F_HEAD, FILL_HEAD; c.alignment = AL_HEAD
                rr += 1
                _fila("Contratista (MEF)", ct.get("valor"), ct.get("veredicto"))
                _fila("N° de contrato", cn.get("numero"), cn.get("veredicto"))
                if cn.get("monto") is not None:
                    _fila("Monto del contrato (S/)", cn.get("monto"), None, FMT_SOLES)
                if _ffmt:
                    _fila("Fecha del contrato", _ffmt)
                _fila("Resolución de aprobación", rs.get("numero") or rs.get("documento"),
                      rs.get("veredicto"))
                # Lo que dice la propia resolución, leída del PDF (capa de texto u
                # OCR local): fecha oficial y consultor nombrado. Es el contraste
                # que faltaba para los expedientes: la fecha alimenta la Regla B y el
                # consultor confirma o desmiente al emisor del certificado.
                lect = fx.get("resolucion_aprobacion")
                if isinstance(lect, dict):
                    if lect.get("legible"):
                        _f_res = _fecha_iso(lect.get("fecha"))
                        _fila("Fecha de la resolución (leída del documento)",
                              _f_res or "no se pudo leer una fecha", None, FMT_FECHA)
                        cons = ", ".join(lect.get("consultores") or [])[:160]
                        _ver_cons = {"confirma": "ok", "nombra_otro": "discrepancia"}.get(
                            lect.get("coincide_emisor"))
                        _fila("Consultor según la resolución",
                              cons or "la resolución no nombra a quien elaboró el expediente",
                              _ver_cons)
                        if lect.get("numero_citado_coincide") is not None:
                            _fila("N° de resolución citado en el certificado",
                                  lect.get("numero_citado") or "—",
                                  "ok" if lect["numero_citado_coincide"] else "discrepancia")
                    else:
                        _fila("Lectura de la resolución",
                              "el PDF es un escaneo sin texto reconocible — se adjunta en el ZIP")
                _fila("CUI confirmado (MEF)", verif.get("cui_confirmado"))
                fuentes = ", ".join(verif.get("fuentes") or [])
                if fuentes:
                    ws.merge_cells(start_row=rr, start_column=6, end_row=rr, end_column=11)
                    ws.cell(rr, 6, f"Fuente: {fuentes}").font = F_CELL
                    rr += 1
        else:
            ws.merge_cells(start_row=rr, start_column=6, end_row=rr, end_column=11)
            c = ws.cell(rr, 6, "VALORIZACIONES — en amarillo, las del periodo del certificado")
            c.font, c.fill = F_PARTE, FILL_PARTE
            c.alignment = Alignment(vertical="center", wrap_text=True)
            rr += 1
            for i, h in enumerate(["N°", "AÑO / MES", "AVANCE FÍSICO REAL",
                                   "VALORIZADO REAL (S/)", "ESTADO", "ARCHIVOS ENCONTRADOS"], start=6):
                cc = ws.cell(rr, i, h)
                cc.font, cc.fill, cc.border, cc.alignment = F_HEAD, FILL_HEAD, BORDER, AL_HEAD
            rr += 1
            for n, v in enumerate(vals, start=1):
                anio, mes = v.get("anio") or 0, v.get("mes") or 0
                resaltar = _mes_en_rango(anio, mes, ini, fin)
                paraliz = "paraliz" in str(v.get("estado") or "").lower()
                # Esta columna describe lo que InfoObras PUBLICÓ para el hito,
                # no el avance operativo de la descarga. `docs` está disponible
                # desde el parseo; por eso nunca debe degradarse a "Pendiente"
                # ni variar si luego falla o todavía no empieza a bajar el ZIP.
                ndoc = int(v.get("docs") or 0)
                texto_docs = ("No se encontraron documentos" if ndoc == 0 else
                              "1 archivo encontrado" if ndoc == 1 else
                              f"{ndoc} archivos encontrados")
                celdas = [n, f"{anio} / {_MES_ES.get(mes, mes)}",
                          v.get("fisico_real"), v.get("valorizado_real"), _sin_jerga(v.get("estado") or ""),
                          texto_docs]
                for i, val in enumerate(celdas, start=6):
                    cc = ws.cell(rr, i, val)
                    cc.font = F_CELL_ROJO if paraliz else F_CELL   # rojo: mes paralizado
                    cc.border, cc.alignment = BORDER, AL_WRAP
                    if i == 8 and isinstance(val, (int, float)):
                        cc.number_format = FMT_PCT
                    if i == 9 and isinstance(val, (int, float)):
                        cc.number_format = FMT_SOLES
                    if resaltar:
                        cc.fill = FILL_VALOR
                rr += 1
            if not vals:
                ws.cell(rr, 6, "Sin valorizaciones registradas en InfoObras").font = F_CELL
                rr += 1

        # modificaciones de plazo: contexto para el evaluador (explican por qué la
        # obra siguió "viva" más allá de sus valorizaciones). NO cuentan como avance.
        mods = fx.get("modificaciones_plazo") or []
        if mods and not es_exped:
            rr += 1
            ws.merge_cells(start_row=rr, start_column=6, end_row=rr, end_column=10)
            c = ws.cell(rr, 6, "MODIFICACIONES DE PLAZO — ampliaciones/suspensiones "
                               "(contexto: NO cuentan como avance, no hay valorización que las respalde)")
            c.font, c.fill = F_PARTE, FILL_PARTE
            c.alignment = Alignment(vertical="center", wrap_text=True)
            rr += 1
            for i, h in enumerate(["N°", "TIPO", "DÍAS", "APROBACIÓN", "NUEVO FIN"], start=6):
                cc = ws.cell(rr, i, h)
                cc.font, cc.fill, cc.border, cc.alignment = F_HEAD, FILL_HEAD, BORDER, AL_HEAD
            rr += 1
            for n, m in enumerate(mods, start=1):
                celdas = [n, m.get("tipo") or "", m.get("dias"),
                          _fecha_iso(m.get("fecha_aprobacion")), _fecha_iso(m.get("fecha_fin"))]
                for i, val in enumerate(celdas, start=6):
                    cc = ws.cell(rr, i, val)
                    cc.font, cc.border, cc.alignment = F_CELL, BORDER, AL_WRAP
                    if i in (9, 10) and isinstance(val, date):
                        cc.number_format = FMT_FECHA
                rr += 1
        return rr - 1

    def render_seace(top: int, datos: dict) -> int:
        """Disponibilidad documental de Bases Integradas y contrato."""
        rr = top
        ws.merge_cells(start_row=rr, start_column=6, end_row=rr, end_column=11)
        c = ws.cell(rr, 6, "DOCUMENTOS DEL PROCESO (SEACE)")
        c.font, c.fill, c.alignment = F_HEAD, FILL_HEAD, AL_HEAD
        rr += 1

        estado = datos.get("estado")
        if estado != "seleccionado":
            textos = {
                "fuente_no_disponible": "Por confirmar — la fuente no respondió.",
                "sin_procesos": "No disponible en datos abiertos (cobertura desde 2018).",
                "sin_tipo": "No se encontró un proceso del tipo correspondiente a la experiencia.",
            }
            texto = textos.get(estado, datos.get("motivo") or "Por confirmar.")
            ws.merge_cells(start_row=rr, start_column=6, end_row=rr, end_column=11)
            c = ws.cell(rr, 6, texto)
            c.font, c.fill, c.border, c.alignment = F_CELL, FILL_PEND, BORDER, AL_WRAP
            ws.row_dimensions[rr].height = max(15, (-(-len(texto) // 70)) * 13 + 2)
            return rr

        etiquetas = {
            "expediente": "Expediente técnico",
            "supervision": "Supervisión",
            "ejecucion": "Ejecución de obra",
        }
        tipo = etiquetas.get(datos.get("proceso_objeto"), datos.get("proceso_objeto") or "—")
        filas = [("Tipo de proceso", tipo)]
        # F5 — rótulo de confianza. `None` cuando el job es anterior al candado:
        # entonces el bloque se dibuja exactamente como antes.
        candado = datos.get("candado") if isinstance(datos.get("candado"), dict) else {}
        rotulo_candado = _rotulo_candado_seace(candado.get("resultado"))
        docs = datos.get("docs") or {}
        for clave, etiqueta in (("bases", "Bases Integradas"), ("contrato", "Contrato firmado")):
            disponible = (docs.get(clave) or {}).get("estado") == "disponible"
            filas.append((etiqueta, "1 archivo encontrado"
                          if disponible else "No disponible en datos abiertos"))
        if datos.get("fecha_suscripcion"):
            filas.append(("Fecha de firma", datos["fecha_suscripcion"]))
        if rotulo_candado:
            filas.append(("Correspondencia con el certificado", rotulo_candado))
        entidad = (datos.get("proceso") or {}).get("entidad_convocante")
        if entidad:
            filas.append(("Entidad convocante", entidad))
        for etiqueta, valor in filas:
            ws.merge_cells(start_row=rr, start_column=6, end_row=rr, end_column=7)
            cl = ws.cell(rr, 6, etiqueta)
            cl.font, cl.border, cl.alignment = F_BOLD, BORDER, AL_WRAP
            ws.merge_cells(start_row=rr, start_column=8, end_row=rr, end_column=11)
            cv = ws.cell(rr, 8, valor)
            cv.font, cv.border, cv.alignment = F_CELL, BORDER, AL_WRAP
            # Amarillo = «por verificar» (convención vigente): solo cuando el
            # candado NO confirmó. Un `confirmado` va sin resalte.
            if (etiqueta == "Correspondencia con el certificado"
                    and candado.get("resultado") != "confirmado"):
                cv.fill = FILL_PEND
            rr += 1
        if rotulo_candado and candado.get("resultado") != "confirmado":
            texto = str(candado.get("motivo") or "")
            if texto:
                ws.merge_cells(start_row=rr, start_column=6, end_row=rr, end_column=11)
                c = ws.cell(rr, 6, texto)
                c.font, c.fill, c.border, c.alignment = F_CELL, FILL_PEND, BORDER, AL_WRAP
                ws.row_dimensions[rr].height = max(15, (-(-len(texto) // 70)) * 13 + 2)
                rr += 1
        if datos.get("ambiguo"):
            texto = ("Por confirmar — hay varios procesos del mismo tipo; se eligió "
                     "el más reciente. Verificar la carátula de los documentos encontrados.")
            ws.merge_cells(start_row=rr, start_column=6, end_row=rr, end_column=11)
            c = ws.cell(rr, 6, texto)
            c.font, c.fill, c.border, c.alignment = F_CELL, FILL_PEND, BORDER, AL_WRAP
            ws.row_dimensions[rr].height = max(15, (-(-len(texto) // 70)) * 13 + 2)
            rr += 1
        return rr - 1

    def render_revision(top: int, motivo: str, accion: Optional[str] = None,
                        lecturas: Optional[list] = None) -> int:
        """Bloque para una experiencia que NO se cruzó: explica por qué quedó en
        revisión humana, en vez de dejar la columna de la obra vacía. El marcador
        especial "[PRIVADA]" pinta el bloque de cliente/obra privada (no es
        revisión: InfoObras no registra obra privada; el respaldo es el certificado)."""
        rr = top
        if str(motivo).startswith("[PRIVADA_PENDIENTE]"):
            detalle = str(motivo).removeprefix("[PRIVADA_PENDIENTE]").strip()
            ws.merge_cells(start_row=rr, start_column=6, end_row=rr, end_column=10)
            c = ws.cell(rr, 6, "REVISIÓN — RUTA PRIVADA / SUNAT PENDIENTE")
            c.font, c.fill, c.alignment = F_AVISO, FILL_AVISO, AL_HEAD
            rr += 1
            ws.merge_cells(start_row=rr, start_column=6, end_row=rr + 3, end_column=10)
            c = ws.cell(rr, 6, f"{_mayus_inicial(detalle)}.\n\nAcción: "
                               f"{accion or _ACCION_GENERICA}.")
            c.font, c.fill, c.border, c.alignment = F_CELL, FILL_AVISO, BORDER, AL_WRAP
            rr += 4
            return rr - 1
        if str(motivo).startswith("[PRIVADA]"):
            ws.merge_cells(start_row=rr, start_column=6, end_row=rr, end_column=10)
            c = ws.cell(rr, 6, "OBRA / CLIENTE PRIVADO")
            c.font, c.fill, c.alignment = F_HEAD, FILL_HEAD, AL_HEAD
            rr += 1
            ws.merge_cells(start_row=rr, start_column=6, end_row=rr + 3, end_column=10)
            c = ws.cell(rr, 6, "Experiencia con cliente/obra privada: InfoObras, MEF "
                               "y SEACE no aplican, por lo que no hay búsqueda de CUI "
                               "ni cruce de valorizaciones.\n\nLa ruta de verificación "
                               "es SUNAT y la revisión documental del certificado "
                               "presentado.")
            c.font, c.border, c.alignment = F_CELL, BORDER, AL_WRAP
            rr += 4
            return rr - 1
        ws.merge_cells(start_row=rr, start_column=6, end_row=rr, end_column=10)
        c = ws.cell(rr, 6, "EXPERIENCIA EN REVISIÓN")
        c.font, c.fill, c.alignment = F_HEAD, FILL_HEAD, AL_HEAD
        rr += 1
        ws.merge_cells(start_row=rr, start_column=6, end_row=rr + 3, end_column=10)
        c = ws.cell(rr, 6, f"{_mayus_inicial(motivo)}.\n\nAcción: "
                           f"{accion or _ACCION_SIN_OBRA}.")
        c.font, c.border, c.alignment = F_CELL, BORDER, AL_WRAP
        rr += 4
        # Lo que dice la resolución de aprobación de cada candidato (expedientes):
        # evidencia oficial para decidir sin salir del Excel.
        for lect in (lecturas or []):
            if not isinstance(lect, dict):
                continue
            f = str(lect.get("fecha") or "")
            fecha = f"{f[8:10]}/{f[5:7]}/{f[0:4]}" if len(f) == 10 else "sin fecha legible"
            ver = lect.get("coincide_emisor")
            if not lect.get("legible"):
                dice = "resolución de aprobación escaneada sin texto reconocible"
                fill = FILL_PEND
            elif ver == "confirma":
                dice = f"resolución del {fecha}: nombra al emisor del certificado como consultor"
                fill = FILL_OK
            elif ver == "nombra_otro":
                dice = (f"resolución del {fecha}: nombra a "
                        f"{str(lect.get('detalle_emisor') or 'otra empresa')[:70]}, no al emisor")
                fill = FILL_ALERTA
            else:
                dice = f"resolución del {fecha}: no nombra a quien elaboró el expediente"
                fill = FILL_PEND
            ws.merge_cells(start_row=rr, start_column=6, end_row=rr, end_column=10)
            c = ws.cell(rr, 6, f"Candidato CUI {lect.get('cui')} — "
                               f"{_sin_jerga(str(lect.get('nombre_obra') or ''))[:70]} → {dice}")
            c.font, c.fill, c.border, c.alignment = F_CELL, fill, BORDER, AL_WRAP
            ws.row_dimensions[rr].height = 30
            rr += 1
        return rr - 1

    def render_aviso_revision(top: int, motivo: str, accion: Optional[str] = None) -> int:
        """Banda de ALERTA (F:K) ENCIMA del bloque de la obra, cuando la experiencia
        sigue en revisión Y el resolver además propuso una obra.

        Va ARRIBA y no debajo a propósito: la banda de revisión y el bloque de la
        obra ocupan la misma franja de columnas, y esto es la advertencia con la que
        hay que leer la ficha que viene a continuación. Debajo quedaría al final de
        las valorizaciones (decenas de filas más abajo), o sea invisible — que es
        justo el bug.

        Dice el MOTIVO y la ACCIÓN reales del item, no una narrativa fija sobre la
        identidad de la obra: los ItemRevision los crean 4 etapas distintas y la
        mayoría no habla de la obra (p. ej. "no se contó una experiencia por una
        fecha sin verificar"). Gritar "la obra no está confirmada, pegue el CUI"
        sobre una obra bien identificada es un falso positivo, y un aviso que miente
        enseña al evaluador a ignorar la banda. Devuelve la última fila usada."""
        rr = top
        if str(motivo).startswith("[PRIVADA]"):
            motivo = ("declarada como obra/cliente privado y aun así se halló una "
                      "obra pública con ese nombre")
            accion = accion or ("confirmar si la obra es pública — InfoObras no "
                                "registra obra privada")
        titulo = f"⚠ EXPERIENCIA EN REVISIÓN — {_mayus_inicial(motivo)}"
        ws.merge_cells(start_row=rr, start_column=6, end_row=rr, end_column=11)
        c = ws.cell(rr, 6, titulo)
        c.font, c.fill = F_AVISO, FILL_AVISO
        c.alignment = Alignment(vertical="center", wrap_text=True)
        # esta fila es la MISMA del título de la experiencia, que banda() ya
        # dimensionó según su texto envuelto: solo AUMENTA (fijarla cortaría el
        # nombre del proyecto justo en la experiencia dudosa).
        ws.row_dimensions[rr].height = max(ws.row_dimensions[rr].height or 15,
                                           (-(-len(titulo) // 78)) * 14 + 6)
        rr += 1
        ws.merge_cells(start_row=rr, start_column=6, end_row=rr, end_column=11)
        c = ws.cell(rr, 6, f"Acción: {_accion_visible(accion) or _ACCION_GENERICA}.")
        c.font, c.fill, c.border, c.alignment = F_CELL, FILL_AVISO, BORDER, AL_WRAP
        ws.row_dimensions[rr].height = max(ws.row_dimensions[rr].height or 15,
                                           (-(-len(str(c.value)) // 78)) * 13 + 2)
        rr += 1
        return rr - 1

    # ── Anti-duplicado del detalle de obra (issue #46 · punto 6) ─────────────
    # Una propuesta puede traer la MISMA obra muchas veces en la hoja de un mismo
    # profesional: p. ej. 4 órdenes de servicio consecutivas del mismo contrato,
    # cada una certificando las mismas 3 obras → 12 bloques idénticos.
    #
    # La PRIMERA versión de este colapso se retiró porque BORRABA EVIDENCIA:
    # colapsaba por CUI y afirmaba "la ficha y las valorizaciones están en
    # Experiencia N" aunque el CUI apuntara a OTRA obra (`_fetch_obra` desambigua
    # por la ventana del certificado) y aunque el bloque destino no tuviera
    # valorizaciones — una AUSENCIA de dato renderizada como puntero a evidencia.
    #
    # Este rediseño no colapsa por identidad, colapsa por CONTENIDO:
    #   · clave de la obra = (CUI, código InfoObras) — el CUI solo no basta;
    #   · huella = TODO lo que el bloque pintaría (campos de la ficha, cada
    #     valorización con sus importes, la verificación/aprobación del
    #     expediente, las modificaciones de plazo y el representante de obra) y,
    #     cuando hay valorizaciones, el periodo del certificado — ver
    #     `_huella_obra`;
    #   · solo colapsa si clave Y huella coinciden exactas → lo omitido es
    #     literalmente idéntico a lo ya pintado, y el reemplazo dice QUÉ hay allá
    #     y en qué fila.
    # Ante cualquier diferencia se pinta completo: repetir es inofensivo,
    # colapsar mal borra evidencia.
    #
    # El registro es una variable LOCAL de esta función → vive por HOJA de
    # profesional. Cada profesional arranca de cero y jamás se referencia la hoja
    # de otro (un "ver Experiencia 3" que apunte a otra pestaña es inservible).
    _obras_pintadas: dict[tuple, list[dict]] = {}

    def _canon(v) -> str:
        """Forma canónica y comparable de un valor anidado (dict/list/fechas)."""
        return json.dumps(v, sort_keys=True, default=str, ensure_ascii=False)

    def _clave_obra(fx: Optional[dict]) -> Optional[tuple]:
        """Identidad de la obra que se pinta: (CUI, código InfoObras). Si falta
        cualquiera de los dos NO hay identidad comprobable → None, y sin clave
        nunca se colapsa."""
        cui = str((fx or {}).get("cui") or "").strip()
        cod = str((fx or {}).get("codigo_infoobras") or "").strip()
        return (cui, cod) if (cui and cod) else None

    def _tipo_bloque(fx: dict, vals: list) -> str:
        """Qué variante pinta `render_obra`: la tabla de valorizaciones o el
        bloque de EXPEDIENTE TÉCNICO. Misma condición que allá."""
        verif, aprob = fx.get("verificacion_expediente"), fx.get("aprobacion_expediente")
        return "expediente" if (verif or (aprob and not vals)) else "valorizaciones"

    def _huella_obra(fx: Optional[dict], ini, fin) -> tuple:
        """QUÉ se pintaría en el bloque, no solo de qué obra es: cada campo que
        `render_obra` (y el `render_representante` que lo acompaña) escriben.

        Sobre el PERIODO: dentro del bloque lo único que depende de él es el
        resaltado amarillo de las valorizaciones, así que se exige que el periodo
        coincida exacto siempre que haya valorizaciones. Cuando NO las hay, el
        bloque no muestra nada que dependa del periodo (dice literalmente "sin
        valorizaciones registradas"), y exigir ahí igualdad de periodo dejaría el
        colapso inerte justo en el caso que motiva esta función — 4 órdenes de
        servicio consecutivas, con periodos distintos por definición, sobre obras
        sin valorizar. La marca de resaltado NO va en la huella por redundante:
        es función de (anio, mes, ini, fin) y los cuatro ya están aquí.

        Tampoco va el tipo de bloque (valorizaciones vs expediente): se deriva de
        `verificacion_expediente`, `aprobacion_expediente` y si hay o no
        valorizaciones, y los tres ya están."""
        fx = fx or {}
        vals = sorted(fx.get("valorizaciones") or [],
                      key=lambda v: (v.get("anio") or 0, v.get("mes") or 0), reverse=True)
        filas_val = tuple(
            (v.get("anio"), v.get("mes"), v.get("fisico_real"), v.get("valorizado_real"),
             v.get("estado"), v.get("docs"))
            for v in vals)
        return (
            fx.get("obra_nombre"), fx.get("estado"), fx.get("monto"),
            fx.get("fecha_inicio"), fx.get("fecha_fin"),
            _canon(fx.get("verificacion_expediente")),
            _canon(fx.get("aprobacion_expediente")),
            filas_val,
            _canon(fx.get("modificaciones_plazo") or []),
            _canon(fx.get("representante_obra")),
        )

    def _registrar_obra(fx: Optional[dict], ini, fin, etiqueta: str, fila: int) -> None:
        """Anota que en `fila` quedó pintado el bloque completo de esta obra con
        esta huella. Se guarda una entrada por huella DISTINTA: si la misma obra
        se pintó con contenidos distintos (p. ej. la ficha recargó con más
        valorizaciones), cada variante puede recibir sus propias repeticiones."""
        clave = _clave_obra(fx)
        if not clave:
            return
        huella = _huella_obra(fx, ini, fin)
        lista = _obras_pintadas.setdefault(clave, [])
        if not any(x["huella"] == huella for x in lista):
            lista.append({"etiqueta": etiqueta, "fila": fila, "huella": huella})

    def _ya_pintada(fx: Optional[dict], ini, fin) -> Optional[dict]:
        """El bloque ya pintado en ESTA hoja que es idéntico al que tocaría
        pintar, o None (ante la mínima diferencia, se pinta completo)."""
        clave = _clave_obra(fx)
        if not clave:
            return None
        huella = _huella_obra(fx, ini, fin)
        for x in _obras_pintadas.get(clave, []):
            if x["huella"] == huella:
                return x
        return None

    def render_ya_pintada(top: int, fx: dict, ref: dict) -> int:
        """Reemplazo compacto del detalle de una obra YA pintada, IDÉNTICA, más
        arriba en esta MISMA hoja. Solo se usa con huella coincidente exacta, así
        que no oculta ni un dato: dice qué hay allá (ficha con N valorizaciones /
        sin valorizaciones / verificación de expediente) y en qué fila."""
        rr = top
        vals = fx.get("valorizaciones") or []
        if _tipo_bloque(fx, vals) == "expediente":
            que = "la ficha y la verificación del expediente técnico"
        elif len(vals) == 1:
            que = "la ficha y su única valorización"
        elif vals:
            que = f"la ficha y sus {len(vals)} valorizaciones"
        else:
            que = "la ficha (InfoObras no registra valorizaciones de esta obra)"
        ws.merge_cells(start_row=rr, start_column=6, end_row=rr, end_column=11)
        c = ws.cell(rr, 6, "OBRA YA DETALLADA EN ESTA HOJA")
        c.font, c.fill, c.alignment = F_HEAD, FILL_HEAD, AL_HEAD
        rr += 1
        txt = (f"Misma obra (código InfoObras {fx.get('codigo_infoobras') or '—'} · "
               f"CUI {fx.get('cui') or '—'}) y MISMO contenido que en "
               f"{ref['etiqueta']}, fila {ref['fila']} de esta hoja: allí está "
               f"{que}. No se repite aquí solo para no alargar la hoja; no se "
               f"omite ningún dato. Si algo difiriera — otra obra del mismo CUI, "
               f"otras valorizaciones u otro periodo resaltado — el detalle se "
               f"pintaría completo.")
        # F:K ≈ 82 caracteres y una celda COMBINADA no auto-ajusta su alto: hay que
        # repartir a mano las filas para que el texto no quede cortado.
        filas = 3
        ws.merge_cells(start_row=rr, start_column=6, end_row=rr + filas - 1, end_column=11)
        c = ws.cell(rr, 6, txt)
        c.font, c.border, c.alignment = F_CELL, BORDER, AL_WRAP
        alto = (-(-len(txt) // 82)) * 13 + 4
        for k in range(filas):
            ws.row_dimensions[rr + k].height = max(
                ws.row_dimensions[rr + k].height or 15, -(-alto // filas))
        rr += filas
        return rr - 1

    _EST_SUBOBRA = {
        "resuelto": "obra hallada en InfoObras",
        "no_encontrado": "el código no figura como obra (posible estudio/plan)",
        "revision": "no se pudo identificar con seguridad — confirmar",
        "privada": "obra/cliente privado — InfoObras no registra obra privada",
        "sin_cui": "el certificado no cita CUI para este proyecto",
        "portal": "InfoObras no respondió — reintentar",
    }
    # de qué fuerza es la evidencia con que se identificó CADA sub-obra: no es la
    # misma cosa un código citado que un nombre parecido, y el evaluador decide.
    _VIA_SUBOBRA = {
        "CODIGO": "por el código citado en el certificado",
        "CUI_TEXTO": "por el código citado en el certificado",
        "RUC": "por el RUC del emisor (ejecutor/supervisor de la obra)",
        "NOMBRE": "por nombre del establecimiento",
        "PROBABLE": "por nombre — candidato PROBABLE, conviene un vistazo",
        "NUMERO": "por el número de la institución educativa, único entre las obras halladas",
        "CONTRATO": "por el contrato de expediente del MEF a nombre del emisor",
        "RESOLUCION": "por la resolución de aprobación del expediente, que nombra al emisor",
        "MEF": "por el nombre oficial del proyecto en el Banco de Inversiones del MEF "
               "(sin registro de ejecución en InfoObras)",
    }

    def render_multi_obra(top: int, sub: list, multi_rubro=None) -> int:
        """RESUMEN (banda F:K de la experiencia madre) de un cert multi-obra: cuántas
        obras se hallaron + las NO halladas en compacto. El DETALLE de cada obra
        hallada va como una SubExperiencia FULL-WIDTH debajo (render_subexperiencias)."""
        rr = top
        n_ok = sum(1 for s in (sub or []) if s.get("estado") == "resuelto")
        ws.merge_cells(start_row=rr, start_column=6, end_row=rr, end_column=11)
        c = ws.cell(rr, 6, f"CERTIFICADO MULTI-OBRA — {n_ok} de {len(sub or [])} obra(s) "
                           f"hallada(s); cada una se detalla abajo como SubExperiencia")
        c.font, c.fill, c.alignment = F_HEAD, FILL_HEAD, AL_HEAD
        rr += 1
        if multi_rubro:
            # candado multi-rubro (ADR-011 · P1): decisión de criterio del Comité,
            # no un NO CUMPLE — el tiempo del vínculo no se toca.
            ws.merge_cells(start_row=rr, start_column=6, end_row=rr, end_column=11)
            c = ws.cell(rr, 6, "Por confirmar — agrupa obras de especialidades "
                               f"distintas ({', '.join(multi_rubro)}) sin declarar el "
                               "tiempo de cada una: para repartir la experiencia por "
                               "especialidad se requiere el anexo de desglose. El "
                               "tiempo total del vínculo no cambia.")
            c.font, c.fill, c.border, c.alignment = F_CELL, FILL_ALERTA, BORDER, AL_WRAP
            ws.row_dimensions[rr].height = max(15, (-(-len(str(c.value)) // 70)) * 13 + 2)
            rr += 1
        for s in (sub or []):
            if s.get("estado") == "resuelto":
                continue  # su detalle full-width va abajo (render_subexperiencias)
            est = _EST_SUBOBRA.get(s.get("estado"), s.get("estado") or "—")
            cui_txt = f"  (CUI {s['cui']})" if s.get("cui") else ""
            # los candidatos de una sub-obra en revisión se MUESTRAN (no hay cola
            # humana por sub-obra): el evaluador necesita ver qué se encontró.
            cands = s.get("candidatos") or []
            cand_txt = ("   ·   candidatos: " + "; ".join(
                f"CUI {c.get('cui')} {c.get('nombre_obra') or ''}".strip()
                for c in cands[:2])) if cands else ""
            ws.merge_cells(start_row=rr, start_column=6, end_row=rr, end_column=11)
            c = ws.cell(rr, 6, f"• {s.get('proyecto') or '—'}{cui_txt} → {est}{cand_txt}")
            c.font, c.border, c.alignment = F_CELL, BORDER, AL_WRAP
            ws.row_dimensions[rr].height = max(15, (-(-len(str(c.value)) // 70)) * 13 + 2)
            rr += 1
        return rr - 1

    def _ficha_sub(s: dict) -> dict:
        """La ficha de una sub-obra CON el nombre garantizado: las fichas viejas no
        lo guardan dentro de `ficha`, pero el nombre sí viaja en `obra.nombre_obra`."""
        ficha = dict(s.get("ficha") or {})
        if not ficha.get("obra_nombre"):
            obra = s.get("obra") if isinstance(s.get("obra"), dict) else {}
            ficha["obra_nombre"] = obra.get("nombre_obra")
        return ficha

    def render_subexperiencias(n_exp, sub, ini, fin) -> None:
        """Cada obra HALLADA de un cert multi-obra como SubExperiencia FULL-WIDTH:
        encabezado + ficha InfoObras + TODAS sus valorizaciones (render_obra, igual
        que una experiencia normal) + la cobertura del tiempo. El TIEMPO ya se contó
        una vez en la experiencia madre (el vínculo); estas SubExperiencias son la
        verificación por obra — NO suman tiempo (no se duplica una cartera simultánea)."""
        nonlocal r
        halladas = [s for s in (sub or []) if s.get("estado") == "resuelto"]
        for j, s in enumerate(halladas, 1):
            ficha = _ficha_sub(s)
            via = _VIA_SUBOBRA.get(s.get("via") or "")
            cab = (f"SubExperiencia {n_exp}.{j}: {s.get('proyecto') or '—'}  "
                   f"(CUI {s.get('cui')})" + (f" — identificada {via}" if via else ""))
            if s.get("sin_verificar"):
                banda(cab + " — obra hallada; su ficha no cargó (portal), reintentar",
                      F_HEAD, FILL_HEAD, 16)
                separador()
                continue
            fila_cab = r
            banda(cab, F_HEAD, FILL_HEAD, 16)
            r_top2 = r
            # ítem completo: ficha + TODAS las valorizaciones (F:K). El resaltado usa
            # el rango POR obra si el cert lo dio; si no, el periodo total del cert.
            oi = _fecha_iso(s.get("fecha_inicial")) or ini
            of = _fecha_iso(s.get("fecha_final")) or fin
            ref = _ya_pintada(ficha, oi, of)
            if ref:
                # esta MISMA obra, con este MISMO contenido, ya está detallada más
                # arriba en la hoja → puntero a su fila en vez del bloque repetido.
                r = max(r, render_ya_pintada(r_top2, ficha, ref) + 1)
            else:
                r_right = render_obra(r_top2, ficha, oi, of)
                r = max(r, r_right + 1)
                # representante de obra (R:U) si la ficha lo trae
                rep = ficha.get("representante_obra")
                if rep:
                    r = max(r, render_representante(r_top2, rep) + 1)
                _registrar_obra(ficha, oi, of, f"SubExperiencia {n_exp}.{j}", fila_cab)
            # cobertura del tiempo del cert para esta obra (si el cert dio rango por obra)
            cob = s.get("cobertura")
            if cob:
                ok = cob.get("cubierto")
                pct = cob.get("pct")
                ci, cf = cob.get("cert_ini"), cob.get("cert_fin")

                def _dd(iso):
                    return f"{iso[8:10]}/{iso[5:7]}/{iso[0:4]}" if iso and len(iso) == 10 else "—"

                base = f"Tiempo del cert para esta obra: {_dd(ci)} – {_dd(cf)}  →  "
                txt = (base + f"{cob.get('nota') or 'no verificable'} — no se puede cruzar el tiempo"
                       if ok is None else
                       base + f"cobertura {pct if pct is not None else '?'}%  —  "
                       + ("cubierto" if ok else "PARCIAL, revisar"))
                ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=11)
                c = ws.cell(r, 1, txt)
                c.font, c.border, c.alignment = F_CELL, BORDER, AL_WRAP
                if ok is not None:
                    c.fill = FILL_OK if ok else FILL_ALERTA
                r += 1
            separador()

    def render_emisor(top: int, s: Optional[dict], fecha_emision, ini, ruc_espejo) -> int:
        """Cuadro del EMISOR del certificado (datos SUNAT) en columnas M:P desde
        `top`, al lado de las valorizaciones. Señala ALT04 (anomalía de antigüedad
        del emisor) en rojo/verde, responde si el emisor estaba HABIDO al emitir y
        durante la obra, y lista sus representantes legales (informativo: ADR-008
        descartó cruzarlos con el firmante). Devuelve la última fila usada."""
        rr = top
        ws.merge_cells(start_row=rr, start_column=13, end_row=rr, end_column=16)
        c = ws.cell(rr, 13, "EMISOR DEL CERTIFICADO (SUNAT)")
        c.font, c.fill, c.alignment = F_HEAD, FILL_HEAD, AL_HEAD
        rr += 1

        def sub(texto):
            nonlocal rr
            ws.merge_cells(start_row=rr, start_column=13, end_row=rr, end_column=16)
            cc = ws.cell(rr, 13, texto)
            cc.font, cc.fill = F_PARTE, FILL_PARTE
            cc.alignment = Alignment(vertical="center", wrap_text=True)
            rr += 1

        def kv(label, value, fill=None, height=None):
            nonlocal rr
            ws.merge_cells(start_row=rr, start_column=13, end_row=rr, end_column=14)
            cl = ws.cell(rr, 13, label); cl.font, cl.border = F_BOLD, BORDER
            cl.alignment = Alignment(vertical="top", wrap_text=True)
            ws.merge_cells(start_row=rr, start_column=15, end_row=rr, end_column=16)
            cv = ws.cell(rr, 15, value); cv.font, cv.border, cv.alignment = F_CELL, BORDER, AL_WRAP
            if fill:
                cv.fill = fill
            if height:
                ws.row_dimensions[rr].height = height
            rr += 1

        def render_habido(h: Optional[dict]) -> None:
            """Lo que el evaluador necesita saber del histórico SUNAT, con la
            PREGUNTA en el título del campo: ¿el emisor estaba habido cuando
            emitió el certificado, y lo estuvo durante la obra que certifica?"""
            emi = (h or {}).get("emision")
            per = (h or {}).get("periodo")
            if not (emi or per):
                kv("¿Estaba habido al emitir y durante la obra?",
                   "Sin información histórica en SUNAT — no verificable")
                return
            if emi:
                ok, cond = emi.get("ok"), emi.get("condicion") or "sin dato"
                prefijo = "Sí — " if ok else ("NO — " if ok is False else "")
                kv("¿Estaba habido al emitir el certificado?",
                   f"{prefijo}{cond} al {_ddmmaa(emi.get('fecha'))}",
                   fill=FILL_OK if ok else (FILL_ALERTA if ok is False else None))
            if per:
                ok = per.get("ok")
                malos = per.get("tramos_no_habido") or []
                if ok:
                    txt = (f"Sí — HABIDO todo el periodo "
                           f"({_ddmmaa(per.get('desde'))} – {_ddmmaa(per.get('hasta'))})")
                elif ok is False:
                    det = "; ".join(
                        f"{t.get('condicion')} {_ddmmaa(t.get('desde'))}–{_ddmmaa(t.get('hasta'))}"
                        for t in malos[:3])
                    txt = f"NO — {det}" + (" y otros" if len(malos) > 3 else "")
                else:
                    sin = per.get("sin_dato") or []
                    if per.get("tramos") and sin:
                        # cobertura PARCIAL: lo conocido fue HABIDO (si hubiera
                        # NO HABIDO, ok sería False), pero hay días sin condición
                        # registrada — nunca un "Sí" con huecos.
                        det = "; ".join(
                            f"{_ddmmaa(h.get('desde'))}–{_ddmmaa(h.get('hasta'))}"
                            for h in sin[:3])
                        txt = ("No verificable — HABIDO en los tramos con dato, "
                               f"pero sin condición registrada en: {det}"
                               + (" y otros" if len(sin) > 3 else ""))
                    else:
                        txt = "Sin dato de condición para ese periodo"
                kv("¿Estuvo habido durante el periodo certificado?", txt,
                   fill=FILL_OK if ok else (FILL_ALERTA if ok is False else None),
                   height=None if ok else 34)

        def render_representantes_emisor(reps: Optional[list]) -> None:
            """Representantes legales del emisor según SUNAT. INFORMATIVO: sin
            cruce con el firmante del certificado (ADR-008 descartó ALT-12)."""
            reps = reps or []
            if not reps:
                return
            nonlocal rr
            sub("Representantes legales (SUNAT) — informativo")

            def fila_rep(nombre, cargo, desde, *, font=F_CELL):
                nonlocal rr
                ws.merge_cells(start_row=rr, start_column=13, end_row=rr, end_column=14)
                for col, val in ((13, nombre), (15, cargo), (16, desde)):
                    cc = ws.cell(rr, col, val)
                    cc.font, cc.border, cc.alignment = font, BORDER, AL_WRAP
                if len(str(nombre)) > 24:
                    ws.row_dimensions[rr].height = 28
                rr += 1

            fila_rep("Nombre", "Cargo", "Desde", font=F_BOLD)
            for rp in reps:
                fila_rep(rp.get("nombre") or "—", rp.get("cargo") or "—",
                         _ddmmaa(rp.get("fecha_desde")))

        creacion = _fecha_iso(s.get("fecha_inscripcion")) if s else None
        if s and s.get("ruc"):                       # datos completos del emisor
            kv("RUC", s.get("ruc"))
            kv("Razón social", s.get("razon_social") or "—")
            if s.get("tipo_contribuyente"):
                kv("Tipo", s.get("tipo_contribuyente"))
            acts = s.get("actividades_economicas") or []
            objeto = re.sub(r"^\s*Principal\s*-\s*", "", acts[0]) if acts else "—"
            kv("Objeto social", objeto, height=58)   # CIIU largo → más alto, envuelve
            estado, cond = s.get("estado"), s.get("condicion")
            mal = (estado and not str(estado).upper().startswith("ACTIVO")) or \
                  (cond and str(cond).upper() != "HABIDO")
            kv("Estado / Condición", f"{estado or '—'} / {cond or '—'}",
               fill=FILL_ALERTA if mal else None)
            ini_act = _fecha_iso(s.get("fecha_inicio_actividades"))
            if ini_act:
                kv("Inicio actividades", ini_act.strftime("%d/%m/%Y"))
            if s.get("domicilio_fiscal"):
                kv("Domicilio fiscal", s.get("domicilio_fiscal"))
            if str(s.get("via") or "").startswith("nombre"):
                detalle = ("por nombre — única idéntica entre varias en SUNAT"
                           if s.get("via") == "nombre_exacto"
                           else "por nombre (el cert no traía RUC)")
                kv("Cruce", detalle)
            render_habido(s.get("habido"))
            render_representantes_emisor(s.get("representantes"))
            emision = _fecha_iso(fecha_emision)
            alt04 = s.get("alt04") or {}
            if not alt04 and creacion and ((emision and creacion > emision)
                                           or (ini and creacion > ini)):
                habido = s.get("habido") or {}
                if any((habido.get(k) or {}).get("ok") is True
                       for k in ("emision", "periodo")):
                    alt04 = {
                        "estado": "REINSCRIPCION",
                        "mensaje": ("La inscripción vigente es posterior, pero el histórico "
                                    "SUNAT acredita actividad en el periodo: probable reinscripción."),
                    }
            if alt04.get("estado") == "REINSCRIPCION":
                txt = "🟡 ALT04 — " + alt04.get(
                    "mensaje", "Probable reinscripción; revisar el histórico SUNAT.")
                fill = FILL_PEND
            elif alt04.get("estado") == "ALERTA":
                txt = "🔴 ALT04 — " + alt04.get(
                    "mensaje", "Confirmar la inscripción original en SUNAT.")
                fill = FILL_ALERTA
            elif creacion and emision and creacion > emision:
                txt = (f"🔴 ALT04 — certificado emitido ({emision.strftime('%d/%m/%y')}) ANTES de "
                       f"la creación de la empresa ({creacion.strftime('%d/%m/%y')}): imposible, revisar.")
                fill = FILL_ALERTA
            elif creacion and ini and creacion > ini:
                txt = (f"🔴 ALT04 — empresa creada ({creacion.strftime('%d/%m/%y')}) DESPUÉS del "
                       f"inicio de la experiencia ({ini.strftime('%d/%m/%y')}).")
                fill = FILL_ALERTA
            elif creacion:
                txt = "✔ ALT04 — sin anomalía de antigüedad del emisor."
                fill = FILL_OK
            else:
                txt = "ALT04 — sin fecha de creación SUNAT (no verificable)."
                fill = None
        elif s and s.get("ambiguo"):                 # varias empresas con ese nombre
            kv("Emisor (cert)", s.get("nombre") or "—")
            txt = (f"⚠ Por verificar — {s.get('ambiguo')} empresas en SUNAT con ese nombre; "
                   f"confirmar el RUC del emisor.")
            fill = FILL_ALERTA
        elif s and s.get("no_encontrado"):           # buscado por nombre, sin match
            kv("Emisor (cert)", s.get("nombre") or "—")
            txt = "Sin coincidencia en SUNAT por ese nombre — verificar."
            fill = None
        else:                                        # sin RUC ni nombre cruzable
            kv("RUC declarado", ruc_espejo or "—")
            txt = "Emisor no verificado en SUNAT (sin datos / consulta fallida)."
            fill = None

        ws.merge_cells(start_row=rr, start_column=13, end_row=rr + 1, end_column=16)
        c = ws.cell(rr, 13, txt)
        c.font, c.border, c.alignment = F_CELL, BORDER, AL_WRAP
        if fill:
            c.fill = fill
        rr += 2
        return rr - 1

    def render_historico(top: int, s: Optional[dict]) -> int:
        """Cuadro HISTÓRICO SUNAT del emisor en columnas R:U, pegado al cuadro del
        emisor (M:P): forman un par. Compacto — solo lo que tiene datos:

          · nombres/razones sociales anteriores, con su fecha de baja
          · condición del contribuyente RECORTADA al periodo de la experiencia
            (el histórico completo puede traer 30 tramos; el resto vive en el
            panel), en rojo lo que no fue HABIDO
          · domicilios fiscales anteriores, con su fecha de baja

        Devuelve la última fila usada (o top-1 si no hay nada que mostrar)."""
        rr = top
        hist = (s or {}).get("historico") or {}
        razones = hist.get("razones_sociales") or []
        domicilios = hist.get("domicilios") or []
        tramos = (((s or {}).get("habido") or {}).get("periodo") or {}).get("tramos") or []
        if not (razones or domicilios or tramos):
            return rr - 1

        ws.merge_cells(start_row=rr, start_column=18, end_row=rr, end_column=21)
        c = ws.cell(rr, 18, "HISTÓRICO SUNAT DEL EMISOR")
        c.font, c.fill, c.alignment = F_HEAD, FILL_HEAD, AL_HEAD
        rr += 1

        def sub(texto):
            nonlocal rr
            ws.merge_cells(start_row=rr, start_column=18, end_row=rr, end_column=21)
            cc = ws.cell(rr, 18, texto)
            cc.font, cc.fill = F_PARTE, FILL_PARTE
            cc.alignment = Alignment(vertical="center", wrap_text=True)
            rr += 1

        def _escribir(cols, font, fill, largo):
            nonlocal rr
            for col, val in cols:
                cc = ws.cell(rr, col, val)
                cc.font, cc.border, cc.alignment = font, BORDER, AL_WRAP
                if fill:
                    cc.fill = fill
            if largo > 40:            # texto ancho (dirección, razón social)
                ws.row_dimensions[rr].height = 28
            rr += 1

        def fila_texto_fecha(texto, fecha, *, font=F_CELL):
            """Texto largo en R:T + su fecha en U (razón social / domicilio)."""
            ws.merge_cells(start_row=rr, start_column=18, end_row=rr, end_column=20)
            _escribir(((18, texto), (21, fecha)), font, None, len(str(texto)))

        def fila_tramo(condicion, desde, hasta, *, font=F_CELL, fill=None):
            """Tramo de condición: R | S | T:U."""
            ws.merge_cells(start_row=rr, start_column=20, end_row=rr, end_column=21)
            _escribir(((18, condicion), (19, desde), (20, hasta)), font, fill, 0)

        if razones:
            sub("Nombre o razón social anterior")
            fila_texto_fecha("Nombre", "Fecha de baja", font=F_BOLD)
            for rz in razones:
                fila_texto_fecha(rz.get("nombre") or "—", _ddmmaa(rz.get("fecha_baja")))

        if tramos:
            sub("Condición del contribuyente durante la experiencia")
            fila_tramo("Condición", "Desde", "Hasta", font=F_BOLD)
            for t in tramos:
                mal = (t.get("condicion") or "").upper() != "HABIDO"
                fila_tramo(t.get("condicion") or "—", _ddmmaa(t.get("desde")),
                           _ddmmaa(t.get("hasta")),
                           fill=FILL_ALERTA if mal else None)

        if domicilios:
            sub("Domicilio fiscal anterior")
            fila_texto_fecha("Dirección", "Fecha de baja", font=F_BOLD)
            for d in domicilios:
                fila_texto_fecha(d.get("direccion") or "—", _ddmmaa(d.get("fecha_baja")))

        return rr - 1

    def render_representante(top: int, rep: Optional[dict]) -> int:
        """Representante de obra (InfoObras): TODOS los contratistas, supervisores/
        inspectores y residentes con todos sus campos (tipo, documento, razón social,
        monto, fechas), en columnas W:Z — a la derecha de los dos cuadros del
        emisor. Numera cada categoría cuando hay más de uno. Devuelve la última
        fila (o top-1 si vacío)."""
        rr = top
        contr = (rep or {}).get("contratistas") or []
        supes = (rep or {}).get("supervisores") or []
        resis = (rep or {}).get("residentes") or []
        if not (contr or supes or resis):
            return rr - 1
        ws.merge_cells(start_row=rr, start_column=23, end_row=rr, end_column=26)
        c = ws.cell(rr, 23, "REPRESENTANTE DE OBRA (InfoObras)")
        c.font, c.fill, c.alignment = F_HEAD, FILL_HEAD, AL_HEAD
        rr += 1

        def sub(texto):
            nonlocal rr
            ws.merge_cells(start_row=rr, start_column=23, end_row=rr, end_column=26)
            cc = ws.cell(rr, 23, texto)
            cc.font, cc.fill = F_PARTE, FILL_PARTE
            cc.alignment = Alignment(vertical="center", wrap_text=True)
            rr += 1

        def kv(label, value, fmt=None):
            nonlocal rr
            if value in (None, ""):
                value = "—"
            ws.merge_cells(start_row=rr, start_column=23, end_row=rr, end_column=24)
            cl = ws.cell(rr, 23, label); cl.font, cl.border = F_BOLD, BORDER
            cl.alignment = Alignment(vertical="top", wrap_text=True)
            ws.merge_cells(start_row=rr, start_column=25, end_row=rr, end_column=26)
            cv = ws.cell(rr, 25, value); cv.font, cv.border, cv.alignment = F_CELL, BORDER, AL_WRAP
            if fmt and isinstance(value, (int, float, date)):
                cv.number_format = fmt
            # valor Y:Z (~36 car) en celda combinada NO auto-ajusta en Excel: si el
            # texto es largo (razón social, URL), subir la altura para que se vea
            # completo. Solo AUMENTA (no pisa la altura de otras bandas en la fila).
            if isinstance(value, str) and len(value) > 34:
                alto = (len(value) // 34 + 1) * 14 + 2
                ws.row_dimensions[rr].height = max(ws.row_dimensions[rr].height or 15, alto)
            rr += 1

        def _nombre(p):
            return " ".join(x for x in [p.get("nombre"), p.get("apellido_paterno"),
                                        p.get("apellido_materno")] if x).strip()

        for i, c_ in enumerate(contr, 1):
            sub(f"Contratista (ejecutor) {i}" if len(contr) > 1 else "Contratista (ejecutor)")
            kv("Tipo de empresa", c_.get("tipo_empresa"))
            kv("RUC", c_.get("ruc"))
            kv("Razón social", c_.get("nombre_empresa"))
            if c_.get("numero_contrato"):
                kv("N° de contrato", c_.get("numero_contrato"))
            kv("Monto contrato (S/)", c_.get("monto_soles"), FMT_SOLES)
            kv("Inicio de contrato", _fecha_iso(c_.get("fecha_contrato")), FMT_FECHA)
            kv("Fin de contrato", _fecha_iso(c_.get("fecha_fin_contrato")), FMT_FECHA)
        for i, s_ in enumerate(supes, 1):
            etiqueta = s_.get("tipo") or "Supervisor"
            sub(f"{etiqueta} {i}" if len(supes) > 1 else etiqueta)
            kv("Tipo de persona", s_.get("tipo_persona"))
            kv("Razón social / empresa", s_.get("empresa") or s_.get("razon_social"))
            if _nombre(s_):
                kv("Persona", _nombre(s_))
            kv("RUC / documento", s_.get("ruc") or s_.get("documento"))
            if s_.get("dni"):
                kv("DNI", s_.get("dni"))
            if s_.get("monto_soles") is not None:
                kv("Monto contrato (S/)", s_.get("monto_soles"), FMT_SOLES)
            kv("Inicio", _fecha_iso(s_.get("fecha_inicio")), FMT_FECHA)
            kv("Fin", _fecha_iso(s_.get("fecha_fin")), FMT_FECHA)
            if s_.get("doc_designacion"):
                kv("Doc. designación", s_.get("doc_designacion"))
        for i, r_ in enumerate(resis, 1):
            sub(f"Residente {i}" if len(resis) > 1 else "Residente")
            kv("Nombre y apellido", _nombre(r_))
            kv("Inicio de labores", _fecha_iso(r_.get("fecha_inicio")), FMT_FECHA)
            kv("Fin de labores", _fecha_iso(r_.get("fecha_fin")), FMT_FECHA)
        return rr - 1

    def separador():
        """Dos filas amarillas (A:Z) tras cada experiencia, como separador visual."""
        nonlocal r
        for _ in range(2):
            for col in range(1, 27):          # columnas A..Z
                ws.cell(r, col).fill = FILL_SEP
            ws.row_dimensions[r].height = 10
            r += 1

    def embeber_cert(cert_pdf, titulo="DOCUMENTO DE LA EXPERIENCIA — constancia / conformidad (imagen)"):
        """Embebe las páginas de un PDF (principal primero) a lo ancho, bajo una
        banda de título, para que el evaluador lo vea sin abrir el PDF. Se usa para
        la constancia de la experiencia y también para el TDR/Anexo (mejora A).
        Tolerante: si PyMuPDF/Pillow fallan, deja una nota y sigue."""
        nonlocal r
        try:
            paginas = _render_cert_pages(cert_pdf)
        except Exception as ex:    # noqa: BLE001 — no romper el Excel por un cert
            logger.warning("certificado no embebido %s: %s", cert_pdf, ex)
            c = ws.cell(r, 1, "Certificado no embebido — revisar el PDF original")
            c.font = F_CELL
            r += 1
            return
        if not paginas:
            return
        from openpyxl.drawing.image import Image as XLImage
        banda(titulo, F_PARTE, FILL_PARTE, 16)
        for i, (jpg, w0, h0) in enumerate(paginas):
            etiqueta = "Página principal" if i == 0 else f"Página {i + 1}"
            ce = ws.cell(r, 1, etiqueta); ce.font = F_BOLD
            r += 1
            img = XLImage(io.BytesIO(jpg))
            img.width = _CERT_ANCHO_PX
            img.height = int(h0 * _CERT_ANCHO_PX / w0)
            ws.add_image(img, f"A{r}")
            r += -(-img.height // 15) + 1     # avanza las filas que ocupa la imagen

    banda(f"PROFESIONAL {n_prof}: {prof.get('cargo', '')}")
    ws.cell(r, 1, f"Nombre: {prof.get('nombre') or '—'}").font = F_BOLD; r += 1
    ws.cell(r, 1, f"Colegiatura: {prof.get('colegiatura') or '—'}").font = F_CELL; r += 1
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=4)
    # La leyenda tiene que describir los colores que la hoja usa REALMENTE. Le
    # faltaban dos: el amarillo suave de «por verificar» —que además compartía el
    # FFFF00 del dato declarado, así que decía una cosa y pintaba otra— y el verde
    # de lo verificado como correcto.
    c = ws.cell(
        r, 1,
        "LEYENDA: violeta = supuesto o inferido · amarillo = dato del certificado / "
        "valorización dentro del periodo · amarillo claro = por verificar · "
        "verde = verificado correcto · cyan = efectivo verificado · naranja = "
        "periodo excluido · rojo = alerta o contradicción",
    )
    c.font, c.alignment = F_CELL, AL_WRAP
    ws.row_dimensions[r].height = 30
    r += 1
    r += 1

    # ── A · Contexto del TDR + Anexo 16, ANTES de las experiencias ───────────
    # Qué pide el TDR para este cargo (texto del espejo + recorte de las bases) y
    # el Anexo 16 declarado/firmado, para evaluar con el requisito a la vista.
    _req = prof.get("requisitos") or {}
    _tdr_pdf = certificados.get((n_prof, "TDR"))
    _anexo_pdf = certificados.get((n_prof, "ANEXO"))
    if _req or _tdr_pdf or _anexo_pdf:
        banda("REQUISITO DEL TDR PARA ESTE CARGO", F_PARTE, FILL_PARTE, 16)
        for label, value in [
            ("CARGOS VÁLIDOS (bases)", _req.get("cargos_validos")),
            ("EXPERIENCIA / PROFESIÓN EXIGIDA", _req.get("tipo_experiencia_valida")),
            ("TIPO DE OBRA VÁLIDA", _req.get("tipo_obra_valida")),
        ]:
            if not value:
                continue
            cl = ws.cell(r, 1, label); cl.font, cl.fill, cl.border = F_BOLD, FILL_RECAP, BORDER
            cl.alignment = Alignment(vertical="top", wrap_text=True)
            ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=4)
            value = _xl(value)
            cv = ws.cell(r, 2, value); cv.font, cv.border, cv.alignment = F_CELL, BORDER, AL_WRAP
            ws.row_dimensions[r].height = max(15, (-(-len(str(value)) // 35)) * 13 + 2)
            r += 1
        if _tdr_pdf:
            import fitz
            with fitz.open(str(_tdr_pdf)) as _tdr_doc:
                _tdr_paginas = _tdr_doc.page_count
            _tdr_rotulo = (
                "REQUISITO DEL TDR — cuadro completo de personal clave "
                "(recorte amplio; ubicar este cargo dentro del rango)"
                if _tdr_paginas > 1 else
                "REQUISITO DEL TDR — recorte de las bases (imagen)"
            )
            embeber_cert(_tdr_pdf, _tdr_rotulo)
        if _anexo_pdf:
            embeber_cert(_anexo_pdf, "ANEXO 16 — EXPERIENCIA DECLARADA Y FIRMADA (imagen)")
        r += 1
    # ── helpers del formato por-certificado (feedback del ingeniero) ─────────
    def _dias_exp(n_exp, ini, fin):
        """(declarado, efectivo, clamp) de una experiencia: días del periodo
        certificado, días efectivos del Paso 5 (recortando paralizaciones /
        sin-valorización) y las ventanas inactivas recortadas (para el cálculo
        ALT11 a nivel del profesional)."""
        if not (ini and fin):
            return None, None, []
        clamp = []
        for p in paralizaciones.get((n_prof, n_exp), []):
            p_ini, p_fin = periodo_fechas(p)
            ci, cf = max(p_ini, ini), min(p_fin, fin)
            if cf >= ci:
                clamp.append((ci, cf))
        tramos = restar_paralizaciones((ini, fin), clamp)
        efectivo = sum(dias_inclusivos(a, b) for a, b in tramos)
        revision = revisiones.get((n_prof, n_exp))
        if _es_revision_efectiva(revision):
            return dias_inclusivos(ini, fin), f"{efectivo} PROVISIONAL", clamp
        return dias_inclusivos(ini, fin), efectivo, clamp

    def cert_marco(n_exp, e, ini, fin, cui, fx=None):
        """Encabezado 'CERT. N°X' (amarillo) + recap 'DATOS DE LA EXPERIENCIA'
        (azul) en columnas A:D, antes de las bandas técnicas (formato ingeniero).
        Muestra el periodo del certificado y el de InfoObras juntos, para comparar."""
        nonlocal r
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=4)
        c = ws.cell(r, 1, f"CERT. N°{n_exp} — {prof.get('cargo', '')} — {prof.get('nombre') or ''}")
        c.font, c.fill = F_CERT, FILL_CERT
        c.alignment = Alignment(vertical="center", wrap_text=True)
        _lns = max(1, -(-len(c.value) // 88))          # A:D ≈ 88 car/línea
        ws.row_dimensions[r].height = max(16, _lns * 14 + 2)
        r += 1
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=4)
        c = ws.cell(r, 1, "DATOS DE LA EXPERIENCIA (del certificado)")
        c.font, c.fill, c.alignment = F_DATOS, FILL_DATOS, AL_HEAD
        r += 1
        if es_exp_prof:
            literal_ini, literal_fin = e.get("fecha_inicial"), e.get("fecha_final")
            periodo = (f"{literal_ini or '—'} – {literal_fin or '—'}")
        else:
            periodo = (f"{ini.strftime('%d/%m/%Y')} – {fin.strftime('%d/%m/%Y')}"
                       if (ini and fin) else "—")
        io_ini = _fecha_iso((fx or {}).get("fecha_inicio"))
        io_fin = _fecha_iso((fx or {}).get("fecha_fin"))
        periodo_io = ("— (obra no ubicada en InfoObras)" if not io_ini else
                      f"{io_ini.strftime('%d/%m/%Y')} – "
                      f"{io_fin.strftime('%d/%m/%Y') if io_fin else '(sin fin)'}")
        cui_cert = e.get("cui")
        if cui_cert and cui and str(cui_cert).strip() != str(cui).strip():
            # ambos existen y difieren: el del documento manda, el del sistema se
            # muestra al lado — nunca uno disfrazado del otro (#60)
            cui_text = f"{cui_cert} · el sistema identificó el CUI {cui} — verificar"
        elif cui_cert:
            cui_text = (f"Citado en el certificado y verificado: {cui_cert}"
                        if cui and str(cui_cert).strip() == str(cui).strip()
                        else f"Citado en el certificado: {cui_cert}")
        elif cui:
            cui_text = f"No consignado en el certificado — el sistema identificó el CUI {cui}"
        else:
            cui_text = "No consignado en el certificado"

        sup = set(e.get("supuestos") or [])
        filas_recap = [
            ("ENTIDAD / EMPRESA QUE EMITE", e.get("entidad_emisora"), "entidad_emisora"),
            ("TIPO DE DOCUMENTO", e.get("tipo_documento"), "tipo_documento"),
            ("PROYECTO U OBRA", e.get("proyecto"), "proyecto"),
            ("PERIODO (certificado)", periodo, "periodo"),
            ("CARGO QUE OCUPÓ", e.get("cargo_ocupado"), "cargo_ocupado"),
            # Si el certificado no citó código, la identificación nació en el
            # enriquecimiento del servidor y se presenta como inferencia.
            ("CÓDIGO (CUI/SNIP)", cui_text, "cui_inferido" if (cui and not cui_cert) else "cui"),
        ]
        if not es_exp_prof:
            filas_recap.insert(4, ("PERIODO (InfoObras)", periodo_io, None))
        for label, value, campo in filas_recap:
            cl = ws.cell(r, 1, label); cl.font, cl.fill, cl.border = F_BOLD, FILL_RECAP, BORDER
            cl.alignment = Alignment(vertical="top", wrap_text=True)
            ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=4)
            value = _xl(value)
            cv = ws.cell(r, 2, value or "—")
            cv.font, cv.border, cv.alignment = F_CELL, BORDER, AL_WRAP
            es_periodo_supuesto = campo == "periodo" and bool(
                {"fecha_inicial", "fecha_final"} & sup)
            if campo == "cui_inferido" or campo in sup or es_periodo_supuesto:
                cv.fill = FILL_SUPUESTO
            lns = max(1, -(-len(str(value or "—")) // 35))   # B:D ≈ 35 car/línea
            ws.row_dimensions[r].height = max(15, lns * 13 + 2)
            r += 1

    periodos_validos: list[tuple[date, date]] = []
    paral_por_idx: dict[int, list[tuple[date, date]]] = {}

    for e in prof.get("experiencias", []):
        n_exp = e.get("n")
        rev = revisiones.get((n_prof, n_exp))
        en_revision = _es_revision_efectiva(rev)
        deducida_detalle = False
        if es_exp_prof:
            ini, fin, deducida_detalle = fechas_calculo(e, regla_periodos)
        else:
            ini, fin = _fecha_iso(e.get("fecha_inicial")), _fecha_iso(e.get("fecha_final"))
        fx = fichas.get((n_prof, n_exp))
        # CUI resuelto por el backend (etapa InfoObras); si no, el del espejo
        cui = cuis.get((n_prof, n_exp)) or (fx or {}).get("cui") or e.get("cui")
        cert_marco(n_exp, e, ini, fin, cui, fx)   # encabezado CERT N°X + recap (cert vs InfoObras)
        r_top = r  # fila del título: el bloque de obra (F:J) arranca alineado aquí
        titulo = f"EXPERIENCIA {n_exp}: {str(e.get('proyecto') or '')}"  # nombre VERBATIM, sin truncar
        extra = " · ".join(x for x in [
            f"CUI {cui}" if cui else "",
            f"folio {e['folio']}" if e.get("folio") else ""] if x)
        banda(titulo + (f"  ({extra})" if extra else ""), F_HEAD, FILL_HEAD, 16)

        for i, h in enumerate(_HITO_HEAD, start=1):
            c = ws.cell(r, i, h)
            c.font, c.fill, c.border, c.alignment = F_HEAD, FILL_HEAD, BORDER, AL_HEAD
        r += 1

        if not (ini and fin) or (es_exp_prof and fin < ini):
            fila("Fechas no computables (parciales o POR VERIFICAR) — revisar "
                 "contra el certificado original",
                 e.get("fecha_inicial"), e.get("fecha_final"), None)
            r += 1
        else:
            sup_hitos = set(prof.get("supuestos") or []) | set(e.get("supuestos") or [])
            fill_periodo = (FILL_SUPUESTO if {"fecha_inicial", "fecha_final"} & sup_hitos
                            else FILL_CLAUDE)
            etiqueta_periodo = ("Período usado para cálculo (mes completo según bases)"
                                if es_exp_prof and deducida_detalle else "Periodo certificado")
            fila(etiqueta_periodo, ini, fin, dias_inclusivos(ini, fin), fill=fill_periodo)

            # periodos inactivos de la obra (dict con tipo, o tupla legacy=paralizado)
            # SOLO los que caen dentro del periodo que supervisó este profesional;
            # InfoObras trae las paralizaciones de toda la vida de la obra, pero las
            # de antes/después de su ventana no le aplican. Se recortan a [ini, fin].
            periodos = ([] if es_exp_prof else
                        paralizaciones.get((n_prof, n_exp), []))
            n_par = n_gap = n_fv = 0
            tuplas: list[tuple[date, date]] = []
            for p in periodos:
                p_ini, p_fin = periodo_fechas(p)
                c_ini, c_fin = max(p_ini, ini), min(p_fin, fin)
                if c_fin < c_ini:
                    continue  # paralización fuera del periodo del profesional → se omite
                tuplas.append((c_ini, c_fin))
                tipo = p.get("tipo", "paralizado") if isinstance(p, dict) else "paralizado"
                if tipo == "sin_valorizacion":
                    n_gap += 1
                    etiqueta = f"Sin valorización {n_gap} — obra parada (InfoObras)"
                elif tipo == "fuera_de_ventana":
                    n_fv += 1
                    etiqueta = f"Sin valorización {n_fv} — fuera del periodo de la obra (InfoObras)"
                elif tipo == "antes_inicio_obra":
                    n_fv += 1
                    _fi_obra = p.get("fecha_inicio_obra") if isinstance(p, dict) else None
                    etiqueta = (f"Sin valorización {n_fv} — antes del inicio de la obra"
                                f" ({_fi_obra})" if _fi_obra else
                                f"Sin valorización {n_fv} — antes del inicio de la obra")
                else:
                    n_par += 1
                    etiqueta = f"Paralización {n_par} de la obra (InfoObras)"
                fila(etiqueta, c_ini, c_fin, dias_inclusivos(c_ini, c_fin), fill=FILL_BACKEND)

            tramos = restar_paralizaciones((ini, fin), tuplas)
            for k, (t_ini, t_fin) in enumerate(tramos, start=1):
                fila(f"Tramo {'provisional' if en_revision else 'efectivo'} {k}", t_ini, t_fin,
                     dias_inclusivos(t_ini, t_fin), fill=FILL_PEND if en_revision else FILL_EFECTIVO)
            efectivo = sum(dias_inclusivos(a, b) for a, b in tramos)
            fila(f"{'PROVISIONAL — POR VERIFICAR' if en_revision else 'EFECTIVO'} EXPERIENCIA {n_exp}",
                 "", "", efectivo, bold=True,
                 fill=FILL_PEND if en_revision else FILL_EFECTIVO)
            r += 1

            idx = len(periodos_validos)
            periodos_validos.append((ini, fin))
            if tuplas:
                paral_por_idx[idx] = tuplas

        # lado derecho: ficha de la obra; si la experiencia está en revisión, un
        # bloque que lo explica (en vez de dejar la columna vacía).
        # El aviso de revisión NO es excluyente con la obra: que el resolver haya
        # propuesto una es justamente cuando más falta hace avisar que está sin
        # confirmar (antes solo se pintaba si NO había obra → 40% de los avisos
        # quedaban invisibles).
        motivo_rev, accion_rev = _motivo_accion(rev) if rev else (None, None)
        if fx and fx.get("sub_obras"):
            # cert multi-obra: la banda F:K muestra un RESUMEN (cuántas + no halladas);
            # el detalle full-width de cada obra hallada va como SubExperiencia debajo.
            top = (r_top if not motivo_rev
                   else render_aviso_revision(r_top, motivo_rev, accion_rev) + 1)
            r_right = render_multi_obra(top, fx["sub_obras"], fx.get("multi_rubro"))
            r = max(r, r_right + 1)
        elif fx and any(fx.get(k) for k in
                        ("codigo_infoobras", "obra_nombre", "estado", "valorizaciones",
                         "verificacion_expediente", "aprobacion_expediente")):
            top = (r_top if not motivo_rev
                   else render_aviso_revision(r_top, motivo_rev, accion_rev) + 1)
            ref = _ya_pintada(fx, ini, fin)
            r_right = (render_ya_pintada(top, fx, ref) if ref
                       else render_obra(top, fx, ini, fin))
            if fx.get("seace"):
                r_right = render_seace(r_right + 1, fx["seace"])
            r = max(r, r_right + 1)
            if not ref:
                _registrar_obra(fx, ini, fin, f"Experiencia {n_exp}", top)
        elif fx and fx.get("seace"):
            top = (r_top if not motivo_rev
                   else render_aviso_revision(r_top, motivo_rev, accion_rev) + 1)
            r_right = render_seace(top, fx["seace"])
            r = max(r, r_right + 1)
        elif motivo_rev:
            r_right = render_revision(r_top, motivo_rev, accion_rev,
                                      (fx or {}).get("resoluciones_candidatos"))
            r = max(r, r_right + 1)

        # 3ª banda (M:P): emisor del certificado (SUNAT) + ALT04, al lado de valorizaciones
        s_emisor = sunat.get((n_prof, n_exp))
        r_emi = render_emisor(r_top, s_emisor,
                              e.get("fecha_emision"), ini, e.get("ruc_emisor"))
        r = max(r, r_emi + 1)

        # 4ª banda (R:U): histórico SUNAT del mismo emisor, pegado al cuadro anterior
        r_his = render_historico(r_top, s_emisor)
        r = max(r, r_his + 1)

        # 5ª banda (W:Z): representante de obra (InfoObras), a la derecha del par
        if not es_exp_prof:
            r_rep = render_representante(r_top, (fx or {}).get("representante_obra"))
            r = max(r, r_rep + 1)

        # imagen del certificado presentado (Fase 2): la skill recortó sus folios a
        # un PDF chico (principal primero); aquí se renderiza y embebe.
        # #47 · si la skill NO pudo confirmar que la página citada muestre al
        # emisor (folio_verificado=False), NO se embebe: una imagen equivocada es
        # el sustento que audita el Comité — peor que ninguna. None = legado.
        cert_pdf = certificados.get((n_prof, n_exp))
        if e.get("folio_verificado") is False:
            banda(f"⚠ DOCUMENTO NO EMBEBIDO — no se pudo confirmar que el folio "
                  f"{e.get('folio') or '—'} corresponda al emisor de esta "
                  "experiencia (posible folio corrido) — verificar en la propuesta",
                  F_AVISO, FILL_AVISO)
        elif cert_pdf:
            embeber_cert(cert_pdf)

        separador()   # 2 filas amarillas (A:Z) cerrando la experiencia

        # cert multi-obra: cada obra hallada baja como SubExperiencia FULL-WIDTH
        # (ficha InfoObras + valorizaciones + cobertura), como un ítem normal.
        if fx and fx.get("sub_obras") and not es_exp_prof:
            render_subexperiencias(n_exp, fx["sub_obras"], ini, fin)

    # ── PARTE 5 (al FINAL): tabla por experiencia — declarado vs efectivo ──────
    # Es la conclusión del profesional (días efectivos del Paso 5). Flush-left;
    # A=52 lleva el Cliente, Objeto (B:D) y Proyecto (F:I) combinados anchos para
    # que el texto no se corte. Reconcilia la suma por-experiencia con ALT11.
    from resolucion.cui import (
        TIPO_EXPEDIENTES, es_expediente_exp, normalizar_tipo_evaluacion,
    )
    from validacion.recalculo import fechas_calculo
    # ADR-010 · en un concurso de ELABORACIÓN DE EXPEDIENTES la fila «Fuente:
    # InfoObras» de la PARTE 5 hablaba de la EJECUCIÓN de la obra — algo que no
    # prueba nada sobre quién elaboró el expediente — y la tabla sumaba días de
    # CUI citado y de CUI inferido como si valieran lo mismo. Para «obras» la
    # PARTE 5 se conserva EXACTAMENTE como estaba.
    _es_concurso_expedientes = (
        normalizar_tipo_evaluacion(tipo_evaluacion) == TIPO_EXPEDIENTES)

    banda("PARTE 5 — EXPERIENCIA DEL PROFESIONAL (días efectivos y certeza de "
          "identificación del expediente)" if _es_concurso_expedientes else
          "PARTE 5 — EXPERIENCIA DEL PROFESIONAL (días declarados y efectivos verificados)",
          F_PARTE, FILL_PARTE, 18)

    # 9 columnas: N°(A) · Proyecto(B:H) · Cliente(I:K) · Objeto(M) · Fuente(N)
    #             · F.inicio(O) · F.fin(P) · Declarado(R) · Efectivo(S).
    # Cabecera en 1 fila; cada experiencia ocupa 2 sub-filas (Certificado /
    # InfoObras) con las fechas de cada fuente una debajo de la otra, para
    # contrastarlas de un vistazo. Las demás celdas se combinan verticalmente.
    def _p5_head():
        nonlocal r
        for ci, cf, val in [(1, 1, "N°"), (2, 8, "Proyecto / Obra"),
                            (9, 11, "Cliente o Empleador"),
                            (13, 13, "Objeto de contratación"), (14, 14, "Fuente"),
                            (15, 15, "Fecha de inicio"), (16, 16, "Fecha de fin"),
                            (18, 18, "Declarado (días)"), (19, 19, "Efectivo (días)")]:
            if cf > ci:
                ws.merge_cells(start_row=r, start_column=ci, end_row=r, end_column=cf)
            c = ws.cell(r, ci, val)
            c.font, c.fill, c.border, c.alignment = F_HEAD, FILL_HEAD, BORDER, AL_WRAP
        ws.row_dimensions[r].height = 30
        r += 1

    def _p5(n, proyecto, cliente, objeto, fini, ffin, io_ini, io_fin, decl, efec,
            supuestos=None):
        nonlocal r
        supuestos = set(supuestos or [])
        # celdas combinadas en vertical (2 sub-filas)
        for ci, cf, val, campo in [(1, 1, n, None), (2, 8, proyecto, "proyecto"),
                                   (9, 11, cliente, "entidad_emisora"),
                                   (13, 13, objeto, "cargo_ocupado")]:
            ws.merge_cells(start_row=r, start_column=ci, end_row=r + 1, end_column=cf)
            c = ws.cell(r, ci, val); c.font, c.border, c.alignment = F_CELL, BORDER, AL_WRAP
            if campo in supuestos and val not in (None, ""):
                c.fill = FILL_SUPUESTO
        # sub-fila 1: fechas del certificado (amarillo = declarado) · sub-fila 2:
        # fechas según InfoObras (naranja = dato del backend). Sin ficha → "—".
        io_falta = "— (obra no ubicada en InfoObras)"
        for dr, fuente, fi, ff, fill in [
                (0, "Certificado", fini or "—", ffin or "—", FILL_CLAUDE),
                (1, "InfoObras", io_ini or io_falta,
                 io_fin or ("(sin fin)" if io_ini else io_falta), FILL_BACKEND)]:
            for ci, val in [(14, fuente), (15, fi), (16, ff)]:
                c = ws.cell(r + dr, ci, val)
                c.font, c.fill, c.border, c.alignment = F_CELL, fill, BORDER, AL_WRAP
                if dr == 0 and ci in (15, 16) and (
                        (ci == 15 and "fecha_inicial" in supuestos)
                        or (ci == 16 and "fecha_final" in supuestos)):
                    c.fill = FILL_SUPUESTO
                if isinstance(val, date):
                    c.number_format = FMT_FECHA
        for ci, val, fill in [(18, decl, FILL_CLAUDE), (19, efec, FILL_EFECTIVO)]:
            ws.merge_cells(start_row=r, start_column=ci, end_row=r + 1, end_column=ci)
            c = ws.cell(r, ci, val); c.font, c.border, c.alignment = F_CELL, BORDER, AL_HEAD
            if isinstance(val, (int, float)):
                c.number_format, c.fill = FMT_INT, fill
            if ci == 18 and {"fecha_inicial", "fecha_final"} & supuestos:
                c.fill = FILL_SUPUESTO
        lns = max(-(-len(str(proyecto)) // 74), -(-len(str(cliente)) // 43),
                  -(-len(str(objeto)) // 14), 1)   # alto total = celda más alta, en 2 filas
        alto = max(28, lns * 13 + 3)
        ws.row_dimensions[r].height = max(15, alto // 2)
        ws.row_dimensions[r + 1].height = max(15, alto - alto // 2)
        r += 2

    def _p5_tot(label, decl_v, efec_v, fill_e=FILL_EFECTIVO):
        nonlocal r
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=16)
        cl = ws.cell(r, 1, label); cl.font, cl.border, cl.alignment = F_BOLD, BORDER, AL_HEAD
        if decl_v is not None:
            cd = ws.cell(r, 18, decl_v)
            cd.font, cd.fill, cd.border, cd.number_format = F_BOLD, FILL_CLAUDE, BORDER, FMT_INT
        if efec_v is not None:
            ce = ws.cell(r, 19, efec_v)
            ce.font, ce.fill, ce.border, ce.number_format = F_BOLD, fill_e, BORDER, FMT_INT
        r += 1

    # ── PARTE 5 · variante EXPEDIENTES ───────────────────────────────────────
    # Cada experiencia baja como un bloque apilado en N (rótulo) + O:P (dato):
    # Certificado · MEF (contrato) · MEF (resolución) · Identificación · Alerta.
    def _p5_head_exp():
        nonlocal r
        for ci, cf, val in [(1, 1, "N°"), (2, 8, "Proyecto / Expediente técnico"),
                            (9, 13, "Emisor / cargo"),
                            (14, 15, "Inicio cálculo"),
                            (16, 17, "Fin cálculo"),
                            (18, 18, "Declarado (días)"), (19, 19, "Efectivo (días)")]:
            if cf > ci:
                ws.merge_cells(start_row=r, start_column=ci, end_row=r, end_column=cf)
            c = ws.cell(r, ci, val)
            c.font, c.fill, c.border, c.alignment = F_HEAD, FILL_HEAD, BORDER, AL_WRAP
        ws.merge_cells(start_row=r, start_column=20, end_row=r, end_column=26)
        c = ws.cell(r, 20, "Observación breve")
        c.font, c.fill, c.border, c.alignment = F_HEAD, FILL_HEAD, BORDER, AL_WRAP
        ws.row_dimensions[r].height = 30
        r += 1

    def _p5_exp(n, proyecto, cliente, objeto, ini, fin, deducida, decl, efec,
                certeza, alertas, mef, supuestos=None, motivo=None):
        """Fila compacta: las fuentes documentales permanecen en el detalle."""
        nonlocal r
        supuestos = set(supuestos or [])
        emisor_cargo = f"{cliente or '—'}\n{objeto or '—'}"
        observaciones = [certeza["etiqueta"]]
        if deducida:
            observaciones.append("mes completo según bases")
        if motivo:
            observaciones.append((f"No computado — {motivo}" if efec is None
                                  else f"Computado; pendiente: {motivo}"))
        elif alertas:
            observaciones.append("; ".join(alertas))
        observacion = " · ".join(x for x in observaciones if x)
        for ci, cf, val, campo in [(1, 1, n, None), (2, 8, proyecto, "proyecto"),
                                   (9, 13, emisor_cargo, "entidad_emisora"),
                                   (14, 15, ini or "—", None),
                                   (16, 17, fin or "—", None),
                                   (18, 18, decl if decl is not None else "—", None),
                                   (19, 19, efec if efec is not None else "No computado", None),
                                   (20, 26, observacion, None)]:
            if cf > ci:
                ws.merge_cells(start_row=r, start_column=ci, end_row=r, end_column=cf)
            c = ws.cell(r, ci, val); c.font, c.border, c.alignment = F_CELL, BORDER, AL_WRAP
            if campo in supuestos and val not in (None, ""):
                c.fill = FILL_SUPUESTO
            if isinstance(val, date):
                c.number_format = FMT_FECHA
            if deducida and ci in (14, 16):
                c.fill = FILL_SUPUESTO
        ws.cell(r, 18).fill = FILL_CLAUDE if decl is not None else FILL_PEND
        ws.cell(r, 19).fill = (_FILL_CERTEZA.get(certeza["color"]) or FILL_PEND)
        ws.row_dimensions[r].height = max(30, -(-len(observacion) // 70) * 14 + 6,
                                               -(-len(str(proyecto)) // 74) * 14 + 6,
                                               len(emisor_cargo.splitlines()) * 14 + 6)
        r += 1

    def _p5_tot_exp(label, efec_v, fill_e):
        _p5_tot(label, None, efec_v, fill_e)

    if not _es_concurso_expedientes:
        # ── camino histórico (concursos de OBRA): intacto ───────────────────
        _p5_head()
        _sd = _se = 0
        _n_decl = 0    # periodos que sí aportan días declarados (desfase máximo)
        for e in prof.get("experiencias", []):
            ne = e.get("n")
            ini_, fin_ = _fecha_iso(e.get("fecha_inicial")), _fecha_iso(e.get("fecha_final"))
            decl, efec, _clamp = _dias_exp(ne, ini_, fin_)
            fx_ = fichas.get((n_prof, ne)) or {}
            _p5(ne, e.get("proyecto") or "—", e.get("entidad_emisora") or "—",
                e.get("cargo_ocupado") or "—", ini_, fin_,
                _fecha_iso(fx_.get("fecha_inicio")), _fecha_iso(fx_.get("fecha_fin")),
                decl, efec,
                set(prof.get("supuestos") or []) | set(e.get("supuestos") or []))
            if isinstance(decl, (int, float)):
                _sd += decl
                _n_decl += 1
            if isinstance(efec, (int, float)):
                _se += efec

        res5 = (dias_efectivos_profesional(periodos_validos, paral_por_idx)
                if periodos_validos else None)
        _p5_tot("TOTAL, DÍAS (suma por experiencia)", _sd, _se)
        if res5 and res5.dias_traslape:
            _p5_tot("(−) Traslapes entre experiencias (ALT11)", None,
                    res5.dias_traslape, FILL_BACKEND)
        _dias_ef = res5.dias_efectivos if res5 else _se
        _hay_revision = any(
            _es_revision_efectiva(rev)
            for e in prof.get("experiencias", [])
            if (rev := revisiones.get((n_prof, e.get("n"))))
        )
        _p5_tot("DÍAS PROVISIONALES DEL PROFESIONAL — POR VERIFICAR" if _hay_revision
                else "DÍAS EFECTIVOS DEL PROFESIONAL", None, _dias_ef,
                FILL_PEND if _hay_revision else FILL_EFECTIVO)
        _fill_anios = FILL_PEND if _hay_revision else FILL_EFECTIVO
        _conclusion = None      # la arma el camino histórico, más abajo
    else:
        # ── camino EXPEDIENTES ──────────────────────────────────────────────
        # UNA sola fuente de días: `fechas_calculo` + `dias_efectivos_profesional`,
        # exactamente lo que hace `reconciliar_resultados_profesionales`. Antes la
        # tabla leía el ISO literal (descartando en silencio los certificados con
        # mes y año) y la conclusión leía el reconciliado: dos números distintos
        # para lo mismo (P5 439 vs 759, P9 574 vs 838, P12 926 vs 1056).
        _p5_head_exp()
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=26)
        leyenda_p5 = ("Declarado = duración del período del certificado calculada con "
                      "la regla vigente. Efectivo computado = aporte antes de descontar "
                      "traslapes; computar no verifica por sí solo tiempo ni cargo.")
        c_ley = ws.cell(r, 1, leyenda_p5)
        c_ley.font, c_ley.fill, c_ley.alignment = F_CELL, FILL_RECAP, AL_WRAP
        ws.row_dimensions[r].height = 32
        r += 1
        _periodos_exp: list[tuple[date, date]] = []
        _paral_exp: dict[int, list[tuple[date, date]]] = {}
        _dias_por_nivel: dict[str, int] = {}
        _hay_provisional = False
        _filas_exp: list[tuple] = []
        from entregables.expedientes import (motivo_periodo_no_computable,
                                             reconciliar_expedientes)
        enr_prof = {f"{n_prof}:{e.get('n')}": {
            **(fichas.get((n_prof, e.get("n"))) or {}),
            "sunat": sunat.get((n_prof, e.get("n"))),
        } for e in prof.get("experiencias", [])}
        espejo_prof = {"_meta": {"tipo_evaluacion": "expedientes"},
                       "reglas_evaluacion": {"periodos_sin_dia": regla_periodos},
                       "profesionales": [prof]}
        reconciliado_prof = reconciliar_expedientes(espejo_prof, enr_prof).get(n_prof, {})
        provisionales_exp = set(reconciliado_prof.get("veredicto_provisional") or [])
        motivos_exclusion = {x.get("n"): x.get("motivo") for x in
                             reconciliado_prof.get("experiencias_excluidas", [])}
        for e in prof.get("experiencias", []):
            ne = e.get("n")
            fx_ = fichas.get((n_prof, ne)) or {}
            # `enr` de esta experiencia: la proyección que viaja en `fichas` más
            # el bloque SUNAT, que llega por su propio canal.
            enr_ = {**fx_, "sunat": sunat.get((n_prof, ne))}
            certeza = clasificar_identificacion(e, enr_)
            alertas = alertas_experiencia(e, enr_)
            ini_, fin_, deducida_ = fechas_calculo(e, regla_periodos)
            motivo_periodo_ = (motivos_exclusion.get(ne)
                               or motivo_periodo_no_computable(e, regla_periodos))
            motivo_provisional_ = None
            if ne in provisionales_exp and not motivo_periodo_:
                if certeza.get("nivel") == "privada":
                    motivo_provisional_ = "identificación del emisor privado pendiente"
                elif enr_.get("sub_obras"):
                    motivo_provisional_ = "sub-obras pendientes de identificación"
                else:
                    motivo_provisional_ = "identificación del expediente pendiente"
            if not (ini_ and fin_) or fin_ < ini_:
                decl_ = efec_ = None
            else:
                idx_ = len(_periodos_exp)
                _periodos_exp.append((ini_, fin_))
                privada_ = str(enr_.get("via") or "").upper() == "PRIVADA"
                clamp_: list[tuple[date, date]] = []
                if not (privada_ or es_expediente_exp(e, tipo_evaluacion)):
                    for p in paralizaciones.get((n_prof, ne), []):
                        p_i, p_f = periodo_fechas(p)
                        c_i, c_f = max(p_i, ini_), min(p_f, fin_)
                        if c_f >= c_i:
                            clamp_.append((c_i, c_f))
                if clamp_:
                    _paral_exp[idx_] = clamp_
                decl_ = dias_inclusivos(ini_, fin_)
                efec_ = sum(dias_inclusivos(a, b)
                            for a, b in restar_paralizaciones((ini_, fin_), clamp_))
                cubeta = bucket_certeza(certeza)
                _dias_por_nivel[cubeta] = _dias_por_nivel.get(cubeta, 0) + efec_
            if es_provisional(certeza["nivel"]):
                _hay_provisional = True
            _filas_exp.append((e, ne, ini_, fin_, deducida_, decl_, efec_,
                               certeza, alertas, fuente_mef(enr_),
                               motivo_periodo_ or motivo_provisional_))

        for (e, ne, ini_, fin_, deducida_, decl_, efec_, certeza, alertas,
             mef, motivo_periodo_) in _filas_exp:
            mostrado = efec_
            _p5_exp(ne, e.get("proyecto") or "—", e.get("entidad_emisora") or "—",
                    e.get("cargo_ocupado") or "—", ini_, fin_, deducida_,
                    decl_, mostrado, certeza, alertas, mef,
                    set(prof.get("supuestos") or []) | set(e.get("supuestos") or []),
                    motivo=motivo_periodo_)

        res5 = (dias_efectivos_profesional(_periodos_exp, _paral_exp)
                if _periodos_exp else None)
        _dias_ef = res5.dias_efectivos if res5 else 0
        _traslape = res5.dias_traslape if res5 else 0
        _d_conf = _dias_por_nivel.get(BUCKET_CONFIRMADO, 0)
        _d_inf = _dias_por_nivel.get(BUCKET_INFERIDO, 0)
        _d_sin = _dias_por_nivel.get(BUCKET_SIN_IDENTIFICAR, 0)
        _d_priv = _dias_por_nivel.get(BUCKET_PRIVADA, 0)
        _suma_computada = sum(v for v in (x[6] for x in _filas_exp)
                              if isinstance(v, (int, float)))
        _p5_tot("TOTAL DECLARADO POR EXPERIENCIAS", sum(
            v for v in (x[5] for x in _filas_exp) if isinstance(v, (int, float))), None)
        _p5_tot_exp("SUMA COMPUTADA ANTES DE TRASLAPES", _suma_computada, FILL_CLAUDE)
        _p5_tot_exp("(−) TRASLAPES ENTRE EXPERIENCIAS", _traslape, FILL_BACKEND)
        _p5_tot_exp("TOTAL EFECTIVO NETO", _dias_ef, FILL_EFECTIVO)

        _fill_anios = (FILL_PEND if reconciliado_prof.get("veredicto_provisional")
                       else FILL_EFECTIVO)
        _conclusion = _conclusion_expedientes(
            {**prof, "cumple_backend": reconciliado_prof.get("cumple_backend")},
            _dias_ef, _traslape, _d_inf, _d_sin, _hay_provisional)

    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=18)
    ca = ws.cell(r, 1, "AÑOS EFECTIVOS (días efectivos / 365)")
    ca.font, ca.border, ca.alignment = F_BOLD, BORDER, AL_HEAD
    cy = ws.cell(r, 19, round(anios(_dias_ef), 2))
    cy.font, cy.fill, cy.border, cy.number_format = (
        F_BOLD, _fill_anios, BORDER, FMT_DEC)

    r += 2
    veredicto = prof.get("cumple_backend") or prof.get("cumple") or "POR VERIFICAR — sin conclusión"
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=6)
    cvl = ws.cell(r, 1, "CONCLUSIÓN DEL TIEMPO EFECTIVO")
    cvl.font, cvl.fill, cvl.border, cvl.alignment = F_BOLD, FILL_RECAP, BORDER, AL_HEAD
    ws.merge_cells(start_row=r, start_column=7, end_row=r, end_column=19)
    if _conclusion is not None:
        # Expedientes: el texto lo arma `_conclusion_expedientes` desde los MISMOS
        # días efectivos que acaba de imprimir la tabla. Nada de `conciliar_
        # conclusion`, que reescribía la frase con el total DECLARADO.
        veredicto = _visible = _conclusion
    else:
        # La conclusión y la PARTE 5 de arriba tienen que decir el MISMO número: si el
        # veredicto del evaluador cita el conteo sin bordes, se antepone el total
        # declarado verificado (`_sd`, el que acaba de imprimirse) y se explica el
        # otro. La línea del equipo evaluador (`cumple_backend`) no se toca: esa ya
        # trae su propia cifra, la de los días efectivos.
        _visible = _sin_jerga(veredicto)
        if not prof.get("cumple_backend"):
            _visible = conciliar_conclusion(_visible, _sd, _n_decl)
    cver = ws.cell(r, 7, _visible)
    cver.font, cver.border, cver.alignment = F_BOLD, BORDER, AL_WRAP
    # El color sale del veredicto ORIGINAL: con el prefijo delante,
    # `_clasificar_veredicto` ya no reconocería el «CUMPLE» inicial.
    cver.fill = (_fill_veredicto(veredicto, "pos") or FILL_PEND)
    ws.row_dimensions[r].height = max(30, (-(-len(str(cver.value)) // 90)) * 14 + 4)

    # ── CRUCE DE FECHAS (T-011), justo bajo la PARTE 5 ───────────────────────
    # La hoja «Cronología de expedientes» es la vista de conjunto del Comité;
    # este bloque es la misma verdad al lado del profesional que se está
    # evaluando, con UNA entrada por experiencia — incluidas las que no tienen
    # proceso publicado, que aparecen con su abstención rotulada en vez de
    # desaparecer. Los valores, textos y colores salen de `presentacion_cruces`:
    # una sola fuente para las dos vistas.
    #
    # Formato VERTICAL (feedback de Rafael, 6-ago): una tarjeta por experiencia
    # — etiqueta en A, dato en B:D — en vez de la tabla ancha de 19 columnas,
    # que resultaba difícil de leer. Los colores no cambian: amarillo en lo que
    # declara el certificado, violeta en la fecha deducida, semáforo en las
    # respuestas. El «NO APLICA» de la tabla ancha desapareció de estas
    # tarjetas (el tipo va en el título); la hoja global lo conserva porque
    # allá todas las experiencias comparten columnas.
    #
    # OJO con `r`: la PARTE 5 termina escribiendo EN la fila `r` sin avanzarla
    # (mismo detalle que documenta el bloque del factor, más abajo).
    if prof.get("experiencias"):
        r += 2
        banda("CRUCE DE FECHAS CONTRA EL CONTRATO Y LA APROBACIÓN DEL EXPEDIENTE",
              F_PARTE, FILL_PARTE, 18)

        def _cf_fila(etiqueta, valor, *, fill=None):
            """Etiqueta (A) + dato (B:D). Devuelve la celda del dato para que
            el llamador la pinte (respuestas, fecha deducida)."""
            nonlocal r
            cl = ws.cell(r, 1, etiqueta)
            cl.font, cl.border = F_BOLD, BORDER
            cl.alignment = Alignment(vertical="top", wrap_text=True)
            ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=4)
            v = _sin_jerga(valor) if isinstance(valor, str) else valor
            cv = ws.cell(r, 2, "—" if v in (None, "") else v)
            cv.font, cv.border, cv.alignment = F_CELL, BORDER, AL_WRAP
            if isinstance(valor, date):
                cv.number_format = FMT_FECHA_LARGA
            if fill is not None and valor not in (None, ""):
                cv.fill = fill
            r += 1
            return cv

        for e in prof.get("experiencias", []):
            p = presentacion_cruces(e, fichas.get((n_prof, e.get("n"))), tipo_evaluacion)
            # La tarjeta muestra SOLO lo que aplica a su tipo (pedido de Rafael,
            # 6-ago): en una obra las filas de término/aprobación nunca dicen
            # nada — el tipo va en el título y esas filas se omiten. La vara es
            # la misma de la Regla B (`aplica_b`): expediente cuando hay
            # verificación/aprobación o el proceso es de expediente. El término
            # de una obra no queda huérfano: su verificación real es el clamp
            # por valorizaciones, que ya vive en la PARTE 5 y en la ficha.
            es_exped = p["aplica_b"]
            titulo = (f"EXPERIENCIA {p['n_exp']} · "
                      + ("expediente" if es_exped else "obra"))
            if p["proceso"]:
                titulo += f" · proceso {p['proceso']}"
            ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=4)
            c = ws.cell(r, 1, titulo)
            c.font, c.fill, c.border, c.alignment = F_HEAD, FILL_HEAD, BORDER, AL_HEAD
            r += 1
            _cf_fila("Inicio declarado", p["inicio"], fill=FILL_CLAUDE)
            _cf_fila("Firma del contrato", p["firma"])
            _pintar_respuesta(
                _cf_fila("¿Empezó después de firmado el contrato?", p["resp_a"]),
                p["resp_a"])
            if es_exped:
                _cf_fila("Término declarado", p["fin"], fill=FILL_CLAUDE)
                cap = _cf_fila("Aprobación del expediente", p["aprobacion"])
                if p["inferida"]:
                    cap.fill = FILL_SUPUESTO   # violeta = fecha deducida
                _pintar_respuesta(
                    _cf_fila("¿Terminó antes de aprobarse el expediente?",
                             p["resp_b"]),
                    p["resp_b"])
            # La explicación, a todo lo ancho de la tarjeta: es el texto que el
            # evaluador copia al acta, no un tooltip.
            texto = p["motivo"] or "Sin observaciones sobre las fechas."
            ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=4)
            c = ws.cell(r, 1, texto)
            c.font, c.border, c.alignment = F_CELL, BORDER, AL_WRAP
            if p["resp_a"] == "POR VERIFICAR" or p["resp_b"] == "POR VERIFICAR":
                c.fill = FILL_PEND
            ws.row_dimensions[r].height = max(15, (-(-len(texto) // 88)) * 13 + 3)
            r += 2      # fila en blanco entre tarjetas

    # ── Factor de evaluación, AL FINAL de la hoja (issue #32) ────────────────
    # La página del Cuadro de Factores (4.2 A — la tabla de puntaje) cierra la
    # hoja: es el baremo con el que se puntúa todo lo de arriba, y el evaluador
    # lo quiere a la mano "para no estar buscando" en las bases. Es la MISMA
    # página para todos, replicada por profesional (ver `_mapear_dir_certs`).
    # OJO con `r`: la PARTE 5 termina escribiendo EN la fila `r` sin avanzarla
    # (nunca hubo nada debajo). Sin este salto, la banda de `embeber_cert` se
    # mergea sobre esa misma fila y openpyxl la absorbe SIN error: el archivo
    # sale válido pero con el título del factor pisando "AÑOS EFECTIVOS" y el
    # número de años huérfano en la columna S.
    _factor_pdf = certificados.get((n_prof, "FACTOR"))
    if _factor_pdf:
        r += 2
        if _factor_a_pdf_valido(_factor_pdf):
            embeber_cert(_factor_pdf, "FACTOR DE EVALUACIÓN — recorte de las bases "
                                      "(el baremo con el que se puntúa lo anterior)")
        else:
            banda("⚠ FACTOR A NO EMBEBIDO — el recorte recibido corresponde a otro "
                  "factor de las bases; corregir la página de origen", F_AVISO, FILL_AVISO)

    # Cierre visual de cada hoja de expedientes. El bloque ya fue resuelto por
    # la misma fuente que alimenta la cronología general; Pillow solo lo pinta.
    if _es_concurso_expedientes and bloque_gantt:
        from entregables.gantt_profesional import renderizar_gantt_profesional
        from openpyxl.drawing.image import Image as XLImage

        r += 2
        fila_gantt = r
        banda("LÍNEA DE TIEMPO FINAL — PERÍODOS DECLARADOS Y CRUCES DOCUMENTALES",
              F_PARTE, FILL_PARTE, 22)
        ancho_px = int(sum((ws.column_dimensions[get_column_letter(i)].width or 8)
                           * 7 + 5 for i in range(1, 27)))
        contenido, img_ancho, img_alto = renderizar_gantt_profesional(
            bloque_gantt, ancho=max(1100, ancho_px))
        img = XLImage(contenido)
        img.width = ancho_px
        img.height = int(img_alto * ancho_px / img_ancho)
        ws.add_image(img, f"A{r}")
        filas_imagen = max(1, -(-img.height // 20))
        for fr in range(r, r + filas_imagen):
            ws.row_dimensions[fr].height = 15
        r += filas_imagen
        ws.print_area = f"A1:Z{r}"
        ws.row_breaks.append(Break(id=fila_gantt - 1))


# ── Entregable completo ──────────────────────────────────────────────────────

def generar_excel_final(
    espejo: dict,
    salida: Path,
    paralizaciones: Optional[Paralizaciones] = None,
    cuis: Optional[dict] = None,
    fichas: Optional[dict] = None,
    revisiones: Optional[dict] = None,
    sunat: Optional[dict] = None,
    certificados: Optional[dict] = None,
    confiabilidad: Optional[dict] = None,
) -> Path:
    """Construye el Excel final: CLAUDE + Base de Datos + 1 hoja por profesional.

    `paralizaciones`: {(n_prof, n_exp): [(inicio, fin), …]} — las ventanas de
    paralización de la obra de cada experiencia, resueltas por la etapa
    INFOOBRAS. Sin ellas, los cuadros muestran brutos = efectivos.
    `cuis`: {(n_prof, n_exp): "2418877"} — el CUI que el backend resolvió por
    experiencia (la etapa InfoObras). Sin él, se usa el CUI del espejo si existe.
    `fichas`: {(n_prof, n_exp): {codigo_infoobras, cui, estado, monto,
    fecha_inicio, fecha_fin, valorizaciones:[…]}} — la ficha de la obra y todas
    sus valorizaciones, para el bloque de la derecha en la hoja del profesional.
    """
    from validacion.recalculo import regla_periodos_de

    paralizaciones = paralizaciones or {}
    cuis = cuis or {}
    fichas = fichas or {}
    revisiones = revisiones or {}
    sunat = sunat or {}
    certificados = certificados or {}
    revisiones_analiticas = len(revisiones)
    revisiones_analiticas += sum(
        1 for p in espejo.get("profesionales", []) or []
        if (((p.get("_backend") or {}).get("formacion") or {}).get("estado")
            == "revision_manual")
    )
    if ((espejo.get("postor") or {}).get("experiencia_postor_total") or {}).get("estado") == "condicionado":
        revisiones_analiticas += 1
    if (espejo.get("resumen_evaluacion") or {}).get("estado_puntaje") == "condicionado":
        revisiones_analiticas += 1
    meta = espejo.setdefault("_meta", {})
    meta["estado_entregable"] = (
        f"FINAL AUTOMÁTICO — REQUIERE REVISIÓN ({revisiones_analiticas})"
        if revisiones_analiticas else "FINAL AUTOMÁTICO — SIN REVISIONES")
    meta["generado_en"] = datetime.now().astimezone().isoformat(timespec="seconds")

    def _analitico(v):
        if isinstance(v, dict):
            excluir = {"descargas_reales", "descarga_documentos", "descargas_estado",
                       "zip_infoobras", "generado_en", "huella_analitica"}
            return {k: _analitico(x) for k, x in v.items() if k not in excluir}
        if isinstance(v, list):
            return [_analitico(x) for x in v]
        return v

    canon = json.dumps(_analitico(espejo), sort_keys=True, default=str,
                       ensure_ascii=False, separators=(",", ":"))
    meta["huella_analitica"] = hashlib.sha256(canon.encode("utf-8")).hexdigest()[:16]
    wb = openpyxl.Workbook()

    ws = wb.active
    ws.title = "CLAUDE"
    construir_hoja_evaluacion(ws, espejo, confiabilidad=confiabilidad)

    construir_hoja_base_datos(wb.create_sheet("Base de Datos"), espejo, cuis,
                              revisiones)

    tipo_excel = _tipo_evaluacion_espejo(espejo)
    fichas_crono = dict(fichas)
    for clave, revision in revisiones.items():
        if _es_ruta_privada(revision):
            fichas_crono[clave] = {**(fichas_crono.get(clave) or {}),
                                   "via": "PRIVADA",
                                   "privada_pendiente": _es_privada_pendiente(revision)}
    from resolucion.cui import TIPO_EXPEDIENTES
    bloques_gantt = (_bloques_linea_de_tiempo(espejo, fichas_crono, tipo_excel)
                     if tipo_excel == TIPO_EXPEDIENTES else [])
    gantt_por_prof = {b.get("n_prof"): b for b in bloques_gantt}

    for prof in espejo.get("profesionales", []):
        nombre = etiqueta_hoja(prof.get("n_prof", 0), prof.get("cargo", ""))
        certs_prof = {k: v for k, v in certificados.items() if k[0] == prof.get("n_prof")}
        construir_hoja_profesional(wb.create_sheet(nombre), prof, paralizaciones,
                                   cuis, fichas, revisiones, sunat, certs_prof,
                                   tipo_evaluacion=tipo_excel,
                                   regla_periodos=regla_periodos_de(espejo),
                                   bloque_gantt=gantt_por_prof.get(prof.get("n_prof")))

    # T-011 · hoja ADITIVA, al final: el formato congelado (CLAUDE + Base de
    # Datos + una por profesional) conserva su orden y su contenido exactos.
    construir_hoja_cronologia(wb.create_sheet(HOJA_CRONOLOGIA), espejo,
                              fichas_crono)

    validar_integridad_entregable(wb, espejo)
    salida.parent.mkdir(parents=True, exist_ok=True)
    wb.save(salida)
    return salida


def validar_integridad_entregable(wb, espejo: dict) -> None:
    """Gate final: el libro no puede publicar autoridades contradictorias."""
    prohibidos = (
        "pendiente de descarga", "documentos en el zip", "redescargar",
        "redactadas antes del recálculo", "¿últimos 20 años?",
    )
    hallazgos = []
    for ws in wb.worksheets:
        for fila in ws.iter_rows():
            for celda in fila:
                if not isinstance(celda.value, str):
                    continue
                bajo = celda.value.lower()
                for texto in prohibidos:
                    if texto in bajo:
                        hallazgos.append(f"{ws.title}!{celda.coordinate}: {texto}")
    resumen = espejo.get("resumen_evaluacion") or {}
    total = resumen.get("puntaje_total")
    factores = resumen.get("factores", []) or []
    if isinstance(total, (int, float)) and factores:
        suma = sum(float(f.get("puntaje")) for f in factores
                   if isinstance(f.get("puntaje"), (int, float)))
        if abs(float(total) - suma) > 0.005:
            hallazgos.append(f"puntaje_total={total} pero factores={suma}")
    if resumen.get("estado_puntaje") == "condicionado" and total is not None:
        hallazgos.append("puntaje condicionado conserva un total definitivo")
    if hallazgos:
        raise ValueError("Entregable inconsistente: " + "; ".join(hallazgos[:12]))


def desempaquetar_enriquecimiento(enriquecimiento: Optional[dict]):
    """De `{'N:M': {...}, 'prof:N': {...}}` (lo que guarda el orquestador) a los
    cuatro dicts `(paral, cuis, fichas, sunat)` que consume `generar_excel_final`.

    Es la MISMA lógica que arma la etapa EXCEL del pipeline; está factorizada aquí
    para que el backfill regenere el Excel sin re-correr scrapers ni duplicarla."""
    paral: dict = {}
    cuis: dict = {}
    fichas: dict = {}
    sunat: dict = {}
    for k, enr in (enriquecimiento or {}).items():
        if ":" not in k or k.startswith("prof:"):
            continue
        np_, ne = (int(x) for x in k.split(":"))
        if enr.get("paralizaciones"):
            paral[(np_, ne)] = enr["paralizaciones"]
        if enr.get("cui"):
            cuis[(np_, ne)] = enr["cui"]
        if enr.get("sunat"):
            sunat[(np_, ne)] = enr["sunat"]
        if (enr.get("obra_ficha") or enr.get("valorizaciones")
                or enr.get("representante_obra") or enr.get("aprobacion_expediente")
                or enr.get("verificacion_expediente") or enr.get("seace")
                or enr.get("inventario_documental") or enr.get("cruces_fechas")
                or enr.get("resoluciones_candidatos")
                or enr.get("sin_documentos_mef") or enr.get("contrato_emisor")
                or enr.get("via") or enr.get("cui") or enr.get("sub_obras")):
            # `obra_ficha` NO trae el nombre (solo código/CUI/estado/monto/fechas);
            # el nombre viaja suelto en `obra_nombre` (o en `obra.nombre_obra`) y sin
            # esta línea nunca llegaba al Excel — el evaluador no podía ver con qué
            # obra se emparejó el certificado.
            _obra = enr.get("obra") if isinstance(enr.get("obra"), dict) else {}
            fichas[(np_, ne)] = {**(enr.get("obra_ficha") or {}),
                                 "cui": (enr.get("cui")
                                         or (enr.get("obra_ficha") or {}).get("cui")),
                                 "obra_nombre": (enr.get("obra_nombre")
                                                 or _obra.get("nombre_obra")),
                                 "valorizaciones": enr.get("valorizaciones") or [],
                                 "modificaciones_plazo": enr.get("modificaciones_plazo") or [],
                                 "representante_obra": enr.get("representante_obra"),
                                 "aprobacion_expediente": enr.get("aprobacion_expediente"),
                                 "verificacion_expediente": enr.get("verificacion_expediente"),
                                 # La PARTE 5 de expedientes tiene que poder decir
                                 # «el MEF no publica contrato ni resolución» en vez
                                 # de dejar la fila muda: sin esta marca, un
                                 # expediente sin documentos se veía igual que uno
                                 # con la consulta fallida.
                                 "sin_documentos_mef": enr.get("sin_documentos_mef"),
                                 # Vía CONTRATO: el contrato que ATA al emisor con
                                 # el expediente (manda sobre el elegido por
                                 # heurística en `verificacion_expediente`).
                                 "contrato_emisor": enr.get("contrato_emisor"),
                                 # Multi-obra al que le faltan sub-obras por ubicar.
                                 "identificacion_incompleta": enr.get("identificacion_incompleta"),
                                 # Resolución de aprobación LEÍDA (fecha, consultor) y
                                 # camino con que se enrutó (ADR-010): deciden el bloque
                                 # expediente/obra de la ficha y sus filas de contraste.
                                 "resolucion_aprobacion": enr.get("resolucion_aprobacion"),
                                 "resoluciones_candidatos": enr.get("resoluciones_candidatos"),
                                 "camino": enr.get("camino"),
                                 "camino_fuente": enr.get("camino_fuente"),
                                 "seace": enr.get("seace"),
                                 "inventario_documental": enr.get("inventario_documental"),
                                 "documentos_encontrados": enr.get("documentos_encontrados"),
                                 "tipo_experiencia": enr.get("tipo_experiencia"),
                                 "via": enr.get("via"),
                                 "sin_verificar": enr.get("sin_verificar"),
                                 "sunat": enr.get("sunat"),
                                 # T-011: los cruces de fechas de la etapa REGLAS.
                                 # Viajan dentro de `fichas` (y no como argumento
                                 # nuevo) para no cambiar la firma de
                                 # `generar_excel_final`, igual que `seace`.
                                 "cruces_fechas": enr.get("cruces_fechas"),
                                 # #63: N registros de obra bajo el mismo CUI
                                 "registros_cui": enr.get("registros_cui")}
        # cert multi-obra: la lista de sub-obras verificadas viaja en `fichas` para
        # que el render la muestre (sin cambiar la firma de generar_excel_final).
        if enr.get("sub_obras"):
            fichas[(np_, ne)] = {**(fichas.get((np_, ne)) or {}),
                                 "sub_obras": enr["sub_obras"],
                                 "via": enr.get("via"),
                                 "identificacion_incompleta": enr.get("identificacion_incompleta"),
                                 "multi_rubro": enr.get("multi_rubro")}
    return paral, cuis, fichas, sunat


def inyectar_veredicto_backend(espejo: dict, enriquecimiento: Optional[dict]) -> None:
    """Copia veredicto y desglose de totales del enriquecimiento al espejo.

    El espejo se persiste UNA vez (al crear el job) y no se vuelve a guardar; el
    enriquecimiento sí se persiste tras cada etapa. En la corrida en vivo la etapa
    REGLAS ya deja el veredicto en el espejo en memoria, pero al REGENERAR el Excel
    desde disco ese espejo viene sin él — y la hoja resumen volvería a mostrar solo
    el veredicto del LLM, que es justo el defecto de #51. Modifica `espejo` in situ.
    """
    resultados = reconciliar_resultados_profesionales(espejo, enriquecimiento)
    for p in (espejo or {}).get("profesionales", []):
        np_ = p.get("n_prof")
        d = resultados.get(np_) or {}
        if isinstance(enriquecimiento, dict) and d:
            # La copia cargada para el Excel queda alineada con lo que se
            # presenta. El repositorio no se escribe desde este helper.
            enriquecimiento[f"prof:{np_}"] = d
        if d:
            p["total_backend"] = {
                "dias_declarados": d.get("dias_brutos"),
                "dias_paralizados": d.get("dias_paralizados"),
                "dias_traslape": d.get("dias_traslape"),
                "dias_efectivos": d.get("dias_efectivos"),
                "anios_efectivos": d.get("anios_efectivos"),
                "incompleto": bool(d.get("veredicto_provisional")),
            }
            p["dias_efectivos_backend"] = d.get("dias_efectivos")
        p.pop("cumple_backend", None)
        p.pop("minimo_exigido_backend", None)
        if d.get("cumple_backend"):
            p["cumple_backend"] = d["cumple_backend"]
            p["minimo_exigido_backend"] = d.get("minimo_texto")
    # También al regenerar desde disco: el puntaje heredado de Factor A no puede
    # sobrevivir si los efectivos actuales no sostienen sus excedentes.
    from orquestador.etapas_reales import _recalcular_factor_a
    _recalcular_factor_a(espejo, enriquecimiento or {})


def inyectar_cruces_fechas(espejo: dict, enriquecimiento: Optional[dict]) -> int:
    """Calcula los cruces de fechas (T-011) de las experiencias que aún no los
    traen, para que un Excel REGENERADO los muestre sin re-correr el pipeline.

    Es el mismo motor puro que usa la etapa REGLAS (`reglas.cruces_fechas`), así
    que el resultado es idéntico al de una corrida en vivo con las mismas
    fuentes; no toca red ni disco. Solo RELLENA: una experiencia que ya trae
    `cruces_fechas` se respeta tal cual (lo que se entregó es lo que se guardó).
    Devuelve cuántas experiencias se completaron."""
    from reglas.cruces_fechas import REGLA_TERMINO, cruces_de_experiencia
    enr_todo = enriquecimiento if isinstance(enriquecimiento, dict) else None
    if enr_todo is None:
        return 0

    def _cruces_consideran_resolucion(enr: dict) -> bool:
        """¿Los cruces guardados ya vieron la resolución LEÍDA? Si la lectura llegó
        después (job procesado antes de esta capacidad, o relectura), se recalculan:
        es evidencia oficial nueva, la misma que usaría una corrida en vivo."""
        lect = enr.get("resolucion_aprobacion")
        if not isinstance(lect, dict) or not lect.get("legible"):
            return True
        for c in enr.get("cruces_fechas") or []:
            if not isinstance(c, dict) or c.get("regla") != REGLA_TERMINO:
                continue
            if lect.get("fecha") and c.get("fecha_fuente") == lect["fecha"]:
                return True
            if "nombra como consultor" in str(c.get("motivo") or ""):
                return True
        return False

    n = 0
    for prof in (espejo or {}).get("profesionales", []):
        for e in prof.get("experiencias", []):
            k = f"{prof.get('n_prof')}:{e.get('n')}"
            enr = enr_todo.get(k)
            if not isinstance(enr, dict):
                continue
            if enr.get("cruces_fechas") and _cruces_consideran_resolucion(enr):
                continue
            enr["cruces_fechas"] = [c.como_dict()
                                    for c in cruces_de_experiencia(enr, e)]
            n += 1
    return n


def regenerar_excel_final(espejo: dict, enriquecimiento: Optional[dict],
                          salida: Path, revisiones: Optional[dict] = None,
                          certificados: Optional[dict] = None,
                          confiabilidad: Optional[dict] = None) -> Path:
    """Regenera el Excel final desde el espejo + enriquecimiento YA en disco (sin
    tocar red). Lo usa el backfill de cargos para dejar el entregable limpio.

    `certificados`: si no se pasa, se mapea la carpeta `certs/` HERMANA del Excel
    (el layout del repositorio: `<job>/final.xlsx` + `<job>/certs/`). Antes no se
    pasaban en absoluto, así que regenerar arrancaba TODAS las imágenes embebidas
    (constancias, TDR, Anexo 16) del entregable — silenciosamente."""
    inyectar_cruces_fechas(espejo, enriquecimiento)
    from validacion import construir_inventario_documental
    construir_inventario_documental(espejo, enriquecimiento or {})
    paral, cuis, fichas, sunat = desempaquetar_enriquecimiento(enriquecimiento)
    from validacion import (aplicar_reglas_formacion, aplicar_reglas_iso,
                            recalcular_experiencia_postor,
                            reconciliar_puntajes)
    from validacion.recalculo import recalcular_espejo
    recalcular_espejo(espejo, sobrescribir=True)
    aplicar_reglas_formacion(espejo)
    recalcular_experiencia_postor(espejo)
    aplicar_reglas_iso(espejo)
    reconciliar_puntajes(espejo)
    inyectar_veredicto_backend(espejo, enriquecimiento)
    salida = Path(salida)
    if certificados is None:
        certificados = _mapear_dir_certs(salida.parent / "certs")
    if salida.exists():
        salida.unlink()
    return generar_excel_final(espejo, salida, paral, cuis, fichas, revisiones or {},
                               sunat, certificados, confiabilidad=confiabilidad)
