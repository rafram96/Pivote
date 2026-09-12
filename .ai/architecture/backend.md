# Backend (backend/)

FastAPI + pipeline de etapas por job. Python 3.12 (`venv/` en la raíz del repo).
Dependencias en `backend/requirements.txt` — **rapidfuzz es dependencia dura**;
NO añadir pandas/duckdb/sqlalchemy/SQLite sin ADR.

## Módulos principales

| Ruta | Rol |
|---|---|
| `api/app.py` | FastAPI: concursos, `POST /api/pivote/analizar` (espejo+excel+certificados), jobs, ZIP bajo demanda (`/jobs/{id}/zip`, se construye lazy) |
| `orquestador/motor.py` | corre el pipeline; REANUDABLE por checkpoints; espejo se guarda UNA vez al crear el job |
| `orquestador/etapas_reales.py` | etapas reales: `EtapaResolucionCuiReal` (único caller del resolver), `EtapaInfoObrasReal` (fetch, clamp, verificación MEF de expedientes, descargas), SUNAT, reglas, excel |
| `orquestador/repositorio.py` | `RepositorioArchivos` (fuente de verdad) + `RepositorioConRespaldo` (write-through a PG best-effort) |
| `resolucion/cui.py` | **resolver de CUI** (ver abajo) |
| `resolucion/base_mef.py` | base local del Banco de Inversiones: índice en memoria con `sys.intern` + índice invertido token→filas (singleton perezoso, carga ~15-60 s según caché de disco, **~370 MB RAM** — fuente única de esta cifra; remedido 2026-07-23: 379 MB; consultas ~0.2 s); `buscar_candidatos / existe_cui / es_entidad_publica` |
| `resolucion/texto.py` | `norm()` / `expandir_abrev()` compartidos |
| `scraping/infoobras.py` | búsqueda, `fetch_by_cui`, valorizaciones (`lAvances`), paralizaciones, `seleccionar_obra` (entre obras del MISMO CUI), descargas |
| `scraping/mef.py` | T-003: ficha 08-A, contratos SEACE vía DWH del MEF, descarga de PDFs de expediente (funciones de parseo puras + fixtures offline) |
| `scraping/sunat.py` | consultar_ruc (ALT-04) |
| `entregables/excel_final.py` | Excel final con imágenes embebidas (P-sheets) y bloques VERIFICACIÓN SEACE/MEF |
| `entregables/zip_infoobras.py` | ZIP de sustento por profesional/experiencia/sección |
| `entregables/identidad.py` | Composición pura de procedencia/certeza para Excel, ZIP y API; no resuelve CUI ni cambia reglas |
| `reglas/resultados_profesionales.py`, `reglas/expedientes.py` | Conciliación de días/resultados de ambas rutas; inyección explícita separada de la función de lectura |
| `reglas/requisitos.py`, `reglas/factor_a.py` | Mínimo exigido, participantes y puntuación; etapas conserva aliases compatibles |
| `reglas/conclusiones.py`, `entregables/textos.py` | Conclusión desde totales y limpieza textual, sin importar Excel |
| `scripts/` | `actualizar_base_mef.py` (ETL semanal), `golden_cui.py` (auditoría de regresión, 277 casos), resubir_job, backfills |

## El resolver de CUI (flujo público-primero)

1. **CUI/SNIP citado** → InfoObras por código (match exacto) + validación contra
   base MEF; autoritativo si calza exacto.
2. **Candidatos por nombre** = fusión base MEF local (top-10 fuzzy) + búsqueda
   InfoObras; candidatos solo-MEF se traen por código (tope 5).
3. **Ranking 100% por IDENTIDAD**: similitud de nombre (max InfoObras/MEF),
   N° de institución (+40/−15), ubigeo oficial, entidad contratante (+15),
   RUC emisor=ejecutor/supervisor (+30, exento de todo veto).
   **Vetos**: rubro contradictorio; provincia contradictoria (ambas declaradas);
   entidad municipal distinta. Distrito distinto solo penaliza (−25).
4. **Candados de abstención**: candidato solo-MEF no gana sin corroboración dura;
   empate ≤4 pts entre CUIs sin señal separadora → revisión con candidatos.
5. **Privadas AL FINAL**: solo si no hubo candidato público fiable (léxico +
   catálogo de 11k entidades públicas; `posible_privada` aditivo).

⚠ El solape de fechas declaradas NO participa en la selección (ADR-003).
Contrato de retorno `{estado, cui, via, decision, candidatos, obra}` acoplado en
etapas_reales, excel_final y zip_infoobras — cambios solo ADITIVOS.
(Antes esta línea listaba «la vista SQL» como cuarto consumidor: no existe. Las
vistas `base_datos`/`analisis` vivían solo en el `db/schema.sql` aspiracional y
se **eliminaron** el 2026-08-05, cuando ese archivo pasó a ser espejo documental
de los DDL reales — ver `architecture/database.md`.)

## Proyección de identidad

Proyección de identidad (12-sep): la ficha efímera de Excel conserva
`_enriquecimiento_identidad`, referencia de lectura al contexto original, para
no reclasificar desde una copia parcial con un CUI aplanado. El helper compartido
admite `_procedencia_cui` legacy, siempre toma el declarado del espejo y conserva
SUNAT por su canal de entrada existente. La referencia no se persiste ni se
exporta al Panel. No centraliza cálculo/días, inventarios o la política de fuentes;
esos componentes conservan sus autoridades actuales.

## Cálculo y presentación

Separación integrada el 12-sep: API y recontraste consultan resultados en reglas,
igual que Excel. Mínimos/Factor A ya no viven en etapas; expedientes conserva un
adaptador en su ubicación anterior. `entregables.__getattr__` carga generadores
solo al solicitarlos: importar reglas/certeza no carga openpyxl ni etapas.
La conciliación es de lectura; la inyección muta explícitamente e idempotentemente.
No cambia umbrales, días, prioridades de conclusión o contratos de datos.
Las sumas de presentación por fila continúan usando los helpers puros de cálculo.
Aceptación y límites en el [handoff](../handoffs/2026-09-12_codex.md#cálculo-separado-de-la-generación-excel).

## Fuentes paralelas y reutilización

SUNAT reutiliza búsquedas no vacías por consulta exacta, durante una sola
ejecución. Sus vacíos no se cachean porque el cliente también devuelve `[]`
cuando falla. Decisiones y alertas se calculan por experiencia, no por caché.

`orquestador/ramas.py` aísla las entradas tras el resolver. El motor incorpora
solo deltas terminados y guarda cada fuente por separado, datos antes del OK.
Hay un solo escritor; no se serializa estado mutable de una fuente en curso.
Fusión por campo conserva resultados hermanos y revisiones; conflictos abortan
y no se reintentan como si fueran caídas del portal. Conserva el orden canónico
de etapas y la barrera antes de reglas. No cambia identidad ni habilita el
rescate circular SEACE→RUC (gate desactivado). Si vuelve a habilitarse ese cruce,
debe declararse su dependencia de InfoObras terminada, no leerla a mitad del pool.
[Aceptación y límites](../handoffs/2026-09-12_codex.md#consultas-repetidas-y-checkpoint-por-fuente).

## Configuración (env `PIVOTE_*`, leída en el punto de uso)

`PIVOTE_DATA_DIR` · `PIVOTE_DB_URL` (opcional) · `PIVOTE_ETAPAS` ·
`PIVOTE_MAX_DESCARGAS` (vacío=todas, 0=ninguna) · `PIVOTE_VERIFICAR_MEF` ·
`PIVOTE_FORZAR_EXPEDIENTES` (modo camino A) · `PIVOTE_MEF_DIAS_FRESCURA`
(default 10; umbral del aviso de base MEF vencida — antes esta línea nombraba
`PIVOTE_MEF_MAX_DIAS`, que nunca existió en el código).

## Pruebas

`venv\Scripts\python.exe -m pytest backend/tests -q` — 100% offline (fakes del
Protocol `Consulta`, fixtures mini en `tests/fixtures/mef/`). Golden de
regresión: `backend/scripts/golden_cui.py --con-base --solo-cache --comparar`
contra `datos_pivote/golden_cui_baseline.json`.
