"""Pruebas offline de la colección documental prioritaria de SEACE."""

from scraping.seace_abierto import documentos_prioritarios


def _documento(identificador, titulo, tipo, url="https://ejemplo.test/doc", formato="pdf"):
    return {"id": identificador, "title": titulo, "documentType": tipo,
            "url": url, "format": formato}


def _componente():
    return {
        "ocid": "ocds-dgv273-seacev3-99",
        "tender": {"documents": [
            _documento("b1", "Bases Integradas - tomo 1", "biddingDocuments", "u-b1"),
            _documento("b2", "Bases integradas - tomo 2", "biddingDocuments", "u-b2"),
            _documento("ba", "Bases Administrativas", "biddingDocuments", "u-ba"),
        ]},
        "contracts": [
            {"id": "c-1", "documents": [
                _documento("f1", "Contrato", "contractSigned", "u-f1"),
                _documento("f2", "Contrato firmado copia", "contractSigned", "u-f2"),
                _documento("a1", "Anexo", "contractAnnexe", "u-a1"),
                _documento("x1", "Otro", "contractNotice", "u-x1"),
            ]},
            {"id": "c-2", "documents": [
                _documento("f3", "Contrato", "contractSigned", "u-f3"),
                _documento("a2", "Anexo", "contractAnnexe", "u-a2"),
            ]},
        ],
    }


def test_colecciona_todas_las_bases_y_adjuntos_prioritarios_en_orden():
    registros = documentos_prioritarios(_componente())
    assert [(r["categoria"], r["id_documento"], r["id_contrato"])
            for r in registros] == [
                ("bases", "b1", None), ("bases", "b2", None),
                ("contrato", "f1", "c-1"), ("contrato", "f2", "c-1"),
                ("contrato", "a1", "c-1"), ("contrato", "f3", "c-2"),
                ("contrato", "a2", "c-2"),
            ]


def test_filtro_explicito_es_exacto_y_sin_fallback():
    assert {r["id_contrato"] for r in documentos_prioritarios(_componente(), "c-2")} == {None, "c-2"}
    assert documentos_prioritarios(_componente(), "no-existe") == [
        r for r in documentos_prioritarios(_componente()) if r["categoria"] == "bases"
    ]


def test_deduplica_solo_identidad_completa_y_preserva_sin_url():
    comp = _componente()
    docs = comp["contracts"][0]["documents"]
    docs.extend([
        _documento("f1", "Duplicado", "contractSigned", "u-f1"),
        _documento("f1", "Mismo ID otra URL", "contractSigned", "u-f1-otra"),
        _documento("f-sin-url", "Contrato sin enlace", "contractSigned", None),
        _documento("f-sin-url", "Contrato sin enlace repetido", "contractSigned", None),
    ])
    registros = documentos_prioritarios(comp)
    ids = [(r["id_contrato"], r["id_documento"], r["url"]) for r in registros]
    assert ids.count(("c-1", "f1", "u-f1")) == 1
    assert ("c-1", "f1", "u-f1-otra") in ids
    assert ids.count(("c-1", "f-sin-url", None)) == 1


def test_no_muta_la_entrada_y_conserva_forma_exacta():
    comp = _componente()
    original = repr(comp)
    registro = documentos_prioritarios(comp)[0]
    assert repr(comp) == original
    assert set(registro) == {"categoria", "id_documento", "id_contrato", "ocid",
                             "url", "titulo", "formato", "tipo_publicado",
                             "rol_documental", "correspondencia"}


def test_registros_sin_identidad_ni_enlace_no_se_colapsan():
    comp = {"contracts": [{"id": "c1", "documents": [
        _documento(None, "Contrato", "contractSigned", None),
        _documento(None, "Anexo", "contractAnnexe", None),
    ]}]}
    registros = documentos_prioritarios(comp)
    assert len(registros) == 2
    assert all(d["url"] is None and d["id_documento"] is None for d in registros)
