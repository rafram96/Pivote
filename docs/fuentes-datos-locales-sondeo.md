# Sondeo de fuentes de datos crudas para bases locales

> **Objetivo de esta fase**: reemplazar consultas web en vivo (flaky, con
> captchas, con rate-limits) por **bases locales descargables**. Antes de
> diseñar arquitectura, saber **qué existe de verdad, qué contiene y si sirve**.
>
> **Fecha del sondeo**: 2026-07-21. Método: verificación en vivo de portales,
> diccionarios de datos oficiales y cabeceras/tamaños reales de los archivos.
>
> **Estado**: sondeo cerrado. La arquitectura se diseña sobre estas conclusiones
> en la fase siguiente.

---

## 1. Lado demanda — qué consume hoy el pipeline (para juzgar "sirve o no")

| # | Fuente en vivo | Host | Para qué se usa | Reemplazo local hoy |
|---|---|---|---|---|
| 1 | **InfoObras / Contraloría** | `infobras.contraloria.gob.pe` | Núcleo: valorizaciones por periodo, paralizaciones (fechas exactas), avance físico, PDFs de sustento, informes de control, **decisor de CUI** | ❌ Ninguno (solo fixtures) |
| 2 | **SUNAT RUC** | `e-consultaruc.sunat.gob.pe` | ALT04 (fecha inscripción), ALT12 (representantes), match nombre-RUC | ⚠️ Solo caché Postgres |
| 3 | **MEF Invierte en vivo** | `ofi5.mef.gob.pe` | Verificación de expedientes técnicos (Formato 08-A + contratos DWH) | ❌ Solo fixtures |
| 4 | **MEF Datos Abiertos CSV** | `fs.datosabiertos.mef.gob.pe` | Resolver de CUI (fuzzy por nombre) | ✅ **Ya es base local** — el patrón a generalizar |
| 5 | Informes de control | (vía InfoObras) | ZIP entregable | ❌ |
| 6 | SEACE / CONOSCE / OCDS | `seace/conosce.osce.gob.pe` | Sondas experimentales, no en producción | 🟡 Camino trazado en `tools/` |
| 7 | RENIPRESS | — | Solo en planeación, sin código aún | — |

**El patrón a replicar ya existe y funciona**: `backend/scripts/actualizar_base_mef.py`
(descarga CSV) + `backend/resolucion/base_mef.py` (índice en memoria, degradación
elegante si la base no está). No hay que inventar el patrón — hay que generalizarlo.

---

## 2. Veredicto por fuente

Leyenda: 🟢 GO (base local viable, alto valor) · 🟡 PARCIAL (útil pero no cierra
el caso solo) · 🔴 NO (descartar como base local).

### 🟢 MEF — Banco de Inversiones + SSI (Formato 12B + Estado Situacional) — **el gran hallazgo**

Tres datasets, org `inversion-publica`, **CSV UTF-8 con BOM, coma, comillas dobles,
actualización DIARIA**. Backend real de la API: `api.datosabiertos.mef.gob.pe/DatosAbiertos/v1/`
con `datastore_search`, `datastore_search_sql` (`?sql=`) y `dump?id=<resource_id>`
→ **se puede consultar por CUI sobre HTTP sin descargar todo y sin captcha**.

| Dataset | URL CSV | Tamaño / filas | Aporta |
|---|---|---|---|
| **Detalle de Inversiones** (maestro) | `fs.datosabiertos.mef.gob.pe/datastorefiles/DETALLE_INVERSIONES.csv` | ~233 MB · 148.777 filas · 148.710 CUIs (1 fila/CUI) | ~72 campos: CUI, SNIP, nombre, marco, tipología, nivel/sector/entidad, ubigeo+lat/long, estado/situación, montos, **`AVANCE_FISICO`**, fechas ejec. física (F8 y F12B), flags `TIENE_F8/F9/F12B`, expediente técnico, informe cierre |
| **Formato 12B** | `.../datastorefiles/FORMATO_12B.csv` | ~170 MB · 219.252 filas | Programación financiera mensual (`MONTO_PROGRAMADO_1..12`, `DEV_ENE..DIC`, `DEVENGADO_ACUMULADO`), **`AVANCE_FISICO` %**, `ULT_ESTADO_SITUACIONAL` (texto con fecha), **`ULT_PROBLEMA`**, `ACC_PROBLEMA` |
| **Estado Situacional** (serie temporal) | `.../datastorefiles/ESTADO_SITUACIONAL.csv` | ~196 MB · 1.373.390 filas · 2017–2026 | 6 cols: `CODIGO_UNICO`, `PERIODO` (YYYYMM), `DESCRIPCION` (texto libre), **`TIP_REGISTRO`**, `COD_TIPO`, `FECHA_REGISTRO` |

Diccionarios: `Detalle_Inversiones_Diccionario.csv`, `F12B_Diccionario.csv`,
`Estado_Situacional_Diccionario.csv` (mismo file server).

**`TIP_REGISTRO` tipifica paralizaciones por CUI+periodo** (conteos reales):
`PROBLEMA (Atrasos y/o paralizaciones)` 36.835 · `PROBLEMA (Paralización)` 404 ·
+ causales: `Resolución de contrato`, `Interferencias`, `Arbitraje`,
`Discrepancias (Valorización observada)`, `Falta de disponibilidad de terreno`,
`Deficiencias en el Expediente Técnico`, etc.

**¿Sustituye a InfoObras?**
- **Avance físico %**: 🟢 SÍ, estructurado y con mejor cobertura (148k CUIs, diario).
  Para "¿en qué % va la obra y entre qué fechas físicas?" reemplaza la consulta viva.
- **Paralización**: 🟡 PARCIAL. Da flag tipificado + causal + periodo mensual + texto,
  pero **NO tabla con `fecha_inicio`/`fecha_fin` exactas por evento**. El **Paso 5
  (días efectivos = restar ventanas exactas)** sigue necesitando InfoObras.
- **Valorizaciones por periodo**: 🔴 NO las trae (son producto Contraloría).

> **Uso recomendado**: base local nueva y **complementaria**. Cross-check de
> identidad de CUI, avance físico, situación vigente y **flag de paralización/causal**
> que dispara revisión aunque InfoObras esté flaky. Ojo: apuntar a
> `fs.datosabiertos.mef.gob.pe` (fresco, diario), **no** al espejo cosechado
> `datosabiertos.gob.pe` (DKAN, más atrasado).

### 🟢 OSCE / CONOSCE — reemplazo del SEACE gated

XLSX anual por dataset, HTTP directo, **sin captcha**, unidos por `CODIGOCONVOCATORIA`.
Reemplaza la búsqueda del SEACE (que es NO-GO por reCAPTCHA v3).

- **Descarga**: `conosce.osce.gob.pe/buscador/assets/67ae6c4a/reportes/{dataset}/{AÑO}/CONOSCE_{DATASET}{AÑO}_0.xlsx`
  (sufijo `_0`, `_1`… en años grandes). Diccionario único: `.../reportes/Diccionario.xlsx`
  (20 datasets). Requiere User-Agent de navegador. Cobertura **2018+**, refresco mensual.
- **Base mínima viable**: Convocatorias + Adjudicaciones + Contratos + Consorcios + Entidades.
  - Convocatorias (28 cols): nomenclatura (`PROCESO`), objeto, valor referencial, fechas, ubigeo.
  - Adjudicaciones (18): **RUC + razón social del ganador**, monto adjudicado, buena pro.
  - Contratos (23): plazo, montos, adicionales, **`URLCONTRATO` (PDF)**.
  - Consorcios: desagrega miembros del consorcio ganador.
- **Documentos** (bases integradas, actas): vía record OCDS
  (`OCID = ocds-dgv273-seaceV3-{CODIGOCONVOCATORIA}` → array `documents`).

> **Límite duro**: 🔴 **ningún dataset OSCE trae CUI** (ni el OCDS). El cruce con la
> base MEF sigue siendo por matching difuso (entidad + ubigeo + descripción) o regex
> sobre la descripción. Estos datos aportan candidatos con RUC/ubigeo confiables, no
> resuelven la identidad.
>
> **Riesgo de red a validar en el server**: `contratacionesabiertas.*.gob.pe`
> (OCDS) falló DNS desde esta laptop (posible geobloqueo US). Verificar desde Perú.

### 🟢 RENIPRESS (SUSALUD) — base local ideal, bajo costo

- **Descarga**: `datos.susalud.gob.pe/sites/default/files/RENIPRESS_2025_v2.csv`
  (+ mirror en datosabiertos con `Diccionario Datos.xlsx`). CSV <10 MB, ~24k IPRESS.
- **Campos**: **RENAES** (código único 8 díg.), nombre, **Categoría (I-1..III-2)**,
  **Institución** (MINSA/EsSalud/GR/PRIVADO/FF.AA./…), ubigeo, DISA/Red/Microred, estado.
- **Cubre dos necesidades de un golpe**: clasificación de nivel hospitalario de la
  experiencia **y** gate de privadas (todo lo no-estatal = privado).

> Complementa el catálogo de entidades públicas MEF/SUNAT que ya existe.

### 🟡 SUNAT — Padrón RUC (índice sí, ALT04 no)

- **Padrón Reducido**: `sunat.gob.pe/descargaPRR/mrc137_padron_reducido.html`
  (ZIP→TXT, ~11M registros, **diario**, Latin-1). **Padrón datos abiertos**:
  `datosabiertos.gob.pe/.../PadronRUC_YYYYMM.zip` (mensual).
- **Campos**: RUC, razón social, estado, condición domicilio, ubigeo, dirección.
- 🔴 **Ninguna versión masiva trae fecha de inscripción / inicio de actividades.**
  Ese campo solo vive en la **ficha RUC individual** (el scraper `consultar_ruc` actual).

> **Veredicto**: útil como índice offline RUC→identidad (nombre/estado/ubigeo), pero
> **ALT04 seguirá necesitando la consulta RUC en vivo por RUC**. No hay atajo masivo.

### 🔴 MEF — SIAF / Consulta Amigable (gasto devengado) — DESCARTAR

- CSV de ~2.8 GB/año (`fs.datosabiertos.mef.gob.pe/datastorefiles/AAAA-Gasto-Devengado.csv`).
- 🔴 **Sin columna CUI** (granularidad mínima = meta presupuestal). No se une al Banco
  de Inversiones. Además *devengado presupuestal ≠ valorización física*.
- La señal financiera por CUI, si se quisiera, vive en el SSI (ya cubierto arriba),
  no en estos dumps.

---

## 3. Cuadro resumen

| Fuente | Veredicto | Descarga | Cadencia | Cierra por sí sola |
|---|---|---|---|---|
| **MEF Detalle Inversiones** | 🟢 GO | CSV directo / API SQL por CUI | Diaria | Identidad CUI + avance físico |
| **MEF Formato 12B** | 🟢 GO | CSV directo | Diaria | Financiero mensual + situación |
| **MEF Estado Situacional** | 🟡 PARCIAL | CSV directo | Diaria | Flag paralización (no fechas exactas) |
| **OSCE CONOSCE** | 🟢 GO | XLSX anual | Mensual | Ficha procedimiento (sin CUI) |
| **OSCE OCDS** | 🟢 GO | jsonl.gz/API | Mensual | Documentos (bases/actas) |
| **RENIPRESS** | 🟢 GO | CSV <10 MB | Periódica | Categoría + público/privado |
| **SUNAT Padrón** | 🟡 PARCIAL | ZIP/TXT | Diaria/Mensual | Índice, **no** fecha ALT04 |
| **MEF SIAF gasto** | 🔴 NO | CSV ~2.8 GB/año | Diaria | — (sin CUI) |
| **InfoObras** | 🔴 sin dataset | scraping en vivo | — | Valorizaciones + fechas exactas paralización |

---

## 4. Lectura para la arquitectura (insumo de la fase siguiente)

1. **Lo que se internaliza a base local** (elimina red flaky/captcha): MEF Inversiones
   (3 datasets), OSCE CONOSCE+OCDS, RENIPRESS. El patrón `actualizar_base_*` +
   `base_*` con degradación elegante se generaliza a un pequeño framework de ingesta.
2. **Lo que se queda en vivo** (no hay dataset abierto equivalente):
   - **InfoObras**: valorizaciones por periodo + ventanas exactas de paralización
     (Paso 5) + PDFs de sustento + informes de control → sigue siendo **decisor**.
   - **SUNAT `consultar_ruc`**: la fecha para ALT04.
   - **MEF 08-A + contratos DWH** en vivo para verificación fina de expediente
     (aunque el avance físico ahora se corrobora con la base local).
3. **CUI sigue sin venir servido** por OSCE — la resolución difusa contra MEF se
   mantiene como el corazón del sistema; ahora con más señales locales (avance físico,
   situación, ubigeo) para desempatar.
4. **Decisión de almacenamiento**: MEF ~600 MB + CONOSCE (varios años) + RENIPRESS.
   Definir si índice en memoria (como base_mef) o tablas Postgres con `ON CONFLICT DO UPDATE`.
5. **Encoding/gotchas confirmados**: MEF Inversiones = UTF-8 con BOM; SIAF y SUNAT =
   Latin-1; CONOSCE = XLSX con acentos sucios en títulos. Parser por fuente, no genérico.

---

## 5. Pendientes antes de diseñar arquitectura

- [ ] Validar desde el **server en Perú** que `contratacionesabiertas.*.gob.pe` (OCDS)
      y `datos.susalud.gob.pe` resuelven (fallaron DNS desde la laptop US).
- [ ] Decidir alcance de esta ronda (RENIPRESS es el de mejor ratio valor/costo).
- [ ] Confirmar política de almacenamiento (memoria vs Postgres) y cadencia de refresco.
