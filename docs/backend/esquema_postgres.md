# Esquema PostgreSQL — persistencia del pivote

> **Status**: ✓ implementado (`backend/orquestador/repositorio_pg.py`) · 2026-07-10
> **Decisión marco**: Postgres **básico** (2026-06-25, contraparte de no cobrar el
> addendum): espejo JSONB de los documentos actuales, **sin modelado relacional**.
> **Decisión de recorte** (2026-07-10, con el usuario): 3 tablas — `jobs` +
> `profesionales` + `documentos` genérica — en vez de una tabla por documento.

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
- **Binarios fuera de la BD**: Excels, ZIPs y PDFs (`{job}.certs/`,
  `{job}.descargas/`) siguen en el volumen `datos_pivote`. `eliminar()` limpia
  tablas Y disco.
- **`{id}.cui.json`** (descarga suelta por CUI) se queda en archivos: estado
  efímero de una tarea, no dato del negocio.

## Activación y switch

```
PIVOTE_DB_URL definida   → RepositorioPostgres (server; compose la inyecta)
PIVOTE_DB_URL ausente    → RepositorioArchivos (esta laptop, tests offline)
```

El motor y la API no distinguen (protocolo `Repositorio`). `psycopg` se importa
perezoso: sin la variable, la lib ni se carga (la laptop no la necesita instalada).

En `deploy/docker-compose.yml`: servicio `db` (postgres:16-alpine, volumen
`pgdata`, sin puerto publicado — solo red interna), `DB_PASSWORD` obligatoria en
`deploy/.env`, y el backend arranca `depends_on: db healthy`.

## Migración de los datos existentes

```bash
docker compose exec backend python scripts/migrar_a_postgres.py
```

Idempotente (upserts). Migra concursos, jobs, espejos (indexando profesionales),
enriquecimientos y decisiones desde los `*.json` de DATA_DIR. Los `.json` viejos
NO se borran: quedan como respaldo hasta verificar el panel.

## Verificación

- Offline (laptop): `tests/test_repositorio.py` — protocolo de decisiones en
  Memoria/Archivos siempre; los tests de Postgres corren solo con
  `PIVOTE_TEST_DB_URL` apuntando a una BD alcanzable (server, o docker local).
- Server: levantar compose → `docker compose ps` (backend healthy implica BD ok),
  correr el backfill, y validar en el panel: histórico visible, búsqueda de
  profesionales, decidir una alerta (escribe en `documentos`).

## Qué NO hace (a propósito)

- No modela profesionales/experiencias como entidades relacionales (decisión
  comercial cerrada — la tabla `profesionales` es un índice de búsqueda, no un modelo).
- No mueve el caché SUNAT ni los binarios a la BD.
- No versiona documentos (la última escritura gana, igual que los archivos).
