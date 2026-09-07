"""Log a archivo del backend (infraestructura.registro)."""
import logging

from infraestructura.registro import _MARCA, configurar_registro


def _quitar_handlers_propios():
    raiz = logging.getLogger()
    for h in list(raiz.handlers):
        if getattr(h, _MARCA, False):
            raiz.removeHandler(h)
            h.close()


def test_escribe_info_en_archivo_y_es_idempotente(tmp_path):
    _quitar_handlers_propios()
    try:
        ruta = configurar_registro(tmp_path, nivel="INFO")
        assert ruta == tmp_path / "logs" / "backend.log"
        logging.getLogger("orquestador.prueba").info("infoobras tiempos P2 E7: 1.0 s")
        for h in logging.getLogger().handlers:
            h.flush()
        assert "infoobras tiempos P2 E7" in ruta.read_text(encoding="utf-8")
        # segunda llamada: no duplica handlers
        antes = len(logging.getLogger().handlers)
        assert configurar_registro(tmp_path) == ruta
        assert len(logging.getLogger().handlers) == antes
    finally:
        _quitar_handlers_propios()
