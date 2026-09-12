"""Exportaciones compatibles; los generadores se cargan solo al solicitarlos.

Importar una clasificación o un cálculo no debe cargar openpyxl, scrapers ni
la etapa de orquestación. Los nombres públicos anteriores se conservan.
"""
from importlib import import_module

__all__ = ["generar_excel_final", "desempaquetar_enriquecimiento",
           "completar_revisiones_privadas",
           "regenerar_excel_final", "reconciliar_resultados_profesionales",
           "inyectar_veredicto_backend",
           "mapear_certificados", "construir_zip_infoobras",
           "descargar_documentos_obra", "inventariar", "descargar_cui", "_zip_carpeta"]

_MODULOS = {
    **dict.fromkeys(("generar_excel_final", "desempaquetar_enriquecimiento",
                     "completar_revisiones_privadas", "regenerar_excel_final",
                     "mapear_certificados"), "entregables.excel_final"),
    **dict.fromkeys(("reconciliar_resultados_profesionales", "inyectar_veredicto_backend"),
                   "reglas.resultados_profesionales"),
    **dict.fromkeys(("construir_zip_infoobras", "descargar_documentos_obra",
                     "inventariar", "descargar_cui", "_zip_carpeta"),
                   "entregables.zip_infoobras"),
}


def __getattr__(nombre):
    modulo = _MODULOS.get(nombre)
    if modulo is None:
        raise AttributeError(f"El módulo {__name__!r} no tiene el atributo {nombre!r}")
    valor = getattr(import_module(modulo), nombre)
    globals()[nombre] = valor
    return valor


def __dir__():
    return sorted(set(globals()) | set(__all__))
