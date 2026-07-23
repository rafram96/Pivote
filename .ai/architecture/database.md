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

---

## Base de Referencia MEF (ETL y Datos Abiertos)

### Estructura de Origen (Datos Abiertos MEF)
El script de ingesta `backend/scripts/actualizar_base_mef.py` descarga y consolida semanalmente los 3 datasets de Datos Abiertos del Banco de Inversiones del MEF (`https://fs.datosabiertos.mef.gob.pe/datastorefiles/`):

1. **`DETALLE_INVERSIONES.csv`** (68 columnas): Inversiones **ACTIVAS** (costos actualizados, devengados, PIM, expediente técnico, avance físico, ubicación).
2. **`CIERRE_INVERSIONES.csv`** (57 columnas): Inversiones **CERRADAS** / culminadas (fechas de cierre, liquidación, transferencia).
3. **`INVERSIONES_DESACTIVADAS.csv`** (42 columnas): Inversiones **DESACTIVADAS** o anuladas por OPMI/UF.

### Volumen Auditado y Artefactos Locales
* **Volumen Total**: ~494,297 registros de inversiones consolidados y ~452,792 CUIs/SNIPs distintos a nivel nacional.
* **Catálogo de Entidades**: 11,004 entidades públicas registradas y extracción automática de siglas (`- AGN`, `- INABIF`, etc.).
* **Ubicación en disco**: `PIVOTE_DATA_DIR/referencia/mef/`:
  * `inversiones.csv.gz` (~26 MB comprimido): `cui`, `snip`, `nombre`, `estado_dataset` (ACTIVO/CERRADA/DESACTIVADA), `situacion`, `ubigeo`, `dpto`, `prov`, `dist`, `entidad`.
  * `entidades_publicas.csv` (544 KB): catálogo de entidades y siglas.
  * `metadata.json`: fecha de corte, recuentos de filas por fuente y URLs de origen.

### Reglas del ETL
* **Escritura Atómica**: Genera archivos `.tmp` y aplica `os.replace` únicamente si la validación de volumen pasa (unión ≥ 400,000 filas y fuentes ≥ 50,000 filas). Si la descarga falla o el MEF emite un archivo trunco, se conserva la versión limpia previa.
* **Modo Offline**: Admite `--desde-dir DIR` para procesar copias locales de los CSV sin red.
* **Consumo en Memoria**: El backend lo consume vía el singleton `resolucion/base_mef.py` — cifra de RAM y técnica (sys.intern + índice invertido): ver `architecture/backend.md` (fuente única). Si la base falta, degrada de forma segura a InfoObras-solo.

---

## Resolución de Certificados de Experiencia y Códigos SNIP vs CUI

### Tratamiento de SNIP vs CUI
* **SNIP** (Sistema antiguo, pre-2017): 5 a 6 dígitos (ej. `373827`).
* **CUI** (Invierte.pe, post-2017): 7 dígitos (ej. `2334685`).
* Los certificados de experiencia antiguos suelen citar "Código SNIP 373827". El índice local resuelve la equivalencia **`SNIP ↔ CUI`** de forma inmediata, convirtiendo códigos SNIP antiguos al CUI oficial vigente.

### Procesamiento de Nombres de Certificados
* **Limpieza de Envoltorios**: Certificados con fórmulas tipo *"Elaboración de Expediente Técnico para..."* o *"Servicio de Consultoría de Obra..."* son limpiados en `resolucion/texto.py` para aislar el nombre propio de la inversión.
* **Agrupación de Localidades**: En certificados que agrupan proyectos o localidades (*"Comunidades Nativas de Mamayaque y Huampani"*), la búsqueda por raras selecciones de tokens y ubicación (Departamento/Provincia/Distrito) desglosa y matchea los proyectos individuales registrados en el MEF.
* **Fusión con Entidad Emisora**: El emisor del certificado (RUC o Razón Social de la municipalidad/GORE) actúa como filtro decisivo para desempatar homónimos.

---

## PROPUESTA NO IMPLEMENTADA — esquema PostgreSQL (`pg_trgm` + FTS) — requiere ADR si se decide adoptar

> ⚠ Nada de esta sección ni de la siguiente («Recomendaciones») existe en el
> código. Hoy el índice es en memoria SIN Postgres (ADR-002, que dejó
> pg_trgm como alternativa reevaluable) y rige la regla de `backend.md`:
> no añadir pg_trgm/sqlalchemy/etc. sin ADR. Se documenta como idea futura.

Para entornos multi-worker o escalamiento horizontal, se define el siguiente esquema optimizado con soporte para trigramas y Full Text Search:

```sql
-- Extensiones requeridas
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;

-- Tabla Principal de Inversiones del MEF
CREATE TABLE IF NOT EXISTS mef_inversiones (
    cui                     VARCHAR(12) PRIMARY KEY,
    snip                    VARCHAR(12),
    nombre_inversion        TEXT NOT NULL,
    nombre_norm             TEXT NOT NULL, -- Mayúsculas, sin tildes ni puntuación
    estado_dataset          VARCHAR(20) NOT NULL, -- 'ACTIVO', 'CERRADA', 'DESACTIVADA'
    situacion               VARCHAR(100),
    
    -- Entidad Ejecutora
    entidad                 VARCHAR(250) NOT NULL,
    entidad_norm            VARCHAR(250) NOT NULL,
    
    -- Ubicación Geográfica
    ubigeo                  VARCHAR(6),
    departamento            VARCHAR(50),
    provincia               VARCHAR(50),
    distrito                VARCHAR(50),
    
    -- Datos Financieros
    monto_viable            NUMERIC(15,2),
    costo_actualizado       NUMERIC(15,2),
    
    -- Full Text Search
    tsv_nombre              tsvector GENERATED ALWAYS AS (
                                to_tsvector('spanish', unaccent(nombre_inversion))
                            ) STORED
);

-- Tabla Auxiliar de Entidades y Siglas
CREATE TABLE IF NOT EXISTS mef_entidades (
    id                      SERIAL PRIMARY KEY,
    entidad                 TEXT NOT NULL,
    entidad_norm            TEXT NOT NULL,
    sigla                   VARCHAR(20)
);

-- ÍNDICES DE ALTO RENDIMIENTO
CREATE INDEX IF NOT EXISTS idx_mef_snip ON mef_inversiones(snip) WHERE snip IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_mef_nombre_trgm ON mef_inversiones USING gin (nombre_norm gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_mef_entidad_trgm ON mef_inversiones USING gin (entidad_norm gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_mef_siglas ON mef_entidades(sigla) WHERE sigla IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_mef_ubigeo ON mef_inversiones(ubigeo);
CREATE INDEX IF NOT EXISTS idx_mef_tsv ON mef_inversiones USING gin (tsv_nombre);
```

### Consulta SQL Tipo (Búsqueda por Similitud):
```sql
SET LOCAL pg_trgm.similarity_threshold = 0.35;

SELECT 
    cui, snip, nombre_inversion, entidad, departamento, provincia, distrito, estado_dataset,
    similarity(nombre_norm, 'CONSTRUCCION INFRAESTRUCTURA EDUCATIVA MAMAYAQUE CENEPA') AS score
FROM mef_inversiones
WHERE 
    nombre_norm % 'CONSTRUCCION INFRAESTRUCTURA EDUCATIVA MAMAYAQUE CENEPA'
    AND (departamento = 'AMAZONAS' OR departamento IS NULL)
ORDER BY score DESC, cui ASC
LIMIT 10;
```

---

## PROPUESTA NO IMPLEMENTADA — recomendaciones asociadas (dependen del esquema anterior)

> ⚠ Igual que arriba: ideas, no estado actual. Los tiempos son proyecciones
> sin medir. OJO con la recomendación 2: paralelizar llamadas contra los
> portales estatales CONTRADICE la práctica pagada de
> `memory/recurring_patterns.md` («secuencial, nunca paralelo contra el
> mismo portal») — si se adopta, la paralelización válida sería solo sobre
> la BD local, jamás sobre InfoObras/SUNAT/MEF en vivo.

### 1. Búsqueda en 2 Etapas (SQL + Python Identity Scoring)
* **Etapa 1 (Filtro SQL Trigrama < 20 ms)**: PostgreSQL devuelve los Top 30 candidatos con mejor similitud de texto.
* **Etapa 2 (Python)**: El resolver `resolucion/cui.py` aplica los candados de abstención (ADR-005), verificación de emisor en SUNAT y contraste de expedientes en vivo.

### 2. Paralelización de Evaluaciones ($N$ Profesionales $\times$ $M$ Experiencias)
* Al evaluar un concurso con 15 profesionales y 80 experiencias totales, la resolución y verificación de red debe lanzarse en paralelo mediante `asyncio.gather` y `ThreadPoolExecutor`.
* **Tiempo Secuencial**: ~60–120 segundos.
* **Tiempo Paralelo**: **~1.5–3.0 segundos** para todo el expediente.
* PostgreSQL permite que decenas de consultas concurrentes se resuelvan simultáneamente sin duplicar la RAM del servidor.

### 3. Actualización de Datos Sin Tiempo de Inactividad (Zero-Downtime Swap)
El proceso de carga del ETL semanal en PostgreSQL debe usar tablas staging:
1. Insertar la nueva carga en `mef_inversiones_staging` y construir sus índices.
2. Intercambiar las tablas atómicamente en una sola transacción SQL (`BEGIN; ALTER TABLE ... RENAME; COMMIT;`). Ninguna consulta de la API se bloquea o falla durante la actualización.

---

## Datos que NO van a la BD ni al repo

Binarios (xlsx/ZIP/PDF) quedan en el volumen de archivos. PDFs/datos del
cliente jamás se commitean. `datos_pivote/` está gitignored.
