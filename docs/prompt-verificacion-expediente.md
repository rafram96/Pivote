# Prompt — Verificación de experiencia de EXPEDIENTE técnico (SEACE + MEF)

> Uso MANUAL (cortesía; la versión automática/integrada es el módulo T-003, se
> cotiza aparte — ver `docs/comercial/cotizacion-verificacion-expedientes.html`).
> Se pega en un Claude con navegador (Claude Code + Chrome, o Claude-en-Chrome)
> junto con la constancia/certificado (imagen o datos). Basado en la receta que
> definió el propio ingeniero (11-jul) + blindaje anti-alucinación.
>
> Desvío anti-captcha: los DATOS se consultan por el **SSI del MEF** (no pide
> código de verificación); la Consulta Pública (que sí pide captcha) solo se usa
> si hace falta el PDF del Formato 08-A — única pausa permitida.

---

Te doy la constancia/certificado de una experiencia de EXPEDIENTE TÉCNICO (imagen o
texto). Verifícala contra SEACE y el MEF, descarga los documentos y dame un reporte
de contraste.

REGLA DE ORO: no me hagas NINGUNA pregunta durante todo el proceso, con UNA sola
excepción: si un portal pide un código de verificación (captcha), detente ahí, dime
"escribe el código y avísame", y continúa cuando te confirme. Todo lo demás lo
decides tú. Si un dato no aparece, no preguntes: anótalo como "no verificable en
línea" y sigue con el resto.

PASO 1 — SEACE (por nombre y fecha):
https://prod2.seace.gob.pe/seacebus-uiwd-pub/buscadorPublico/buscadorPublico.xhtml
Busca el proceso por el NOMBRE del proyecto y el AÑO del contrato. Abre la
convocatoria y DESCARGA: las Bases Integradas y el Contrato. Del listado de
contratos anota: contratista (puede ser empresa o persona natural), número de
contrato, monto y fechas.

PASO 2 — MEF, datos del proyecto (ruta SIN captcha):
Busca el proyecto en el SSI del MEF (Sistema de Seguimiento de Inversiones —
ssi.mef.gob.pe; expone los mismos datos del Banco de Inversiones sin código de
verificación). Si el certificado no trae CUI, encuéntralo ahí buscando por el
nombre del proyecto. Anota: CUI, nombre oficial, estado (ACTIVO/CERRADO),
situación (VIABLE), monto, unidad ejecutora, y las contrataciones registradas.

PASO 3 — MEF, resolución de aprobación del expediente (puede pedir captcha):
Solo si necesitas el PDF: entra a la Consulta Pública de Inversiones
(https://ofi5.mef.gob.pe/invierte/consultapublica/consultainversiones), busca el
CUI, click en el número → "REGISTROS EN LA FASE DE INVERSIÓN" → abre el PDF de la
fila bajo "ver" (Formato N°08-A) → baja hasta "B. Datos de la fase de Ejecución:
Expediente técnico o documento equivalente" y DESCARGA el PDF de la columna ET/DE
(la resolución de aprobación del expediente). Si aquí sale el captcha, es la única
pausa permitida.

PASO 4 — CONTRASTE con el certificado. Compara y repórtame en una tabla:
- Contratista (¿es quien emite/respalda el certificado?)
- Número de contrato, monto y fechas
- Resolución de aprobación del expediente (número y fecha)
- CUI y nombre oficial del proyecto
Marca cada fila: ✅ coincide / ⚠️ no verificable en línea / ❌ discrepancia.

REGLAS DE EVIDENCIA: solo reporta datos que VISTE en pantalla en esta sesión —
nunca de memoria ni deducidos. Cada dato con su fuente (SEACE o MEF/SSI). Si el
CUI citado en el certificado lleva a un proyecto viejo que no cuadra con las
fechas, busca el proyecto reformulado por nombre (los proyectos se re-registran
con CUI nuevo) y repórtalo como "CUI citado X → vigente Y". Las diferencias
menores (p.ej. valor referencial vs monto adjudicado) señálalas como esperables,
no como inconsistencias.

ARCHIVOS: guarda todo en una carpeta con el nombre del caso, numerado:
01_Bases_Integradas_..., 02_Contrato_..., 03_Resolucion_Aprobacion_..., y al
final lista qué descargaste y qué no se pudo.
