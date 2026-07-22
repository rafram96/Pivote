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
| `resolucion/base_mef.py` | base local del Banco de Inversiones: índice en memoria (singleton perezoso, ~60 s carga, ~370 MB RAM, consultas ~0.2 s); `buscar_candidatos / existe_cui / es_entidad_publica` |
| `resolucion/texto.py` | `norm()` / `expandir_abrev()` compartidos |
| `scraping/infoobras.py` | búsqueda, `fetch_by_cui`, valorizaciones (`lAvances`), paralizaciones, `seleccionar_obra` (entre obras del MISMO CUI), descargas |
| `scraping/mef.py` | T-003: ficha 08-A, contratos SEACE vía DWH del MEF, descarga de PDFs de expediente (funciones de parseo puras + fixtures offline) |
| `scraping/sunat.py` | consultar_ruc (ALT-04) |
| `entregables/excel_final.py` | Excel final con imágenes embebidas (P-sheets) y bloques VERIFICACIÓN SEACE/MEF |
| `entregables/zip_infoobras.py` | ZIP de sustento por profesional/experiencia/sección |
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
etapas_reales, excel_final, zip_infoobras y la vista SQL — cambios solo ADITIVOS.

## Configuración (env `PIVOTE_*`, leída en el punto de uso)

`PIVOTE_DATA_DIR` · `PIVOTE_DB_URL` (opcional) · `PIVOTE_ETAPAS` ·
`PIVOTE_MAX_DESCARGAS` (vacío=todas, 0=ninguna) · `PIVOTE_VERIFICAR_MEF` ·
`PIVOTE_FORZAR_EXPEDIENTES` (modo camino A) · `PIVOTE_MEF_MAX_DIAS`.

## Pruebas

`venv\Scripts\python.exe -m pytest backend/tests -q` — 100% offline (fakes del
Protocol `Consulta`, fixtures mini en `tests/fixtures/mef/`). Golden de
regresión: `backend/scripts/golden_cui.py --con-base --solo-cache --comparar`
contra `datos_pivote/golden_cui_baseline.json`.
