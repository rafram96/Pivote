-- ============================================================================
-- Esquema PostgreSQL del pivote InfoObras — versión BÁSICA acordada (2026-06-25)
-- con vistas que entregan el valor del "modelo completo" sin su costo.
--
-- Diseño (híbrido de las opciones de docs/backend/modelo_datos.md):
--   · 4 tablas JSONB que ESPEJAN la interfaz `Repositorio` (concursos, jobs,
--     espejos, enriquecimientos) → `RepositorioPostgres` es un mapeo 1:1 de
--     blobs, sin lógica de explosión en Python (~0.5 d de cableado).
--   · Columnas GENERADAS sobre el JSONB para lo que se filtra/lista (estado,
--     nomenclatura, postor, fechas) → índices reales sin duplicar datos.
--   · La hoja "Base de Datos" (1 fila = 1 experiencia, 25 columnas) es una
--     VISTA que explota el JSONB con LATERAL → buscable/exportable por SQL,
--     siempre consistente con el espejo, cero ETL.
--
-- Los BINARIOS (xlsx, ZIP, PDFs de certs y descargas) NO van a la BD: siguen
-- en disco/volumen (`PIVOTE_DATA_DIR`); la BD guarda metadatos y JSON.
--
-- Uso:  psql -U infoobras -d infoobras -f schema.sql   (idempotente)
-- ============================================================================

-- ── Helpers de cast seguro (el JSON puede traer null/texto sucio) ───────────
CREATE OR REPLACE FUNCTION fecha_segura(t text) RETURNS date
LANGUAGE sql IMMUTABLE RETURNS NULL ON NULL INPUT AS $$
  SELECT CASE WHEN t ~ '^\d{4}-\d{2}-\d{2}' THEN substring(t, 1, 10)::date END
$$;

CREATE OR REPLACE FUNCTION numero_seguro(t text) RETURNS numeric
LANGUAGE sql IMMUTABLE RETURNS NULL ON NULL INPUT AS $$
  SELECT CASE WHEN t ~ '^-?\d+(\.\d+)?$' THEN t::numeric END
$$;

-- ── 1 · concursos — cabecera del concurso (1:N con jobs) ────────────────────
CREATE TABLE IF NOT EXISTS concursos (
  concurso_id    text PRIMARY KEY,
  datos          jsonb NOT NULL,          -- el .concurso.json tal cual
  nomenclatura   text GENERATED ALWAYS AS (datos->>'nomenclatura') STORED,
  creado_en      timestamptz NOT NULL DEFAULT now(),
  actualizado_en timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE concursos IS 'Cabecera del concurso (blob JSONB, espejo de guardar_concurso)';

-- ── 2 · jobs — el registro del análisis (cabecera liviana) ──────────────────
CREATE TABLE IF NOT EXISTS jobs (
  job_id           text PRIMARY KEY,
  concurso_id      text REFERENCES concursos(concurso_id) ON DELETE CASCADE,
  datos            jsonb NOT NULL,        -- el .job.json tal cual (etapas, items_revision…)
  estado           text GENERATED ALWAYS AS (datos->>'estado') STORED,
  descargas_estado text GENERATED ALWAYS AS (datos->>'descargas_estado') STORED,
  postor           text GENERATED ALWAYS AS (datos->>'postor') STORED,
  origen           text GENERATED ALWAYS AS (datos->>'origen') STORED,
  creado_en        timestamptz NOT NULL DEFAULT now(),
  actualizado_en   timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE jobs IS 'Job del pipeline (blob JSONB, espejo de guardar/cargar/listar). El repo rellena concurso_id desde datos al guardar';

-- ── 3 · espejos — el JSON espejo de la skill (el dato fuente) ────────────────
CREATE TABLE IF NOT EXISTS espejos (
  job_id         text PRIMARY KEY REFERENCES jobs(job_id) ON DELETE CASCADE,
  datos          jsonb NOT NULL,          -- el .espejo.json completo (v1.2.0)
  actualizado_en timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE espejos IS 'JSON espejo v1.2.0 producido por la skill (blob, espejo de guardar_espejo)';

-- ── 4 · enriquecimientos — lo que el backend agrega por experiencia ─────────
CREATE TABLE IF NOT EXISTS enriquecimientos (
  job_id         text PRIMARY KEY REFERENCES jobs(job_id) ON DELETE CASCADE,
  datos          jsonb NOT NULL,          -- {"n_prof:n_exp": {cui, via, obra, paralizaciones, valorizaciones, …}}
  actualizado_en timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE enriquecimientos IS 'Enriquecimiento por experiencia, clave "n_prof:n_exp" (espejo de guardar_enriquecimiento)';

-- ── Índices (lo que el panel filtra/lista; a esta escala, pocos y baratos) ──
CREATE INDEX IF NOT EXISTS jobs_concurso_idx  ON jobs (concurso_id);
CREATE INDEX IF NOT EXISTS jobs_estado_idx    ON jobs (estado);
CREATE INDEX IF NOT EXISTS jobs_creado_idx    ON jobs (creado_en DESC);
CREATE INDEX IF NOT EXISTS concursos_nom_idx  ON concursos (lower(nomenclatura));

-- ============================================================================
-- VISTA base_datos — la hoja "Base de Datos" del Excel (1 fila = 1 experiencia,
-- las 25 columnas + lo enriquecido). Explota el espejo con LATERAL y hace join
-- del enriquecimiento por la clave "n_prof:n_exp". Siempre al día con el blob.
--   · buscar a una persona ENTRE concursos:  WHERE profesional ILIKE '%…%'
--   · cruzar por obra:                        WHERE cui = '…'
--   · exportar la hoja:                       SELECT * WHERE job_id = '…'
-- ============================================================================
CREATE OR REPLACE VIEW base_datos AS
SELECT
  e.job_id,
  j.concurso_id,
  j.postor,
  -- profesional (denormalizado, como en la hoja)
  (prof->>'cargo')                                   AS cargo_postula,
  (prof->>'n_prof')::int                             AS n_prof,
  (prof->>'nombre')                                  AS profesional,
  (prof->>'colegiatura')                             AS colegiatura,
  numero_seguro(prof->>'cargo_bases_num')::int       AS cargo_bases_num,
  (prof->>'cargo_bases_nombre')                      AS cargo_bases_nombre,
  (prof->>'cumple')                                  AS cumple_profesional,
  -- experiencia (las columnas de la hoja)
  (exp->>'n')::int                                   AS n_exp,
  (exp->>'entidad_emisora')                          AS entidad_emisora,
  (exp->>'proyecto')                                 AS proyecto,
  COALESCE(enr_e->>'cui', exp->>'cui')               AS cui,   -- el resuelto pisa al citado
  (exp->>'tipo_documento')                           AS tipo_doc,
  (exp->>'nombre_emisor')                            AS nombre_emisor,
  (exp->>'cargo_emisor')                             AS cargo_emisor,
  fecha_segura(exp->>'fecha_inicial')                AS fecha_inicial,
  fecha_segura(exp->>'fecha_final')                  AS fecha_final,
  fecha_segura(exp->>'fecha_emision')                AS fecha_emision,
  (exp->>'folio')                                    AS folio,
  numero_seguro(exp->>'dias')                        AS dias,
  numero_seguro(exp->>'meses')                       AS meses,
  numero_seguro(exp->>'anios')                       AS anios,
  (exp->>'cargo_ocupado')                            AS cargo_ocupado,
  (exp->>'cargo_bases_valido')                       AS cargo_en_bases,
  (exp->>'anterior_colegiatura')                     AS ant_colegiatura,
  (exp->>'incluye_covid')                            AS incluye_covid,
  (exp->>'traslape')                                 AS traslape,
  (exp->>'tipo_obra_valido')                         AS tipo_obra_solicitado,
  (exp->>'observaciones')                            AS observaciones,
  -- enriquecido por el backend (join por "n_prof:n_exp")
  (enr_e->>'via')                                    AS cui_via,
  (enr_e->>'codigo_infoobras')                       AS codigo_infoobras,
  (enr_e->>'obra_nombre')                            AS obra_infoobras,
  (enr_e->'obra')                                    AS obra,            -- jsonb
  (enr_e->'paralizaciones')                          AS paralizaciones,  -- jsonb
  (enr_e->'valorizaciones')                          AS valorizaciones,  -- jsonb
  (enr_e->'candidatos')                              AS candidatos,      -- jsonb (alternativas del resolver)
  (exp->'_backend')                                  AS backend,         -- jsonb
  exp                                                AS raw              -- la experiencia cruda (auditoría)
FROM espejos e
JOIN jobs j USING (job_id)
CROSS JOIN LATERAL jsonb_array_elements(e.datos->'profesionales') AS prof
CROSS JOIN LATERAL jsonb_array_elements(prof->'experiencias')     AS exp
LEFT JOIN enriquecimientos en USING (job_id)
CROSS JOIN LATERAL (
  SELECT en.datos -> ((prof->>'n_prof') || ':' || (exp->>'n'))
) AS enr(enr_e);

COMMENT ON VIEW base_datos IS 'La hoja "Base de Datos" (1 fila = 1 experiencia) explotada del espejo + enriquecimiento. Sin ETL: siempre consistente con los blobs';

-- ── VISTA analisis — la cabecera para el histórico del panel ─────────────────
CREATE OR REPLACE VIEW analisis AS
SELECT
  j.job_id,
  j.concurso_id,
  c.nomenclatura                                     AS concurso,
  j.postor,
  j.estado,
  j.descargas_estado,
  j.origen,
  fecha_segura(c.datos->>'fecha_presentacion')       AS fecha_ofertas,
  j.creado_en,
  (e.datos->'resumen_evaluacion')                    AS resumen,        -- jsonb (factores + puntaje)
  (j.datos->'observaciones')                         AS observaciones,  -- jsonb (alertas)
  (e.datos->'postor')                                AS postor_data,    -- jsonb (oferta, consorciados)
  (SELECT count(*)
     FROM jsonb_array_elements(coalesce(j.datos->'items_revision', '[]'::jsonb)) it
    WHERE NOT coalesce((it->>'resuelto')::boolean, false)) AS pendientes_revision
FROM jobs j
LEFT JOIN concursos c USING (concurso_id)
LEFT JOIN espejos   e USING (job_id);

COMMENT ON VIEW analisis IS 'Cabecera de cada análisis para el histórico filtrable del panel';
