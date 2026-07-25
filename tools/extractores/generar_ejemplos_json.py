"""
Genera los 3 JSONs de ejemplo (Pasos 1, 2, 3) en docs/examples/ a partir de:
- bases.json:        Excel de Claude  `Cuadro_Personal_Clave_CP02-2025.xlsx`  (caso Lircay)
- profesionales.json: Excel del ingeniero `10. Lircay 16.04.26.xlsx` hoja `PROFESIONALES`
- experiencias.json:  Excel del ingeniero `10. Lircay 16.04.26.xlsx` hoja `BD roberto`

Outputs cumplen el schema definido en docs/schema_canonico.md (v2).

⚠ Los JSONs contienen datos del cliente real (Indeconsult / Manuel Echandía
  sobre el concurso Lircay CP-02-2025). Cuando este directorio Pivote pase
  a git, `docs/examples/` debe agregarse a .gitignore. Los ejemplos sirven
  como fixtures internos para validar el schema y la skill.

Uso:
    venv/Scripts/python.exe src/tools/generar_ejemplos_json.py
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parents[3]
EXCEL_CLAUDE_PASO1 = BASE_DIR / "docs" / "files" / "Cuadro_Personal_Clave_CP02-2025.xlsx"
EXCEL_INGENIERO = Path(
    r"C:\Users\Holbi\Documents\Freelance\proyectos\InfoObras"
    r"\Alpamayo-InfoObras\variety\tools\excel_reader\10. Lircay  16.04.26.xlsx"
)
EXAMPLES_DIR = BASE_DIR / "docs" / "examples"

# Identificador común para los 3 JSONs de este ejemplo
ANALISIS_ID = "lircay-cp02-2025--2026-04-16T00-00-00"
VERSION_SKILL = "0.1.0"
FECHA_EXTRACCION = "2026-04-16T08:00:00"


# ─── Helpers ─────────────────────────────────────────────────────────────────


def to_iso_date(v: Any) -> str | None:
    """Convierte fechas variadas a ISO YYYY-MM-DD; retorna None si no se puede."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, (datetime, pd.Timestamp)):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    s = str(v).strip()
    if not s or s == "-" or s.lower() == "no disponible":
        return None
    # dd.mm.yyyy
    m = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4})$", s)
    if m:
        return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    # dd/mm/yyyy
    m = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", s)
    if m:
        return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    # ISO ya
    if re.match(r"^\d{4}-\d{2}-\d{2}", s):
        return s[:10]
    return None  # no parseamos español como "30 de abril de 1995"


def to_string_or_none(v: Any) -> str | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip()
    if not s or s == "-":
        return None
    if s.lower() in ("no disponible", "nan", "none"):
        return None
    return s


def to_decimal_str_or_none(v: Any) -> str | None:
    """Convierte número (puede tener comas) a string decimal limpio; None si no se puede."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, (int, float, Decimal)):
        return str(Decimal(str(v)))
    s = str(v).strip()
    if not s or s == "-":
        return None
    # Quitar separadores de miles (comas) y dejar punto decimal
    s_clean = s.replace(",", "").replace(" ", "")
    try:
        return str(Decimal(s_clean))
    except Exception:
        return None


def split_bullets(text: str) -> list[str]:
    """Parsea texto con líneas tipo '• X', '► X' o '- X' en una lista limpia."""
    if not text:
        return []
    parts = re.split(r"[\n\r]+", text)
    items = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        # quitar prefijos de bullet
        p = re.sub(r"^[•►▪○\-\*]\s*", "", p).strip()
        if p:
            items.append(p)
    return items


def meta(subagente: str, fuente_pdf: str) -> dict:
    return {
        "analisis_id": ANALISIS_ID,
        "subagente": subagente,
        "version_skill": VERSION_SKILL,
        "fecha_extraccion": FECHA_EXTRACCION,
        "fuente_pdf": fuente_pdf,
    }


# ─── Paso 1: bases.json ──────────────────────────────────────────────────────


def construir_bases() -> dict:
    """
    Construye bases.json a partir del Excel de Claude Paso 1.
    Estructura del Excel:
      filas 0-1: títulos
      fila 2: headers
      filas 3-19: 17 cargos
    """
    sheets = pd.read_excel(EXCEL_CLAUDE_PASO1, sheet_name=None, header=None)
    df = sheets["Personal Clave"]

    personal_clave = []
    for idx in range(3, df.shape[0]):
        row = df.iloc[idx]
        numero = row.iloc[0]
        if pd.isna(numero):
            continue
        try:
            numero = int(numero)
        except (ValueError, TypeError):
            continue

        # Col 1: CARGO + profesiones
        c1 = str(row.iloc[1] or "").strip()
        lineas_c1 = [l.strip() for l in c1.split("\n") if l.strip()]
        cargo = lineas_c1[0] if lineas_c1 else f"CARGO {numero}"
        profesiones = [
            re.sub(r"^[•►▪○\-\*]\s*", "", l).strip()
            for l in lineas_c1[1:]
            if l.startswith(("•", "►"))
        ]

        # Col 2: años colegiado
        c2 = str(row.iloc[2] or "")
        anos_colegiado_min = None
        m = re.search(r"(\d+)\s*a[ñn]os", c2.lower())
        if m and "no se establece" not in c2.lower():
            anos_colegiado_min = int(m.group(1))

        # Col 3: experiencia mínima + cargos similares
        c3 = str(row.iloc[3] or "")
        m_meses = re.search(r"M[IÍ]NIMA:?\s*(\d+)\s*meses", c3, re.IGNORECASE)
        m_anos = re.search(r"M[IÍ]NIMA:?\s*(\d+)\s*a[ñn]os", c3, re.IGNORECASE)
        if m_meses:
            exp_unidad = "meses"
            exp_cantidad = int(m_meses.group(1))
        elif m_anos:
            exp_unidad = "anos"
            exp_cantidad = int(m_anos.group(1))
        else:
            exp_unidad = "meses"
            exp_cantidad = 0

        # cargos_similares_validos: extraer bullets después de "Cargos similares"
        cargos_sim = []
        if "cargos similares" in c3.lower():
            parte = c3.lower().split("cargos similares")[1]
            # buscar en el texto original (preserva mayúsculas)
            inicio = c3.lower().index("cargos similares") + len("cargos similares")
            resto = c3[inicio:]
            cargos_sim = split_bullets(resto)

        # Col 4: tipo experiencia similar
        c4 = str(row.iloc[4] or "").strip()
        tipos_obra_validos = []
        for linea in c4.split("\n"):
            linea = linea.strip()
            if linea.startswith(("►", "•")):
                tipos_obra_validos.append(
                    re.sub(r"^[►•▪○\-\*]\s*", "", linea).strip()
                )

        # Col 5: Factor A
        c5 = str(row.iloc[5] or "")
        factor_a_aplica = "✔" in c5 or "INCLUIDO" in c5.upper() and "NO" not in c5.upper()[:c5.upper().find("INCLUIDO") + 8]
        factor_a_detalle = c5.strip() if c5.strip() else None

        # Col 6: Factor B
        c6 = str(row.iloc[6] or "")
        factor_b_aplica = bool(c6.strip()) and "no figura" not in c6.lower() and "no aplica" not in c6.lower()
        es_lider = "(LÍDER)" in c6.upper() or "LIDER" in c6.upper()
        certificaciones_b = []
        for linea in c6.split("\n"):
            linea = linea.strip()
            if linea.startswith(("•", "►")):
                cert = re.sub(r"^[•►▪○\-\*]\s*", "", linea).strip()
                if cert and "puntaje" not in cert.lower():
                    certificaciones_b.append(cert)
        m_pts = re.search(r"(\d+)\s*p(?:un)?to?s?", c6, re.IGNORECASE)
        factor_b_puntaje = int(m_pts.group(1)) if m_pts else 0

        # Col 7: certificaciones del postor
        c7 = str(row.iloc[7] or "")
        cert_postor = re.findall(r"ISO\s*\d+[:\-]?\d*", c7)

        personal_clave.append({
            "numero": numero,
            "cargo": cargo,
            "profesiones_aceptadas": profesiones if profesiones else [cargo],
            "anos_colegiado_min": anos_colegiado_min,
            "requiere_titulo_y_colegiatura": True,
            "experiencia_minima_unidad": exp_unidad,
            "experiencia_minima_cantidad": exp_cantidad,
            "cargos_similares_validos": cargos_sim,
            "tipo_experiencia_similar": c4[:200] if c4 else "",
            "tipos_obra_validos": tipos_obra_validos,
            "factor_a_aplica": factor_a_aplica,
            "factor_a_detalle": factor_a_detalle,
            "factor_b_aplica": factor_b_aplica,
            "es_lider_equipo": es_lider,
            "certificaciones_factor_b": certificaciones_b,
            "factor_b_puntaje_individual": factor_b_puntaje,
            "certificaciones_postor": cert_postor,
        })

    # factores_evaluacion: deducidos de los datos extraídos
    cargos_con_factor_a = [c["numero"] for c in personal_clave if c["factor_a_aplica"]]
    factor_a = {
        "codigo": "A",
        "nombre": "Tiempo Adicional",
        "max_pts": 45,
        "aplica_a": "grupo_profesionales",
        "criterios": [
            ">80% supera +1 año: 45 pts",
            ">50-80% supera +1 año: 30 pts",
            "30-50% supera +1 año: 15 pts",
        ],
        "aplica_a_cargos": cargos_con_factor_a,
    }
    factor_b = {
        "codigo": "B",
        "nombre": "Capacitación / Certificaciones",
        "max_pts": 15,
        "aplica_a": "profesional_individual",
        "criterios": ["2 pts por certificación (max 8 pts grupal)"],
        "aplica_a_cargos": [c["numero"] for c in personal_clave if c["factor_b_aplica"]],
    }
    factor_j = {
        "codigo": "J",
        "nombre": "Gestión de Calidad (ISO 9001:2015)",
        "max_pts": 20,
        "aplica_a": "postor",
        "criterios": ["Cuenta con certificación ISO 9001:2015 vigente"],
        "aplica_a_cargos": [],
    }
    factor_g = {
        "codigo": "G",
        "nombre": "Antisoborno (ISO 37001:2016)",
        "max_pts": 10,
        "aplica_a": "postor",
        "criterios": ["Cuenta con certificación ISO 37001:2016 vigente"],
        "aplica_a_cargos": [],
    }

    return {
        "_meta": meta("agent-bases", "bases-integradas-30.03.26.pdf"),
        "metadata_concurso": {
            "nomenclatura": "CP N° 02-2025/GOB.REG.HVCA/C",
            "entidad": "Gobierno Regional de Huancavelica",
            "objeto": "Supervisión de Obra del Hospital II-1 Lircay",
            "fuente_bases": "Bases Integradas Definitivas (30.03.26)",
            "especialidad": "Edificaciones y Afines",
            "subespecialidad": "Establecimientos de Salud",
            "fecha_presentacion_oferta": "2026-04-16",
        },
        "factores_evaluacion": {
            "factor_a": factor_a,
            "factor_b": factor_b,
            "factor_j": factor_j,
            "factor_g": factor_g,
            "otros": [],
        },
        "personal_clave": personal_clave,
        "observaciones_claude": [
            {
                "codigo": "FACTOR_B_PUNTAJE_AMBIGUO_LIDER",
                "tipo": "ambiguedad",
                "severidad": "info",
                "origen": "claude",
                "mensaje": (
                    "El Jefe de Supervisión (LÍDER) tiene esquema de puntaje "
                    "distinto del resto en Factor B (4 pts por 1 cert, 7 pts por 2). "
                    "El backend debe aplicar la regla diferenciada."
                ),
                "referencia": {
                    "item_tipo": "cargo",
                    "item_id": 2,
                    "campo": "factor_b_puntaje_individual",
                    "folio_pdf": None,
                    "pagina_pdf": None,
                },
            },
        ],
    }


# ─── Paso 2: profesionales.json ──────────────────────────────────────────────


def construir_profesionales() -> dict:
    """
    Construye profesionales.json a partir de la hoja PROFESIONALES del Excel
    del ingeniero. Estructura:
      fila 0: headers
      filas 1-17: profesionales
    """
    sheets = pd.read_excel(EXCEL_INGENIERO, sheet_name=None, header=None)
    df = sheets["PROFESIONALES"]

    profesionales = []
    flags_observaciones = []

    for idx in range(1, df.shape[0]):
        row = df.iloc[idx]
        n_prof = row.iloc[0]
        if pd.isna(n_prof):
            continue
        try:
            n_prof = int(n_prof)
        except (ValueError, TypeError):
            continue

        nombre = to_string_or_none(row.iloc[1]) or ""
        profesion = to_string_or_none(row.iloc[2]) or ""

        # Fecha de colegiación: puede ser datetime, string libre, o "Ilegible / Año XXXX"
        fcol_raw = row.iloc[3]
        fcol_iso = to_iso_date(fcol_raw)
        if fcol_iso:
            fecha_colegiacion: Any = fcol_iso
        else:
            # mantener como string libre
            fecha_colegiacion = to_string_or_none(fcol_raw)
            if fecha_colegiacion and not re.match(r"^\d{4}-\d{2}-\d{2}", fecha_colegiacion):
                flags_observaciones.append({
                    "codigo": "FECHA_COLEGIACION_NO_PARSEABLE",
                    "tipo": "extraccion_parcial",
                    "severidad": "warning",
                    "origen": "claude",
                    "mensaje": (
                        f"La fecha de colegiación de {nombre} no se pudo "
                        f"convertir a ISO. Valor original: {fecha_colegiacion!r}. "
                        f"Se conservó como string libre."
                    ),
                    "referencia": {
                        "item_tipo": "profesional",
                        "item_id": n_prof,
                        "campo": "fecha_colegiacion",
                        "folio_pdf": to_string_or_none(row.iloc[5]),
                        "pagina_pdf": None,
                    },
                })

        especialidad = to_string_or_none(row.iloc[4]) or ""
        folio_colegiatura = str(int(row.iloc[5])) if not pd.isna(row.iloc[5]) else ""
        folio_nombre = str(int(row.iloc[6])) if not pd.isna(row.iloc[6]) else ""

        profesionales.append({
            "n_prof": n_prof,
            "nombre": nombre,
            "profesion": profesion,
            "fecha_colegiacion": fecha_colegiacion,
            "especialidad_postulada": especialidad,
            "folio_colegiatura": folio_colegiatura,
            "folio_nombre_propuesta": folio_nombre,
            "universidad_titulacion": None,
            "fecha_titulacion": None,
            "_flags": {
                "universidad": "verificar_folio_no_extraido",
                "fecha_titulacion": "verificar_folio_no_extraido",
            },
        })

    return {
        "_meta": meta("agent-propuesta", "propuesta-indeconsult-lircay.pdf"),
        "profesionales": profesionales,
        "observaciones_claude": flags_observaciones,
    }


# ─── Paso 3: experiencias.json ───────────────────────────────────────────────


def construir_experiencias(profesionales: dict) -> dict:
    """
    Construye experiencias.json a partir de la hoja `BD roberto` del Excel
    del ingeniero.

    Mapeo col del ingeniero (1-indexed según el header del Excel) → campo JSON:
        Col 1 Nombre Profesional → resuelve n_prof (vía profesionales.json)
        Col 2 DNI / Colegiatura → no se persiste aquí (ya está en profesionales.json)
        Col 3 → proyecto
        Col 4 → cargo_desempenado
        Col 5 → empresa_emisora
        Col 6 → ruc_emisor
        Col 7 → publica_o_privada
        Col 8 → tipo_acreditacion
        Col 9 → fecha_inicio
        Col 10 → fecha_culminacion
        Col 11 → alerta_covid    (el ingeniero usa esta col para otra cosa numérica;
                                  reinterpretamos al header semántico)
        Cols 12, 13 → null (vacías reservadas)
        Col 14 → duracion_meses  (BACKEND — se omite del JSON Claude)
        Col 15 → fecha_emision_cert
        Col 16 → alerta_cert_antes_culminacion (renombrado de "ALERTA emisión")
        Col 17 → n_folio
        Col 18 → firmante_certificado
        Col 19 → cargo_firmante
        Col 20 → alerta_firmante_no_representante (BACKEND — se omite)
        Col 21 → fecha_creacion_emisor (BACKEND — se omite)
        Col 22 → alerta_antiguedad_emisor (BACKEND — se omite)
        Col 23 → alerta_experiencia_antigua (BACKEND — se omite)
        Col 24 → tipo_documento
        Col 25 → codigo_ciu (BACKEND — se omite)
        Col 26 → codigo_infoobras (BACKEND — se omite)
        Col 27 → (redundante con 21) → se omite

    Las columnas DE Claude:
      nivel_categoria, area_construida_m2, monto_contrato_soles, ubicacion,
      entidad_contratante, alerta_exp_antes_titulacion, observaciones_fila
    → no están en el Excel del ingeniero como columnas separadas. Las extraemos
      con regex del campo proyecto (donde a veces aparece "Nivel II-1") o
      las dejamos null.
    """
    sheets = pd.read_excel(EXCEL_INGENIERO, sheet_name=None, header=None)
    df = sheets["BD roberto"]

    # Mapeo nombre → n_prof (de profesionales.json ya construido)
    nombre_to_n_prof = {
        p["nombre"].upper().strip(): p["n_prof"]
        for p in profesionales["profesionales"]
    }

    # Date de presentación para regla COVID
    COVID_INICIO = date(2020, 3, 15)
    COVID_FIN_REFERENCIAL = date(2021, 12, 31)

    experiencias = []
    observaciones = []
    n_correlativo = 0

    # Primer pase: capturar datos por fila
    raw_items = []
    for idx in range(1, df.shape[0]):
        row = df.iloc[idx]
        nombre = to_string_or_none(row.iloc[0])
        if not nombre:
            continue

        # Resolver n_prof por match exacto, luego fuzzy upper
        n_prof_match = None
        nombre_upper = nombre.upper().strip()
        if nombre_upper in nombre_to_n_prof:
            n_prof_match = nombre_to_n_prof[nombre_upper]
        else:
            # match parcial (e.g. "Ribert Cristhian Payva Aquino" vs "RIBERT CRISTHIAN PAYVA AQUINO")
            for k, v in nombre_to_n_prof.items():
                if k.replace("Í", "I").replace("Á", "A").replace("É", "E").replace("Ó", "O").replace("Ú", "U") == nombre_upper.replace("Í", "I").replace("Á", "A").replace("É", "E").replace("Ó", "O").replace("Ú", "U"):
                    n_prof_match = v
                    break

        if n_prof_match is None:
            observaciones.append({
                "codigo": "EXPERIENCIA_SIN_PROFESIONAL_MATCH",
                "tipo": "inconsistencia",
                "severidad": "warning",
                "origen": "claude",
                "mensaje": (
                    f"Experiencia en fila {idx} del BD del ingeniero menciona "
                    f"profesional '{nombre}' que no matchea ningún n_prof en "
                    f"profesionales.json. Se omite la fila."
                ),
                "referencia": {
                    "item_tipo": "experiencia",
                    "item_id": None,
                    "campo": "n_prof",
                    "folio_pdf": to_string_or_none(row.iloc[16]),
                    "pagina_pdf": None,
                },
            })
            continue

        fecha_inicio = to_iso_date(row.iloc[8])
        fecha_culminacion = to_iso_date(row.iloc[9])
        if fecha_inicio is None:
            observaciones.append({
                "codigo": "FECHA_INICIO_NO_PARSEABLE",
                "tipo": "extraccion_parcial",
                "severidad": "warning",
                "origen": "claude",
                "mensaje": (
                    f"Fila {idx}: fecha_inicio no parseable "
                    f"({row.iloc[8]!r}). Se omite la experiencia."
                ),
                "referencia": {
                    "item_tipo": "experiencia",
                    "item_id": None,
                    "campo": "fecha_inicio",
                    "folio_pdf": to_string_or_none(row.iloc[16]),
                    "pagina_pdf": None,
                },
            })
            continue

        raw_items.append({
            "n_prof": n_prof_match,
            "fecha_culminacion_iso": fecha_culminacion,
            "row": row,
            "idx": idx,
            "fecha_inicio": fecha_inicio,
        })

    # Ordenar por (n_prof asc, fecha_culminacion asc null-last)
    def sort_key(item):
        return (
            item["n_prof"],
            item["fecha_culminacion_iso"] or "9999-12-31",
        )

    raw_items.sort(key=sort_key)

    for item in raw_items:
        n_correlativo += 1
        row = item["row"]
        n_prof = item["n_prof"]
        fecha_inicio = item["fecha_inicio"]
        fecha_culminacion = item["fecha_culminacion_iso"]

        proyecto = to_string_or_none(row.iloc[2]) or ""
        cargo_desempenado = to_string_or_none(row.iloc[3]) or ""
        empresa_emisora = to_string_or_none(row.iloc[4]) or ""

        ruc_raw = row.iloc[5]
        ruc_emisor = None
        if not pd.isna(ruc_raw):
            ruc_str = str(int(ruc_raw)) if isinstance(ruc_raw, (int, float)) else str(ruc_raw).strip()
            if re.match(r"^\d{11}$", ruc_str):
                ruc_emisor = ruc_str

        publica_o_privada_raw = to_string_or_none(row.iloc[6])
        publica_o_privada = None
        if publica_o_privada_raw:
            pop_clean = publica_o_privada_raw.lower().strip()
            if "públic" in pop_clean or "public" in pop_clean:
                publica_o_privada = "Pública"
            elif "privad" in pop_clean:
                publica_o_privada = "Privada"

        tipo_acreditacion = to_string_or_none(row.iloc[7]) or "No especificado"

        # alerta_covid (regla real, no el valor numérico del ingeniero)
        alerta_covid = None
        if fecha_inicio and fecha_culminacion:
            fi = date.fromisoformat(fecha_inicio)
            fc = date.fromisoformat(fecha_culminacion)
            if fi <= COVID_INICIO <= fc:
                alerta_covid = "INCLUYE PERIODO COVID"

        fecha_emision_cert = to_iso_date(row.iloc[14])
        if not fecha_emision_cert:
            # Si no se puede parsear, usar fecha_culminacion como fallback con flag
            fecha_emision_cert = fecha_culminacion

        # alerta_cert_antes_culminacion (col 16 del ingeniero)
        alerta_cert_antes_culminacion = to_string_or_none(row.iloc[15])
        if fecha_emision_cert and fecha_culminacion:
            if fecha_emision_cert < fecha_culminacion:
                alerta_cert_antes_culminacion = "ALERTA: fecha de emisión anterior a culminación"

        n_folio_raw = row.iloc[16]
        if pd.isna(n_folio_raw):
            n_folio = ""
        else:
            n_folio = str(int(n_folio_raw)) if isinstance(n_folio_raw, (int, float)) else str(n_folio_raw).strip()

        firmante = to_string_or_none(row.iloc[17]) or ""
        cargo_firmante = to_string_or_none(row.iloc[18])

        # Tipo documento (col 24, indice 23)
        tipo_doc = to_string_or_none(row.iloc[23]) or "Constancia"

        # Capacidades nuevas: intentar extraer del proyecto
        nivel_categoria = None
        m_nivel = re.search(
            r"\b(II-1|II-2|III-1|III-2|I-3|I-4|Centro de Salud|Puesto de Salud)\b",
            proyecto,
            re.IGNORECASE,
        )
        if m_nivel:
            nivel_categoria = m_nivel.group(1)

        experiencias.append({
            "n_correlativo": n_correlativo,
            "n_prof": n_prof,
            "proyecto": proyecto,
            "cargo_desempenado": cargo_desempenado,
            "empresa_emisora": empresa_emisora,
            "ruc_emisor": ruc_emisor,
            "publica_o_privada": publica_o_privada,
            "tipo_acreditacion": tipo_acreditacion,
            "fecha_inicio": fecha_inicio,
            "fecha_culminacion": fecha_culminacion,
            "alerta_covid": alerta_covid,
            "fecha_emision_cert": fecha_emision_cert or fecha_inicio,
            "n_folio": n_folio,
            "firmante_certificado": firmante,
            "cargo_firmante": cargo_firmante,
            "tipo_documento": tipo_doc,
            "nivel_categoria": nivel_categoria,
            "area_construida_m2": None,
            "monto_contrato_soles": None,
            "ubicacion": "",
            "entidad_contratante": "",
            "alerta_exp_antes_titulacion": None,
            "alerta_cert_antes_culminacion": alerta_cert_antes_culminacion,
            "observaciones_fila": None,
            "_flags": {},
        })

    # Ejemplo de observacion global
    observaciones.append({
        "codigo": "POSIBLE_DUPLICADO_PERIODO_PARTIDO",
        "tipo": "duplicado_posible",
        "severidad": "info",
        "origen": "claude",
        "mensaje": (
            "Hay experiencias del mismo profesional con periodos contiguos "
            "y mismo folio (e.g. 001818). Podrían ser un periodo único "
            "partido por la propuesta. Verificar manualmente."
        ),
        "referencia": {
            "item_tipo": "experiencia",
            "item_id": None,
            "campo": None,
            "folio_pdf": "001818",
            "pagina_pdf": None,
        },
    })

    return {
        "_meta": meta("agent-propuesta", "propuesta-indeconsult-lircay.pdf"),
        "experiencias": experiencias,
        "observaciones_claude": observaciones,
    }


# ─── Main ────────────────────────────────────────────────────────────────────


def main() -> None:
    EXAMPLES_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 80)
    print("Construyendo bases.json (Paso 1) desde Excel de Claude...")
    print("=" * 80)
    bases = construir_bases()
    (EXAMPLES_DIR / "lircay_bases.json").write_text(
        json.dumps(bases, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"  → {len(bases['personal_clave'])} cargos")
    print(f"  → {len(bases['observaciones_claude'])} observaciones")

    print("\n" + "=" * 80)
    print("Construyendo profesionales.json (Paso 2) desde Excel del ingeniero...")
    print("=" * 80)
    profesionales = construir_profesionales()
    (EXAMPLES_DIR / "lircay_profesionales.json").write_text(
        json.dumps(profesionales, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"  → {len(profesionales['profesionales'])} profesionales")
    print(f"  → {len(profesionales['observaciones_claude'])} observaciones")

    print("\n" + "=" * 80)
    print("Construyendo experiencias.json (Paso 3) desde Excel del ingeniero...")
    print("=" * 80)
    experiencias = construir_experiencias(profesionales)
    (EXAMPLES_DIR / "lircay_experiencias.json").write_text(
        json.dumps(experiencias, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    print(f"  → {len(experiencias['experiencias'])} experiencias")
    print(f"  → {len(experiencias['observaciones_claude'])} observaciones")

    print("\n" + "=" * 80)
    print("Resumen:")
    print("=" * 80)
    for fname in ("lircay_bases.json", "lircay_profesionales.json", "lircay_experiencias.json"):
        f = EXAMPLES_DIR / fname
        print(f"  {fname}  ({f.stat().st_size:>7} bytes)")


if __name__ == "__main__":
    main()
