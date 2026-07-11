# Esquema PostgreSQL — persistencia del pivote

> **Status**: ✓ implementado (`backend/orquestador/repositorio_pg.py`) · act. 2026-07-11
> **Decisión marco**: Postgres **básico** (2026-06-25, contraparte de no cobrar el
> addendum): espejo JSONB de los documentos actuales, **sin modelado relacional**.
> **Decisión de recorte** (2026-07-10): 3 tablas — `jobs` + `profesionales` +
> `documentos` genérica — en vez de una tabla por documento.
> **Decisión de rol** (2026-07-11): la BD **NO reemplaza a los archivos** — es el
> **respaldo lógico**. Los archivos (una carpeta por job) siguen siendo la fuente
> de verdad; Postgres recibe cada escritura vía `RepositorioConRespaldo`
> (write-through best-effort) y sirve para backup/restore y consulta ad-hoc.

## Las 3 tablas

```
jobs            job_id PK · concurso_id · estado · datos JSONB · creado_en · actualizado_en
documentos      (clave, tipo) PK · datos JSONB · actualizado_en
                tipo ∈ espejo | enriquecimiento | decisiones (clave=job_id)
                       | concurso (clave=concurso_id)
profesionales   (job_id, n_prof) PK · nombre/colegiatura/cargo (+ *_norm) · datos JSONB
```

El DDL completo vive en `repositorio_pg.py::_DDL` (el backend lo aplica solo al
arrancar, `CREATE TABLE IF NOT EXISTS` — sin migrador aparte, coherente con "básico").

### Por qué así (y no 6 tablas ni modelado relacional)

- **`jobs` con `concurso_id`/`estado` planos**: son los DOS únicos filtros reales
  del sistema (el panel lista por concurso; el arranque reanuda los `en_proceso`).
  Todo lo demás se lee documento completo por id.
- **`profesionales`**: índice DERIVADO del espejo (se regenera en cada
  `guardar_espejo`, DELETE+INSERT). Alimenta la búsqueda global del panel con un
  `LIKE` sobre columnas pre-normalizadas en Python (`sin_tildes`) — sin depender
  de la extensión `unaccent`. Mismo shape de respuesta que el escaneo de archivos.
- **`documentos` genérica**: espejo/enriquecimiento/decisiones/concurso se leen y
  escriben SIEMPRE completos por id — una tabla por cada uno no aporta nada; el
  par `(clave, tipo)` da upsert idempotente y cero carreras (las decisiones antes
  se escribían con read-modify-write directo a disco desde `app.py`).
- **Binarios fuera de la BD**: Excels, ZIPs y PDFs (`{job}/certs/`,
  `{job}/descargas/`) viven en la carpeta del job. El borrado en disco lo hace
  el primario (archivos); `eliminar()` de Postgres solo limpia sus tablas.
- **`{id}.cui.json`** (descarga suelta por CUI) se queda en archivos: estado
  efímero de una tarea, no dato del negocio.

## Estructura de archivos (la fuente de verdad)

`datos_pivote/` dejó de ser una raíz con todo suelto: cada job tiene SU carpeta.

```
datos_pivote/
  {concurso_id}.concurso.json     ← concursos en la raíz (livianos, pocos)
  {job_id}/
    job.json · espejo.json · enriquecimiento.json · decisiones.json
    claude.xlsx · final.xlsx · infoobras.zip
    certs/ · descargas/
```

La migración del layout viejo (todo suelto) es **automática e idempotente** al
construir `RepositorioArchivos` (arranque del backend): mueve `{id}.tipo` →
`{id}/tipo`. Las descargas sueltas por CUI (`{id}.cui.json`) quedan como están.

## Activación y switch

```
PIVOTE_DB_URL definida   → RepositorioConRespaldo(archivos, Postgres)  (server)
PIVOTE_DB_URL ausente    → RepositorioArchivos a secas  (esta laptop, tests)
```

Con respaldo activo: toda LECTURA va a archivos; toda ESCRITURA va a archivos y
luego, best-effort, a Postgres — si la BD se cae, se loguea y **el análisis
sigue**. El motor y la API no distinguen (protocolo `Repositorio`). `psycopg`
se importa perezoso: sin la variable, la lib ni se carga.

En `deploy/docker-compose.yml`: servicio `db` (postgres:16-alpine, volumen
`pgdata`, sin puerto publicado — solo red interna), `DB_PASSWORD` obligatoria en
`deploy/.env`, y el backend arranca `depends_on: db healthy`.

## Sincronizar el respaldo (backfill inicial o tras una caída de la BD)

```bash
docker compose exec backend python scripts/migrar_a_postgres.py
```

Idempotente (upserts): vuelca TODO lo que hay en archivos a Postgres. Sirve para
el backfill inicial y para re-sincronizar si la BD estuvo caída un rato (el
write-through es best-effort y no reintenta).

## Verificación

- Offline (laptop): `tests/test_repositorio.py` — protocolo de decisiones en
  Memoria/Archivos siempre; los tests de Postgres corren solo con
  `PIVOTE_TEST_DB_URL` apuntando a una BD alcanzable (server, o docker local).
- Server: levantar compose → `docker compose ps` (backend healthy implica BD ok),
  correr el backfill, y validar en el panel: histórico visible, búsqueda de
  profesionales, decidir una alerta (escribe en `documentos`).

## Ojo: scripts de operador

Los scripts de `backend/scripts/` (avance_descargas, limpiar_*, resubir_job,
redescargar_documentos, backfill_representante) leen/escriben los JSON de
DATA_DIR **directo**, sin pasar por el repo. Como los archivos son la fuente de
verdad, eso sigue siendo correcto — PERO (1) asumen el layout viejo suelto
(`{id}.espejo.json`), hay que adaptarles la ruta a `{id}/espejo.json` cuando se
usen, y (2) lo que escriban NO llega al respaldo Postgres hasta re-correr
`migrar_a_postgres.py`.

## Qué NO hace (a propósito)

- No modela profesionales/experiencias como entidades relacionales (decisión
  comercial cerrada — la tabla `profesionales` es un índice de búsqueda, no un modelo).
- No mueve el caché SUNAT ni los binarios a la BD.
- No se LEE de Postgres en operación normal (solo restore/consulta ad-hoc) —
  por eso la búsqueda de profesionales del panel escanea archivos (la verdad);
  la tabla índice queda como copia consultable.
- No versiona documentos (la última escritura gana, igual que los archivos).
