---
name: analizar-licitacion-osce
description: 'Evalúa una propuesta técnica de un concurso OSCE (supervisión/consultoría de obra) leyendo bases.pdf + propuesta.pdf. Orquesta subagentes — agent-bases (requisitos/factores/personal clave + límite inferior), agent-propuesta-mapa (datos a nivel postor + bundle de folios por profesional), un agent-propuesta-profesional POR profesional (extracción profunda de su bundle, 1 fila/periodo), y agent-evaluador (cruza requisitos × experiencia y evalúa cumplimiento con razones literales) — y emite DOS artefactos: el Excel "Formato de Evaluación" (5 partes) y un JSON espejo con bloque `_backend` para que el servidor on-prem verifique (SUNAT/InfoObras) y enriquezca. Si la propuesta es un PDF escaneado sin capa de texto, hace OCR en español primero (Paso 0). Úsala siempre que el usuario diga "analizar/evaluar una licitación o propuesta OSCE", "llenar el formato de evaluación", "/analizar-licitacion-osce bases.pdf propuesta.pdf", mencione personal clave, factores A/B, experiencia del postor/profesional, o suba un par bases+propuesta de un concurso de obra. Es el motor central del pivote InfoObras (Claude evalúa; el backend verifica).'
---

# analizar-licitacion-osce

## Propósito

Claude es el **motor central** de evaluación: lee `bases.pdf` + `propuesta.pdf`,
**extrae y evalúa** la propuesta, y produce dos artefactos que viajan al backend
on-prem:

1. **Excel "Formato de Evaluación"** (una hoja, 5 partes) — el entregable humano.
2. **JSON espejo** — la misma información estructurada, con un bloque `_backend`
   en `null` que marca lo que el servidor debe verificar/llenar (cruces SUNAT e
   InfoObras, recálculos).

> **Regla de oro**: Claude hace lo no-determinístico (razonar sobre PDFs y
> evaluar). NO inventa lo que requiere fuentes oficiales — eso lo deja en `null`
> dentro de `_backend` para el servidor. Ver `references/salida.md`.

## Topología de subagentes

Las propuestas reales son grandes (miles de folios), así que la separación de
concerns no es un lujo, es lo que evita que se omitan profesionales o
experiencias. La extracción de la propuesta se hace en **dos niveles** (mapa →
profundidad por profesional):

- **`agent-bases`** lee SOLO las bases (`.pdf` **o `.docx`**) → qué exige el concurso
  (requisitos, factores con `aplica`, personal clave, cuantía y **límite inferior**).
  Maneja el **TACHADO** de las Bases Integradas (requisitos eliminados): si es `.docx`
  lo limpia con `scripts/limpiar_bases_docx.py` (determinístico → PDF limpio); si es
  `.pdf` lo excluye por visión. Ver su Paso 0 en `prompts/agent-bases.md`.
- **`agent-propuesta-mapa`** hace UNA pasada estructural a `propuesta.pdf` → datos
  a nivel postor (anexos, oferta económica, experiencia del postor, ISOs) y el
  **bundle de folios de cada profesional** (rango de páginas por apellido).
  **Acota** la experiencia del postor por folios (no la transcribe: es el ~80%
  manual del req. 3.4) y, si hubo Camino A, ubica apellidos por **grep** del índice.
- **`agent-propuesta-profesional`** — **uno por profesional**: lee SOLO el bundle
  de ese profesional y extrae a fondo sus experiencias atómicas (1 fila/periodo),
  con cross-check NOTA 1 contra su cuadro resumen. Más profundidad por profesional,
  sin que se mezclen experiencias entre ellos.
- **`agent-evaluador`** NO lee PDFs: recibe bases + mapa + todos los profesionales y
  **evalúa el cumplimiento** con razones literales (el criterio que aporta Claude y
  que el motor OCR viejo no tenía).

## Flujo

### Paso 0 — OCR de la propuesta escaneada (condicional)
Si `propuesta.pdf` **no tiene capa de texto** (escaneo de imagen), necesitas leer
las páginas como imagen antes de mapear. Hay dos caminos, en orden de preferencia:

**Camino A — Tesseract (PREFERIDO si está disponible).** Saca el OCR del **modelo**
(visión = caro, consume tu límite) y lo hace **local** (CPU = gratis). El script ya
vive en la skill: `scripts/ocr_propuesta.py`. Llámalo **en bucle** hasta que imprima
`ALLDONE` (es reanudable y se auto-limita por tiempo):

```
python3 scripts/ocr_propuesta.py "<propuesta.pdf>" "<out_ocr>" 33 120
```

Si en vez de avanzar imprime **`NO_TESSERACT`** (o `NO_PYMUPDF`) y sale con código 3,
el entorno **no** tiene el binario → cae al **Camino B** sin pedir instalar nada.
(En **Cowork** / sandbox Linux, antes de rendirte intenta `pip install -q pymupdf` y
comprueba `tesseract --version`; si el binario no está y no puedes instalarlo, B.)
Cada página queda en `<out_ocr>/pNNNN.txt` (= el índice por folio). Diseño:
- Tesseract con idioma `spa` (tessdata_fast) en un `TESSDATA_PREFIX` escribible.
- **`OMP_THREAD_LIMIT=1`** por proceso (evita que Tesseract sobre-suscriba hilos);
  paraleliza con un `Pool` = nº de CPUs.
- **Reanudable/idempotente**: el shell del entorno tiene timeout corto (~45 s) y no
  conserva procesos de fondo entre llamadas — el script se auto-limita por tiempo y
  retoma donde quedó en cada corrida.
- DPI **110-130** basta para nombres/fechas/folios.
- Construye un **índice por folio** (folio = número grande del borde de la página,
  ≈ número de página) que consumen el mapa y los subagentes por profesional.

**Camino B — OCR nativo de Claude (fallback por defecto si NO hay Tesseract).**
Si en la máquina **no está** `scripts/ocr_propuesta.py` ni el binario de Tesseract,
**no falles ni pidas instalar nada**: lee el `propuesta.pdf` **directamente con tu
propia visión** — ves cada página como imagen y la transcribes. Es el camino que ya
se validó en producción (corrida ESSALUD-Vitarte: 14 profesionales / 51
experiencias mapeadas **sin Tesseract**). Reglas para que el fallback sea fiable:
- Lee el PDF por **rangos de páginas** (no todo de golpe) para no omitir folios.
- El **folio** = número grande del borde de la página (≈ nº de página); arma el
  **mismo índice por folio** que produciría el Camino A, para que el mapa y los
  subagentes por profesional citen folios igual que con Tesseract.
- Transcribe **literal**: nombres, fechas, montos, RUC y razón social del emisor
  tal cual aparecen — no normalices ni "corrijas" el texto fuente.

> ⚠ **Entorno**: el Camino A (Tesseract) **matiza la regla "solo Node"** — la PC
> del ingeniero necesitaría Python + Tesseract **solo** para ese paso. El Camino B
> (OCR nativo) **no requiere instalar nada** y es el comportamiento por defecto
> cuando Tesseract no está. Si el PDF **ya trae capa de texto**, **omite el Paso 0**
> por completo (ningún OCR) y lee el texto directo.

### Paso 1 — `agent-bases` ‖ `agent-propuesta-mapa` EN PARALELO
Lanza los dos en el **mismo turno** (dos llamadas a la herramienta de subagentes)
porque son independientes. Pásales su prompt (`prompts/agent-bases.md`,
`prompts/agent-propuesta-mapa.md`) + el `analisis_id` (y al mapa, el texto/índice
OCR si hubo Paso 0).

### Paso 2 — `agent-propuesta-profesional` ×N EN PARALELO (depende de 1)
Cuando `agent-propuesta-mapa` devuelva la lista de profesionales con sus bundles,
lanza **un subagente por profesional en el mismo turno** (`prompts/agent-propuesta-
profesional.md`), pasándole `n_prof`, `cargo`, `apellido_clave`, `folios_bundle`,
`experiencia_total_declarada` y el texto de **solo esos folios**. Cada uno devuelve
su profesional + experiencias atómicas + `cross_checks` (NOTA 1). El nº de
subagentes = nº de profesionales del mapa.

> Si hay muchísimos profesionales, lánzalos por lotes; ninguno debe quedar sin
> procesar (NOTA 1: no omitir profesionales).

### Paso 3 — `agent-evaluador` (depende de 1 y 2)
Cuando bases + mapa + **todos** los profesionales estén listos, lanza
`agent-evaluador` (`prompts/agent-evaluador.md`) pasándole esas salidas (sin PDFs).
Devuelve la evaluación: cumple/no-cumple por profesional, DÍAS/MESES/AÑOS por
experiencia, ¿cargo válido para emitir?, ¿anterior a colegiatura?, traslapes en
rojo, descalificación económica vs límite inferior, factores A/B/C/E/J con puntaje
(y "NO APLICA" donde corresponda), todo con **razón literal**.

### Paso 4 — Consolidar → Excel + JSON espejo + imágenes de constancias
Guarda la salida de cada subagente en la carpeta del análisis y corre el
**consolidador determinístico** — NO ensambles el espejo a mano (inviable y
propenso a errores en propuestas grandes):
- `bases.json` (agent-bases), `roster_bundles.json` (agent-propuesta-mapa —
  **incluye el bloque `postor`**: `formularios`, `oferta_economica`,
  `experiencia_postor`, `isos_certificaciones`, `consorciados`),
  `evaluacion.json` (agent-evaluador), `_prof/profesional_NN.json` (uno por prof).
- `node scripts/consolidar_espejo.js <carpeta_analisis>` → escribe `espejo.json`
  uniendo todo, normalizando los alias/typos de los subagentes (cada uno diverge)
  y dejando `_backend` en `null`. Auto-detecta N de `_prof/`; si falta el bloque
  postor del mapa, lo deja vacío + un aviso en `observaciones_claude`.
- el **JSON espejo** resultante (estructura en `references/salida.md`);
- el **Excel** de 5 partes (`node scripts/generar_excel.js` — construcción
  dinámica: un bloque por cargo, filas variables por experiencia, estilos del
  ingeniero + resaltado Claude/backend. Validado con el caso Trujillo);
- las **imágenes de las constancias** (Fase 2): recorta de `propuesta.pdf` las
  páginas de la constancia de cada experiencia (usa `paginas_pdf` = páginas FÍSICAS
  reales, principal 1ª — el folio impreso ≠ página no siempre) a un ZIP —
  `node scripts/extraer_certificados.js <espejo.json> <propuesta.pdf> certificados.zip <bases.pdf>`.
  Son los documentos de la **experiencia** (constancias/conformidades de servicio),
  NO los títulos/colegiatura. El backend los embebe en cada bloque `CERT N°X`.
  **Mejora A:** si pasas `bases.pdf`, también recorta por profesional el requisito
  del TDR (`requisitos.folio`, de las bases) y el Anexo 16 (`folio_anexo`, de la
  propuesta) → `P{n}_TDR.pdf` / `P{n}_ANEXO.pdf`; el backend los embebe **antes de
  las experiencias** en la hoja del profesional.

Persiste todo en `~/InfoObras/analisis/<analisis_id>/`.

### Paso 4.5 — Resolver y VERIFICAR el CUI de cada experiencia (TÚ, buscando en la web)
El backend resuelve CUIs por nombre con un scorer difuso, pero TÚ tienes el contexto
completo del certificado (establecimiento, ubicación, fechas, nivel del hospital) y
desambiguas mejor. Corres en Claude Code con salida a internet (curl / navegador /
búsqueda web). Después de consolidar `espejo.json`, recorre TODAS las experiencias:
las que tienen `cui: null` (resolver) **y las que ya citan un CUI (verificar — un CUI
citado puede estar desactualizado, ver punto 4)**.

**División de fuentes:** el **Banco de Inversiones del MEF** es el registro maestro —
los CUI nacen ahí, tiene el nombre oficial, el estado (ACTIVO/CERRADO) y las
reformulaciones. **InfoObras** es el registro de ejecución que consume el backend.
Por eso el flujo es: **MEF para ENCONTRAR el CUI por nombre → InfoObras para
CONFIRMARLO**.

1. **Sonda primero (una sola vez):** haz una consulta de prueba a la búsqueda pública
   de InfoObras. Si no hay salida a internet o el portal no responde, **omite este
   paso completo** y sigue al Paso 5 — el backend resolverá como siempre (cero regresión).
2. **Busca la experiencia POR NOMBRE en el Banco de Inversiones del MEF** (SSI —
   Sistema de Seguimiento de Inversiones / Consulta de Inversiones, con el navegador
   o búsqueda web `"<nombre de la obra>" CUI`). Usa 2-3 variantes del nombre: el
   proyecto completo; sin el envoltorio de consultoría ("elaboración del expediente
   técnico de…", "estudio de…"); solo establecimiento + localidad. Del resultado toma
   el **CUI del proyecto con estado vigente** (ACTIVO/VIABLE) cuyo nombre coincide con
   el objeto del certificado — si hay un par viejo/reformulado con el mismo nombre,
   el vigente es el bueno.
3. **Confirma ese CUI en InfoObras** (el backend solo consume InfoObras). La búsqueda
   es un POST simple (sin login):
   ```
   curl -s "https://infobras.contraloria.gob.pe/InfobrasWeb/Mapa/busqueda/obrasBasic?page=0&rowsPerPage=20&Parameters=%7B%22nombrObra%22%3A%22%22%2C%22codSnip%22%3A%22<CUI>%22%7D" -X POST
   ```
   Cada resultado trae `codUniqInv` (el CUI, 7 díg.), `codigoObra`, `nombrObra`,
   `nombrDepartamento`, `nombreEntidad`, `estObra`. Verifica nombre/departamento
   contra el certificado. (`Parameters` admite también `nombrObra` para buscar por
   nombre directamente en InfoObras — OJO: matchea por **substring contiguo** del
   nombre oficial, no por palabras sueltas; útil como apoyo, pero el MEF es la
   fuente primaria de identidad.)
4. **VERIFICA los CUI citados (no los tomes por buenos):** consulta InfoObras con
   `codSnip=<cui citado>`. Si la obra devuelta **no solapa en absoluto** el periodo
   del certificado (p.ej. obra ejecutada 2015-2016 vs certificado 2022-2023) o no
   existe, es probable un **CUI desactualizado**: el proyecto se reformuló/re-registró
   con un CUI nuevo (caso real: el cert citaba CUI 2140959 → obra vieja 2015-16; el
   proyecto vigente con el MISMO nombre era CUI 2448758 en el MEF). Ve al punto 2
   (MEF por nombre); si aparece el proyecto con nombre coincidente y época que SÍ
   cuadra, usa ese CUI (`cui_fuente: "skill"`) y deja constancia del reemplazo en
   `observaciones_claude` (citado X → vigente Y). Sin reemplazo claro, deja el
   citado — el backend lo marcará a revisión por cobertura.
5. **Elige con tu contexto** cuando haya varios candidatos: departamento del
   certificado, fechas (una obra cuyo estado/época no cuadra con el periodo
   certificado NO es), establecimiento y nivel. Homónimos en distinta región o
   década: descártalos.
   **Excepción — experiencias de EXPEDIENTE técnico/estudio:** esas obras suelen NO
   tener ejecución/valorizaciones (el trabajo fue el papel, no la construcción), así
   que el solape de época NO aplica como criterio; confirma solo por nombre/ubicación.
   El backend las acepta por el hito "Aprobación del proyecto" de InfoObras.
6. **Confirma SIEMPRE antes de escribir** (anti-alucinación): todo CUI que escribas
   debe haber pasado por el punto 3 (visto en la respuesta de InfoObras o del MEF,
   coincidiendo en nombre/departamento). El backend trata el CUI como **autoritativo**
   — un CUI inventado o mal confirmado lo llevaría a la obra EQUIVOCADA. **Nunca
   escribas un CUI que no confirmaste; jamás lo deduzcas "de memoria".**
7. **Escribe en `espejo.json`**: `cui` (solo dígitos) + `cui_fuente: "skill"`. En las
   experiencias donde el cert ya citaba CUI y quedó verificado, deja
   `cui_fuente: "certificado"`. Si no hay candidato convincente, deja `cui: null` —
   caerá a "Por confirmar" en el panel, como hoy. **Mejor null que un CUI dudoso.**
8. Re-valida el espejo (`node scripts/validar_espejo.js`) tras editarlo.

> **Alcance:** esto aplica a obras/proyectos PÚBLICOS (InfoObras/MEF). Las
> experiencias con cliente PRIVADO no tienen CUI ni están en estos registros — déjalas
> con `cui: null` sin insistir; su verificación es otro flujo (fuera de este alcance).

### Paso 4.6 — Verificación de EXPEDIENTES contra SEACE + MEF (módulo de verificación)
Para cada experiencia de **EXPEDIENTE técnico/estudio** (las detectadas en 4.5 —
nombre de expediente/consultoría de proyecto), además del CUI verifica el
**contrato detrás del certificado**. Requiere NAVEGADOR (Chrome MCP); si no hay
navegador disponible, omite este paso y anota en `observaciones_claude` que la
verificación SEACE quedó pendiente — no bloquees el análisis.

1. **SEACE** (buscador público:
   `https://prod2.seace.gob.pe/seacebus-uiwd-pub/buscadorPublico/buscadorPublico.xhtml`):
   busca el proceso por NOMBRE del proyecto y AÑO del contrato. De la convocatoria
   DESCARGA las **Bases Integradas** y el **Contrato** a la carpeta del análisis
   (`verificacion/P{n}_E{m}/01_Bases…`, `02_Contrato…`). Anota: contratista (empresa
   o persona natural), N° de contrato, monto y fechas.
2. **MEF — datos por el SSI** (ssi.mef.gob.pe, expone el Banco de Inversiones SIN
   código de verificación): estado del proyecto, situación, monto, unidad ejecutora,
   contrataciones registradas.
3. **MEF — resolución de aprobación** (solo si hace falta el PDF): Consulta Pública
   de Inversiones → CUI → "Registros en la Fase de Inversión" → **Formato N°08-A** →
   sección "B. Datos de la fase de Ejecución: Expediente técnico" → descarga el PDF
   (`03_Resolucion_Aprobacion…`). Si pide captcha, es la ÚNICA pausa permitida:
   pide al usuario "escribe el código y avísame" y continúa.
4. **Contraste** y registro: compara contratista / N° contrato / monto / fechas /
   resolución contra el certificado. Escribe el resultado en `observaciones_claude`
   de esa experiencia con el formato:
   `VERIFICACION_EXPEDIENTE: contratista ✅|⚠️|❌ · contrato ✅|⚠️|❌ · resolución ✅|⚠️|❌ — detalle corto (fuente: SEACE/MEF)`.
   Diferencias menores (valor referencial vs adjudicado) = esperables, no ❌.
   **Mismas reglas de evidencia del 4.5**: solo datos vistos en pantalla, nada de
   memoria; si algo no aparece, ⚠️ "no verificable en línea" y sigues.

(Para verificar un expediente SUELTO sin correr el análisis completo existe el
prompt manual: `docs/prompt-verificacion-expediente.md`.)

### Paso 5 — Transporte al backend (POR DEFECTO: MCP, automático)
**El default es subir por el MCP, sin preguntar.** Tras consolidar y validar:
1. `probar_conexion` del MCP `infoobras-onprem-bridge` (ver `mcp-server/`). Si
   responde, continúa; si no, ve al fallback.
2. `subir_analisis(json_espejo, excel_base64, certificados_base64)` — crea/usa el
   concurso y hace POST multipart por LAN a `/api/pivote/analizar` (espejo + Excel +
   el ZIP de constancias del Paso 4 en base64, si lo hay). Devuelve `job_id`.
3. `consultar_estado(job_id)` — reporta el estado + los enlaces de descarga del
   Excel/ZIP enriquecidos.

**Fallback (Camino B, solo si el MCP/backend NO responde):** deja Excel + JSON en
la carpeta del análisis y dile al usuario que los suba por el dropzone del panel.
No te quedes esperando: si el backend está apagado, reporta el fallback y termina.

## Validación y retry

Tras consolidar el JSON espejo, **valídalo**:

```
node scripts/validar_espejo.js <ruta_json>
```

(usa `schemas/espejo.js`, zod). Imprime `OK · …` si es válido, o `INVÁLIDO · …`
con la lista de errores (campo + mensaje).

Si sale `INVÁLIDO`, toma cada error y **reintenta el subagente responsable** de
ese campo (máx. 2 reintentos por subagente), pasándole el texto literal del
error — una falla aislada no debe tumbar toda la corrida.

**Mapa error → subagente responsable** (por el prefijo de la ruta del error):

| Prefijo de la ruta del error | Reintentar | Pasándole |
|---|---|---|
| `profesionales[i].experiencias[…]` | `agent-propuesta-profesional` del `n_prof = i+1` | su bundle + el error |
| `profesionales[i].*` (resto de campos del profesional) | `agent-propuesta-profesional` del `n_prof = i+1` | su bundle + el error |
| `postor.*` | `agent-propuesta-mapa` | el error (re-pasada acotada) |
| `resumen_evaluacion.*` | `agent-evaluador` | bases + mapa + profesionales + el error |
| `profesionales[i].cumple` / `anios_adicionales` / `dias·meses·anios` | `agent-evaluador` (campos de juicio) | ídem |
| `_meta.*` | nadie — lo corrige el **orquestador** (él genera `_meta`) | — |
| error de `n_prof` no contiguo (raíz) | nadie — el **orquestador** reindexa contra el mapa | — |

Si tras los reintentos persiste el error, NO descartes la corrida: entrega el
espejo con el problema documentado en `observaciones_claude`
(`severidad: critical`) y díselo al usuario — el backend lo rechazará en ingesta
y quedará trazado.

El schema ya verifica los invariantes clave: `n_prof` 1..N contiguo, `n` de
experiencias contiguo por profesional, fechas coherentes (`fecha_final ≥
fecha_inicial`, solo entre fechas ISO completas), montos ≥ 0, fechas en una de
tres formas (ISO · parcial `"YYYY-MM (anotación)"` · `"POR VERIFICAR…"`),
`puntaje` numérico o `"NO APLICA…"`, y `_backend` opcional (Claude lo deja vacío).

> **Entorno**: el código client-side es **Node** (`exceljs`, `zod`). Instalar una
> vez: `cd ~/.claude/skills/analizar-licitacion-osce && npm install`. El **Paso 0
> (OCR)** solo corre cuando la propuesta es un escaneo sin texto, y su Camino A usa
> **Python + Tesseract**; si Tesseract no está, el Camino B (OCR nativo de Claude)
> cubre ese paso **sin instalar nada**. El validador y generador en Python viven en
> el **backend** (`backend/scripts/`), que regenera el Excel enriquecido.

## Salida esperada (reporte en chat)

```
✓ agent-bases:               N cargos · M factores · cuantía/límite inferior · fecha presentación …
✓ agent-propuesta-mapa:      N profesionales (bundles) · anexos · oferta · ISOs
✓ agent-propuesta-profesional ×N:  K experiencias atómicas · cross-check NOTA 1 OK
✓ agent-evaluador:           evaluación lista · X observaciones (Y críticas)
📦 Excel + JSON espejo en ~/InfoObras/analisis/<analisis_id>/
→ Transporte: subir_analisis (MCP, por defecto) → job_id · fallback dropzone si el backend no responde
```

## Referencias
- `prompts/agent-bases.md`, `prompts/agent-propuesta-mapa.md`, `prompts/agent-propuesta-profesional.md`, `prompts/agent-evaluador.md` — prompts de los subagentes.
- `references/salida.md` — contrato de salida (JSON espejo + bloque `_backend` + las 5 partes del Excel).
- `schemas/espejo.js` — **schema ejecutable del espejo (zod, v1.2.0)**; su gemelo
  Pydantic vive en `backend/schemas/espejo.py` y `tools/test_contrato.py` garantiza
  la paridad.
- `docs/contrato/contrato_refactor.md` — contrato técnico autoritativo del pivote.
