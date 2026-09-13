"""El motivo de revisión de la vía MEF no debe afirmar que «hay un proyecto con
ese nombre» cuando la ficha más parecida quedó lejos del nombre del certificado
(auditoría 12-sep: un expediente interno sin registro en el Banco recibía como
motivo que el MEF sí lo registraba, con una ficha de otro establecimiento).
Datos sintéticos."""
from resolucion import cui as _cui


def _best(mef_score, nombre="MEJORAMIENTO DEL HOSPITAL DE APOYO SAN JACINTO", score=50.0):
    return {"cui": "2999001", "mef_score": mef_score, "nombre_obra": nombre,
            "score": score, "solo_ficha": True, "origen": "mef"}


def _exp():
    return {"proyecto": "Ampliación del área de hospitalización del Hospital I San Fermín - Ancón",
            "ubicacion": "Ancón"}


def _via(best):
    return _cui._via_mef_expediente(_exp(), best, [best], [dict(best)], None, False)


def test_parecido_bajo_dice_que_no_se_encontro():
    r = _via(_best(mef_score=40.0))
    assert r["estado"] == "revision" and r["cui"] is None
    assert r["decision"].startswith("no se encontró en el Banco de Inversiones del MEF")
    assert "hay un proyecto con ese nombre" not in r["decision"]
    assert "2999001" in r["decision"]


def test_sin_mef_score_cuenta_como_parecido_bajo():
    r = _via(_best(mef_score=None))
    assert r["decision"].startswith("no se encontró en el Banco de Inversiones del MEF")


def test_parecido_alto_pero_insuficiente_conserva_el_motivo_clasico():
    r = _via(_best(mef_score=90.0, score=90.0))
    assert r["estado"] == "revision"
    assert r["decision"].startswith("hay un proyecto con ese nombre en el Banco de Inversiones del MEF")
    assert "no coincide lo suficiente" in r["decision"]
