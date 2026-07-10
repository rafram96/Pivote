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
import io
import re
from datetime import date
from pathlib import Path
from typing import Optional

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from reglas import (
    anios, dias_efectivos_profesional, dias_inclusivos, periodo_fechas,
    restar_paralizaciones,
)
from scripts.generar_excel import (
    AL_HEAD, AL_WRAP, BORDER, F_BOLD, F_CELL, F_HEAD, F_PARTE, F_PROF,
    FILL_BACKEND, FILL_CLAUDE, FILL_HEAD, FILL_PARTE, FILL_PROF,
    FMT_DEC, FMT_FECHA, FMT_INT, _fill_veredicto, construir_hoja_evaluacion,
    fecha_excel,
)

Paralizaciones = dict[tuple[int, int], list[tuple[date, date]]]

# Paleta de fondos por profesional para la hoja Base de Datos (suaves, ciclan)
_PALETA_PROF = ["FFF2CC", "DDEBF7", "E2EFDA", "FCE4D6", "EDEDED", "D9E1F2",
                "FBE2D5", "E4DFEC"]

# Amarillo para resaltar las valorizaciones que caen dentro del certificado
FILL_VALOR = PatternFill("solid", fgColor="FFFF00")
# Rojo: meses PARALIZADOS en la tabla de valorizaciones (la obra estuvo parada → no
# cuentan para la experiencia; el ingeniero los marcaba así, a mano e incompleto).
F_CELL_ROJO = Font(size=9, color="FF0000")
# Amarillo separador: 2 filas (A:Z) entre experiencias en la hoja por profesional
FILL_SEP = PatternFill("solid", fgColor="FFFF00")
# Semántico para el cuadro del emisor (SUNAT): rojo = anomalía (ALT04), verde = ok.
FILL_ALERTA = PatternFill("solid", fgColor="F4CCCC")
FILL_OK = PatternFill("solid", fgColor="D9EAD3")
# Sistema de color del ingeniero en las hojas por profesional:
#   amarillo = declarado / dentro del periodo · cyan = efectivo verificado (Paso 5)
#   naranja = excluido (paralización / sin valorización) · azules = jerarquía de marco.
FILL_EFECTIVO = PatternFill("solid", fgColor="00FFFF")     # cyan: días efectivos
FILL_CERT = PatternFill("solid", fgColor="FFFF00")         # amarillo: encabezado CERT N°X
F_CERT = Font(bold=True, size=10, color="15212E")
FILL_DATOS = PatternFill("solid", fgColor="1F4E78")        # azul oscuro: header del recap
F_DATOS = Font(bold=True, size=10, color="FFFFFF")
FILL_RECAP = PatternFill("solid", fgColor="DDEBF7")        # azul claro: etiquetas del recap
FMT_SOLES = '#,##0.00'
# El avance físico de InfoObras ya viene en escala de porcentaje (38.36 = 38.36%).
# El formato nativo '0.00%' de Excel multiplica ×100 (mostraría 3836.00%), así que
# usamos el '%' como literal para no reescalar.
FMT_PCT = '0.00"%"'

_MES_ES = {1: "ENERO", 2: "FEBRERO", 3: "MARZO", 4: "ABRIL", 5: "MAYO",
           6: "JUNIO", 7: "JULIO", 8: "AGOSTO", 9: "SEPTIEMBRE",
           10: "OCTUBRE", 11: "NOVIEMBRE", 12: "DICIEMBRE"}


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


def _nombre_hoja(n_prof: int, cargo: str) -> str:
    """Nombre de hoja Excel útil y corto (≤31 chars). Quita el prefijo redundante
    "Especialista en/de" (el cargo distintivo se ve de una) y, si aún excede,
    corta en LÍMITE DE PALABRA — no a media palabra. El prefijo P{n} garantiza
    unicidad aunque dos cargos empiecen igual."""
    txt = re.sub(r'[\\/*?:\[\]]', "", cargo or "").strip()
    txt = re.sub(r"^especialista\s+(?:en|de|del)\s+", "", txt, flags=re.I)
    base = f"P{n_prof} {txt}".strip()
    if len(base) <= 31:
        return base
    cut = base[:31]
    if base[31] != " ":               # solo retrocede si cortó a media palabra
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(" ,;-")


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


def mapear_certificados(dir_base, job_id) -> dict:
    """Lee la carpeta `{job_id}.certs/` (un PDF `P{n}_E{m}.pdf` por experiencia, con
    la página principal primero — lo recorta la skill) y devuelve
    `{(n_prof, n_exp): Path}` para pasarle a `generar_excel_final`."""
    certs: dict = {}
    cdir = Path(dir_base) / f"{job_id}.certs"
    if cdir.is_dir():
        for f in cdir.glob("P*_E*.pdf"):
            try:
                np_, ne = f.stem[1:].split("_E")
                certs[(int(np_), int(ne))] = f
            except ValueError:
                continue
        # Mejora A: recorte del TDR (de las bases) y del Anexo 16 por profesional,
        # `P{n}_TDR.pdf` / `P{n}_ANEXO.pdf` → clave (n_prof, "TDR"/"ANEXO"). No
        # colisiona con las experiencias (n_exp es int).
        for tag in ("TDR", "ANEXO"):
            for f in cdir.glob(f"P*_{tag}.pdf"):
                try:
                    certs[(int(f.stem[1:].split("_")[0]), tag)] = f
                except ValueError:
                    continue
    return certs


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


def construir_hoja_base_datos(ws, espejo: dict) -> int:
    """Construye la hoja "Base de Datos". Devuelve el nº de filas de datos."""
    for i, w in enumerate(_BD_WIDTHS, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w

    for i, h in enumerate(_BD_HEAD, start=1):
        c = ws.cell(1, i, h)
        c.font, c.fill, c.border, c.alignment = F_HEAD, FILL_HEAD, BORDER, AL_HEAD
    ws.row_dimensions[1].height = 30

    r = 2
    for idx, prof in enumerate(espejo.get("profesionales", [])):
        fill = PatternFill("solid", fgColor=_PALETA_PROF[idx % len(_PALETA_PROF)])
        for e in prof.get("experiencias", []):
            valores = [
                prof.get("cargo"), prof.get("n_prof"), prof.get("nombre"),
                prof.get("colegiatura"), e.get("n"), e.get("entidad_emisora"),
                e.get("proyecto"), e.get("cui"), e.get("tipo_documento"),
                e.get("nombre_emisor"), e.get("cargo_emisor"),
                fecha_excel(e.get("fecha_inicial")), fecha_excel(e.get("fecha_final")),
                fecha_excel(e.get("fecha_emision")), e.get("folio"),
                e.get("dias"), e.get("meses"), e.get("anios"), e.get("cargo_ocupado"),
                e.get("cargo_bases_valido"), e.get("anterior_colegiatura"),
                e.get("incluye_covid"), e.get("traslape"), e.get("tipo_obra_valido"),
                e.get("observaciones"),
            ]
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
            r += 1

    ws.auto_filter.ref = f"A1:{get_column_letter(len(_BD_HEAD))}{max(r - 1, 1)}"
    ws.freeze_panes = "A2"
    return r - 2


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
    return v


def construir_hoja_profesional(
    ws, prof: dict, paralizaciones: Paralizaciones,
    cuis: Optional[dict] = None,
    fichas: Optional[dict] = None,
    revisiones: Optional[dict] = None,
    sunat: Optional[dict] = None,
    certificados: Optional[dict] = None,
) -> None:
    cuis = cuis or {}
    fichas = fichas or {}
    revisiones = revisiones or {}
    sunat = sunat or {}
    certificados = certificados or {}
    # A:D hitos · F:K obra+valorizaciones · M:P emisor SUNAT · R:U representante de obra
    anchos = {"A": 52, "B": 14, "C": 14, "D": 10, "E": 2,
              "F": 5, "G": 18, "H": 14, "I": 18, "J": 14, "K": 13, "L": 2,
              "M": 16, "N": 12, "O": 18, "P": 12, "Q": 2,
              "R": 17, "S": 12, "T": 22, "U": 14}
    for col, w in anchos.items():
        ws.column_dimensions[col].width = w
    n_prof = prof.get("n_prof")
    r = 1

    # ancho útil (caracteres aprox.) de la banda combinada A:D, para envolver
    # títulos largos sin truncarlos.
    _ancho_banda = sum({"A": 52, "B": 14, "C": 14, "D": 10}.values())

    def banda(texto, font=F_PROF, fill=FILL_PROF, h=20):
        nonlocal r
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
        valores = [hito, desde, hasta, dias_v]
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
        ws.merge_cells(start_row=rr, start_column=6, end_row=rr, end_column=10)
        c = ws.cell(rr, 6, "OBRA EN INFOOBRAS (origen del análisis)")
        c.font, c.fill, c.alignment = F_HEAD, FILL_HEAD, AL_HEAD
        rr += 1

        def kv(label, value, fmt=None):
            nonlocal rr
            ws.merge_cells(start_row=rr, start_column=6, end_row=rr, end_column=7)
            cl = ws.cell(rr, 6, label); cl.font, cl.border = F_BOLD, BORDER
            ws.merge_cells(start_row=rr, start_column=8, end_row=rr, end_column=10)
            cv = ws.cell(rr, 8, value); cv.font, cv.border, cv.alignment = F_CELL, BORDER, AL_WRAP
            if fmt and isinstance(value, (int, float, date)):
                cv.number_format = fmt
            rr += 1

        kv("Código InfoObras", fx.get("codigo_infoobras") or "—")
        kv("CUI", fx.get("cui") or "—")
        kv("Estado de obra", fx.get("estado") or "—")
        kv("Monto ejecutado (S/)", fx.get("monto") if fx.get("monto") is not None else "—", FMT_SOLES)
        kv("Inicio de obra", _fecha_iso(fx.get("fecha_inicio")) or "—", FMT_FECHA)
        kv("Fin de obra", _fecha_iso(fx.get("fecha_fin")) or "—", FMT_FECHA)
        rr += 1

        vals = sorted(fx.get("valorizaciones") or [],
                      key=lambda v: (v.get("anio") or 0, v.get("mes") or 0), reverse=True)
        ws.merge_cells(start_row=rr, start_column=6, end_row=rr, end_column=11)
        c = ws.cell(rr, 6, "VALORIZACIONES — en amarillo, las del periodo del certificado")
        c.font, c.fill = F_PARTE, FILL_PARTE
        c.alignment = Alignment(vertical="center", wrap_text=True)
        rr += 1
        for i, h in enumerate(["N°", "AÑO / MES", "AVANCE FÍSICO REAL",
                               "VALORIZADO REAL (S/)", "ESTADO", "ARCHIVOS (ZIP)"], start=6):
            cc = ws.cell(rr, i, h)
            cc.font, cc.fill, cc.border, cc.alignment = F_HEAD, FILL_HEAD, BORDER, AL_HEAD
        rr += 1
        for n, v in enumerate(vals, start=1):
            anio, mes = v.get("anio") or 0, v.get("mes") or 0
            resaltar = _mes_en_rango(anio, mes, ini, fin)
            paraliz = "paraliz" in str(v.get("estado") or "").lower()
            ndoc = v.get("docs") or 0
            celdas = [n, f"{anio} / {_MES_ES.get(mes, mes)}",
                      v.get("fisico_real"), v.get("valorizado_real"), v.get("estado") or "",
                      f"Sí ({ndoc})" if ndoc else "—"]
            for i, val in enumerate(celdas, start=6):
                cc = ws.cell(rr, i, val)
                cc.font = F_CELL_ROJO if paraliz else F_CELL    # rojo: mes paralizado (obra parada)
                cc.border, cc.alignment = BORDER, AL_WRAP
                if i == 8 and isinstance(val, (int, float)):
                    cc.number_format = FMT_PCT
                if i == 9 and isinstance(val, (int, float)):
                    cc.number_format = FMT_SOLES
                if resaltar:
                    cc.fill = FILL_VALOR
            rr += 1
        if not vals:
            aprob = fx.get("aprobacion_expediente")
            if aprob:
                # Experiencia de EXPEDIENTE técnico: no hay valorizaciones; su respaldo
                # es la "Aprobación del proyecto" en InfoObras y cuenta por el periodo
                # del certificado. En amarillo, igual que un mes válido.
                f = aprob.get("fecha")                                   # ISO "AAAA-MM-DD"
                fm = f"{f[8:10]}/{f[5:7]}/{f[0:4]}" if f and len(f) == 10 else None
                msg = ("Expediente técnico aprobado" + (f" el {fm}" if fm else "")
                       + " — aceptada por el periodo del certificado "
                         "(experiencia de expediente, sin valorizaciones)")
                ws.merge_cells(start_row=rr, start_column=6, end_row=rr, end_column=11)
                c = ws.cell(rr, 6, msg); c.font, c.alignment, c.fill = F_CELL, AL_WRAP, FILL_VALOR
                rr += 1
                if aprob.get("nombre"):
                    ws.merge_cells(start_row=rr, start_column=6, end_row=rr, end_column=11)
                    ws.cell(rr, 6, f"Documento: {aprob['nombre']}").font = F_CELL
                    rr += 1
            else:
                ws.cell(rr, 6, "Sin valorizaciones registradas en InfoObras").font = F_CELL
                rr += 1

        # modificaciones de plazo: contexto para el evaluador (explican por qué la
        # obra siguió "viva" más allá de sus valorizaciones). NO cuentan como avance.
        mods = fx.get("modificaciones_plazo") or []
        if mods:
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

    def render_revision(top: int, motivo: str) -> int:
        """Bloque para una experiencia que NO se cruzó: explica por qué quedó en
        revisión humana, en vez de dejar la columna de la obra vacía."""
        rr = top
        ws.merge_cells(start_row=rr, start_column=6, end_row=rr, end_column=10)
        c = ws.cell(rr, 6, "EXPERIENCIA EN REVISIÓN")
        c.font, c.fill, c.alignment = F_HEAD, FILL_HEAD, AL_HEAD
        rr += 1
        ws.merge_cells(start_row=rr, start_column=6, end_row=rr + 3, end_column=10)
        c = ws.cell(rr, 6, f"{str(motivo).capitalize()}.\n\nAcción: confirmar la obra "
                           f"o pegar el CUI correcto en el panel para completar el cruce.")
        c.font, c.border, c.alignment = F_CELL, BORDER, AL_WRAP
        rr += 4
        return rr - 1

    def render_emisor(top: int, s: Optional[dict], fecha_emision, ini, ruc_espejo) -> int:
        """Cuadro del EMISOR del certificado (datos SUNAT) en columnas M:P desde
        `top`, al lado de las valorizaciones. Señala ALT04 (anomalía de antigüedad
        del emisor) en rojo/verde. Devuelve la última fila usada."""
        rr = top
        ws.merge_cells(start_row=rr, start_column=13, end_row=rr, end_column=16)
        c = ws.cell(rr, 13, "EMISOR DEL CERTIFICADO (SUNAT)")
        c.font, c.fill, c.alignment = F_HEAD, FILL_HEAD, AL_HEAD
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
            emision = _fecha_iso(fecha_emision)
            if creacion and emision and creacion > emision:
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
                   f"elegir el RUC correcto en el panel.")
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

    def render_representante(top: int, rep: Optional[dict]) -> int:
        """Representante de obra (InfoObras): TODOS los contratistas, supervisores/
        inspectores y residentes con todos sus campos (tipo, documento, razón social,
        monto, fechas), en columnas R:U — al lado del emisor SUNAT. Numera cada
        categoría cuando hay más de uno. Devuelve la última fila (o top-1 si vacío)."""
        rr = top
        contr = (rep or {}).get("contratistas") or []
        supes = (rep or {}).get("supervisores") or []
        resis = (rep or {}).get("residentes") or []
        if not (contr or supes or resis):
            return rr - 1
        ws.merge_cells(start_row=rr, start_column=18, end_row=rr, end_column=21)
        c = ws.cell(rr, 18, "REPRESENTANTE DE OBRA (InfoObras)")
        c.font, c.fill, c.alignment = F_HEAD, FILL_HEAD, AL_HEAD
        rr += 1

        def sub(texto):
            nonlocal rr
            ws.merge_cells(start_row=rr, start_column=18, end_row=rr, end_column=21)
            cc = ws.cell(rr, 18, texto)
            cc.font, cc.fill = F_PARTE, FILL_PARTE
            cc.alignment = Alignment(vertical="center", wrap_text=True)
            rr += 1

        def kv(label, value, fmt=None):
            nonlocal rr
            if value in (None, ""):
                value = "—"
            ws.merge_cells(start_row=rr, start_column=18, end_row=rr, end_column=19)
            cl = ws.cell(rr, 18, label); cl.font, cl.border = F_BOLD, BORDER
            cl.alignment = Alignment(vertical="top", wrap_text=True)
            ws.merge_cells(start_row=rr, start_column=20, end_row=rr, end_column=21)
            cv = ws.cell(rr, 20, value); cv.font, cv.border, cv.alignment = F_CELL, BORDER, AL_WRAP
            if fmt and isinstance(value, (int, float, date)):
                cv.number_format = fmt
            # valor T:U (~36 car) en celda combinada NO auto-ajusta en Excel: si el
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
            c = ws.cell(r, 1, f"(certificado no embebido: {ex})")
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
            embeber_cert(_tdr_pdf, "REQUISITO DEL TDR — recorte de las bases (imagen)")
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
        return dias_inclusivos(ini, fin), sum(dias_inclusivos(a, b) for a, b in tramos), clamp

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
        periodo = (f"{ini.strftime('%d/%m/%Y')} – {fin.strftime('%d/%m/%Y')}"
                   if (ini and fin) else "—")
        io_ini = _fecha_iso((fx or {}).get("fecha_inicio"))
        io_fin = _fecha_iso((fx or {}).get("fecha_fin"))
        periodo_io = ("— (obra no ubicada en InfoObras)" if not io_ini else
                      f"{io_ini.strftime('%d/%m/%Y')} – "
                      f"{io_fin.strftime('%d/%m/%Y') if io_fin else '(sin fin)'}")
        for label, value in [("ENTIDAD / EMPRESA QUE EMITE", e.get("entidad_emisora")),
                             ("TIPO DE DOCUMENTO", e.get("tipo_documento")),
                             ("PROYECTO U OBRA", e.get("proyecto")),
                             ("PERIODO (certificado)", periodo),
                             ("PERIODO (InfoObras)", periodo_io),
                             ("CARGO QUE OCUPÓ", e.get("cargo_ocupado")),
                             ("CÓDIGO (CUI/SNIP)",
                              str(cui) if cui else "No consignado en el certificado")]:
            cl = ws.cell(r, 1, label); cl.font, cl.fill, cl.border = F_BOLD, FILL_RECAP, BORDER
            cl.alignment = Alignment(vertical="top", wrap_text=True)
            ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=4)
            value = _xl(value)
            cv = ws.cell(r, 2, value or "—")
            cv.font, cv.border, cv.alignment = F_CELL, BORDER, AL_WRAP
            lns = max(1, -(-len(str(value or "—")) // 35))   # B:D ≈ 35 car/línea
            ws.row_dimensions[r].height = max(15, lns * 13 + 2)
            r += 1

    periodos_validos: list[tuple[date, date]] = []
    paral_por_idx: dict[int, list[tuple[date, date]]] = {}

    for e in prof.get("experiencias", []):
        n_exp = e.get("n")
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

        if not (ini and fin):
            fila("Fechas no computables (parciales o POR VERIFICAR) — revisar espejo",
                 e.get("fecha_inicial"), e.get("fecha_final"), None)
            r += 1
        else:
            fila("Periodo certificado", ini, fin, dias_inclusivos(ini, fin), fill=FILL_CLAUDE)

            # periodos inactivos de la obra (dict con tipo, o tupla legacy=paralizado)
            # SOLO los que caen dentro del periodo que supervisó este profesional;
            # InfoObras trae las paralizaciones de toda la vida de la obra, pero las
            # de antes/después de su ventana no le aplican. Se recortan a [ini, fin].
            periodos = paralizaciones.get((n_prof, n_exp), [])
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
                else:
                    n_par += 1
                    etiqueta = f"Paralización {n_par} de la obra (InfoObras)"
                fila(etiqueta, c_ini, c_fin, dias_inclusivos(c_ini, c_fin), fill=FILL_BACKEND)

            tramos = restar_paralizaciones((ini, fin), tuplas)
            for k, (t_ini, t_fin) in enumerate(tramos, start=1):
                fila(f"Tramo efectivo {k}", t_ini, t_fin,
                     dias_inclusivos(t_ini, t_fin), fill=FILL_EFECTIVO)
            efectivo = sum(dias_inclusivos(a, b) for a, b in tramos)
            fila(f"EFECTIVO EXPERIENCIA {n_exp}", "", "", efectivo, bold=True,
                 fill=FILL_EFECTIVO)
            r += 1

            idx = len(periodos_validos)
            periodos_validos.append((ini, fin))
            if tuplas:
                paral_por_idx[idx] = tuplas

        # lado derecho: ficha de la obra; si la experiencia está en revisión, un
        # bloque que lo explica (en vez de dejar la columna vacía).
        if fx:
            r_right = render_obra(r_top, fx, ini, fin)
            r = max(r, r_right + 1)
        elif (n_prof, n_exp) in revisiones:
            r_right = render_revision(r_top, revisiones[(n_prof, n_exp)])
            r = max(r, r_right + 1)

        # 3ª banda (M:P): emisor del certificado (SUNAT) + ALT04, al lado de valorizaciones
        r_emi = render_emisor(r_top, sunat.get((n_prof, n_exp)),
                              e.get("fecha_emision"), ini, e.get("ruc_emisor"))
        r = max(r, r_emi + 1)

        # 4ª banda (R:U): representante de obra (InfoObras), al lado del emisor SUNAT
        r_rep = render_representante(r_top, (fx or {}).get("representante_obra"))
        r = max(r, r_rep + 1)

        # imagen del certificado presentado (Fase 2): la skill recortó sus folios a
        # un PDF chico (principal primero); aquí se renderiza y embebe.
        cert_pdf = certificados.get((n_prof, n_exp))
        if cert_pdf:
            embeber_cert(cert_pdf)

        separador()   # 2 filas amarillas (A:Z) cerrando la experiencia

    # ── PARTE 5 (al FINAL): tabla por experiencia — declarado vs efectivo ──────
    # Es la conclusión del profesional (días efectivos del Paso 5). Flush-left;
    # A=52 lleva el Cliente, Objeto (B:D) y Proyecto (F:I) combinados anchos para
    # que el texto no se corte. Reconcilia la suma por-experiencia con ALT11.
    banda("PARTE 5 — EXPERIENCIA DEL PROFESIONAL (días declarados y efectivos verificados)",
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

    def _p5(n, proyecto, cliente, objeto, fini, ffin, io_ini, io_fin, decl, efec):
        nonlocal r
        # celdas combinadas en vertical (2 sub-filas)
        for ci, cf, val in [(1, 1, n), (2, 8, proyecto), (9, 11, cliente),
                            (13, 13, objeto)]:
            ws.merge_cells(start_row=r, start_column=ci, end_row=r + 1, end_column=cf)
            c = ws.cell(r, ci, val); c.font, c.border, c.alignment = F_CELL, BORDER, AL_WRAP
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
                if isinstance(val, date):
                    c.number_format = FMT_FECHA
        for ci, val, fill in [(18, decl, FILL_CLAUDE), (19, efec, FILL_EFECTIVO)]:
            ws.merge_cells(start_row=r, start_column=ci, end_row=r + 1, end_column=ci)
            c = ws.cell(r, ci, val); c.font, c.border, c.alignment = F_CELL, BORDER, AL_HEAD
            if isinstance(val, (int, float)):
                c.number_format, c.fill = FMT_INT, fill
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

    _p5_head()
    _sd = _se = 0
    for e in prof.get("experiencias", []):
        ne = e.get("n")
        ini_, fin_ = _fecha_iso(e.get("fecha_inicial")), _fecha_iso(e.get("fecha_final"))
        decl, efec, _clamp = _dias_exp(ne, ini_, fin_)
        fx_ = fichas.get((n_prof, ne)) or {}
        _p5(ne, e.get("proyecto") or "—", e.get("entidad_emisora") or "—",
            e.get("cargo_ocupado") or "—", ini_, fin_,
            _fecha_iso(fx_.get("fecha_inicio")), _fecha_iso(fx_.get("fecha_fin")),
            decl, efec)
        if isinstance(decl, (int, float)):
            _sd += decl
        if isinstance(efec, (int, float)):
            _se += efec

    res5 = dias_efectivos_profesional(periodos_validos, paral_por_idx) if periodos_validos else None
    _p5_tot("TOTAL, DÍAS (suma por experiencia)", _sd, _se)
    if res5 and res5.dias_traslape:
        _p5_tot("(−) Traslapes entre experiencias (ALT11)", None, res5.dias_traslape, FILL_BACKEND)
    _dias_ef = res5.dias_efectivos if res5 else _se
    _p5_tot("DÍAS EFECTIVOS DEL PROFESIONAL", None, _dias_ef)
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=18)
    ca = ws.cell(r, 1, "AÑOS EFECTIVOS (días efectivos / 365)")
    ca.font, ca.border, ca.alignment = F_BOLD, BORDER, AL_HEAD
    cy = ws.cell(r, 19, round(anios(_dias_ef), 2))
    cy.font, cy.fill, cy.border, cy.number_format = F_BOLD, FILL_EFECTIVO, BORDER, FMT_DEC


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
    paralizaciones = paralizaciones or {}
    cuis = cuis or {}
    fichas = fichas or {}
    revisiones = revisiones or {}
    sunat = sunat or {}
    certificados = certificados or {}
    wb = openpyxl.Workbook()

    ws = wb.active
    ws.title = "CLAUDE"
    construir_hoja_evaluacion(ws, espejo)

    construir_hoja_base_datos(wb.create_sheet("Base de Datos"), espejo)

    for prof in espejo.get("profesionales", []):
        nombre = _nombre_hoja(prof.get("n_prof", 0), prof.get("cargo", ""))
        certs_prof = {k: v for k, v in certificados.items() if k[0] == prof.get("n_prof")}
        construir_hoja_profesional(wb.create_sheet(nombre), prof, paralizaciones,
                                   cuis, fichas, revisiones, sunat, certs_prof)

    salida.parent.mkdir(parents=True, exist_ok=True)
    wb.save(salida)
    return salida


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
                or enr.get("representante_obra") or enr.get("aprobacion_expediente")):
            fichas[(np_, ne)] = {**(enr.get("obra_ficha") or {}),
                                 "valorizaciones": enr.get("valorizaciones") or [],
                                 "modificaciones_plazo": enr.get("modificaciones_plazo") or [],
                                 "representante_obra": enr.get("representante_obra"),
                                 "aprobacion_expediente": enr.get("aprobacion_expediente")}
    return paral, cuis, fichas, sunat


def regenerar_excel_final(espejo: dict, enriquecimiento: Optional[dict],
                          salida: Path, revisiones: Optional[dict] = None) -> Path:
    """Regenera el Excel final desde el espejo + enriquecimiento YA en disco (sin
    tocar red). Lo usa el backfill de cargos para dejar el entregable limpio."""
    paral, cuis, fichas, sunat = desempaquetar_enriquecimiento(enriquecimiento)
    salida = Path(salida)
    if salida.exists():
        salida.unlink()
    return generar_excel_final(espejo, salida, paral, cuis, fichas, revisiones or {}, sunat)
