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

import pytest
import requests

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


# ── Huecos de valorización (obra parada sin estado "Paralizado") ─────────────

def test_huecos_de_valorizacion_caso_real():
    # tabla real (caso del ingeniero): valorizaciones hasta dic-2017, reanuda
    # abr-2018 → ene/feb/mar-2018 ausentes, TODAS las filas dicen "En ejecución"
    avances = infoobras._procesar_avances(
        [_avance(2017, m, "En ejecución")
         for m in ("AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE")]
        + [_avance(2018, m, "En ejecución")
           for m in ("ABRIL", "MAYO", "JUNIO", "JULIO", "AGOSTO")])
    huecos = infoobras._huecos_de_valorizacion(avances)
    assert huecos == [(date(2018, 1, 1), date(2018, 3, 31))]
    from reglas import dias_inclusivos
    assert dias_inclusivos(*huecos[0]) == 90  # ene+feb+mar 2018


def test_huecos_no_marca_meses_consecutivos():
    avances = infoobras._procesar_avances([
        _avance(2021, "ENERO", "En ejecución"),
        _avance(2021, "FEBRERO", "En ejecución"),
        _avance(2021, "MARZO", "En ejecución"),
    ])
    assert infoobras._huecos_de_valorizacion(avances) == []


def test_periodos_inactividad_combina_paralizado_y_hueco_ordenados():
    avances = infoobras._procesar_avances([
        _avance(2017, "DICIEMBRE", "En ejecución"),   # último antes del hueco
        _avance(2018, "ABRIL", "Paralizado"),          # reanuda pero paralizado
        _avance(2018, "MAYO", "En ejecución"),
    ])
    per = infoobras.periodos_inactividad(avances)
    tipos = {p["tipo"] for p in per}
    assert tipos == {"sin_valorizacion", "paralizado"}
    # ordenados por inicio: el hueco (ene) va antes que la paralización (abr)
    assert per[0]["tipo"] == "sin_valorizacion"
    assert per[0]["inicio"] == date(2018, 1, 1)


# ── selección de obra cuando un CUI devuelve varias ──────────────────────────

def _obra(estado="", ini=None, fin=None, **extra):
    def ts(d):
        if not d:
            return None
        import calendar
        epoch = calendar.timegm(d.timetuple()) * 1000
        return f"/Date({epoch})/"
    return {"estObra": estado, "fechaIniObra": ts(ini), "fechaFinObra": ts(fin), **extra}


def test_seleccionar_obra_unica_la_devuelve():
    o = _obra("En ejecución", codigoObra=1)
    assert infoobras.seleccionar_obra([o]) is o


def test_seleccionar_obra_prefiere_finalizada():
    # caso real: 7 registros del mismo CUI, solo 1 finalizado
    obras = [_obra("En ejecución", codigoObra=i) for i in range(6)]
    fin = _obra("Finalizado", codigoObra=99)
    obras.insert(3, fin)
    assert infoobras.seleccionar_obra(obras)["codigoObra"] == 99


def test_seleccionar_obra_por_solape_con_el_certificado():
    # dos finalizadas; gana la que cubre el periodo del certificado
    lejana = _obra("Finalizado", date(2010, 1, 1), date(2011, 1, 1), codigoObra=1)
    cubre = _obra("Finalizado", date(2021, 1, 1), date(2023, 12, 31), codigoObra=2)
    elegida = infoobras.seleccionar_obra(
        [lejana, cubre], date(2021, 5, 13), date(2023, 5, 6))
    assert elegida["codigoObra"] == 2


def test_seleccionar_obra_sin_fechas_cae_a_la_primera_finalizada():
    a = _obra("Finalizado", codigoObra=7)
    b = _obra("Finalizado", codigoObra=8)
    assert infoobras.seleccionar_obra([a, b])["codigoObra"] == 7


def test_seleccionar_obra_solape_usa_valorizaciones_no_cabecera():
    # caso 133630: la cabecera de la obra A termina antes del certificado, pero
    # sus valorizaciones llegan hasta 2016-07 → es la que realmente solapa.
    # La obra B (principal) arranca DESPUÉS del certificado y por cercanía de
    # fecha ganaría con el criterio viejo (cabecera).
    a = _obra("Finalizado", date(2014, 10, 30), date(2015, 2, 27), codigoObra=33900)
    b = _obra("Finalizado", date(2017, 6, 1), date(2018, 12, 1), codigoObra=71173)
    rangos = {
        33900: (date(2015, 1, 1), date(2016, 7, 1)),
        71173: (date(2017, 6, 1), date(2021, 4, 1)),
    }
    cert_ini, cert_fin = date(2016, 6, 10), date(2017, 5, 15)
    # sin valorizaciones (solo cabecera) gana la principal 71173 — el bug viejo
    assert infoobras.seleccionar_obra([a, b], cert_ini, cert_fin)["codigoObra"] == 71173
    # con el rango real de valorizaciones gana 33900 (la única que solapa)
    elegida = infoobras.seleccionar_obra(
        [a, b], cert_ini, cert_fin, rango_valorizaciones=lambda oid: rangos[oid])
    assert elegida["codigoObra"] == 33900


def test_seleccionar_obra_sin_solape_principal_paralizada_gana_a_contingencia():
    # caso Egoavil 1:4: ninguna obra solapa el certificado (2023-11 → 2025-07);
    # la principal PARALIZADA y reciente debe ganarle a la contingencia
    # FINALIZADA antigua por cercanía — sin gate duro de finalizada.
    contingencia = _obra("Finalizado", date(2017, 12, 1), date(2019, 3, 1), codigoObra=64149)
    principal = _obra("Paralizada", date(2019, 11, 1), date(2022, 10, 1), codigoObra=66057)
    rangos = {64149: (date(2017, 12, 1), date(2019, 3, 1)),
              66057: (date(2019, 11, 1), date(2022, 10, 1))}
    elegida = infoobras.seleccionar_obra(
        [contingencia, principal], date(2023, 11, 22), date(2025, 7, 22),
        rango_valorizaciones=lambda oid: rangos[oid])
    assert elegida["codigoObra"] == 66057


def test_seleccionar_obra_cabecera_no_da_solape_falso():
    # caso 3:1 Tacna: 41414 figura en cabecera hasta 2019-07 pero sus
    # valorizaciones pararon en 2017-03; 83130 valoriza durante el certificado.
    # La cabecera NO debe darle a 41414 un solape falso que le robe el match.
    a = _obra("Finalizado", date(2016, 10, 1), date(2019, 7, 29), codigoObra=41414)
    b = _obra("Paralizada", date(2017, 12, 1), date(2019, 7, 25), codigoObra=83130)
    rangos = {41414: (date(2016, 10, 1), date(2017, 3, 1)),
              83130: (date(2017, 12, 1), date(2025, 9, 1))}
    elegida = infoobras.seleccionar_obra(
        [a, b], date(2018, 3, 5), date(2019, 4, 30),
        rango_valorizaciones=lambda oid: rangos[oid])
    assert elegida["codigoObra"] == 83130


def test_elegir_obra_raw_valida_el_bypass_por_cobertura():
    # Valdizán: el resolver puede pasar 71173 (no cubre el cert); el bypass debe
    # corregir a 33900 (la que cubre). Si pasa 33900, se respeta.
    a = _obra("Finalizado", date(2014, 10, 30), date(2015, 2, 27), codigoObra=33900)
    b = _obra("Finalizado", date(2017, 6, 1), date(2018, 12, 1), codigoObra=71173)
    rangos = {33900: (date(2015, 1, 1), date(2016, 7, 1)),
              71173: (date(2017, 6, 1), date(2021, 4, 1))}
    ci, cf, rv = date(2016, 6, 10), date(2017, 5, 15), lambda oid: rangos[oid]

    # bypass con obra que NO cubre → corrige por solape a 33900
    assert infoobras.elegir_obra_raw([a, b], ci, cf, 71173, rv)["codigoObra"] == 33900
    # bypass con obra que SÍ cubre → se respeta
    assert infoobras.elegir_obra_raw([a, b], ci, cf, 33900, rv)["codigoObra"] == 33900
    # sin obra_id → selección por solape
    assert infoobras.elegir_obra_raw([a, b], ci, cf, None, rv)["codigoObra"] == 33900
    # sin fechas de certificado → no se puede validar, se respeta el bypass
    assert infoobras.elegir_obra_raw([a, b], None, None, 71173, rv)["codigoObra"] == 71173


def test_coincide_codigo_filtra_colision_por_substring():
    # buscar '95555' no debe traer '2595555' (substring): solo match exacto
    real = _obra("Finalizado", codSnip="95555", codUniqInv="2157301")
    ajena = _obra("Finalizado", codSnip="2595555", codUniqInv="2595555")
    assert infoobras.coincide_codigo(real, "95555")          # codSnip exacto
    assert infoobras.coincide_codigo(real, "2157301")        # codUniqInv exacto
    assert not infoobras.coincide_codigo(ajena, "95555")     # substring → descartar
    assert infoobras.coincide_codigo(ajena, "2595555")       # su propio CUI sí


class _SesionInestable:
    """Sesión falsa que falla `fallos` veces y luego responde."""
    def __init__(self, fallos: int, texto="var lAvances = [];"):
        self.headers, self.fallos, self.texto, self.llamadas = {}, fallos, texto, 0

    def _responder(self):
        self.llamadas += 1
        if self.llamadas <= self.fallos:
            raise requests.ConnectionError("RemoteDisconnected transitorio")

        class R:
            text = self.texto
            def raise_for_status(self_inner):
                return None
        return R()

    def get(self, *a, **k):
        return self._responder()


def test_datos_ejecucion_reintenta_ante_caida_transitoria(monkeypatch):
    # 2 caídas y a la 3ra responde → debe recuperar (no perder la obra)
    monkeypatch.setattr(infoobras.time, "sleep", lambda *_: None)
    ses = _SesionInestable(fallos=2)
    datos = infoobras._extraer_datos_ejecucion(ses, 999)
    assert ses.llamadas == 3 and "lAvances" in datos


def test_datos_ejecucion_propaga_si_agota_reintentos(monkeypatch):
    # si el portal nunca responde, propaga (la etapa lo marca como error honesto)
    monkeypatch.setattr(infoobras.time, "sleep", lambda *_: None)
    with pytest.raises(requests.RequestException):
        infoobras._extraer_datos_ejecucion(_SesionInestable(fallos=99), 1)


def test_consulta_query_reintenta_con_backoff(monkeypatch):
    # microcaída del portal: la búsqueda por código debe reintentar (no degradar
    # a "sin resultados" al primer fallo, que mandaba 6:1 a revisión por error)
    import resolucion.cui as cui_mod
    monkeypatch.setattr(cui_mod.time, "sleep", lambda *_: None)
    estado = {"n": 0}

    class R:
        def raise_for_status(self):
            return None

        def json(self):
            return {"Result": [{"codSnip": "123456", "codUniqInv": "1234567"}]}

    class Ses:
        def post(self, *a, **k):
            estado["n"] += 1
            if estado["n"] < 3:
                raise requests.ConnectionError("microcaída del portal")
            return R()

    c = cui_mod.ConsultaInfoObras()
    monkeypatch.setattr(c, "_ses", lambda: Ses())
    res = c.por_codigo("123456")
    assert estado["n"] == 3 and len(res) == 1


def test_fetch_by_cui_con_bypass_obra_id(monkeypatch):
    # Simula que buscar CUI devuelve 2 obras (por ejemplo, contingencia y principal).
    # Si le pasamos un obra_id específico, debe seleccionar esa obra y saltarse seleccionar_obra.
    import scraping.infoobras as infoobras_mod
    class FakeSession:
        headers = {}
        def get(self, *a, **k):
            class R:
                text = "var lAvances = [];"
                def raise_for_status(self_inner):
                    return None
            return R()

    monkeypatch.setattr(infoobras_mod, "_crear_session", lambda: FakeSession())

    obras = [
        {"codigoObra": 111, "nombrObra": "OBRA 1 CONTINGENCIA", "codSnip": "133630", "codUniqInv": "2130855", "estObra": "Finalizado"},
        {"codigoObra": 222, "nombrObra": "OBRA 2 PRINCIPAL", "codSnip": "133630", "codUniqInv": "2130855", "estObra": "Paralizada"}
    ]
    monkeypatch.setattr(infoobras_mod, "_buscar_por_cui", lambda *_: obras)
    monkeypatch.setattr(infoobras_mod.time, "sleep", lambda *_: None)

    # Si llamamos con obra_id=222, debe elegir la de ID 222 (aunque sea paralizada y sin solape)
    res = infoobras_mod.fetch_by_cui("133630", obra_id=222)
    assert res is not None
    assert res.obra_id == 222
    assert res.nombre == "OBRA 2 PRINCIPAL"
