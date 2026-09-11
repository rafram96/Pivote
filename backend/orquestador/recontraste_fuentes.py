"""Lecturas nuevas MEF/SUNAT sin sustituir el contrato de la investigación."""
from copy import deepcopy

from orquestador.etapas import Contexto
from orquestador.etapas_reales import EtapaSunatReal
from schemas.pipeline import Job
from scraping import mef, sunat


class FuentesRecontraste:
    """Caché por lote de datos crudos; los cruces se calculan por certificado."""

    def __init__(self, *, ficha=None, contratos=None, empresa=None, buscar=None, extras=None):
        self.ficha = ficha or mef.fetch_ficha_08a
        self.contratos = contratos or mef._fetch_contratos_crudo
        self.empresa = empresa or sunat.consultar_ruc
        self.buscar = buscar or sunat.buscar_por_razon_social
        self.extras = extras or (lambda r: (sunat.consultar_representantes(r), sunat.consultar_historico(r)))
        self.cache = {}

    def leer(self, tipo, clave, funcion):
        llave = (tipo, clave)
        if llave not in self.cache:
            try:
                self.cache[llave] = (funcion(clave), None)
            except Exception as exc:
                self.cache[llave] = (None, type(exc).__name__)
        return self.cache[llave]

    def contrastar_mef(self, cert, cui, seace):
        html, error_ficha = self.leer("mef_ficha", cui, self.ficha)
        crudo, error_contratos = self.leer("mef_contratos", cui, self.contratos)
        ficha = mef.parsear_ficha_08a(html) if isinstance(html, str) else {}
        try:
            contratos = mef.normalizar_contratos(crudo) if isinstance(crudo, list) else []
        except (TypeError, AttributeError, ValueError):
            contratos, crudo, error_contratos = [], None, "respuesta_invalida"
        origen = seace.get("proceso_fuente") or {}
        seleccionados = origen.get("contracts") or []
        exactos = []
        if len(seleccionados) == 1:
            seleccionado = seleccionados[0]
            numeros = {str(seleccionado.get(k) or "").strip().casefold() for k in ("id", "title")} - {""}
            nomen = str((seace.get("proceso") or {}).get("nomenclatura") or "").strip().casefold()
            exactos = [c for c in contratos if c["numero"].strip().casefold() in numeros
                       and nomen and c["nomenclatura"].strip().casefold() == nomen]
        # El verificador tradicional elige por emisor/precio. Al recibir SOLO el
        # contrato exacto no puede cambiar la selección. El rótulo 08-A es candidato,
        # no resolución comprobada de este encargo: no se lo damos como aprobación.
        exactos = exactos if len(exactos) == 1 else []
        bloque = mef.verificar_expediente({**cert, "cui": cui}, {}, exactos)
        bloque.pop("cui_confirmado", None)
        # No activar el descargador MEF genérico, que vuelve a elegir por precio.
        # El contrato seleccionado ya se descarga por la vía SEACE exacta.
        bloque["cui_consultado"] = cui
        bloque["estado"] = "recontrastado"
        bloque["aprobacion_identificada"] = False
        bloque["documentos_08a"] = ficha.get("documentos") or []
        bloque["contratos_consultados"] = [
            {**c, "fecha_suscripcion": c["fecha_suscripcion"].isoformat() if c["fecha_suscripcion"] else None}
            for c in contratos]
        bloque["resolucion"] = {"veredicto": "no_verificable", "detalle":
            "Aprobación de este encargo por identificar entre los documentos del 08-A; una etiqueta no la demuestra."}
        motivos = [bloque["resolucion"]["detalle"]]
        if not exactos:
            motivos.append("MEF no permitió vincular un único contrato al número y proceso seleccionados; no se eligió otro.")
        estados = {"ficha": "disponible" if ficha.get("tiene_ficha") else "no_disponible",
                   "contratos": "disponible" if isinstance(crudo, list) else "no_disponible"}
        if estados["ficha"] != "disponible" or estados["contratos"] != "disponible":
            motivos.append("La lectura MEF fue incompleta; no prueba inexistencia del expediente o de sus documentos.")
        bloque["detalle"] = bloque["motivo"] = " ".join(motivos)
        return bloque, {"estado": "disponible" if all(v == "disponible" for v in estados.values()) else "parcial",
                        "recursos": estados, "errores": [e for e in (error_ficha, error_contratos) if e]}, motivos

    def contrastar_sunat(self, cert, unidad, espejo):
        estados = {}

        def consultar(ruc):
            emp, error = self.leer("sunat", ruc, self.empresa)
            valido = emp is not None and str(emp.ruc) == str(ruc)
            estados["ruc"] = "disponible" if valido else "no_disponible"
            if error:
                estados["error"] = error
            return emp if valido else None

        def buscar(nombre):
            filas, error = self.leer("sunat_busqueda", nombre, self.buscar)
            estados["busqueda"] = "disponible" if isinstance(filas, list) else "no_disponible"
            if error:
                estados["error"] = error
            return filas if isinstance(filas, list) else []

        def extras(ruc):
            valor, error = self.leer("sunat_extras", ruc, self.extras)
            estados["historico"] = "disponible" if valor and valor[1] is not None else "no_disponible"
            if error:
                estados["error_extras"] = error
            return valor or ([], None)

        mini = deepcopy(espejo)
        mini["profesionales"] = [{"n_prof": 1, "experiencias": [{**cert, "n": 1}]}]
        ctx = Contexto(Job(job_id="recontraste", analisis_id="recontraste"), mini,
                       enriquecimiento={"1:1": deepcopy(unidad)})
        resultado = EtapaSunatReal(consultor=consultar, buscador=buscar, extras=extras).correr(ctx)
        bloque = ctx.enriquecimiento["1:1"].get("sunat") or {}
        if estados.get("busqueda") == "no_disponible":
            bloque.pop("no_encontrado", None)
        motivos = []
        if not bloque.get("ruc"):
            motivos.append("No se obtuvo una ficha SUNAT del emisor inequívocamente identificado; no prueba que la empresa no exista.")
        if estados.get("historico") != "disponible":
            motivos.append("Sin histórico SUNAT utilizable para contrastar el periodo; estado actual no demuestra estado pasado.")
        bloque["observaciones_recontraste"] = [o.model_dump(mode="json") for o in resultado.observaciones]
        bloque["estado_consulta"] = "disponible" if bloque.get("ruc") else "no_disponible"
        return bloque, {"estado": bloque["estado_consulta"], "recursos": estados}, motivos
