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

- **`agent-bases`** lee SOLO `bases.pdf` → qué exige el concurso (requisitos,
  factores con `aplica`, personal clave, cuantía y **límite inferior**).
- **`agent-propuesta-mapa`** hace UNA pasada estructural a `propuesta.pdf` → datos
  a nivel postor (anexos, oferta económica, experiencia del postor, ISOs) y el
  **bundle de folios de cada profesional** (rango de páginas por apellido).
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

**Camino A — Tesseract (si está disponible).** Enfoque heredado del flujo manual,
determinístico y barato; ideal en propuestas de miles de folios cuando el script y
el binario están instalados:
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

### Paso 4 — Consolidar → Excel + JSON espejo
El orquestador une todas las salidas (bases + mapa + N profesionales + evaluador) en:
- el **JSON espejo** (estructura en `references/salida.md`), dejando el bloque
  `_backend` en `null`;
- el **Excel** de 5 partes (`node scripts/generar_excel.js` — construcción
  dinámica: un bloque por cargo, filas variables por experiencia, estilos del
  ingeniero + resaltado Claude/backend. Validado con el caso Trujillo).

Persiste ambos en `~/InfoObras/analisis/<analisis_id>/`.

### Paso 5 — Transporte al backend (POR DEFECTO: MCP, automático)
**El default es subir por el MCP, sin preguntar.** Tras consolidar y validar:
1. `probar_conexion` del MCP `infoobras-onprem-bridge` (ver `mcp-server/`). Si
   responde, continúa; si no, ve al fallback.
2. `subir_analisis(json_espejo, excel_base64)` — crea/usa el concurso y hace POST
   multipart por LAN a `/api/pivote/analizar`. Devuelve `job_id`.
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
