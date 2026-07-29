# ADR-009 · ETL MEF serving-first: índice RAM + PostgreSQL

- Fecha: 2026-07-23; decisión final 2026-07-29
- Estado: **ACEPTADO**

## Contexto

ADR-002 creó un archivo compacto y un índice RAM para que el resolver busque
inversiones por nombre sin depender de la red. El objetivo del nuevo ETL es
enriquecer ese resolver: una vez identificado un CUI/SNIP candidato, debe poder
contrastar más datos oficiales.

La RAM no es una restricción, pero cargar allí toda la ficha no aporta valor.
PostgreSQL ya forma parte del despliegue on-prem y el desarrollador confirmó que
es el destino obligatorio. El EDA real encontró 620,985 filas, 579,481 CUIs y
una sola identidad duplicada.

## Decisión

El ETL publica dos representaciones coordinadas:

1. `inversiones.csv.gz`, cargado en RAM, conserva la búsqueda difusa por nombre.
2. `mef.investments` en PostgreSQL conserva la ficha enriquecida y se consulta
   por `(load_id, CUI/SNIP)`.

El schema independiente `mef` contiene:

- `mef.loads`: estado y metadata de cada carga;
- `mef.investments`: ficha canónica por identidad y carga;
- `mef.active_load`: puntero operativo a la carga publicada.

Los artefactos de disco y PostgreSQL comparten `load_id`. El resolver toma el
`load_id` del manifest de disco y lo incluye en la consulta SQL; así nunca mezcla
el índice RAM de una versión con fichas de otra.

Publicación:

1. construir gzip, catálogo y metadata en staging;
2. cargar PostgreSQL por `COPY` y reconciliar el total de identidades;
3. marcar la carga `validated`;
4. publicar el manifest mediante `os.replace`;
5. actualizar `mef.active_load` en una transacción.

PostgreSQL es obligatorio para ejecutar una nueva carga. Si cae durante una
consulta del resolver, `BaseMef` degrada a la ficha mínima del gzip y el análisis
puede continuar.

La ficha v1 incluye identidad, nombre, estado/situación, entidad, ubicación
compatible, nivel/sector/función, tipo de inversión, tipología, modalidad,
montos, fechas, expediente técnico y OPMI/UF/UEI/UEP. Las coordenadas se
excluyen.

## Consecuencias

Positivas:

- consulta enriquecida compartida entre procesos;
- tipos e índices gobernados en PostgreSQL;
- trazabilidad y rollback por carga;
- la búsqueda RAM ya validada no se reescribe;
- queda una base directa para API/panel futuros.

Costos:

- PostgreSQL pasa a ser requisito del cron, aunque no del resolver en ejecución;
- filesystem y PG no comparten una transacción distribuida;
- se mantienen dos representaciones derivadas;
- cada nueva señal de scoring exige pytest + golden.

## Alternativas descartadas

### Todo en RAM

Aumenta carga inicial y replica campos por proceso sin beneficiar el lookup
exacto.

### SQLite

Era técnicamente suficiente para una sola máquina, pero contradice la decisión
de infraestructura del proyecto y no comparte naturalmente las fichas entre
procesos/consumidores.

### Reemplazar RAM por PostgreSQL

Obligaría a rediseñar la búsqueda difusa ya validada y haría al resolver
dependiente de PG. No aporta una mejora demostrada.

## Regla para enriquecer el resolver

El ETL transporta datos, no cambia el scoring. Cada campo nuevo debe definir
coincidencia, contradicción y ausencia. Tipología, modalidad y unidades
responsables nunca rechazan por estar vacías. Todo cambio al resolver exige
pytest y golden.

## Referencias

- `docs/backend/eda_datos_abiertos_mef.md`
- `docs/backend/modulo_etl_mef.md`
- `.ai/decisions/ADR-002-base-local-mef.md`
