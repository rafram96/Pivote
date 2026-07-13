# Consultas NL → SQL (PostgreSQL del pivote)

> Recetario de preguntas en lenguaje natural con su SQL, **todas probadas contra
> los 25 jobs reales** migrados (2026-07-13). Sirve de base para un futuro
> "Directorio de profesionales" / capa NL2SQL en el panel.
>
> **Modelo de datos** (respaldo lógico):
> - `jobs(job_id, concurso_id, estado, datos jsonb, creado_en, actualizado_en)`
> - `documentos(clave, tipo, datos jsonb, actualizado_en)` — `tipo` ∈ espejo · enriquecimiento · decisiones · concurso. `clave` = job_id (o concurso_id para tipo=concurso).
> - `profesionales(job_id, n_prof, nombre, colegiatura, cargo, nombre_norm, colegiatura_norm, cargo_norm, datos jsonb)` — índice para búsqueda.
> - Lo rico (experiencias, CUIs, valorizaciones, SUNAT) vive dentro del JSONB de `documentos` (espejo/enriquecimiento). Se navega con `jsonb_array_elements` / `jsonb_each`.

---

### 1 · ¿Qué profesionales se repiten en más concursos? (cartera reutilizada)
```sql
select nombre, colegiatura, count(distinct job_id) as concursos
from profesionales
where nombre !~ '^Prof'
group by nombre, colegiatura
order by concursos desc
limit 20;
```

### 2 · ¿Qué profesionales están escritos de forma inconsistente entre concursos?
```sql
select nombre_norm, count(distinct colegiatura) as formas_distintas
from profesionales
group by nombre_norm
having count(distinct colegiatura) > 1
order by formas_distintas desc;
```

### 3 · ¿Qué especialidades (cargos) son las más frecuentes?
```sql
select cargo, count(*) as veces
from profesionales
where nombre !~ '^Prof'
group by cargo
order by veces desc;
```

### 4 · ¿Qué concursos tienen más personal clave?
```sql
select datos->'_meta'->>'concurso' as concurso,
       jsonb_array_length(datos->'profesionales') as n_profesionales
from documentos
where tipo = 'espejo'
order by n_profesionales desc;
```

### 5 · ¿En qué proyectos participó un profesional? (con su CUI)
```sql
select p->>'nombre'        as profesional,
       e->>'proyecto'      as proyecto,
       e->>'cui'           as cui,
       e->>'fecha_inicial' as inicio,
       e->>'fecha_final'   as fin
from documentos d,
     jsonb_array_elements(d.datos->'profesionales') p,
     jsonb_array_elements(p->'experiencias')        e
where d.tipo = 'espejo'
  and p->>'nombre' ilike '%GUERRA VALLE%';   -- cambiar el nombre
```

### 6 · ¿Cuántas experiencias en total citan un CUI?
```sql
select count(*) as experiencias_con_cui
from documentos d,
     jsonb_array_elements(d.datos->'profesionales') p,
     jsonb_array_elements(p->'experiencias')        e
where d.tipo = 'espejo'
  and e->>'cui' is not null;
```

### 7 · ¿Qué obras (cruzadas con InfoObras) tienen más valorizaciones?
```sql
select e.key                                                as experiencia,
       e.value->>'obra_nombre'                              as obra,
       jsonb_array_length(coalesce(e.value->'valorizaciones','[]')) as valorizaciones
from documentos d,
     jsonb_each(d.datos) e
where d.tipo = 'enriquecimiento'
  and jsonb_typeof(d.datos) = 'object'
  and e.value ? 'obra_nombre'
order by valorizaciones desc
limit 20;
```

### 8 · ¿Cuántas experiencias tienen paralizaciones detectadas?
```sql
select count(*) as experiencias_con_paralizacion
from documentos d,
     jsonb_each(d.datos) e
where d.tipo = 'enriquecimiento'
  and jsonb_typeof(e.value) = 'object'
  and jsonb_array_length(coalesce(e.value->'paralizaciones','[]')) > 0;
```

### 9 · ¿Qué emisores quedaron ambiguos en SUNAT? (varios RUC posibles)
```sql
select e.value->'sunat'->>'nombre'                     as emisor,
       jsonb_array_length(e.value->'sunat'->'candidatos') as ruc_candidatos
from documentos d,
     jsonb_each(d.datos) e
where d.tipo = 'enriquecimiento'
  and jsonb_typeof(e.value) = 'object'
  and (e.value->'sunat'->>'ambiguo')::int > 1;
```

### 10 · ¿Cómo quedaron los análisis por estado?
```sql
select estado, count(*) as n
from jobs
group by estado
order by n desc;
```

---

## Notas para el futuro (la BD maestra "de verdad")
- Estas consultas **funcionan hoy** sobre el respaldo, pero las experiencias viven
  en JSONB, no como filas. Para analítica cross-job robusta conviene una tabla
  `experiencias(job_id, n_prof, n_exp, cui, proyecto, fechas, obra_id, valoriz, …)`.
- La agrupación por `nombre + colegiatura` cuenta como dos a un mismo ingeniero si
  la colegiatura se escribió distinto (`CIP N° 1649…` vs `CIP 1649…`) → normalizar
  la colegiatura es el primer paso de la BD maestra. Ver la idea T-005 (Directorio
  de profesionales) en `docs/comercial/`.
