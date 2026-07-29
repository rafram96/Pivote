# ADR-009 · ETL MEF serving-first: índice RAM + fichas SQLite

- Fecha: 2026-07-23; decisión revisada 2026-07-29
- Estado: **ACEPTADO**

## Contexto

ADR-002 creó un archivo compacto y un índice RAM para buscar inversiones por
nombre sin depender de la red. El resolver ya consume esa base para proponer
candidatos, comprobar CUI/SNIP y reconocer entidades públicas.

El objetivo inmediato no es explotar históricamente las 95 columnas del MEF:
es aumentar la precisión del resolver con una ficha oficial más rica una vez
que existe un CUI candidato. La RAM no es una restricción, pero tampoco conviene
cargar en ella campos que solo se consultan por clave exacta.

El EDA real del corte 2026-07-26 encontró 620,985 filas, 579,481 CUIs y una sola
identidad duplicada. CUI, o SNIP cuando no existe CUI, permite un lookup local
simple. PostgreSQL añadiría operación y dependencia sin aportar una ventaja
material a este caso de uso inmediato.

## Decisión

El ETL publica dos representaciones coordinadas:

1. `inversiones.csv.gz`, cargado en RAM, conserva el índice invertido y la
   búsqueda difusa por nombre.
2. `inversiones.sqlite`, indexado por CUI y SNIP, conserva la ficha enriquecida
   que se consulta después de identificar un candidato.

Ambos artefactos, el catálogo de entidades y la metadata pertenecen a un mismo
`load_id`. Cada carga vive en un directorio inmutable y `manifest.json` cambia
atómicamente el puntero a la versión activa. `BaseMef` detecta el cambio y
recarga su índice sin reiniciar el backend.

La ficha SQLite v1 incluye identidad, nombre, estado/situación, entidad,
nivel/sector/función, tipo de inversión, tipología, modalidad, montos, fechas,
expediente técnico y unidades OPMI/UF/UEI/UEP. Ubicación permanece en el
artefacto compatible mientras el resolver actual la usa; las coordenadas no se
incorporan.

El Programador de tareas de Windows ejecutará semanalmente un contenedor
one-shot del ETL. Descarga con retry/backoff, aplica gates y deja intacta la
carga anterior ante cualquier fallo.

PostgreSQL y la conservación íntegra de las 95 columnas quedan diferidos hasta
que exista un consumidor de historia, consultas analíticas o concurrencia que
lo justifique.

## Consecuencias

Positivas:

- lookup por CUI/SNIP sin cargar la ficha completa en RAM;
- no se introduce una nueva dependencia de servicio;
- búsqueda por nombre conserva el comportamiento ya validado;
- publicación, rollback y adopción de cargas son explícitos;
- SQLite puede distribuirse y probarse como un único artefacto inmutable.

Costos:

- se mantienen dos representaciones derivadas;
- el ETL debe reconciliarlas por `load_id` y conteos;
- los cambios que usen nuevos campos para puntuar necesitan pytest + golden;
- SQLite no resuelve por sí solo necesidades futuras de analítica histórica.

## Alternativas

### Todo en RAM

Es rápido, pero aumenta carga inicial y memoria por proceso con campos que solo
se consultan una vez conocido el CUI.

### Solo SQLite

Simplifica artefactos, pero obligaría a rediseñar y volver a validar la búsqueda
difusa que hoy funciona con el índice invertido RAM.

### PostgreSQL

Adecuado para API compleja, historia y múltiples consumidores. Se difiere
porque el resolver local no necesita esas capacidades todavía.

## Regla para enriquecer el resolver

El ETL transporta datos; no decide su efecto en el scoring. Cada nueva señal
debe clasificar explícitamente coincidencia, contradicción y dato ausente.
Campos incompletos como tipología, modalidad o unidades responsables nunca
producen rechazo por ausencia. Todo cambio al resolver exige pytest y golden.

## Referencias

- `docs/backend/eda_datos_abiertos_mef.md`
- `docs/backend/modulo_etl_mef.md`
- `.ai/decisions/ADR-002-base-local-mef.md`
