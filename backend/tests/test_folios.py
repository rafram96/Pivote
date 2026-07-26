"""
Verificación folio ↔ certificado (issue #47).

Caso de referencia: job `95af90f1578e`, prof 1 exp 1 — el espejo declara folio
358 para un certificado de SAN CARLOS CONTRATISTAS GENERALES SRL, pero el 358 es
un documento de la Municipalidad Distrital de San José (el certificado está en el
359). Lo que estos tests protegen, en orden de importancia:

  1. que un certificado de OTRA entidad NUNCA salga «coincide», ni cuando
     comparte palabras sueltas con el emisor declarado (el falso CUMPLE), ni
     cuando la identidad declarada es tan genérica que cualquiera la satisface;
  2. que un escaneo sin texto NUNCA se reporte como sospechoso (sería una falsa
     alarma por cada experiencia: en la corrida real los 63 recortes son
     escaneos puros);
  3. que el ruido del OCR —espacios dentro de las palabras, saltos de línea, una
     letra mal leída— no dispare alarmas sobre el documento correcto.

Los PDFs sintéticos se generan con fitz en `tmp_path`. Los tests contra datos
reales usan los dos únicos recortes del corpus que traen capa de texto (job
`36d710f27694`): dos consorcios hermanos que comparten «CONSORCIO SUPERVISOR
HOSPITAL» y se distinguen solo por la ciudad. Cruzarlos es la prueba real de que
el módulo discrimina — y de que no se limita a abstenerse siempre.
"""
from __future__ import annotations

import json
from pathlib import Path

import fitz
import pytest

from config import data_dir
from validacion.folios import (
    ESTADO_NO_VERIFICABLE, ESTADO_OK, ESTADO_SOSPECHOSO, LETRAS_MINIMAS,
    SENAL_NOMBRE, SENAL_RUC, Verificacion, compactar, contiene_ruc,
    extraer_paginas, frase_emisor, identidad_verificable, normalizar,
    revisar_certificados, ruta_certificado, terminos_emisor,
    verificar_certificado, verificar_paginas, verificar_texto,
)

# ── Textos de certificado (recortados de los reales, sin datos del cliente) ──

CERT_SAN_CARLOS = """SAN CARLOS CONTRATISTAS GENERALES S.R.L.
R.U.C. N° 20505655215
CERTIFICADO DE TRABAJO
El que suscribe, Representante Legal, hace constar que el Ing. MIGUEL CACERES
se desempeño como Residente de Obra en la CONSTRUCCION DEL CENTRO DE SALUD
MATERNO INFANTIL CHANCHAMAYO PUERTO YURINAKI, del 26/09/2016 al 03/01/2017.
Se extiende el presente para los fines que estime conveniente."""

# El folio corrido de verdad: la constancia que está en el 358 en lugar del
# certificado de San Carlos. Comparte «SAN» (San José) y «CARLOS» (el nombre del
# ingeniero) con el emisor declarado, sueltos y a media página de distancia.
CERT_OTRO_EMISOR = """MUNICIPALIDAD DISTRITAL DE SAN JOSE
CONSTANCIA DE HABILITACION URBANA
El que suscribe, Gerente de Desarrollo Urbano de la Municipalidad Distrital de
San Jose, hace constar que el Ing. Juan Carlos Mendoza Rojas presento el
expediente que cumple con los requisitos establecidos en el reglamento vigente
para la ejecucion de la obra."""

CERT_TARAPOTO = """CONSORCIO SUPERVISOR HOSPITAL TARAPOTO
CONSTANCIA DE PRESTACION DE SERVICIOS
El suscrito, Representante legal del Consorcio Supervisor Hospital Tarapoto,
con RUC N° 20544148380, hace constar que el profesional se desempeño como
JEFE DE SUPERVISION en la construccion del Hospital de EsSalud de Tarapoto."""

EMISOR_SAN_CARLOS = "SAN CARLOS CONTRATISTAS GENERALES SRL"
RUC_SAN_CARLOS = "20505655215"


def _pdf(tmp_path: Path, *paginas: str, nombre: str = "cert.pdf") -> Path:
    """PDF con capa de texto real, una página por argumento."""
    ruta = tmp_path / nombre
    doc = fitz.open()
    for texto in paginas:
        pg = doc.new_page()
        pg.insert_text((50, 60), texto, fontsize=9)
    doc.save(ruta)
    doc.close()
    return ruta


def _pdf_escaneado(tmp_path: Path, sello: str = "", nombre: str = "escaneo.pdf") -> Path:
    """PDF sin capa de texto: solo una imagen (y, opcionalmente, el sello de folio).

    Reproduce lo que produce el recortador real: la página es una imagen y el
    único texto es el número de folio estampado encima.
    """
    ruta = tmp_path / nombre
    doc = fitz.open()
    pg = doc.new_page()
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 8, 8))
    pix.clear_with(220)
    pg.insert_image(fitz.Rect(40, 40, 550, 700), pixmap=pix)
    if sello:
        pg.insert_text((20, 20), sello, fontsize=8)
    doc.save(ruta)
    doc.close()
    return ruta


def _exp(**extra) -> dict:
    return {"n": 1, "entidad_emisora": EMISOR_SAN_CARLOS, "ruc_emisor": RUC_SAN_CARLOS,
            "folio": 358, **extra}


# ── Normalización, frase y términos del emisor ──────────────────────────────

def test_normalizar_quita_tildes_y_puntuacion():
    assert normalizar("Perené, S.A.C. — N° 12") == "PERENE S A C N 12"


def test_compactar_borra_los_espacios_que_mete_el_ocr():
    """El OCR real escribe «c o n», «d e»: sin espacios, el texto vuelve a ser texto."""
    assert compactar("S A N   C A R L O S") == "SANCARLOS"


def test_frase_emisor_es_el_nombre_contiguo_sin_forma_societaria():
    """La forma societaria se poda: el membrete puede omitirla o escribirla de otro modo."""
    assert frase_emisor(EMISOR_SAN_CARLOS) == "SANCARLOSCONTRATISTASGENERALES"


def test_frase_emisor_conserva_los_genericos():
    """«CONSORCIO SUPERVISOR HOSPITAL» no identifica por sí solo, pero es parte del
    membrete impreso y su largo es lo que da fuerza a la contigüidad."""
    assert frase_emisor("CONSORCIO SUPERVISOR HOSPITAL DE MOYOBAMBA") \
        == "CONSORCIOSUPERVISORHOSPITALDEMOYOBAMBA"


def test_frase_emisor_poda_el_honorifico_de_una_persona():
    """El extractor arrastra «Ing.»; el documento puede firmar sin él."""
    assert frase_emisor("Ing. Hugo Pichilingue Mugruza") == "HUGOPICHILINGUEMUGRUZA"


def test_terminos_emisor_descarta_forma_societaria_y_generico():
    """Queda solo lo que identifica: SRL, CONTRATISTAS y GENERALES no identifican."""
    assert terminos_emisor(EMISOR_SAN_CARLOS) == ("SAN", "CARLOS")


def test_terminos_emisor_ignora_la_glosa_entre_parentesis():
    """El paréntesis lo agrega el extractor, no está en el membrete del documento."""
    assert terminos_emisor("PROYECTO ESPECIAL ALTO MAYO (Gobierno Regional San Martín)") \
        == ("ALTO", "MAYO")


def test_terminos_emisor_no_cae_a_los_genericos():
    """Sin término propio no hay identidad: devolver los genéricos sería convertir
    la ausencia de dato identificatorio en evidencia a favor del documento."""
    assert terminos_emisor("Empresa Constructora S.A.C.") == ()
    assert terminos_emisor("S & S CONSULTORES Y CONTRATISTAS GENERALES S.A.C.") == ()


def test_sin_emisor_no_hay_terminos():
    assert terminos_emisor(None) == ()


def test_identidad_verificable_exige_senal_distintiva():
    assert identidad_verificable(EMISOR_SAN_CARLOS)
    assert identidad_verificable("CONSORCIO SUPERVISOR HOSPITAL DE MOYOBAMBA")
    # Solo genéricos: nada propio que buscar.
    assert not identidad_verificable("S & S CONSULTORES Y CONTRATISTAS GENERALES S.A.C.")
    # Un único término corto: «SUR» cabe dentro de «SURCO» sin que nadie lo note.
    assert not identidad_verificable("CONSORCIO HOSPITAL DEL SUR")
    assert not identidad_verificable("Corporación KG Consultoría y Construcción S.A.C.")
    assert not identidad_verificable(None)


# ── Señal dura: el RUC ──────────────────────────────────────────────────────

def test_ruc_literal_confirma_el_folio(tmp_path):
    v = verificar_certificado(_pdf(tmp_path, CERT_SAN_CARLOS), _exp())
    assert (v.ok, v.estado, v.senal) == (True, ESTADO_OK, SENAL_RUC)
    assert v.folio == 358 and v.n_exp == 1


def test_ruc_con_separadores_de_maquetacion_igual_cuenta():
    """«20 505 655 215» y «R.U.C.\\n20505655215» son el mismo RUC."""
    assert contiene_ruc("RUC N° 20 505 655 215 del emisor", RUC_SAN_CARLOS)
    assert contiene_ruc("R.U.C.\n20505655215", RUC_SAN_CARLOS)
    assert contiene_ruc("RUC 20.505.655-215", RUC_SAN_CARLOS)


def test_ruc_de_otra_empresa_no_dispara_la_senal():
    assert not contiene_ruc("RUC N° 20544148380", RUC_SAN_CARLOS)


def test_el_ruc_no_se_arma_cruzando_campos_del_documento():
    """Los once dígitos aparecen en orden, pero repartidos entre un expediente y un
    año. Sin frontera y sin acotar los separadores, la «señal dura» del módulo se
    dispararía con cualquier documento suficientemente numérico."""
    assert not contiene_ruc("Expediente 205-056/55-215 del año 2016", RUC_SAN_CARLOS)


def test_el_ruc_no_cuenta_como_parte_de_un_numero_mas_largo():
    assert not contiene_ruc("Codigo 9205056552150", RUC_SAN_CARLOS)


def test_ruc_malformado_no_sirve_de_senal_pero_el_nombre_si(tmp_path):
    """Un RUC truncado no se usa como prueba; el veredicto lo decide el nombre."""
    v = verificar_certificado(_pdf(tmp_path, CERT_SAN_CARLOS), _exp(ruc_emisor="20505"))
    assert v.ok is True and v.senal == SENAL_NOMBRE


# ── Señal blanda: el nombre de la entidad, como frase contigua ──────────────

def test_nombre_confirma_el_folio_cuando_no_hay_ruc(tmp_path):
    v = verificar_certificado(_pdf(tmp_path, CERT_SAN_CARLOS), _exp(ruc_emisor=None))
    assert (v.ok, v.senal) == (True, SENAL_NOMBRE)
    assert v.encontrados == ("SAN", "CARLOS")


def test_nombre_partido_por_salto_de_linea(tmp_path):
    texto = ("SAN\nCARLOS CONTRATISTAS\nGENERALES SRL\n" + CERT_OTRO_EMISOR.split("\n", 1)[1])
    v = verificar_certificado(_pdf(tmp_path, texto), _exp(ruc_emisor=None))
    assert v.ok is True


def test_espacios_dentro_de_las_palabras_no_rompen_el_nombre():
    """OCR real: «S A N  C A R L O S  C O N T R A T I S T A S».

    El texto NO contiene ningún otro documento: el nombre tiene que salir del
    membrete espaciado y de ningún otro lado.
    """
    texto = ("S A N  C A R L O S  C O N T R A T I S T A S  G E N E R A L E S\n"
             "CERTIFICADO DE TRABAJO\n"
             "El que suscribe, Representante Legal, hace constar que el profesional\n"
             "se desempeño como Residente de Obra en la obra de saneamiento indicada.")
    v = verificar_texto(texto, EMISOR_SAN_CARLOS, None)
    assert (v.ok, v.senal) == (True, SENAL_NOMBRE)


def test_una_letra_mal_leida_por_el_ocr_no_dispara_alarma():
    """Caso real: el membrete de Moyobamba salió «MOVOBAMBA»."""
    texto = ("CONSORCIO SUPERVISOR HOSPITAL DE MOVOBAMBA\n"
             "CONSTANCIA DE PRESTACION DE SERVICIOS PROFESIONALES a favor del "
             "profesional que se desempeño como Jefe de Supervision en la obra "
             "Fortalecimiento de la Capacidad Resolutiva del establecimiento.")
    v = verificar_texto(texto, "CONSORCIO SUPERVISOR HOSPITAL DE MOYOBAMBA", None)
    assert v.ok is True and v.senal == SENAL_NOMBRE


def test_el_membrete_puede_omitir_la_forma_societaria():
    texto = ("SAN CARLOS CONTRATISTAS GENERALES\n"
             "CERTIFICADO DE TRABAJO. El que suscribe, Representante Legal, hace "
             "constar que el profesional se desempeño como Residente de Obra.")
    assert verificar_texto(texto, EMISOR_SAN_CARLOS, None).ok is True


# ── Lo que el módulo existe para atrapar ────────────────────────────────────

def test_documento_de_otro_emisor_es_sospechoso(tmp_path):
    """El caso real: el folio muestra un documento de otra entidad."""
    v = verificar_certificado(_pdf(tmp_path, CERT_OTRO_EMISOR), _exp(ruc_emisor=None))
    assert (v.ok, v.estado) == (False, ESTADO_SOSPECHOSO)
    assert v.sospechoso and "corrido" in v.motivo


def test_palabras_sueltas_compartidas_no_dan_por_bueno_el_folio():
    """LA prueba del módulo. La constancia de la «MUNICIPALIDAD DISTRITAL DE SAN
    JOSE» nombra al «Ing. Juan Carlos Mendoza Rojas»: contiene «SAN» y «CARLOS»,
    los dos términos identificatorios de «SAN CARLOS CONTRATISTAS GENERALES SRL»,
    pero sueltos y a media página de distancia. Buscar los términos por separado
    daba «coincide» sobre justo el folio corrido que este módulo persigue.
    """
    norm = normalizar(CERT_OTRO_EMISOR)
    assert "SAN" in norm.split() and "CARLOS" in norm.split(), \
        "el fixture debe contener ambos términos sueltos, o el test no prueba nada"
    v = verificar_texto(CERT_OTRO_EMISOR, EMISOR_SAN_CARLOS, None)
    assert v.ok is False and v.encontrados == ()


def test_un_termino_dentro_de_otra_palabra_no_acredita_nada():
    """«CONSORCIO SUPERVISOR LA UNION» se apoya en «UNION», que vive dentro de
    «reunión». Como frase, el nombre no aparece por ningún lado."""
    texto = ("MUNICIPALIDAD PROVINCIAL DE BAGUA\n"
             "Se deja constancia que, segun acta de reunion de fecha 12 de octubre, "
             "se aprobo la valorizacion presentada por el consorcio ejecutor de la obra.")
    assert verificar_texto(texto, "CONSORCIO SUPERVISOR LA UNION", None).ok is not True


def test_entidades_parecidas_no_se_confunden():
    """«Consorcio Supervisor Hospital Tarapoto» comparte 3 de 4 términos con el de
    Moyobamba: dar esto por bueno sería el falso CUMPLE que el módulo debe evitar."""
    v = verificar_texto(CERT_TARAPOTO, "CONSORCIO SUPERVISOR HOSPITAL DE MOYOBAMBA", None)
    assert v.ok is False and "MOYOBAMBA" in v.faltantes


def test_identidad_solo_generica_se_abstiene_en_vez_de_dar_por_bueno():
    """«S & S CONSULTORES Y CONTRATISTAS GENERALES» no deja nada propio. Un
    certificado de OTRA empresa que hable de «consultores y contratistas
    generales» satisface la frase sin ser la misma empresa: el veredicto correcto
    es abstenerse, no «coincide» — y tampoco «sospechoso»."""
    texto = ("JJ CONTRATISTAS GENERALES S.R.L.\n"
             "CONSTANCIA DE TRABAJO. La empresa, dedicada a servicios de consultores "
             "y contratistas generales, deja constancia de los servicios prestados "
             "por el profesional en la obra de la referencia.")
    v = verificar_texto(texto, "S & S CONSULTORES Y CONTRATISTAS GENERALES S.A.C.", None)
    assert (v.ok, v.estado) == (None, ESTADO_NO_VERIFICABLE)
    assert not v.sospechoso and "distintivo" in v.motivo


def test_identidad_de_un_solo_termino_corto_se_abstiene():
    """«CONSORCIO HOSPITAL DEL SUR» contra un certificado del «CONSORCIO HOSPITAL
    DEL SURCO»: la frase entra como subcadena y «SUR» vive dentro de «SURCO». Sin
    más señal que esa, ni el sí ni el no son de fiar."""
    texto = ("CONSORCIO HOSPITAL DEL SURCO\n"
             "CONSTANCIA DE PRESTACION DE SERVICIOS a favor del profesional que se "
             "desempeño como Jefe de Supervision durante la ejecucion de la obra.")
    v = verificar_texto(texto, "CONSORCIO HOSPITAL DEL SUR", None)
    assert v.ok is None and not v.sospechoso


def test_con_identidad_debil_el_ruc_ausente_no_es_alarma():
    """La entidad no deja término propio y el documento no imprime el RUC: un
    certificado válido puede perfectamente no llevarlo. Callarse es obligatorio."""
    v = verificar_texto(CERT_TARAPOTO, "Empresa Constructora S.A.C.", RUC_SAN_CARLOS)
    assert v.ok is None and "no se puede concluir" in v.motivo


def test_con_identidad_debil_el_ruc_presente_si_confirma(tmp_path):
    """La abstención por identidad genérica no debe tapar la señal dura."""
    v = verificar_texto(CERT_SAN_CARLOS, "Empresa Constructora S.A.C.", RUC_SAN_CARLOS)
    assert (v.ok, v.senal) == (True, SENAL_RUC)


# ── Abstención: ausencia de evidencia NO es alarma ──────────────────────────

def test_pdf_sin_capa_de_texto_no_es_verificable(tmp_path):
    v = verificar_certificado(_pdf_escaneado(tmp_path), _exp())
    assert (v.ok, v.estado) == (None, ESTADO_NO_VERIFICABLE)
    assert not v.sospechoso and "escaneada" in v.motivo


def test_el_sello_del_folio_no_cuenta_como_capa_de_texto(tmp_path):
    """Caso real: los recortes traen «358» estampado y nada más. Son dígitos: no
    acreditan nada, y tomarlos por texto convertiría la corrida en falsas alarmas."""
    v = verificar_certificado(_pdf_escaneado(tmp_path, sello="358"), _exp())
    assert v.ok is None and v.letras == 0


def test_membrete_suelto_tampoco_alcanza(tmp_path):
    """Pocas letras sueltas no permiten concluir que el emisor NO está."""
    v = verificar_certificado(_pdf(tmp_path, "CERTIFICADO"), _exp())
    assert v.ok is None


def test_experiencia_sin_emisor_ni_ruc_no_es_verificable(tmp_path):
    v = verificar_certificado(_pdf(tmp_path, CERT_SAN_CARLOS),
                              _exp(entidad_emisora=None, ruc_emisor=None))
    assert v.ok is None and "no declara" in v.motivo


def test_archivo_inexistente_no_es_verificable(tmp_path):
    v = verificar_certificado(tmp_path / "no_existe.pdf", _exp())
    assert (v.ok, v.estado) == (None, ESTADO_NO_VERIFICABLE)
    assert "No se encontró" in v.motivo


def test_archivo_vacio_o_corrupto_no_es_verificable(tmp_path):
    roto = tmp_path / "roto.pdf"
    roto.write_bytes(b"esto no es un PDF")
    assert verificar_certificado(roto, _exp()).ok is None
    vacio = tmp_path / "vacio.pdf"
    vacio.write_bytes(b"")
    assert extraer_paginas(vacio) is None


def test_recorte_sin_paginas_no_es_verificable():
    assert verificar_paginas([], EMISOR_SAN_CARLOS, RUC_SAN_CARLOS).ok is None


# ── Solo manda la página principal ──────────────────────────────────────────

def test_el_emisor_en_una_pagina_posterior_no_salva_el_folio(tmp_path):
    """Firma exacta del folio corrido: el recorte arranca con el documento
    equivocado y el certificado real viene detrás. Mirar la página 2 para dar por
    bueno el folio lavaría el error que se persigue."""
    ruta = _pdf(tmp_path, CERT_OTRO_EMISOR, CERT_SAN_CARLOS)
    v = verificar_certificado(ruta, _exp())
    assert v.ok is False and v.pagina_alterna == 2
    assert "página 2" in v.motivo


def test_pagina_principal_correcta_no_necesita_las_demas(tmp_path):
    ruta = _pdf(tmp_path, CERT_SAN_CARLOS, CERT_OTRO_EMISOR)
    assert verificar_certificado(ruta, _exp()).ok is True


# ── Recorrido del espejo completo ───────────────────────────────────────────

def test_revisar_certificados_recorre_el_espejo(tmp_path):
    _pdf(tmp_path, CERT_SAN_CARLOS, nombre="P1_E1.pdf")
    _pdf(tmp_path, CERT_OTRO_EMISOR, nombre="P1_E2.pdf")
    _pdf_escaneado(tmp_path, sello="360", nombre="P2_E1.pdf")
    espejo = {"profesionales": [
        {"n_prof": 1, "experiencias": [_exp(n=1), _exp(n=2, folio=359, ruc_emisor=None)]},
        {"n_prof": 2, "experiencias": [_exp(n=1, folio=360)]},
    ]}
    r = revisar_certificados(tmp_path, espejo)
    assert [v.ok for v in r] == [True, False, None]
    assert [(v.n_prof, v.n_exp) for v in r] == [(1, 1), (1, 2), (2, 1)]


def test_espejo_vacio_no_revienta():
    assert revisar_certificados("no/existe", {}) == []


def test_ruta_certificado():
    assert ruta_certificado("/x", 3, 12).name == "P3_E12.pdf"


# ── Contra los certificados reales (se saltan si no están en la máquina) ────

def _certs_reales(job: str) -> tuple[Path, dict]:
    carpeta = data_dir() / job / "certs"
    espejo = data_dir() / job / "espejo.json"
    if not carpeta.is_dir() or not espejo.is_file():
        pytest.skip(f"datos reales no disponibles en esta máquina: {carpeta}")
    return carpeta, json.loads(espejo.read_text(encoding="utf-8"))


def _experiencia_real(espejo: dict, n_prof: int, n_exp: int) -> dict:
    for prof in espejo.get("profesionales") or []:
        if prof.get("n_prof") != n_prof:
            continue
        for exp in prof.get("experiencias") or []:
            if exp.get("n") == n_exp:
                return exp
    pytest.skip(f"el espejo real no trae P{n_prof}_E{n_exp}")


def _pagina_principal_real(carpeta: Path, n_prof: int, n_exp: int) -> str:
    paginas = extraer_paginas(ruta_certificado(carpeta, n_prof, n_exp))
    if not paginas:
        pytest.skip(f"no se pudo leer P{n_prof}_E{n_exp}.pdf")
    return paginas[0]


def test_certs_reales_confirman_su_propio_emisor(capsys):
    """Job 36d710f27694 — los dos únicos recortes reales con capa de texto.

    P1_E1 (CONSORCIO SUPERVISOR HOSPITAL TARAPOTO) trae el RUC literal; P1_E2
    (CONSORCIO SUPERVISOR HOSPITAL DE MOYOBAMBA) no trae RUC y su membrete salió
    «MOVOBAMBA». Entre los dos ejercitan las dos señales sobre ruido real, y
    exigen un veredicto POSITIVO: un módulo que se abstuviera siempre falla aquí.
    """
    carpeta, espejo = _certs_reales("36d710f27694")
    r = revisar_certificados(carpeta, espejo)
    con_texto = [v for v in r if v.letras >= LETRAS_MINIMAS]
    with capsys.disabled():
        print(f"\n  36d710f27694 — {len(r)} experiencias, {len(con_texto)} con capa de texto")
        for v in con_texto:
            print(f"    P{v.n_prof}_E{v.n_exp} folio {v.folio}: {v.estado} ({v.senal})")
    if not con_texto:
        pytest.skip("esta copia de los datos no trae recortes con capa de texto")
    assert all(v.ok is True for v in con_texto), \
        "los recortes reales con texto son del emisor declarado: no deben salir sospechosos"
    assert {v.senal for v in con_texto} == {SENAL_RUC, SENAL_NOMBRE}


def test_certs_reales_cruzados_no_dan_por_bueno_el_folio(capsys):
    """La prueba real de discriminación, sobre texto real y emisores reales.

    Los dos certificados con texto del job 36d710f27694 son de consorcios
    hermanos que comparten el membrete «CONSORCIO SUPERVISOR HOSPITAL» y se
    distinguen solo por la ciudad — exactamente la confusión que produce un folio
    corrido. Cruzar cada texto con el emisor declarado del otro debe dar
    sospechoso: si saliera «coincide», el candado estaría blanqueando folios.
    """
    carpeta, espejo = _certs_reales("36d710f27694")
    a, b = _experiencia_real(espejo, 1, 1), _experiencia_real(espejo, 1, 2)
    texto_a = _pagina_principal_real(carpeta, 1, 1)
    texto_b = _pagina_principal_real(carpeta, 1, 2)
    if min(sum(c.isalpha() for c in texto_a), sum(c.isalpha() for c in texto_b)) < LETRAS_MINIMAS:
        pytest.skip("esta copia de los datos no trae recortes con capa de texto")

    cruces = [
        ("texto de E1 × emisor de E2", texto_a, b),
        ("texto de E2 × emisor de E1", texto_b, a),
    ]
    with capsys.disabled():
        print()
        for etiqueta, texto, exp in cruces:
            v = verificar_texto(texto, exp.get("entidad_emisora"), exp.get("ruc_emisor"))
            print(f"  {etiqueta}: {v.estado} faltantes={v.faltantes}")
    for etiqueta, texto, exp in cruces:
        v = verificar_texto(texto, exp.get("entidad_emisora"), exp.get("ruc_emisor"))
        assert v.ok is False, f"{etiqueta}: certificado ajeno dado por bueno ({v.estado})"


def test_certs_reales_de_la_corrida_del_folio_corrido(capsys):
    """Job 95af90f1578e — la corrida donde P1_E1 tiene el folio corrido en −1.

    Los 63 recortes son escaneos puros (la capa de texto trae, a lo sumo, el
    sello del folio), así que el módulo se abstiene en todos: NO hay una sola
    falsa alarma. El folio corrido de P1_E1 **no se puede atrapar sin OCR**: es
    una limitación de alcance declarada, no un fallo silencioso.

    Lo que sí se comprueba aquí es que la abstención viene de la falta de texto y
    no de una identidad inservible: el emisor declarado de P1_E1 SÍ es
    verificable, de modo que el día que los recortes lleguen con OCR el módulo
    emitirá veredicto en vez de callarse.
    """
    carpeta, espejo = _certs_reales("95af90f1578e")
    r = revisar_certificados(carpeta, espejo)
    conteo = {"ok": sum(v.ok is True for v in r),
              "sospechoso": sum(v.ok is False for v in r),
              "no_verificable": sum(v.ok is None for v in r)}
    with capsys.disabled():
        print(f"\n  95af90f1578e — {len(r)} experiencias: {conteo}")
    assert r, "el espejo real no trajo experiencias"
    assert conteo["sospechoso"] == 0, "falsas alarmas sobre recortes escaneados"

    p1e1 = _experiencia_real(espejo, 1, 1)
    assert identidad_verificable(p1e1.get("entidad_emisora")), \
        "el emisor del caso de referencia debe dar para juzgar cuando haya OCR"
    # Y con texto, ese mismo emisor declarado rechaza el documento equivocado: es
    # el veredicto que saldrá cuando el recorte del folio 358 traiga capa de texto.
    v = verificar_texto(CERT_OTRO_EMISOR, p1e1.get("entidad_emisora"), p1e1.get("ruc_emisor"))
    assert v.ok is False, "el documento del folio 358 debe salir sospechoso, no coincide"


def test_verificacion_es_inmutable():
    """El veredicto no se parchea en sitio: el integrador lo consume tal cual."""
    v = Verificacion(None, ESTADO_NO_VERIFICABLE, "x")
    with pytest.raises(Exception):
        v.ok = True
