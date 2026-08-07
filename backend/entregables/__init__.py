"""Entregables del backend: Excel final enriquecido + ZIP de InfoObras."""
from .excel_final import (
    completar_revisiones_privadas, desempaquetar_enriquecimiento,
    generar_excel_final, mapear_certificados, reconciliar_resultados_profesionales,
    regenerar_excel_final, inyectar_veredicto_backend,
)
from .zip_infoobras import (
    construir_zip_infoobras, descargar_cui, descargar_documentos_obra, inventariar,
    _zip_carpeta,
)

__all__ = ["generar_excel_final", "desempaquetar_enriquecimiento",
           "completar_revisiones_privadas",
           "regenerar_excel_final", "reconciliar_resultados_profesionales",
           "inyectar_veredicto_backend",
           "mapear_certificados", "construir_zip_infoobras",
           "descargar_documentos_obra", "inventariar", "descargar_cui", "_zip_carpeta"]
