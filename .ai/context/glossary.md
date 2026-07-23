# Glosario

| Término | Significado |
|---|---|
| **CUI** | Código Único de Inversiones (7 díg.) del Banco de Inversiones del MEF; identifica un proyecto público. Predecesor: **SNIP** (5-6 díg.). |
| **Espejo** | JSON consolidado que produce la skill (profesionales, experiencias, factores) — contrato skill↔backend (Pydantic↔zod v1.2.0, `tools/test_contrato.py`). |
| **Experiencia** | Un periodo de trabajo de un profesional acreditado por un certificado (1 fila = 1 periodo, atómico). |
| **Camino A / B** | Trato por tipo: A = expediente/estudio (verificación MEF); B = obra (valorizaciones InfoObras). |
| **Valorizaciones** | Avances mensuales pagados de una obra en InfoObras — la evidencia de CUÁNDO la obra se ejecutó de verdad. Solo VEREDICTO, jamás selección. |
| **Clamp / Paso 5** | Recorte de los días declarados a la ventana real de valorizaciones; días fuera no cuentan. |
| **«Por confirmar»** | Cola de revisión humana en el panel (ItemRevision) — terminología visible al evaluador, sin jerga. |
| **Golden** | Auditoría de regresión del resolver: casos reales con verdad auditada (`golden_cui_baseline.json` + caché de respuestas para re-corridas offline). Conteo actual: ver `architecture/backend.md` (fuente única). |
| **T-00x** | Componentes del paquete de extras (T-003 MEF expedientes ✔, T-004 SEACE, T-005 fechas ET, T-006 RENIPRESS, T-007 SUNAT habido, T-008 refactor CUI ✔). |
| **ALT-xx** | Alertas del motor de reglas (ej. ALT-04 = emisor más joven que la experiencia). ALT-12 (firmante=rep. legal) DESCARTADA. |
| **Formato 08-A** | Ficha MEF de la fase de ejecución; su sección B trae la resolución de aprobación del expediente técnico. |
| **RTM** | Requisitos Técnicos Mínimos de las bases del concurso. |
| **Factor A** | Puntaje por experiencia adicional de ciertos cargos (bases). |
| **Bases integradas** | Versión final de las bases del proceso (SEACE); el tachado (w:strike) marca requisitos ELIMINADOS. |
| **Cowork** | Entorno Linux de Claude donde corre la skill del cliente (como plugin). |
| **Concurso de referencia** | CP-02-2025 GOB.REG.HVCA "Lircay" — origen del formato Excel congelado. |
