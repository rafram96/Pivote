# Modelo de datos — PostgreSQL (plan)

Hoy la persistencia es en **archivos** (`{job}.espejo.json` + `{job}.enriquecimiento.json`
+ `{job}.job.json` por análisis). El contrato pide **PostgreSQL**. Este doc define el
modelo y la migración, sin reescribir el sistema.

---

## Las entidades (de mayor a menor)
Tu intuición es correcta — el corazón son **profesionales** y **experiencias**, colgando
de la **propuesta/análisis**:

```
concurso ──1:N── analisis ──1:1── postor (la propuesta)
                    │
                    ├──1:N── profesional ──1:N── experiencia      ← el núcleo
                    │
                    └──1:N── observacion (alertas)
```

| Entidad | Qué es | Clave |
|---|---|---|
| **concurso** | la licitación | nomenclatura, entidad, objeto, fecha de ofertas |
| **analisis** | una corrida del sistema (1 propuesta evaluada) | estado, fechas, descargas_estado |
| **postor** | el que presenta (la propuesta / consorcio) | detalle, representante, oferta, consorciados, ISOs, experiencia 3.4 |
| **profesional** ⭐ | cada profesional clave evaluado | cargo, nombre, DNI, colegiatura, **veredicto** (cumple), años adicionales |
| **experiencia** | cada periodo de obra del profesional | proyecto, fechas, **días declarados/efectivos**, cargo, **CUI**, veredictos |
| **observacion** | alertas del análisis | severidad, tipo, mensaje |

---

## Estrategia recomendada: **híbrido (tablas + JSONB)**
No conviene normalizar TODO en 20 tablas hijas (valorizaciones, paralizaciones,
razones literales cambian de forma con el contrato espejo). La regla:

- **Tabla real** para lo que se **filtra, busca o lista** → permite el histórico y las
  búsquedas del panel.
- **JSONB** para lo **rico y variable que NO se filtra** → mantiene la flexibilidad
  del espejo v1.2.0 sin migrar el schema cada vez.

### Esbozo de tablas
```sql
concurso(
  id PK, nomenclatura, entidad, objeto, fecha_ofertas, creado_en)

analisis(
  id PK, concurso_id FK, postor, estado, descargas_estado,
  creado_en, actualizado_en,
  espejo JSONB,            -- el espejo completo, como respaldo/auditoría
  enriquecimiento JSONB)   -- el cruce del backend (paralizaciones, valorizaciones…)

postor(
  id PK, analisis_id FK, detalle, representante_comun, cumple_34,
  oferta_economica JSONB, consorciados JSONB, isos JSONB,
  experiencia_postor JSONB)            -- el 3.4, hoy manual

profesional(                            -- ⭐ la principal
  id PK, analisis_id FK, n_prof,
  cargo, cargo_bases_num, cargo_bases_nombre,
  nombre, dni, titulo, colegiatura, fecha_colegiatura, profesion_valida,
  cumple TEXT,                          -- el veredicto literal
  anios_adicionales,
  UNIQUE(analisis_id, n_prof))

experiencia(
  id PK, profesional_id FK, n,
  proyecto, cliente, objeto, fecha_inicial, fecha_final,
  dias_declarados, dias_efectivos, cargo_ocupado,
  cui, codigo_infoobras,
  veredictos JSONB,                     -- cargo_bases_valido, tipo_obra, anterior_colegiatura…
  paralizaciones JSONB, valorizaciones JSONB,
  UNIQUE(profesional_id, n))

observacion(
  id PK, analisis_id FK, severidad, tipo, mensaje, referencia)
```

### Índices que dan el valor del panel
```sql
CREATE INDEX ON profesional (lower(nombre));   -- buscar a una persona
CREATE INDEX ON profesional (dni);             -- … entre TODOS los concursos
CREATE INDEX ON experiencia (cui);             -- cruzar por obra
CREATE INDEX ON analisis (concurso_id);        -- histórico por concurso
CREATE INDEX ON analisis (creado_en);          -- histórico por fecha
```

> **Bonus de diseño:** como `profesional` es tabla real con índice por **DNI/nombre**,
> podrás **buscar a un mismo profesional entre concursos** (los rosters se reusan —
> lo vimos en datos reales). Eso es una capacidad nueva valiosa, casi gratis con este modelo.

---

## Decisión abierta (para conversar)
**¿`profesional` por análisis, o una persona maestra deduplicada?**
- **v1 (recomendado):** `profesional` es **una fila por aparición** (por análisis).
  Para "ver a una persona entre concursos" se consulta por DNI. Simple, suficiente.
- **v2 (a futuro):** una tabla `persona(dni PK, nombre)` y que `profesional` apunte a
  ella → historial real por persona. Más trabajo; no hace falta para cerrar.

---

## Migración (sin reescribir el sistema)
El backend ya tiene una **interfaz de repositorio** (`RepositorioArchivos`). El cambio
es localizado:
1. Implementar **`RepositorioPostgres`** con la misma interfaz → cambiar **1 línea** en
   `api/app.py` (qué repositorio se instancia).
2. Al persistir un job: guardar `espejo`+`enriquecimiento` como **JSONB** (respaldo) y
   **poblar las tablas** normalizadas (concurso/analisis/postor/profesional/experiencia/observacion).
3. **Script de backfill:** leer los `*.job.json` / `*.espejo.json` existentes en
   `datos_pivote/` e insertarlos en Postgres (no se pierde el histórico ya corrido).
4. Descomentar el servicio **`db`** en `deploy/docker-compose.yml` + `DATABASE_URL` +
   `psycopg2-binary` en requirements.

## Lo que NO va a la base de datos
Los **documentos descargados** (PDFs, ZIP) siguen en **disco / volumen** — son binarios
grandes; la BD solo guarda metadatos y referencias.

## Esfuerzo estimado
~1.5–2 días (repositorio Postgres + tablas + backfill + cablear el compose).
