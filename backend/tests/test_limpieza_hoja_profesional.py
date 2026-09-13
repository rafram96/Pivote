"""La hoja del profesional vuelve al formato compacto acordado (12-sep-2026).

Diez puntos de limpieza pedidos por el cliente después de ver una entrega real:
los textos que se añadieron en septiembre recargaron la hoja sin decidir nada.
Cada prueba fija UN punto y lo comprueba en las DOS rutas del producto
(expedientes y obras), con datos sintéticos: ni nombres, ni RUC, ni CUI reales.

Lo retirado del Excel NO se borra del producto: sigue íntegro en el análisis, en
la API y en el ZIP (ver `test_estado_fuentes_entregables.py` y
`test_candado_seace.py`). Aquí solo se fija qué se PINTA.
"""
from __future__ import annotations

import openpyxl
import pytest

from entregables.excel_final import (
    desempaquetar_enriquecimiento, generar_excel_final,
)

RUTAS = ["expedientes", "obras"]

# Textos de septiembre que el cliente señaló como basura. Ninguno puede volver
# a una hoja de profesional, por ninguna de las dos rutas.
BASURA = (
    "SERVICIO ESPERADO (concurso)",
    "SERVICIO DECLARADO (certificado)",
    "CONTRASTE DE SERVICIO",
    "Estado de fuentes y documentos",
    "enlace identificado; descarga no registrada",
    "Sin documentos en el inventario del análisis",
    "ver estado de fuentes",
    "Adjuntos del contrato",
    "Datos del proceso vs. certificado",
    "Contenido de los documentos",
    "Identidad pendiente. Señales fuertes a favor",
    "En esta corrida no se obtuvieron procesos de contratación",
    "Fuente: MEF",
    "no hay valorizaciones",
    "respuesta no interpretable",
    "no permite afirmar ausencia",
    "Representantes legales",
    "Domicilio fiscal",
    "Objeto social",
    "Inicio actividades",
    "Nombre o razón social anterior",
    "Efectivo computado = aporte antes de descontar",
)


def _candado_por_confirmar():
    return {"resultado": "por_confirmar", "senales": [
        {"nombre": "temporal", "sentido": "en_contra", "fuerza": "debil",
         "detalle": "Fechas: el profesional declara inicio el 01/03/2021 pero el "
                    "contrato del proceso se firmó el 02/05/2021."}],
        "motivo": "Identidad pendiente. Señales fuertes a favor: 0; se requieren "
                  "al menos 2, incluyendo al adjudicatario."}


def _seace_con_documentos():
    return {
        "estado": "seleccionado", "cui": "9000011", "proceso_objeto": "expediente",
        "fecha_suscripcion": "2021-05-02", "candado": _candado_por_confirmar(),
        "documentos": [
            {"categoria": "bases", "url": "https://fuente/bases.pdf"},
            {"categoria": "contrato", "url": "https://fuente/contrato.pdf"},
            {"categoria": "contrato", "url": None},
        ],
        "proceso": {"entidad_convocante": "ENTIDAD FICTICIA"},
    }


def _sunat_con_ruc():
    return {
        "ruc": "20999999999", "razon_social": "EMPRESA FICTICIA SAC",
        "fecha_inscripcion": "2010-01-05", "estado": "ACTIVO", "condicion": "HABIDO",
        "tipo_contribuyente": "SOCIEDAD ANONIMA CERRADA",
        "actividades_economicas": ["Principal - 7110 - ACTIVIDADES DE INGENIERÍA"],
        "domicilio_fiscal": "CAL. FICTICIA NRO. 1 LIMA",
        "fecha_inicio_actividades": "2010-02-01",
        "representantes": [{"nombre": "PERSONA FICTICIA UNO", "cargo": "APODERADO",
                            "fecha_desde": "2020-08-17"}],
        "historico": {
            "razones_sociales": [{"nombre": "EMPRESA FICTICIA EIRL",
                                  "fecha_baja": "2016-05-04"}],
            "domicilios": [{"direccion": "JR. FICTICIO 55", "fecha_baja": "2016-05-04"}]},
        "habido": {
            "emision": {"fecha": "2022-02-01", "condicion": "HABIDO", "ok": True},
            "periodo": {"desde": "2021-03-01", "hasta": "2021-12-31", "ok": True,
                        "tramos": [{"condicion": "HABIDO", "desde": "2021-03-01",
                                    "hasta": "2021-12-31"}]}},
    }


def _espejo(tipo):
    experiencias = []
    for n, proyecto in ((1, "PROYECTO FICTICIO CON PROCESO"),
                        (2, "PROYECTO FICTICIO SIN PROCESO")):
        experiencias.append({
            "n": n, "proyecto": proyecto, "fecha_inicial": "2021-03-01",
            "fecha_final": "2021-12-31", "fecha_emision": "2022-02-01",
            "ruc_emisor": "20999999999"})
    return {
        "_meta": {"analisis_id": "limpieza", "concurso": "C-TEST", "postor": "P",
                  "tipo_evaluacion": tipo},
        "postor": {},
        "profesionales": [{"n_prof": 1, "cargo": "ESPECIALISTA",
                           "nombre": "PERSONA FICTICIA", "requisitos": {},
                           "experiencias": experiencias}],
        "resumen_evaluacion": {"factores": []},
    }


def _enriquecimiento():
    """Dos experiencias: una con proceso y documentos, otra sin nada de eso."""
    verificacion = {
        "contratista": {"valor": "EMPRESA FICTICIA SAC", "veredicto": "ok"},
        "contrato": {"numero": "001-2021", "fecha": "2021-05-02", "monto": 100000.0,
                     "veredicto": "ok"},
        "resolucion": {"numero": "0001-2022", "veredicto": "por_confirmar"},
        "cui_confirmado": "9000011", "fuentes": ["MEF-SEACE", "MEF-08A"],
    }
    return {
        "1:1": {
            "via": "CUI_TEXTO", "cui": "9000011", "camino": "expediente",
            "obra_nombre": "PROYECTO FICTICIO CON PROCESO",
            "codigo_infoobras": "999001", "valorizaciones": [],
            "verificacion_expediente": verificacion,
            "seace": _seace_con_documentos(),
            "inventario_documental": {"documentos": [
                {"id": "d1", "tipo": "contrato"}, {"id": "d2", "tipo": "bases"}]},
            # el contraste de servicio existe como DATO; no se pinta como filas
            "contraste_servicio": {
                "estado": "difiere", "motivo": "El concurso pide otro servicio.",
                "esperado": {"tipo": "supervision_obra"},
                "declarado": {"tipo": "elaboracion_expediente",
                              "texto": "Elaboración del expediente"}},
            "consultas_fuentes": {
                "sunat_ruc": {"estado": "con_resultados", "motivo": ""}},
            "sunat": _sunat_con_ruc(),
        },
        "1:2": {
            "via": "CUI_TEXTO", "cui": "9000012", "camino": "expediente",
            "obra_nombre": "PROYECTO FICTICIO SIN PROCESO",
            "codigo_infoobras": "999002", "valorizaciones": [],
            "verificacion_expediente": {"cui_confirmado": "9000012",
                                        "fuentes": ["MEF-08A"]},
            "seace": {"estado": "sin_procesos", "cui": "9000012"},
            "inventario_documental": {"documentos": []},
            "consultas_fuentes": {
                "sunat_nombre": {"estado": "respuesta_no_reconocida",
                                 "motivo": "HTML no reconocible (estructura inesperada)."}},
            "sunat": {"nombre": "EMPRESA FICTICIA DOS SAC", "no_encontrado": True},
        },
    }


def _hoja(tmp_path, tipo, enr=None):
    espejo = _espejo(tipo)
    enr = enr if enr is not None else _enriquecimiento()
    paral, cuis, fichas, sunat = desempaquetar_enriquecimiento(enr)
    salida = generar_excel_final(espejo, tmp_path / f"{tipo}.xlsx", paral, cuis,
                                fichas, {}, sunat)
    wb = openpyxl.load_workbook(salida)
    ws = next(w for w in wb if w.title.startswith("P1."))
    celdas = [str(c.value) for fila in ws.iter_rows() for c in fila
              if c.value not in (None, "")]
    return wb, ws, "\n".join(celdas), celdas


# ── 0 · nada de lo señalado como basura sobrevive en ninguna ruta ────────────

@pytest.mark.parametrize("tipo", RUTAS)
@pytest.mark.parametrize("texto", BASURA)
def test_ningun_texto_retirado_vuelve_a_la_hoja(tmp_path, tipo, texto):
    _wb, _ws, contenido, _ = _hoja(tmp_path, tipo)
    assert texto not in contenido
    _wb.close()


# ── 1 · el contraste de servicio no se pinta como tres filas ────────────────

@pytest.mark.parametrize("tipo", RUTAS)
def test_el_contraste_de_servicio_no_ocupa_filas_propias(tmp_path, tipo):
    """El dato sigue en el análisis (API/ZIP) y en la diferencia del cargo; lo que
    se retiró son las tres filas que lo repetían en cada certificado."""
    _wb, _ws, contenido, _ = _hoja(tmp_path, tipo)
    for fila in ("SERVICIO ESPERADO", "SERVICIO DECLARADO", "CONTRASTE DE SERVICIO"):
        assert fila not in contenido
    _wb.close()


# ── 2 · ni bloque de estados de fuente ni la línea de documentos SEACE ──────

@pytest.mark.parametrize("tipo", RUTAS)
def test_sin_bloque_de_estado_de_fuentes(tmp_path, tipo):
    enr = _enriquecimiento()
    enr["1:1"]["descargas_reales"] = {"secciones": {"Documentos SEACE": {
        "documentos": [{"titulo": "Contrato", "estado": "enlace_sin_descarga_registrada"}]}}}
    _wb, _ws, contenido, _ = _hoja(tmp_path, tipo, enr)
    assert "Estado de fuentes" not in contenido
    assert "descarga no registrada" not in contenido
    assert "Documentos SEACE:" not in contenido
    _wb.close()


# ── 3 · «Documentos encontrados» ───────────────────────────────────────────

@pytest.mark.parametrize("tipo", RUTAS)
def test_documentos_encontrados_dice_cuantos_o_que_no_hay(tmp_path, tipo):
    _wb, _ws, contenido, celdas = _hoja(tmp_path, tipo)
    assert "2 archivos encontrados" in celdas        # experiencia 1
    assert "Sin documentos descargados" in celdas    # experiencia 2
    assert "Sin documentos registrados en este análisis" not in contenido
    assert "inventario del análisis" not in contenido
    _wb.close()


# ── 4 · bloque DOCUMENTOS DEL PROCESO (SEACE) ──────────────────────────────

@pytest.mark.parametrize("tipo", RUTAS)
def test_el_bloque_seace_vuelve_a_sus_filas_acordadas(tmp_path, tipo):
    _wb, _ws, contenido, celdas = _hoja(tmp_path, tipo)
    # a · el contrato se llama por su nombre y cuenta archivos
    assert "Contrato firmado" in celdas
    assert "Adjuntos del contrato" not in contenido
    assert "1 archivo encontrado" in celdas
    assert "enlace encontrado" not in contenido
    assert "registro(s) sin enlace" not in contenido
    # b · correspondencia con el rótulo corto del candado, sin la explicación
    assert "Correspondencia con el certificado" in celdas
    assert "Por confirmar" in celdas
    assert "no se pudo verificar contra el certificado" not in contenido
    # c · ni observación de fechas ni el informe de identidad dentro del bloque
    assert "Identidad pendiente" not in contenido
    assert "el profesional declara inicio el" not in contenido
    # d · sin procesos, en pocas palabras
    assert "Sin procesos en SEACE para este CUI" in celdas
    _wb.close()


@pytest.mark.parametrize("tipo", RUTAS)
def test_una_contradiccion_del_candado_cabe_en_su_propia_fila(tmp_path, tipo):
    enr = _enriquecimiento()
    enr["1:1"]["seace"]["candado"] = {
        "resultado": "contradice", "senales": [],
        "motivo": "El proceso encontrado CONTRADICE al certificado: la entidad "
                  "convocante no es la que emite la constancia."}
    _wb, _ws, contenido, celdas = _hoja(tmp_path, tipo, enr)
    fila = next(c for c in celdas if c.startswith("Contradice"))
    assert "la entidad convocante no es la que emite la constancia" in fila
    assert len(fila.splitlines()) == 1
    assert "El proceso encontrado CONTRADICE al certificado:" not in contenido
    _wb.close()


@pytest.mark.parametrize("tipo", RUTAS)
def test_un_candado_confirmado_no_explica_nada(tmp_path, tipo):
    enr = _enriquecimiento()
    enr["1:1"]["seace"]["candado"] = {"resultado": "confirmado", "senales": [],
                                      "motivo": "explicación que no va al Excel"}
    _wb, _ws, contenido, celdas = _hoja(tmp_path, tipo, enr)
    assert "Confirmado" in celdas
    assert "explicación que no va al Excel" not in contenido
    assert "Coincidencias de metadatos" not in contenido
    _wb.close()


# ── 5 · la observación de fechas, solo con un resultado concreto ────────────

def test_sin_fecha_comparada_no_hay_fila_de_observacion(tmp_path):
    """Ruta de expedientes: dos «POR VERIFICAR» sin fecha no son observación."""
    enr = _enriquecimiento()
    enr["1:1"].pop("seace")
    enr["1:2"].pop("seace")
    _wb, ws, contenido, _ = _hoja(tmp_path, "expedientes", enr)
    assert "Observación de fechas" not in contenido
    _wb.close()


def test_con_fecha_comparada_la_observacion_se_pinta_sin_partes_vacias(tmp_path):
    enr = _enriquecimiento()
    enr["1:1"]["cruces_fechas"] = [
        {"regla": "FECHA_CONTRATO", "resultado": "dispara",
         "fecha_fuente": "2021-05-02",
         "motivo": "El inicio declarado es anterior a la firma del contrato."},
        {"regla": "FECHA_APROBACION_ET", "resultado": "por_confirmar",
         "motivo": "No se obtuvo la aprobación del expediente."}]
    _wb, ws, contenido, _ = _hoja(tmp_path, "expedientes", enr)
    nota = next(str(c.value) for c in ws["A"]
                if str(c.value).startswith("Observación de fechas"))
    assert "Inicio frente al contrato: NO" in nota
    assert "El inicio declarado es anterior a la firma del contrato." in nota
    # el término no tiene fecha de aprobación con la que comparar: no se enuncia
    # ni arrastra su motivo
    assert "Término frente a aprobación" not in nota
    assert "No se obtuvo la aprobación del expediente." not in nota
    _wb.close()


def test_obras_no_recibe_la_fila_de_observacion_de_fechas(tmp_path):
    _wb, _ws, contenido, _ = _hoja(tmp_path, "obras")
    assert "Observación de fechas" not in contenido
    _wb.close()


# ── 6 · la fila «Fuente: MEF-…» desaparece ─────────────────────────────────

@pytest.mark.parametrize("tipo", RUTAS)
def test_sin_fila_de_fuente_las_etiquetas_mef_ya_lo_dicen(tmp_path, tipo):
    _wb, _ws, contenido, celdas = _hoja(tmp_path, tipo)
    assert not any(c.startswith("Fuente:") for c in celdas)
    assert "Contratista (MEF)" in celdas and "CUI confirmado (MEF)" in celdas
    _wb.close()


# ── 7 · cabecera del expediente sin la explicación pegada ──────────────────

@pytest.mark.parametrize("tipo", RUTAS)
def test_cabecera_de_expediente_sin_parentesis(tmp_path, tipo):
    _wb, _ws, contenido, celdas = _hoja(tmp_path, tipo)
    assert "EXPEDIENTE TÉCNICO — verificación" in celdas
    assert "no hay valorizaciones" not in contenido
    assert "no ejecutó la obra" not in contenido
    _wb.close()


# ── 8 · el emisor sin identificar se explica como lo haría un evaluador ────

@pytest.mark.parametrize("tipo", RUTAS)
def test_sunat_sin_emisor_habla_en_lenguaje_de_evaluador(tmp_path, tipo):
    _wb, _ws, contenido, celdas = _hoja(tmp_path, tipo)
    assert "SUNAT no respondió; emisor por confirmar." in celdas
    for jerga in ("búsqueda por nombre", "respuesta no interpretable",
                  "no permite afirmar ausencia", "HTML no reconocible",
                  "sunat_nombre"):
        assert jerga not in contenido
    _wb.close()


@pytest.mark.parametrize("tipo", RUTAS)
def test_sunat_sin_coincidencias_lo_dice_en_una_frase(tmp_path, tipo):
    enr = _enriquecimiento()
    enr["1:2"]["consultas_fuentes"] = {"sunat_nombre": {"estado": "sin_resultados"}}
    _wb, _ws, _contenido, celdas = _hoja(tmp_path, tipo, enr)
    assert "Sin coincidencia en SUNAT." in celdas
    _wb.close()


@pytest.mark.parametrize("tipo", RUTAS)
def test_varias_empresas_con_ese_nombre_piden_confirmar_el_ruc(tmp_path, tipo):
    enr = _enriquecimiento()
    enr["1:2"]["sunat"] = {"nombre": "EMPRESA FICTICIA DOS SAC", "ambiguo": 3}
    _wb, _ws, contenido, _ = _hoja(tmp_path, tipo, enr)
    assert "3 empresas en SUNAT con ese nombre" in contenido
    assert "confirmar el RUC del emisor" in contenido
    _wb.close()


# ── 9 · la leyenda de la PARTE 5, en una línea ─────────────────────────────

def test_leyenda_de_la_parte_5_en_una_linea(tmp_path):
    _wb, _ws, _contenido, celdas = _hoja(tmp_path, "expedientes")
    leyenda = next(c for c in celdas if c.startswith("Declarado ="))
    assert leyenda == ("Declarado = días del período certificado. "
                       "Efectivo = aporte antes de descontar traslapes.")
    assert len(leyenda) < 120


def test_obras_no_pinta_la_leyenda_de_expedientes(tmp_path):
    _wb, _ws, contenido, _ = _hoja(tmp_path, "obras")
    assert "Declarado =" not in contenido


# ── 10 · el cuadro del emisor conserva solo lo que decide ──────────────────

@pytest.mark.parametrize("tipo", RUTAS)
def test_el_cuadro_del_emisor_conserva_lo_que_decide(tmp_path, tipo):
    _wb, _ws, contenido, celdas = _hoja(tmp_path, tipo)
    for conservado in ("RUC", "Razón social", "Estado / Condición",
                       "¿Estaba habido al emitir el certificado?",
                       "¿Estuvo habido durante el periodo certificado?",
                       "Condición del contribuyente durante la experiencia",
                       "Condición", "Desde", "Hasta"):
        assert conservado in celdas, conservado
    assert any(c.startswith("✔ ALT04") for c in celdas)
    _wb.close()


@pytest.mark.parametrize("tipo", RUTAS)
def test_el_cuadro_del_emisor_suelta_lo_informativo(tmp_path, tipo):
    _wb, _ws, contenido, _ = _hoja(tmp_path, tipo)
    for retirado in ("Representantes legales", "PERSONA FICTICIA UNO", "APODERADO",
                     "Domicilio fiscal", "CAL. FICTICIA NRO. 1", "JR. FICTICIO 55",
                     "Objeto social", "ACTIVIDADES DE INGENIERÍA",
                     "Inicio actividades", "SOCIEDAD ANONIMA CERRADA",
                     "Nombre o razón social anterior", "EMPRESA FICTICIA EIRL"):
        assert retirado not in contenido, retirado
    _wb.close()


@pytest.mark.parametrize("tipo", RUTAS)
def test_alt04_sigue_usando_la_inscripcion_aunque_no_se_pinte(tmp_path, tipo):
    """La fila «Inicio actividades» ya no se pinta, pero ALT04 sigue comparando
    la creación del emisor contra la emisión y el inicio de la experiencia."""
    enr = _enriquecimiento()
    enr["1:1"]["sunat"] = {**_sunat_con_ruc(), "fecha_inscripcion": "2023-01-05",
                           "fecha_inicio_actividades": "2023-02-01", "habido": None}
    _wb, _ws, contenido, celdas = _hoja(tmp_path, tipo, enr)
    alerta = next(c for c in celdas if "ALT04" in c)
    assert "ANTES de" in alerta and "05/01/23" in alerta
    assert "Inicio actividades" not in contenido
    _wb.close()


# ── 11 · sin contrato ni resolución, el bloque MEF dice qué pasó en el portal ──

@pytest.mark.parametrize("tipo", ["expedientes"])
def test_sin_documentos_mef_la_fila_dice_que_el_portal_no_publica(tmp_path, tipo):
    enr = _enriquecimiento()
    _, _, texto, _ = _hoja(tmp_path, tipo, enr)
    assert "no publica contrato ni adjuntos para este CUI" in texto
    assert "CUI según la ficha del MEF (sin documento que lo respalde)" in texto
    # la experiencia CON documentos conserva su etiqueta de siempre
    assert "CUI confirmado (MEF)" in texto


@pytest.mark.parametrize("tipo", ["expedientes"])
def test_con_adjuntos_sin_clasificar_la_fila_los_cuenta(tmp_path, tipo):
    enr = _enriquecimiento()
    enr["1:2"]["verificacion_expediente"]["documentos_08a"] = [
        {"label": "RER N° 1-2013", "url": "https://mef/a.pdf"},
        {"label": "INFORME N° 2-2014", "url": "https://mef/b.pdf"},
        {"label": "CARTA N° 3-2015", "url": "https://mef/c.pdf"}]
    _, _, texto, _ = _hoja(tmp_path, tipo, enr)
    assert "publica 3 adjunto(s) para este CUI, pero ninguno es contrato ni resolución" in texto
    assert "van al ZIP como adjuntos sin clasificar" in texto
    assert "no publica contrato ni adjuntos" not in texto
