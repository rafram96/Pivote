"""observabilidad/traza.py — el tracer JSONL y su integración con el resolver."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from observabilidad import traza as tz  # noqa: E402


def _leer(p: Path) -> list[dict]:
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def test_eventos_y_spans_basicos(tmp_path):
    t = tz.Traza(tmp_path / "t.jsonl", trace_id="job-1")
    token = tz.usar(t)
    try:
        t.ev("hola", n=1)
        with t.span("etapa_a", clave="1:1"):
            t.ev("adentro", x="y")
            with t.span("sub"):
                pass
    finally:
        tz.restaurar(token)
    evs = _leer(tmp_path / "t.jsonl")
    por_ev = {e["ev"]: e for e in evs}
    assert por_ev["hola"]["trace"] == "job-1" and por_ev["hola"]["n"] == 1
    assert por_ev["adentro"]["en"] == "etapa_a"          # jerarquía por contexto
    spans = [e for e in evs if e["ev"] == "span"]
    assert {s["span"] for s in spans} == {"etapa_a", "etapa_a/sub"}
    assert all(isinstance(s["ms"], (int, float)) for s in spans)


def test_error_se_registra_y_relanza(tmp_path):
    t = tz.Traza(tmp_path / "t.jsonl")
    try:
        with t.span("boom"):
            raise ValueError("kaput")
    except ValueError:
        pass
    else:
        raise AssertionError("el span no debe tragar excepciones")
    e = _leer(tmp_path / "t.jsonl")[0]
    assert e["ev"] == "error" and "kaput" in e["error"] and e["span"] == "boom"


def test_sin_tracer_activo_es_noop():
    # instrumentación sin tracer: no lanza, no escribe nada
    tr = tz.actual()
    tr.ev("nada", x=1)
    with tr.span("nada"):
        pass


def test_resolver_emite_traza(tmp_path):
    """El resolver deja su historia: span + decision (+ veto en el caso golden)."""
    from resolucion.cui import resolver
    from test_resolucion_rubro import EXP_CHINCHINGA, ConsultaCongelada

    t = tz.Traza(tmp_path / "t.jsonl", trace_id="golden")
    token = tz.usar(t)
    try:
        resolver(EXP_CHINCHINGA, ConsultaCongelada())
    finally:
        tz.restaurar(token)
    evs = _leer(tmp_path / "t.jsonl")
    tipos = {e["ev"] for e in evs}
    assert {"span", "decision", "busqueda", "ranking", "veto_rubro"} <= tipos
    dec = next(e for e in evs if e["ev"] == "decision")
    # con la deportiva vetada, la obra correcta (2376130) puede ganar el ranking;
    # el contrato es: JAMÁS la deportiva — correcta o revisión (ver golden test)
    assert dec["en"] == "resolver_cui"
    assert dec.get("cui") != "2468642"
    assert dec["estado"] in ("resuelto", "revision")
    vetos = [e for e in evs if e["ev"] == "veto_rubro"]
    assert "2468642" in {v["cui"] for v in vetos}          # la losa deportiva
    # todo veto es una contradicción positiva contra el rubro del certificado
    assert all(v["rubro_cert"] == ["salud"] and v["rubro_obra"]
               and "salud" not in v["rubro_obra"] for v in vetos)
