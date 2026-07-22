# Persistencia y datos

## Principio: archivos = fuente de verdad

Cada job es una **carpeta** en `PIVOTE_DATA_DIR` (local: `backend/datos_pivote/`):
`espejo.json`, `enriquecimiento.json` (clave "n_prof:n_exp"), `job.json`,
`claude.xlsx`, `final.xlsx`, `certs/`, `descargas/`, `infoobras.zip` (lazy).
Escritura atómica (`_escribir_atomico`).

## PostgreSQL = respaldo lógico OPCIONAL

Solo si `PIVOTE_DB_URL` está definida (`RepositorioConRespaldo`, write-through
best-effort: si PG cae, se loguea y se sigue). Re-sync completo:
`backend/scripts/migrar_a_postgres.py`.

⚠ **Dos esquemas divergen** (decisión pendiente de unificar):
- DDL **real** (corre al arrancar): embebido en `orquestador/repositorio_pg.py`
  — 3 tablas: `jobs`, `documentos` (JSONB), `profesionales` (columnas `*_norm`
  para LIKE, sin extensiones de PG).
- `backend/db/schema.sql`: diseño aspiracional (4 tablas JSONB + vistas
  `base_datos` y `analisis`). No es el que corre.

Tip local: la laptop tiene un Postgres de Windows ocupando el 5432 → usar
**55432** para pruebas.

## Base de referencia MEF (nueva, sin PG)

`PIVOTE_DATA_DIR/referencia/mef/`: `inversiones.csv.gz` (~26 MB — cui, snip,
nombre, estado_dataset, situacion, ubigeo, dpto/prov/dist, entidad),
`entidades_publicas.csv` (11,004 nombres + siglas), `metadata.json` (fecha).
Se genera con `backend/scripts/actualizar_base_mef.py` (descarga ~523 MB de
Datos Abiertos del MEF, valida ≥400k filas, escritura atómica; refresco
recomendado: cron semanal). El backend la consume vía índice en memoria
(`resolucion/base_mef.py`) — sin base, el sistema degrada a InfoObras-solo.

## Datos que NO van a la BD ni al repo

Binarios (xlsx/ZIP/PDF) quedan en el volumen de archivos. PDFs/datos del
cliente jamás se commitean. `datos_pivote/` está gitignored.
