-- ============================================================================
-- Esquema PostgreSQL del pivote InfoObras — ESPEJO DOCUMENTAL de los DDL reales
--
-- ⚠ ESTE ARCHIVO NO ES FUENTE DE VERDAD. El código lo es.
--    Lo que existe en una BD viva es lo que crean los dos módulos de abajo, y
--    cada uno lo hace solo, sin leer este archivo. Aquí está para poder LEER el
--    esquema completo de un vistazo y para levantarlo a mano (bootstrap,
--    inspección, `pg_dump` de referencia). Si el código y este archivo
--    discrepan, el que miente es este archivo — y hay un test que lo impide:
--    `backend/tests/test_schema_sql.py` compara los bloques marcados
--    `>>> ESPEJO` contra las constantes del código, normalizados.
--
-- Contexto de la decisión (ADR-009, addendum del 2026-08-05): PostgreSQL es
-- OBLIGATORIO en el despliegue, y su uso PRINCIPAL es la base MEF —por eso el
-- schema `mef` va primero—; el respaldo lógico de jobs es el uso secundario.
-- Ambos degradan con gracia si la BD no responde (red de seguridad ante una
-- caída transitoria, NO un modo de operación aceptable).
--
-- Los BINARIOS (xlsx, ZIP, PDFs de certs y descargas) NO van a la BD: viven en
-- disco (`PIVOTE_DATA_DIR`). La BD guarda metadatos y JSON.
--
-- Uso manual:  psql -U pivote -d pivote -f schema.sql   (todo es idempotente)
-- ============================================================================


-- ############################################################################
-- 1 · SCHEMA `mef` — ficha enriquecida del ETL de Datos Abiertos  [PRINCIPAL]
-- ############################################################################
--
-- QUIÉN lo crea: `backend/scripts/actualizar_base_mef.py` (constante `_DDL_PG`).
-- CUÁNDO: al iniciar una carga del ETL, contra la conexión de la carga.
-- POR QUÉ existe: el resolver de CUI busca por nombre en el índice RAM
--   (`inversiones.csv.gz`, ADR-002) y, una vez que tiene un CUI/SNIP candidato,
--   consulta AQUÍ la ficha completa por `(load_id, CUI/SNIP)` para contrastar
--   rubro, entidad, ubicación y montos. Sin PG esa ficha no existe: `BaseMef`
--   degrada al gzip y el análisis sigue, más ciego.
-- CARGAS: `mef.loads` versiona cada corrida; `mef.investments` guarda sus filas
--   (PK compuesta con `load_id`, así que las cargas conviven); `mef.active_load`
--   es un puntero singleton a la publicada. Los artefactos de disco comparten el
--   `load_id`, y el resolver lo toma del manifest → nunca mezcla el índice RAM
--   de una versión con fichas de otra.
-- VOLUMEN real medido (corte 26-jul): 620,985 filas, tabla+índices 719.3 MB.

-- >>> ESPEJO: backend/scripts/actualizar_base_mef.py :: _DDL_PG >>>
CREATE SCHEMA IF NOT EXISTS mef;
CREATE TABLE IF NOT EXISTS mef.loads (
    load_id TEXT PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN ('loading', 'validated', 'published', 'failed')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    metadata JSONB
);
CREATE TABLE IF NOT EXISTS mef.investments (
    load_id TEXT NOT NULL REFERENCES mef.loads(load_id) ON DELETE CASCADE,
    identity_key TEXT NOT NULL,
    cui TEXT,
    snip TEXT,
    nombre TEXT NOT NULL,
    nombre_norm TEXT NOT NULL,
    estado_dataset TEXT NOT NULL,
    estado TEXT,
    situacion TEXT,
    entidad TEXT,
    entidad_norm TEXT,
    ubigeo TEXT,
    dpto TEXT,
    prov TEXT,
    dist TEXT,
    nivel TEXT,
    sector TEXT,
    funcion TEXT,
    tipo_inversion TEXT,
    tipologia TEXT,
    modalidad TEXT,
    monto_viable NUMERIC(18,2),
    costo_actualizado NUMERIC(18,2),
    fecha_registro TEXT,
    fecha_viabilidad TEXT,
    expediente_tecnico TEXT,
    opmi TEXT,
    uf TEXT,
    uei TEXT,
    uep TEXT,
    fuente TEXT NOT NULL,
    fila_origen INTEGER NOT NULL,
    PRIMARY KEY (load_id, identity_key)
);
CREATE INDEX IF NOT EXISTS mef_investments_cui_idx
    ON mef.investments(load_id, cui) WHERE cui <> '';
CREATE INDEX IF NOT EXISTS mef_investments_snip_idx
    ON mef.investments(load_id, snip) WHERE snip <> '';
CREATE INDEX IF NOT EXISTS mef_investments_entidad_idx
    ON mef.investments(load_id, entidad_norm);
CREATE TABLE IF NOT EXISTS mef.active_load (
    singleton BOOLEAN PRIMARY KEY DEFAULT TRUE CHECK (singleton),
    load_id TEXT NOT NULL REFERENCES mef.loads(load_id),
    published_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- <<< FIN ESPEJO <<<

-- Notas de lectura del schema `mef` (no son DDL):
--   · `identity_key` es la identidad de la fila (CUI si lo hay, si no el SNIP):
--     el ETL reconcilia el total de identidades antes de marcar `validated`.
--   · `estado_dataset` distingue ACTIVO / CERRADA / DESACTIVADA — es señal de
--     DESEMPATE del resolver, jamás filtro (hay verdades auditadas que viven en
--     filas DESACTIVADA: un CUI reformulado y un certificado que cita al viejo).
--   · `nombre_norm` / `entidad_norm` se normalizan en Python (mayúsculas, sin
--     tildes) — no hay `pg_trgm` ni `unaccent` y no se añaden sin ADR.
--   · Las fechas viajan como TEXT a propósito: el origen es CSV heterogéneo y
--     castearlas en la carga perdería filas.
--   · Las coordenadas se excluyen (decisión de la ficha v1, ADR-009).
--
-- Publicación de una carga (`actualizar_base_mef.py`), en orden:
--   1. staging en disco (gzip, catálogo, metadata);
--   2. COPY a `mef.investments` + reconciliación de identidades;
--   3. `mef.loads.status = 'validated'`;
--   4. manifest de disco por `os.replace`;
--   5. `mef.active_load` en una transacción.
-- Retención: se conservan las 2 últimas cargas (`RETENER_CARGAS`).


-- ############################################################################
-- 2 · Respaldo lógico del orquestador (3 tablas)              [SECUNDARIO]
-- ############################################################################
--
-- QUIÉN lo crea: `backend/orquestador/repositorio_pg.py` (constante `_DDL`).
-- CUÁNDO: en el PRIMER USO que de verdad conecta (`RepositorioPostgres.abrir()`,
--   conexión perezosa desde el 2026-08-05) — NO en el import de `api/app.py`.
--   Si Postgres no responde al arrancar, queda UN warning, el respaldo se
--   desactiva en esa corrida y el backend opera 100% sobre archivos.
-- POR QUÉ existe: NO reemplaza a los archivos. Cada job es una carpeta en
--   `PIVOTE_DATA_DIR` y esa es la fuente de verdad; estas tablas la espejan vía
--   `RepositorioConRespaldo` (write-through best-effort) para tener respaldo
--   restaurable, copia consultable por SQL y la búsqueda global del panel.
-- DEUDA CONOCIDA (ADR-009 addendum, sondeos B01/B02): el write-through no tiene
--   cola de re-sincronización ni marca de desincronizado, y con PG caído a
--   mitad de job cada escritura bloquea hasta el timeout del pool. El único
--   mitigador es correr `backend/scripts/migrar_a_postgres.py` A MANO (upserts;
--   no borra filas huérfanas de un `eliminar()` perdido).

-- >>> ESPEJO: backend/orquestador/repositorio_pg.py :: _DDL >>>
CREATE TABLE IF NOT EXISTS jobs (
    job_id          text PRIMARY KEY,
    concurso_id     text,
    estado          text,
    datos           jsonb NOT NULL,
    creado_en       timestamptz,
    actualizado_en  timestamptz
);
CREATE INDEX IF NOT EXISTS jobs_concurso_idx ON jobs (concurso_id);
CREATE INDEX IF NOT EXISTS jobs_estado_idx   ON jobs (estado);

CREATE TABLE IF NOT EXISTS documentos (
    clave           text NOT NULL,
    tipo            text NOT NULL,
    datos           jsonb NOT NULL,
    actualizado_en  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (clave, tipo)
);

CREATE TABLE IF NOT EXISTS profesionales (
    job_id           text NOT NULL,
    n_prof           int  NOT NULL,
    nombre           text,
    colegiatura      text,
    cargo            text,
    nombre_norm      text,
    colegiatura_norm text,
    cargo_norm       text,
    datos            jsonb NOT NULL,
    PRIMARY KEY (job_id, n_prof)
);
CREATE INDEX IF NOT EXISTS profesionales_nombre_idx ON profesionales (nombre_norm);
-- <<< FIN ESPEJO <<<

-- Notas de lectura del respaldo lógico (no son DDL):
--   · `jobs.concurso_id` y `jobs.estado` son columnas PLANAS que Python rellena
--     desde el blob al guardar (no son GENERATED). Son los DOS únicos filtros
--     reales del sistema: listar por concurso y reanudar `en_proceso` al
--     arrancar. Todo lo demás se lee del JSONB `datos`.
--   · `documentos` es un almacén JSONB genérico por `(clave, tipo)`: un mismo
--     `job_id` tiene filas `espejo`, `enriquecimiento` y `decisiones`, y el
--     `concurso_id` tiene su fila `concurso`. No hay una tabla por documento.
--   · `profesionales` es un índice DERIVADO del espejo, no un dato original: se
--     regenera entero (DELETE + INSERT en una transacción) cada vez que se
--     guarda el espejo del job. Las columnas `*_norm` se normalizan en Python
--     para poder buscar con un LIKE indexable, sin extensiones de PG.
--   · `buscar_profesionales()` es el ÚNICO consumidor que LEE de PostgreSQL
--     (sondeo B05); todas las demás lecturas van a archivos.
--   · `eliminar(job_id)` borra en las 3 tablas; los binarios los borra el
--     repositorio primario (archivos).


-- ============================================================================
-- Lo que este archivo YA NO declara, y por qué
-- ----------------------------------------------------------------------------
-- Hasta el 2026-08-05 aquí vivía un esquema ASPIRACIONAL que nadie ejecutaba:
-- tablas `concursos`, `espejos` y `enriquecimientos`, columnas GENERATED, las
-- funciones `fecha_segura`/`numero_seguro` y dos vistas (`base_datos`,
-- `analisis`) que consultaban tablas que ningún DDL real crea. Aplicarlo sobre
-- una BD viva levantaba un esquema paralelo muerto, y sus vistas no funcionaban
-- contra las tablas reales (sondeo B04).
--
-- Se eliminó por decisión explícita, no por olvido: la documentación del
-- proyecto ya se corrigió (T-TAREA-001) para dejar de listar «la vista SQL»
-- como consumidor del contrato del resolver — esa vista nunca existió en
-- ninguna BD real. Si alguna vez se quiere una vista que explote el espejo,
-- entra por ADR y por el código, no reapareciendo aquí.
-- ============================================================================
