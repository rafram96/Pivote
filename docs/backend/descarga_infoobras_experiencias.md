# Descarga de archivos InfoObras + ZIP por experiencia

> Estado: ✅ **IMPLEMENTADO** (2026-06-15). Lo de abajo describe el flujo real
> en código. La sección "Historia / planeación" al final conserva el contexto
> original (2026-06-01) cuando esto era solo alcance por descubrir.

## Cómo funciona hoy (flujo real)

El ZIP **NO se arma durante la corrida del pipeline** — se ensambla **on-demand**
en el endpoint del API la primera vez que se pide. Tres piezas:

### 1. Descarga de documentos — etapa InfoObras (durante el pipeline)
`EtapaInfoObrasReal.correr` ([backend/orquestador/etapas_reales.py](../../backend/orquestador/etapas_reales.py))
descarga los documentos de cada experiencia a:
```
{job_id}.descargas/P{n_prof}_E{n_exp}/Valorizaciones/<AAAA-MM MES>/<documento>.pdf
{job_id}.descargas/P{n_prof}_E{n_exp}/<Sección obra-level>/<documento>.pdf
```
- **Solo corre si `PIVOTE_MAX_DESCARGAS > 0`** (env var; acota cuántas OBRAS se
  descargan por corrida — los PDFs de valorización pueden pesar ~48 MB c/u).
- Usa `descargar_documentos_obra_por_hito` (ver pieza 2).

### 2. Inventario + descarga por hito — `entregables/zip_infoobras.py`
- `inventariar_por_avance(html)` — liga cada documento a su **mes/año** (desde
  `lImgValorizacion` en `var lAvances` de DatosEjecucion) y separa los documentos
  **obra-level** (expediente, cronograma, adendas, ampliaciones…) que no
  pertenecen a un mes.
- `descargar_documentos_obra_por_hito(obra_id, destino)` — baja las valorizaciones
  a `Valorizaciones/<AAAA-MM MES>/` y lo obra-level a su sección. Endpoints:
  `/Mapa/DatosEjecucion` (inventario inline `var lAvances` + botones
  `data-download-url`) → descarga por `/Mapa/DownloadFile`.
- Falla por archivo se maneja con gracia (cuenta `fallidos`, sigue).

### 3. Ensamblado del ZIP — on-demand en el API
`GET /api/pivote/jobs/{job_id}/zip` ([backend/api/app.py:300](../../backend/api/app.py)):
si el `.zip` no existe, lee las carpetas `{job_id}.descargas/P{n}_E{m}/`, las
mapea a `(n_prof, n_exp)`, llama `construir_zip_infoobras(espejo, descargas, ruta)`
y cachea el resultado. La etapa Excel solo setea la **URL de referencia**
(`job.zip_infoobras`) y borra el `.zip` previo para que se reconstruya.

### Estructura final del ZIP (5 niveles)
```
<Concurso>/
└── {nn} - {cargo}/                      ← Profesional
    └── Exp {n} - {proyecto[:60]}/       ← Experiencia
        ├── Valorizaciones/
        │   ├── 2025-12 DICIEMBRE/<doc>.pdf   ← por HITO/valorización
        │   └── 2025-11 NOVIEMBRE/<doc>.pdf
        ├── Expediente técnico/<doc>.pdf      ← obra-level (no por mes)
        ├── Cronograma/<doc>.pdf
        └── …
```
Las experiencias sin documentos llevan `SIN_DOCUMENTOS.txt` con el motivo
(obra sin CUI, fuera de InfoObras, o descarga fallida). El árbol incluye un
`indice.txt`.

### En el Excel
Cada fila de valorización tiene la columna **"ARCHIVOS (ZIP)"**: `Sí (N)` / `—`,
para que el evaluador sepa qué hitos tienen sustento documental antes de abrir
el ZIP. El dato sale del parseo (`AvanceMensual.num_documentos`), no requiere
descargar.

## Decisiones cerradas (preguntas originales resueltas)
1. **¿Qué archivos?** ✅ Documentos adjuntos de valorización (por hito) + los
   obra-level (expediente, cronograma, adendas…). Imágenes de avance físico NO
   (van solo si `incluir_imagenes`).
2. **¿Qué es una experiencia?** ✅ Nivel 3 del árbol.
3. **Nomenclatura.** ✅ `{nn} - {cargo}` / `Exp {n} - {proyecto}` / `Valorizaciones/<AAAA-MM MES>`.
4. **¿Archivos compartidos entre experiencias?** Se duplican (cada experiencia
   tiene su carpeta con sus descargas). Sin dedup cross-experiencia por ahora.
5. **¿Dónde corre?** Descarga en la etapa InfoObras (Fase A); ensamblado en el API.
6. **¿Entregable?** Vía el panel/API (`/zip`), se arma on-demand.
7. **Decisión 2026-06-15:** se descargan **TODOS los hitos** de la obra (no solo
   el periodo del certificado), aunque infle el ZIP. Ver [[decisiones-cliente-2026-06-10]].

## Validado a escala (2026-06-15) ✅
Medido en vivo con `tools/medir_descargas.py` sobre las obras pesadas del demo:
- **Tamaños reales:** obra 68513 = 116 docs, **711 MB**, con un PDF de **49.9 MB**;
  obra 83130 = 208 MB. El "archivo de 48 MB" que preocupaba **existe y es común**.
- **Bug encontrado y arreglado:** el portal corta la conexión (`IncompleteRead`)
  en casi todos los archivos grandes. El código bajaba con `resp.content` y
  contaba el corte como fallido **sin reintentar** → ~12 sustentos críticos se
  perdían en silencio del ZIP. Fix (`3b1a0a7`): `_descargar_a_carpeta()` baja en
  streaming a `.part`, verifica `Content-Length` y reintenta con backoff.
- **Resultado:** obra 68513 pasó de **107/9 fallidos a 116/0**; los 12 cortes se
  recuperaron en el reintento; 711 MB completos en 121 s. Config:
  `INFOOBRAS_DOWNLOAD_RETRIES` (def 3), `INFOOBRAS_DOWNLOAD_BASE_DELAY` (def 1.0).

## Pendiente / riesgos conocidos
- Un ZIP por concurso puede pesar **varios GB** (711 MB es UNA obra; un concurso
  tiene 40+). No es un bug, pero conviene decidir con Manuel: ¿se descargan todas
  las obras siempre, o se acota por tamaño/relevancia? Hoy lo gobierna
  `PIVOTE_MAX_DESCARGAS` (nº de obras), no el tamaño.
- Otras secciones de "Información complementaria" (cronograma, adendas,
  controversias, etc.) hoy salen vacías en los datos estructurados — ver
  [[infoobras-secciones-tabla-html]].

## Historia / planeación (2026-06-01, superado)
El requerimiento surgió tras la aprobación del pivote: descargar los archivos que
InfoObras expone y empaquetarlos en un ZIP por experiencia, porque **sobre esos
documentos se hace el análisis humano**. La jerarquía de 4 niveles se definió
ahí; el nivel extra (por hito) se agregó el 2026-06-15. El prototipo
`tools/descargar_documentos_infoobras.py` descubrió los endpoints (`/DownloadFile`,
`data-download-url`) contra la obra 72056.
