# Integraciones externas (todas estatales, Perú)

La investigación de identidad dispone de `preparar_investigacion_identidad` por
MCP (GET del contexto del job), junto con lectura de candidatos y fichas. No
descarga ni promueve selecciones. El cliente ejecuta la investigación, si tiene
modelo/presupuesto y herramientas disponibles; Chrome es opcional. Protocolo:
`skill/references/investigacion-identidad.md`. No requiere modificar el espejo.

Aplicación posterior explícita: `aplicar_investigacion_identidad` llama POST
`/jobs/{job_id}/investigacion-identidad/aplicar`. Backend relee ficha/proceso exactos,
no ranking; respalda corpus anterior y activa descargador existente. Huella obsoleta
o fuente no comprobada rechazan el lote. Luego relee la ficha exacta, recalcula
contraste/cálculos y publica Excel/ZIP; ambos bloqueados hasta terminar. Reconsulta
SUNAT por emisor y MEF en expedientes; contrato MEF solo por número/proceso exactos.
Documentos 08-A candidatos, no aprobación acreditada por etiqueta. No se activa el
descargador MEF genérico, que volvería a elegir contrato; contrato exacto vía SEACE.
No hereda cruces anteriores. Fallo de
publicación mantiene diario y bloqueo. No se han aplicado cambios a jobs históricos.

| Fuente | Uso | Acceso | Estado |
|---|---|---|---|
| **MEF Datos Abiertos** | base local de CUIs (452,793) + catálogo de entidades | 3 CSV en `fs.datosabiertos.mef.gob.pe/datastorefiles/` (DETALLE_INVERSIONES solo ACTIVAS; unir con CIERRE y DESACTIVADAS), refresco semanal del MEF | ✔ producción (ETL propio) |
| **MEF Invierte.pe** (08-A, contratos DWH) | verificación de expedientes: resolución de aprobación del ET + contrato SEACE vía `traeContratoSeaceDWH`; descarga de PDFs | requests con sesión, SIN captcha | ✔ producción (T-003) |
| **MEF SSI** (`busInvNombreSSI`) | búsqueda por nombre en vivo | POST sin captcha; matchea por substring; portal intermitente | opcional (la base local lo reemplazó como camino crítico) |
| **InfoObras (Contraloría)** | obras, valorizaciones (`lAvances`), paralizaciones, documentos, representantes | requests sin login; **portal flaky** → reintentos con backoff y distinción "caído ≠ vacío" (`PortalNoResponde`). Documentos: caché mutable por job y `obra_id`; corpus completo una vez, informes filtrados localmente al materializar cada experiencia | ✔ producción |
| **SUNAT** | antigüedad del emisor (ALT-04); representantes legales e información histórica del emisor —condición HABIDO en el tiempo— (informativos, sin regla automática) | scraping con reintentos, sin captcha real: `consPorRuc` + `getRepLeg` + `getinfHis` encadenadas; una consulta por RUC por job. OJO: `getinfHis` declara ISO-8859-1 y manda UTF-8 | ✔ producción |
| **SEACE buscador** | bases integradas + contrato firmado | ⛔ reCAPTCHA v3 → NO-GO por requests puro | fallback navegador (T-004) |
| **CONOSCE / API OCDS (OECE)** | vía alterna sin captcha a bases/contrato/fechas por CUI (`records?projectID=`); cobertura medida 86% (2018+) | datasets Excel anuales + API JSON | sonda ✔ GO (`tools/conosce.py`, `tools/ocds.py`); integración = T-004 |
| **RENIPRESS (SUSALUD)** | evidencia auxiliar de existencia para toda experiencia de salud, pública o privada | Cliente en `scraping/renipress.py` sobre WS DataTables sin captcha; contrato explícito `encontrado / sin_resultados / portal_no_disponible`; API `GET /api/pivote/renipress`; etapa paralela del orquestador | ✔ integrado al pipeline; todavía sin regla automática de matching/veredicto |

Regla transversal: **nunca inventar** un CUI/documento/número; lo no publicado
se declara pendiente y cae a «Por confirmar».

## Lectura de identidad InfoObras (código local, 10-sep)

`scraping/consulta_infoobras.py` añade lectura con estados de fuente a través
de dos GET `/api/pivote/infoobras/candidatos` y `/api/pivote/infoobras/ficha`.
El MCP expone `listar_fichas_infoobras` y `consultar_ficha_infoobras`; no lanza
jobs ni baja PDFs, y exige `obra_id` explícito para leer ficha. Reutiliza
búsqueda por código, limita texto por sección y declara que la lista del portal
no está certificada como completa. Un fallo HTTP/formato/transporte no es
ausencia. Títulos internos con otro ID no se aceptan como ficha solicitada.
Datos fuente, fechas y enlaces quedan sin dictamen ni clasificación documental.
Backend/MCP necesitan reinicio/reentrega para usar estas adiciones; no se hizo.

En el fetch del pipeline, una ficha explícita ya no se reemplaza por una con
mejor solape temporal. Sin ID explícito sigue la selección histórica: pendiente
de separar alternativas de identidad en el orquestador y los entregables.
SEACE: `goods` no se clasifica como obra por el texto del proyecto; la señal
temporal se conserva débil y visible, sin confirmar/vetar identidad por sí sola.
La consulta sin procesos no se atribuye automáticamente a cobertura desde 2018.
