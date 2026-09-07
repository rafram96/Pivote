"""Cronómetro de etapa: puro, con reloj inyectado."""
from orquestador.cronometro import Cronometro


class _Reloj:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def avanza(self, s):
        self.t += s


def test_fuente_dentro_de_experiencia_se_apunta_a_ambas():
    r = _Reloj()
    c = Cronometro(reloj=r)
    with c.experiencia("2:7"):
        with c.medir("mef"):
            r.avanza(100)
        with c.medir("resolucion"):
            r.avanza(5)
        r.avanza(1)
    assert c.tiempos_de("2:7") == {"total": 106.0, "mef": 100.0, "resolucion": 5.0}
    assert c.por_fuente == {"mef": [100.0, 1], "resolucion": [5.0, 1]}
    assert c.actual is None


def test_fuente_fuera_de_experiencia_solo_cuenta_en_la_fuente():
    r = _Reloj()
    c = Cronometro(reloj=r)
    with c.medir("seace"):
        r.avanza(7)
    assert c.por_fuente == {"seace": [7.0, 1]}
    assert c.por_experiencia == {}


def test_fases_y_resumen_legible():
    r = _Reloj()
    c = Cronometro(reloj=r)
    with c.fase("candidatos"):
        r.avanza(180)
    with c.fase("bucle"):
        with c.experiencia("1:3"):
            with c.medir("infoobras"):
                r.avanza(1740)
        with c.experiencia("4:2"):
            r.avanza(0.4)                    # < 1 s: no aparece entre las lentas
    resumen = c.resumen()
    assert "fases: candidatos 3.0 min · bucle 29.0 min" in resumen
    assert "fuentes: infoobras 29.0 min (1 llamadas)" in resumen
    assert "experiencias más lentas: P1 E3 29.0 min" in resumen
    assert "P4 E2" not in resumen
    assert c.linea_experiencia("1:3") == "P1 E3: 29.0 min (infoobras 29.0 min)"


def test_sin_mediciones():
    assert Cronometro().resumen() == "sin mediciones"
    assert Cronometro().tiempos_de("9:9") == {}
