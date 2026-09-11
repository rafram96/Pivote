from datetime import date

from orquestador.recontraste_fuentes import FuentesRecontraste
from scraping.sunat import EmpresaSUNAT


def fuentes(**kwargs):
    return FuentesRecontraste(**{
        "ficha": lambda c: "B. Datos de la fase de Ejecución",
        "contratos": lambda c: [], "empresa": lambda r: None,
        "buscar": lambda n: [], "extras": lambda r: ([], None), **kwargs})


def test_mef_solo_cruza_contrato_exacto_aunque_otro_sea_mas_barato():
    filas = [{"NUM_CONTRATO": n, "NOMENCLATURA": "CP-UNO", "MTO_TOTAL": m,
              "NOM_CONTRATISTA": "EMPRESA UNO", "DES_PROCESO": "Elaboración de expediente técnico",
              "FEC_SUSCRIPCION": "01/03/2022"} for n, m in [("contrato-1", 1), ("contrato-2", 100)]]
    f = fuentes(contratos=lambda c: filas)
    seleccionado = {"proceso": {"nomenclatura": "CP-UNO"},
                    "proceso_fuente": {"contracts": [{"id": "contrato-2"}]}}
    b, estado, faltantes = f.contrastar_mef({"entidad_emisora": "EMPRESA UNO"}, "2000002", seleccionado)
    assert b["contrato"]["numero"] == "contrato-2"
    assert b["contrato"]["monto"] == 100
    assert "cui_confirmado" not in b  # no activar descargador que volvería a elegir
    assert b["resolucion"]["veredicto"] == "no_verificable"
    assert faltantes
    assert estado["estado"] == "disponible"
    from reglas.cruces_fechas import expediente_verificado
    assert expediente_verificado(b)[0] is False  # contrato coincidente no acredita aprobación


def test_mef_sin_numero_o_con_otro_proceso_no_elige_el_primero():
    f = fuentes(contratos=lambda c: [{"NUM_CONTRATO": "1", "NOMENCLATURA": "OTRO",
                                    "DES_PROCESO": "Expediente técnico"}])
    for s in ({}, {"proceso": {"nomenclatura": "CP-UNO"}, "proceso_fuente": {"contracts": [{"id": "1"}]}}):
        b, _, _ = f.contrastar_mef({}, "2000002", s)
        assert "contrato" not in b
        assert not b["verificado_en_mef"]


def test_mef_cachea_fallos_y_no_los_declara_ausencia():
    llamadas = []
    def caida(c):
        llamadas.append(c)
        raise TimeoutError()
    f = fuentes(ficha=caida, contratos=caida)
    for _ in range(2):
        b, estado, _ = f.contrastar_mef({}, "2000002", {})
        assert "no prueba inexistencia" in b["motivo"]
        assert estado["recursos"] == {"ficha": "no_disponible", "contratos": "no_disponible"}
    assert llamadas == ["2000002", "2000002"]


def test_mef_respuesta_malformada_no_afirma_contratos_inexistentes():
    f = fuentes(contratos=lambda c: [{"NUM_CONTRATO": 123}])
    b, estado, _ = f.contrastar_mef({}, "2000002", {})
    assert estado["recursos"]["contratos"] == "no_disponible"
    assert "respuesta_invalida" in estado["errores"]
    assert not b["verificado_en_mef"]


def test_integracion_actualiza_sunat_sin_mef_en_obras_y_sin_modificar_seleccion():
    from test_aplicar_identidad import insumos, proyectar
    from orquestador.recontraste_identidad import recontrastar_asociaciones
    e, enr, r = insumos()
    nuevo, _ = proyectar(e, enr, r)
    e["profesionales"][0]["experiencias"][0]["ruc_emisor"] = "20123456789"
    nuevo["1:1"]["sunat"] = {"ruc": "20999999999", "alt04": {"estado": "VIEJO"}}
    def no_mef(c):
        raise AssertionError("No consultar MEF para obras")
    f = fuentes(ficha=no_mef, contratos=no_mef,
                empresa=lambda ruc: EmpresaSUNAT(ruc=ruc, razon_social="EMPRESA NUEVA"))
    final = recontrastar_asociaciones(e, nuevo, ["1:1"], leer_obra=lambda *a, **kw: None, fuentes=f)
    assert final["1:1"]["sunat"]["ruc"] == "20123456789"
    assert final["1:1"]["sunat"]["alt04"] is None
    assert nuevo["1:1"]["sunat"]["ruc"] == "20999999999"
    assert final["1:1"]["seace"]["ocid"] == nuevo["1:1"]["seace"]["ocid"]
    assert not any(k[0].startswith("mef") for k in f.cache)


def test_sunat_recalcula_por_periodo_y_cachea_lectura_sin_heredar():
    llamadas = []
    def empresa(r):
        llamadas.append(r)
        return EmpresaSUNAT(ruc=r, razon_social="EMPRESA UNO", fecha_inscripcion=date(2021, 1, 1))
    f = fuentes(empresa=empresa)
    bloques = []
    for inicio in ("2020-01-01", "2022-01-01"):
        b, estado, _ = f.contrastar_sunat({"ruc_emisor": "20123456789", "fecha_inicial": inicio}, {}, {})
        bloques.append(b)
        assert estado["estado"] == "disponible"
    assert bloques[0]["alt04"]["estado"] == "ALERTA"
    assert bloques[1]["alt04"] is None
    assert llamadas == ["20123456789"]


def test_sunat_otro_ruc_y_busqueda_caida_no_confirman_empresa():
    f = fuentes(empresa=lambda r: EmpresaSUNAT(ruc="20999999999"))
    b, estado, _ = f.contrastar_sunat({"ruc_emisor": "20123456789"}, {}, {})
    assert not b.get("ruc") and estado["estado"] == "no_disponible"
    def caida(n): raise TimeoutError()
    f = fuentes(buscar=caida)
    b, estado, _ = f.contrastar_sunat({"entidad_emisora": "EMPRESA UNO"}, {}, {})
    assert "no_encontrado" not in b
    assert estado["recursos"]["busqueda"] == "no_disponible"
