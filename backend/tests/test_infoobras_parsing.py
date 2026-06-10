"""
Tests offline del parseo InfoObras — funciones puras, sin red.

No hay dumps HTML de InfoObras guardados (las páginas embeben las variables JS
`var lXxx = [...]`), así que los tests usan snippets sintéticos con la
estructura real observada (probe CUI 2427358 Tambobamba, documentada en
_procesar_avances). Si InfoObras renombra variables o campos, estos tests
definen el comportamiento esperado del parser.
"""
from __future__ import annotations

from datetime import date

from scraping import infoobras


# ── _parse_js_vars ───────────────────────────────────────────────────────────

HTML_VARS = """
<html><script>
var lAvances = [
  {"Anio": "2024", "Mes": "ENERO", "Estado": "Paralizado",
   "DiasParalizado": "31", "PorcRealFisico": "0.3114"},
  {"Anio": "2024", "Mes": "FEBRERO", "Estado": "En ejecuci\\u00f3n",
   "PorcRealFisico": "0.3331"}
];
var lSupervisor = [
  {"Nombres": "JUAN", "Apellidos": "PEREZ", "Documentos": [{"tipo": "DNI"}]}
];
var lResidente = null;
var lRoto = [{"sin_cerrar": ;
</script></html>
"""


def test_parse_js_vars_basico():
    variables = infoobras._parse_js_vars(HTML_VARS)

    assert len(variables["lAvances"]) == 2
    assert variables["lAvances"][0]["Mes"] == "ENERO"
    # sub-arrays anidados no rompen el raw_decode
    assert variables["lSupervisor"][0]["Documentos"][0]["tipo"] == "DNI"
    # var null → lista vacía (existe pero sin datos)
    assert variables["lResidente"] == []
    # var malformada → se omite sin tumbar el resto
    assert "lRoto" not in variables


def test_parse_js_vars_html_sin_vars():
    assert infoobras._parse_js_vars("<html><body>nada</body></html>") == {}


# ── Parseo de fechas ─────────────────────────────────────────────────────────

def test_parse_fecha_ddmmyyyy():
    assert infoobras._parse_fecha_ddmmyyyy("24/05/2017") == date(2017, 5, 24)
    assert infoobras._parse_fecha_ddmmyyyy(" 01/12/2023 ") == date(2023, 12, 1)
    assert infoobras._parse_fecha_ddmmyyyy("2017-05-24") is None
    assert infoobras._parse_fecha_ddmmyyyy("") is None
    assert infoobras._parse_fecha_ddmmyyyy(None) is None


def test_parse_timestamp_json():
    # /Date(1574485200000)/ = 2019-11-23 (UTC)
    assert infoobras._parse_timestamp_json("/Date(1574485200000)/") == date(2019, 11, 23)
    assert infoobras._parse_timestamp_json("no es timestamp") is None
    assert infoobras._parse_timestamp_json(None) is None


# ── Avances y periodos de suspensión (corazón del Paso 5) ───────────────────

def _avance(anio: int, mes: str, estado: str, **extra) -> dict:
    return {"Anio": str(anio), "Mes": mes, "Estado": estado, **extra}


def test_procesar_avances_campos():
    avances = infoobras._procesar_avances([
        _avance(2024, "ENERO", "Paralizado", DiasParalizado="31",
                PorcRealFisico="0.3114", FechaParalizacion="05/01/2024"),
    ])
    av = avances[0]
    assert (av.anio, av.mes) == (2024, 1)
    assert av.estado == "Paralizado"
    assert av.dias_paralizado == 31
    assert av.avance_fisico_real == 0.3114
    assert av.fecha_paralizacion == date(2024, 1, 5)


def test_periodos_suspension_meses_consecutivos_se_fusionan():
    # Réplica del patrón real de la hoja "Estructura" del Excel Libertador:
    # racha de meses Paralizado → UN periodo continuo
    avances = infoobras._procesar_avances([
        _avance(2023, "ENERO", "En ejecución"),
        _avance(2023, "FEBRERO", "Paralizado"),
        _avance(2023, "MARZO", "Paralizado"),
        _avance(2023, "ABRIL", "Paralizado"),
        _avance(2023, "MAYO", "En ejecución"),
    ])
    periodos = infoobras._extraer_periodos_suspension(avances)

    assert len(periodos) == 1
    inicio, fin = periodos[0]
    assert inicio == date(2023, 2, 1)
    assert fin >= date(2023, 4, 30)  # cubre hasta el fin de la racha


def test_periodos_suspension_rachas_separadas():
    avances = infoobras._procesar_avances([
        _avance(2023, "ENERO", "Paralizado"),
        _avance(2023, "FEBRERO", "En ejecución"),
        _avance(2023, "MARZO", "En ejecución"),
        _avance(2023, "JUNIO", "Paralizado"),
        _avance(2023, "JULIO", "Paralizado"),
        _avance(2023, "AGOSTO", "En ejecución"),
    ])
    periodos = infoobras._extraer_periodos_suspension(avances)

    assert len(periodos) == 2
    assert periodos[0][0] == date(2023, 1, 1)
    assert periodos[1][0] == date(2023, 6, 1)


def test_periodos_suspension_sin_paralizaciones():
    avances = infoobras._procesar_avances([
        _avance(2023, "ENERO", "En ejecución"),
        _avance(2023, "FEBRERO", "Finalizado"),
    ])
    assert infoobras._extraer_periodos_suspension(avances) == []


def test_periodos_suspension_usa_fecha_exacta_de_paralizacion():
    avances = infoobras._procesar_avances([
        _avance(2023, "MARZO", "Paralizado", FechaParalizacion="17/03/2023"),
        _avance(2023, "ABRIL", "Paralizado"),
    ])
    periodos = infoobras._extraer_periodos_suspension(avances)
    assert periodos[0][0] == date(2023, 3, 17)


# ── Desambiguación por nombre (insumo de la resolución de CUI) ──────────────

def test_extraer_palabras_clave_obra_hospitalaria():
    nombre = (
        "MEJORAMIENTO DE LA CAPACIDAD RESOLUTIVA DE LOS SERVICIOS DE SALUD "
        "DEL HOSPITAL REGIONAL HERMILIO VALDIZAN DE HUANUCO, NIVEL II-1"
    )
    queries = infoobras._extraer_palabras_clave(nombre)

    assert queries, "debe producir al menos un fragmento de búsqueda"
    # El marcador de establecimiento + nombre propio debe estar en los fragmentos
    assert any("HERMILIO VALDIZAN" in q.upper() for q in queries)


def test_normalizar_tokens_y_jaccard():
    a = "Hospital Regional Hermilio Valdizan de Huanuco"
    b = "HOSPITAL REGIONAL HERMILIO VALDIZÁN DE HUÁNUCO"
    assert infoobras._jaccard(a, b) >= 0.9  # acentos/case no separan

    c = "Centro de Salud de Pichari"
    assert infoobras._jaccard(a, c) < 0.5
