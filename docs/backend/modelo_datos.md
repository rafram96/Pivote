# Modelo de datos — PostgreSQL (plan)

Hoy la persistencia es en **archivos** (`{job}.espejo.json` + `{job}.enriquecimiento.json`
+ `{job}.job.json`). El contrato pide **PostgreSQL**. Este modelo sigue la **hoja
"Base de Datos"** del Excel: **plano, 1 fila = 1 experiencia**, con el profesional
denormalizado en cada fila (igual que la hoja). Simple y fiel a lo que ya usan.

---

## Las dos tablas

```
analisis  ──1:N──  base_datos   (la hoja "Base de Datos" tal cual)
 (1 corrida)         (1 fila = 1 experiencia)
```

- **`analisis`** — cabecera liviana: agrupa las filas y da el **histórico** (por
  concurso, entidad, fecha). Aquí van también, como JSONB, las cosas que NO son la
  tabla de experiencias (resumen de factores, alertas, datos del postor).
- **`base_datos`** — el corazón: cada fila es una experiencia, con las **25 columnas
  de la hoja** + lo que el backend enriquece.

---

## `base_datos` — mapeo 1:1 con la hoja
Cada columna de la hoja "Base de Datos" es una columna de la tabla:

| # | Columna de la hoja | Columna SQL | Tipo |
|---|---|---|---|
| 1 | CARGO AL QUE POSTULA | `cargo_postula` | text |
| 2 | N° PROF | `n_prof` | int |
| 3 | PROFESIONAL | `profesional` | text |
| 4 | N° COLEGIATURA | `colegiatura` | text |
| 5 | N° EXP | `n_exp` | int |
| 6 | ENTIDAD / EMPRESA EMISORA | `entidad_emisora` | text |
| 7 | PROYECTO U OBRA | `proyecto` | text |
| 8 | CUI | `cui` | text |
| 9 | TIPO DOC | `tipo_doc` | text |
| 10 | NOMBRE DEL EMISOR | `nombre_emisor` | text |
| 11 | CARGO DEL EMISOR | `cargo_emisor` | text |
| 12 | FECHA INICIAL | `fecha_inicial` | date NULL *(+ crudo en `raw`)* |
| 13 | FECHA FINAL | `fecha_final` | date NULL |
| 14 | FECHA EMISIÓN | `fecha_emision` | date NULL |
| 15 | FOLIO | `folio` | text *(puede ser rango "14-32")* |
| 16 | DÍAS | `dias` | numeric |
| 17 | MESES | `meses` | numeric |
| 18 | AÑOS | `anios` | numeric |
| 19 | CARGO QUE OCUPÓ | `cargo_ocupado` | text |
| 20 | ¿CARGO EN BASES? | `cargo_en_bases` | text |
| 21 | ¿ANT. COLEGIAT.? | `ant_colegiatura` | text |
| 22 | ¿INCLUYE COVID? | `incluye_covid` | text |
| 23 | ¿TRASLAPE? | `traslape` | text |
| 24 | ¿TIPO DE OBRA SOLICITADO? | `tipo_obra_solicitado` | text |
| 25 | OBSERVACIONES | `observaciones` | text |

### + lo que el backend agrega (no está en la hoja de Claude)
| Columna SQL | Tipo | Origen |
|---|---|---|
| `cargo_bases_num` / `cargo_bases_nombre` | int / text | a qué cargo de las bases corresponde |
| `cumple_profesional` | text | el veredicto del profesional (de la hoja P) |
| `dias_efectivos` | numeric | **Paso 5** (descuento de paralizaciones) |
| `codigo_infoobras` | text | cruce InfoObras |
| `paralizaciones` | **jsonb** | periodos paralizados (InfoObras) |
| `valorizaciones` | **jsonb** | valorizaciones mensuales |
| `backend` | **jsonb** | el bloque `_backend` (ALT04, vinculación, etc.) |
| `raw` | **jsonb** | la experiencia cruda del espejo (respaldo/auditoría) |

```sql
CREATE TABLE base_datos (
  id              bigserial PRIMARY KEY,
  analisis_id     text NOT NULL REFERENCES analisis(id),
  -- profesional (denormalizado, como en la hoja)
  cargo_postula   text, n_prof int, profesional text, colegiatura text,
  cargo_bases_num int, cargo_bases_nombre text, cumple_profesional text,
  -- experiencia (las 25 columnas)
  n_exp int, entidad_emisora text, proyecto text, cui text, tipo_doc text,
  nombre_emisor text, cargo_emisor text,
  fecha_inicial date, fecha_final date, fecha_emision date, folio text,
  dias numeric, meses numeric, anios numeric,
  cargo_ocupado text, cargo_en_bases text, ant_colegiatura text,
  incluye_covid text, traslape text, tipo_obra_solicitado text, observaciones text,
  -- enriquecido por el backend
  dias_efectivos numeric, codigo_infoobras text,
  paralizaciones jsonb, valorizaciones jsonb, backend jsonb, raw jsonb,
  UNIQUE (analisis_id, n_prof, n_exp)
);
```

---

## `analisis` — la cabecera
```sql
CREATE TABLE analisis (
  id              text PRIMARY KEY,        -- el analisis_id / job_id
  concurso        text,
  entidad         text,
  objeto          text,
  postor          text,
  fecha_ofertas   date,
  estado          text,                    -- recibido | en_proceso | requiere_revision | completado | error
  descargas_estado text,                   -- pendiente | en_progreso | listas | error
  creado_en       timestamptz DEFAULT now(),
  -- lo que NO es la tabla de experiencias, como JSONB:
  resumen         jsonb,    -- factores A/B/C + puntaje (hoja CLAUDE)
  observaciones   jsonb,    -- alertas (severidad/tipo/mensaje)
  postor_data     jsonb,    -- oferta económica, consorciados, experiencia 3.4
  espejo          jsonb     -- el espejo completo (respaldo/auditoría)
);
```

---

## Índices (lo que da valor al panel)
```sql
CREATE INDEX ON base_datos (lower(profesional));  -- buscar a una persona…
CREATE INDEX ON base_datos (cui);                 -- …o cruzar por obra
CREATE INDEX ON base_datos (analisis_id);
CREATE INDEX ON analisis (concurso);
CREATE INDEX ON analisis (creado_en);
```
> **Bonus:** con el índice por `profesional`/`colegiatura` puedes **buscar a la misma
> persona entre concursos** (los rosters se reusan — lo vimos en datos reales). Casi gratis.

## Regla de diseño
- **Columna** = lo que se **filtra, busca o exporta** (las 25 de la hoja + Paso 5).
  Así la hoja "Base de Datos" se reconstruye con un simple `SELECT … FROM base_datos`.
- **JSONB** = lo **rico y variable** (valorizaciones, paralizaciones, `_backend`,
  razones literales). No hay que migrar el schema cuando el contrato evoluciona.

## Trade-off (honesto)
La tabla es **denormalizada**: el profesional se repite en cada fila de experiencia
(igual que la hoja). A tu escala (100–200 análisis/mes, 1 usuario) la redundancia es
trivial y **gana en simplicidad + export directo a Excel**. Si algún día se quiere
historial por persona deduplicado, se agrega una tabla `persona(dni)` — mejora futura,
no hace falta para cerrar.

---

## Migración (sin reescribir el sistema)
1. Implementar **`RepositorioPostgres`** con la misma interfaz que `RepositorioArchivos`
   → cambiar **1 línea** en `api/app.py`.
2. Al persistir: poblar `analisis` (1 fila) + `base_datos` (1 fila por experiencia),
   guardando lo variable en los JSONB.
3. **Backfill:** un script que lee los `*.espejo.json` / `*.enriquecimiento.json`
   existentes en `datos_pivote/` y los inserta (no se pierde el histórico ya corrido).
4. Descomentar el servicio **`db`** en `deploy/docker-compose.yml` + `DATABASE_URL` +
   `psycopg2-binary` en requirements.

## Lo que NO va a la base de datos
Los **documentos descargados** (PDFs, ZIP) siguen en **disco / volumen** — son binarios
grandes; la BD solo guarda metadatos y referencias.

## Esfuerzo estimado
~1.5–2 días (repositorio Postgres + las 2 tablas + backfill + cablear el compose).

---

## ✅ DECISIÓN TOMADA (2026-07-01): esquema HÍBRIDO — ver `backend/db/schema.sql`
> El esquema quedó **diseñado, escrito y VALIDADO** contra un Postgres 16 real
> (Docker efímero con un job real: la vista devolvió las 19 experiencias con
> cui/via/fechas correctos). Es un **híbrido** que costó como la Opción 1 y entrega
> el valor de la 2:
>
> - **4 tablas JSONB** espejo del `Repositorio` (`concursos`, `jobs`, `espejos`,
>   `enriquecimientos`) → el `RepositorioPostgres` es mapeo 1:1 de blobs (~0.5 d).
> - **Columnas generadas** (estado, postor, nomenclatura…) + índices para el panel.
> - **La hoja "Base de Datos" es una VISTA** (`base_datos`) que explota el JSONB con
>   LATERAL — buscable/exportable por SQL, **sin ETL** y siempre consistente. También
>   la vista `analisis` (cabecera del histórico con `pendientes_revision`).
>
> Lo que queda para cablear en el server: `RepositorioPostgres` (blobs 1:1, misma
> interfaz), `psycopg2-binary`, descomentar `db` en el compose, backfill de
> `datos_pivote/`. Las tablas `analisis`/`base_datos` FÍSICAS de abajo ya no se
> crean — quedaron como VISTAS (misma forma, cero mantenimiento).

### Análisis original de las dos opciones (histórico)

### El desajuste a resolver
La interfaz real `Repositorio` ([`backend/orquestador/repositorio.py`](../../backend/orquestador/repositorio.py))
está orientada a **blobs** (Job / Concurso / espejo / enriquecimiento), no a las tablas
`analisis` + `base_datos` de este doc. Hay **dos formas** de cablear `RepositorioPostgres`:

| | **Opción 1 — Blob JSONB** | **Opción 2 — Modelo completo** ⭐ |
|---|---|---|
| Qué hace | Espeja el `Protocol` actual: 1 tabla JSONB por tipo (`jobs`, `espejos`, `concursos`, `enriquecimientos`) | Las tablas `analisis` + `base_datos` de arriba; explota cada experiencia a fila |
| Cambio en `api/app.py` | 1 línea | 1 línea (misma interfaz) + lógica de mapeo en el repo |
| Cumple el contrato ("usa PostgreSQL") | ✅ | ✅ |
| Búsqueda/filtro/export SQL del panel | ❌ (todo en JSONB) | ✅ tabla buscable, "misma persona entre concursos" |
| Esfuerzo | ~0.5–0.75 d | ~1.5–2 d + backfill |

**Recomendación: Opción 2.** El contrato cobra Postgres y el valor está en la tabla
buscable; la Opción 1 cumple "de nombre" pero no entrega el histórico filtrable que el
panel promete. La Opción 1 solo se justifica si hay que cerrar el hito contra reloj.

### Mapeo de la interfaz `Repositorio` → modelo completo (Opción 2)
| Método del `Protocol` | A dónde va |
|---|---|
| `guardar(job)` / `cargar` / `listar` | fila en `analisis` (cabecera) + estado/descargas |
| `guardar_espejo` / `cargar_espejo` | `analisis.espejo` (JSONB) **y** explotar `experiencias[]` → filas `base_datos` |
| `guardar_enriquecimiento` / `cargar` | merge sobre `base_datos` (dias_efectivos, paralizaciones, valorizaciones, `backend`) |
| `guardar_concurso` / `cargar` / `listar_concursos` | tabla `concursos` (cabecera del concurso; 1:N con `analisis`) |
| `eliminar(job_id)` | `DELETE` en cascada (`analisis`+`base_datos`) **+ borrar binarios de disco** (xlsx/zip/certs — siguen en disco, ver arriba) |
| `eliminar_concurso` | `DELETE` en `concursos` |

> ⚠ `eliminar` hoy borra también artefactos de disco ([`repositorio.py:146`](../../backend/orquestador/repositorio.py)).
> El repo Postgres debe conservar ese borrado de disco — la BD no guarda los binarios.

### Cómo probarlo (por qué necesita el server / un Postgres)
A diferencia del resto de tests offline, este sí necesita una BD:
- Local: `docker run -e POSTGRES_PASSWORD=dev -p 5432:5432 postgres:16` y apuntar
  `DATABASE_URL` ahí; o `testcontainers` en los tests.
- Server: descomentar el servicio `db` del compose (paso 4 de Migración).

### Notas de cableado
- Rama de trabajo: **`dev`** (no `demo`).
- Dependencia nueva: `psycopg2-binary` en `backend/requirements.txt`.
- El motor **no cambia**: depende del `Protocol`, no de la implementación.
