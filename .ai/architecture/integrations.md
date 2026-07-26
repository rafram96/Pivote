# Integraciones externas (todas estatales, Perú)

| Fuente | Uso | Acceso | Estado |
|---|---|---|---|
| **MEF Datos Abiertos** | base local de CUIs (452,793) + catálogo de entidades | 3 CSV en `fs.datosabiertos.mef.gob.pe/datastorefiles/` (DETALLE_INVERSIONES solo ACTIVAS; unir con CIERRE y DESACTIVADAS), refresco semanal del MEF | ✔ producción (ETL propio) |
| **MEF Invierte.pe** (08-A, contratos DWH) | verificación de expedientes: resolución de aprobación del ET + contrato SEACE vía `traeContratoSeaceDWH`; descarga de PDFs | requests con sesión, SIN captcha | ✔ producción (T-003) |
| **MEF SSI** (`busInvNombreSSI`) | búsqueda por nombre en vivo | POST sin captcha; matchea por substring; portal intermitente | opcional (la base local lo reemplazó como camino crítico) |
| **InfoObras (Contraloría)** | obras, valorizaciones (`lAvances`), paralizaciones, documentos, representantes | requests sin login; **portal flaky** → reintentos con backoff y distinción "caído ≠ vacío" (`PortalNoResponde`) | ✔ producción |
| **SUNAT** | antigüedad del emisor (ALT-04); representantes legales e información histórica del emisor —condición HABIDO en el tiempo— (informativos, sin regla automática) | scraping con reintentos, sin captcha real: `consPorRuc` + `getRepLeg` + `getinfHis` encadenadas; una consulta por RUC por job. OJO: `getinfHis` declara ISO-8859-1 y manda UTF-8 | ✔ producción |
| **SEACE buscador** | bases integradas + contrato firmado | ⛔ reCAPTCHA v3 → NO-GO por requests puro | fallback navegador (T-004) |
| **CONOSCE / API OCDS (OECE)** | vía alterna sin captcha a bases/contrato/fechas por CUI (`records?projectID=`); cobertura medida 86% (2018+) | datasets Excel anuales + API JSON | sonda ✔ GO (`tools/conosce.py`, `tools/ocds.py`); integración = T-004 |
| **RENIPRESS (SUSALUD)** | ¿existe el establecimiento de salud? (privadas de salud) | WS DataTables sin captcha; combos con default "0" (vacío = 0 filas silencioso) | sonda ✔ GO; integración = T-006 |

Regla transversal: **nunca inventar** un CUI/documento/número; lo no publicado
se declara pendiente y cae a «Por confirmar».
