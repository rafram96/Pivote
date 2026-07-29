# ETL de Datos Abiertos del MEF — plan de implementación

> Estado: **plan técnico v2; implementación no iniciada**
> Fecha: 2026-07-29
> Rama de planificación: `plan/etl-mef-v2`
> Evidencia: [`eda_datos_abiertos_mef.md`](eda_datos_abiertos_mef.md)
> Nota de alcance: la épica #12 y sus issues fueron una lluvia de ideas inicial.
> Este documento no las adopta como especificación.

## 1. Resultado buscado

Un proceso semanal desatendido debe descargar los tres CSV públicos del Banco
de Inversiones, conservar su contenido completo, construir una representación
canónica consultable y publicar los artefactos compactos que ya consume el
resolver.

El resultado válido de una ejecución es una **carga identificable, trazable y
reversible**. Si descarga, transformación o validación fallan, continúa activa
la última carga buena y el fallo queda visible.

## 2. Decisiones de arquitectura

1. **ADR-002 sigue vigente.** `inversiones.csv.gz` y el índice RAM continúan
   siendo el camino primario del resolver. PostgreSQL no se vuelve requisito
   para resolver un concurso.
2. **El cron ejecuta el ETL.** En el servidor actual (Windows 11 + Docker
   Desktop), el disparador será el Programador de tareas de Windows. No se
   agregará un daemon de scheduling al backend.
3. **PostgreSQL es la capa histórica y consultable**, dentro del clúster ya
   previsto pero en un schema independiente `mef`. No comparte tablas con el
   repositorio del orquestador.
4. **Una ejecución genera un solo `load_id`** para fuentes, tablas,
   artefactos, métricas y logs.
5. **No se renombran tablas por carga.** Se insertan filas versionadas y una
   transacción cambia el puntero de carga activa después de todos los gates.
6. **Raw no transforma ni pierde información.** La fila completa se conserva
   como JSONB. Canonical y serving solo proyectan campos tipados con un
   consumidor concreto.
7. **EDA es parte de cada carga.** Se detectan cambios de esquema, volumen,
   cobertura, duplicados y calidad frente a la última carga publicada.
8. **No se paraleliza la búsqueda por anticipación.** Primero se mide el
   resolver secuencial; esta optimización no pertenece al ETL.

## 3. Flujo de extremo a extremo

```text
Programador de tareas (domingo 03:00)
                │
                ▼
        wrapper PowerShell
   lock + log + código de salida
                │
                ▼
   DESCARGA / --desde-dir (staging)
   3 CSV + checksum + cabeceras
                │
                ▼
      PERFILADO Y CONTRATO
 esquema · volumen · nulls · tipos
 aliases · duplicados · drift
                │
       falla ───┴───► conservar carga activa + alerta
                ▼
        TRANSFORMACIÓN ÚNICA
       raw + canonical + serving
          ┌─────┴─────┐
          ▼           ▼
 PostgreSQL `mef`   artefactos staging
 raw/canonical      gzip + catálogo + metadata
          └─────┬─────┘
                ▼
         GATES INTEGRADOS
 mismos conteos · mismo load_id · smoke queries
                │
                ▼
      PUBLICACIÓN DE LA CARGA
 puntero PG + manifest/artefactos de disco
                │
                ▼
   resolver RAM / API / operación y auditoría
```

PostgreSQL y el filesystem no permiten una transacción distribuida. Para
reducir el intervalo de inconsistencia:

1. se construyen primero los archivos con nombres versionados;
2. se cargan y validan las tablas con estado `validated`;
3. se publica el manifest de disco mediante `os.replace`;
4. una transacción corta cambia `mef.active_load`;
5. el health check compara ambos `load_id`.

El resolver lee la versión indicada por el manifest. Si PostgreSQL no está
disponible, sigue funcionando con esa versión. Un desacuerdo de `load_id` no
destruye datos: marca la carga como degradada y permite reanudar la publicación.

## 4. Capas y modelo de datos

### 4.1 Source / staging

Directorio no versionado por `load_id`, con los tres CSV originales:

- `DETALLE_INVERSIONES.csv`;
- `CIERRE_INVERSIONES.csv`;
- `INVERSIONES_DESACTIVADAS.csv`;
- `manifest.json`: URL, tamaño, SHA-256, cabeceras, fecha y resultado HTTP.

Los archivos se descargan en streaming, con timeout, tres intentos y backoff
exponencial con jitter. `--desde-dir` recorre exactamente el mismo pipeline sin
red.

### 4.2 Raw / cold en PostgreSQL

```text
mef.loads
  load_id uuid PK, started_at, finished_at, status,
  previous_load_id, producer_version, error_summary

mef.source_files
  load_id FK, source, sha256, bytes, row_count,
  headers jsonb, profile jsonb, PRIMARY KEY(load_id, source)

mef.raw_rows
  load_id FK, source, source_row, identity_key,
  payload jsonb, payload_hash,
  PRIMARY KEY(load_id, source, source_row)
```

`raw_rows` conserva incluso la repetición observada. No se crea un índice GIN
general sobre todo el JSONB: su costo debe justificarse con consultas reales.
Los primeros índices son `load_id`, `identity_key` y, si el benchmark lo exige,
índices de expresión específicos.

### 4.3 Canonical / hot

`mef.investments` contiene una fila por identidad y por carga:

```text
load_id, identity_key, source, source_row,
cui, snip, nombre, nombre_norm,
estado_dataset, estado, situacion,
entidad, entidad_norm,
nivel, sector, funcion, tipo_inversion, tipologia, modalidad,
ubigeo, departamento, provincia, distrito,
monto_viable numeric(18,2), costo_actualizado numeric(18,2),
fecha_registro date, fecha_viabilidad date,
expediente_tecnico,
opmi, uf, uei, uep
```

Reglas:

- `identity_key = CUI:<cui>`; si falta CUI, `SNIP:<snip>`;
- aliases `CODIGO_SNIP`/`COD_SNIP` y `NOMBRE_*`/`NOM_*` se resuelven por
  contrato de fuente;
- strings vacíos pasan a `NULL`; el original permanece en raw;
- montos se parsean como decimal, nunca `float`;
- tipología, modalidad y unidades responsables son opcionales;
- coordenadas no forman parte del hot v1 por su calidad observada;
- toda selección entre duplicados es determinista y deja `source_row`.

Índices v1:

- `(load_id, cui)` y `(load_id, snip)`;
- `(load_id, identity_key)` único;
- `pg_trgm` sobre `nombre_norm` y `entidad_norm`;
- índices B-tree solo para filtros que tenga la API v1.

No se agrega FTS en español hasta comparar su relevancia contra trigramas con
consultas reales.

### 4.4 Serving / gold

- `inversiones.<load_id>.csv.gz`: contrato compatible con `base_mef.py`;
- `entidades_publicas.<load_id>.csv`;
- `metadata.<load_id>.json`: perfil y resultado de gates;
- `manifest.json`: puntero atómico a la versión activa.

El catálogo incorpora `ENTIDAD`, `NOMBRE_*` y `NOM_*`. El formato actual sin
versionar se mantiene durante una transición y luego se retira cuando todos
los lectores usen el manifest.

## 5. Contrato de fuentes y EDA recurrente

Cada fuente tiene un contrato explícito de:

- aliases aceptados;
- columnas requeridas para identidad y nombre;
- columnas opcionales conocidas;
- parsers de tipos;
- umbrales de volumen y cobertura.

Tratamiento de drift:

| Cambio | Comportamiento |
|---|---|
| Falta identidad o nombre | Bloquea la publicación |
| Desaparece una columna hot | Bloquea; no publica una base degradada |
| Aparece una columna | Preserva en raw y emite aviso |
| Cambia un alias conocido | Bloquea y muestra diff de cabeceras |
| Baja volumen/cobertura fuera de tolerancia | Bloquea y compara con carga previa |
| Aparecen duplicados | Conserva raw; canonical aplica regla y reporta tasa |
| Falla un parseo hot | Bloquea si supera tolerancia; conserva valor raw |

Los umbrales iniciales se derivan del corte 2026-07-26, pero la implementación
debe expresarlos como configuración y registrar el valor observado. No basta un
único gate global de 400 mil filas.

## 6. Gates de publicación

Una carga solo pasa a `published` si cumple:

1. existen las tres fuentes y sus checksums;
2. cabeceras requeridas y aliases válidos por fuente;
3. mínimos absolutos y variación relativa de filas contra la carga anterior;
4. ninguna fila sin CUI y SNIP simultáneamente;
5. unicidad y tasa de duplicados dentro de tolerancia;
6. parseo de fechas y montos dentro de tolerancia;
7. conteo del catálogo y cobertura de entidad dentro de tolerancia;
8. los conteos raw, canonical y artefactos son reconciliables;
9. PostgreSQL y archivos contienen el mismo `load_id`;
10. smoke tests por CUI, SNIP y nombre producen resultados esperados;
11. el artefacto puede cargarse mediante `BaseMEF` y supera sus tests de
    regresión.

Todo gate produce una métrica estructurada, no solo texto de consola.

## 7. Cron y operación

### Disparador

El Programador de tareas ejecuta semanalmente un wrapper PowerShell versionado.
El wrapper:

- cambia al directorio del despliegue;
- adquiere un lock exclusivo para impedir dos cargas simultáneas;
- invoca un contenedor one-shot del ETL con las variables necesarias;
- escribe stdout/stderr en un log rotado;
- devuelve código distinto de cero ante cualquier fallo;
- libera el lock incluso si la ejecución falla.

La tarea usa una cuenta de servicio con permiso mínimo sobre Docker, staging,
artefactos y secretos. No se guardan credenciales en el XML ni en el repo.

### Observabilidad mínima

`GET /health` debe exponer, sin datos sensibles:

- `mef_load_id`;
- fecha de última carga buena;
- edad de la base;
- estado `ok`, `stale`, `failed` o `mismatch`;
- último error resumido;
- versión cargada por el índice RAM y versión activa en PostgreSQL.

Se considera `stale` al superar ocho días sin una publicación válida. El
Programador de tareas registra el código de salida y se configura una acción de
notificación disponible en el entorno; el mecanismo concreto se cierra con la
operación del servidor.

### Recuperación

- un reintento reutiliza staging si los checksums coinciden;
- la carga anterior nunca se sobrescribe;
- rollback = cambiar el manifest y `active_load` al `load_id` anterior;
- las cargas fallidas conservan metadata y diagnóstico, no necesariamente el
  payload completo;
- un comando `--reanudar <load_id>` completa una publicación interrumpida.

## 8. Retención y capacidad

El EDA proyecta ~1.02 GB de JSON compacto por carga antes del overhead de
PostgreSQL. Política inicial:

- payload completo de la carga activa y la anterior;
- artefactos de serving de ambas;
- metadata, checksums, perfiles y errores para todas las cargas;
- staging fallido por 14 días;
- VACUUM/backup medidos antes de ampliar historia.

Una importación desechable en PostgreSQL debe medir tamaño real de tabla, TOAST,
índices, tiempo de carga, consulta, backup y restore. Esa evidencia fija la
política definitiva; no se promete una retención semanal indefinida.

## 9. API y consumidores

La API v1 propuesta es `GET /api/pivote/mef/buscar`, con búsqueda por CUI, SNIP
o nombre y filtros acotados. Debe depender de una interfaz de lectura, no de
SQL embebido en el endpoint.

- El resolver conserva `BaseMEF`/RAM para no cambiar sus resultados ni su
  degradación.
- La API y futuros paneles pueden leer PostgreSQL.
- Ambos caminos declaran el `load_id` usado.
- Cualquier cambio al resolver se trabaja aparte y cumple pytest + golden.

## 10. Fases ejecutables y criterios de salida

### Fase 0 — contrato y benchmark de capacidad

- versionar el perfil EDA reproducible;
- completar semántica de campos pendientes;
- importar una carga en PostgreSQL desechable;
- medir almacenamiento y consultas;
- congelar DDL y umbrales.

**Salida:** ADR-009 aceptado, DDL revisado y presupuesto de capacidad medido.

### Fase 1 — robustecer el ETL de archivos

- corregir aliases del catálogo;
- agregar retry/backoff;
- introducir `load_id`, artefactos versionados y manifest;
- implementar perfilado/gates comparativos;
- tests unitarios e integración offline.

**Salida:** una ejecución `--desde-dir` publica o revierte de forma determinista.

### Fase 2 — persistencia PostgreSQL

- migraciones del schema `mef`;
- carga streaming/batch de raw y canonical;
- índices mínimos y consultas de smoke;
- publicación por puntero y retención.

**Salida:** una carga real cumple reconciliación y rollback RAM/PG.

### Fase 3 — automatización operativa

- wrapper PowerShell y contenedor one-shot;
- tarea semanal documentada;
- lock, logs, health/staleness y reanudación;
- simulación de caída en descarga, PG y publicación.

**Salida:** dos ejecuciones programadas controladas, incluida una falla
inyectada que conserva la base anterior y deja alarma visible.

### Fase 4 — API y adopción

- endpoint y contrato;
- paginación, límites y pruebas;
- panel/consumidores solo cuando exista necesidad validada.

**Salida:** API trazable por `load_id`, sin alterar resultados del resolver.

## 11. Trabajo fuera de este plan

- paralelizar profesionales o portales;
- cambiar scoring o reglas de resolución CUI;
- usar coordenadas como señal sin saneamiento comprobado;
- guardar datos de clientes;
- construir analítica o BI sin consultas acordadas;
- convertir PostgreSQL en dependencia obligatoria del resolver.

## 12. Relación con las issues existentes

Las issues actuales sirven como inventario histórico, no como desglose final.
Antes de implementar:

1. la épica #12 debe enlazar este plan y el EDA;
2. se cierran o reescriben tareas cuya premisa cambió;
3. se crean tickets por las fases anteriores, con criterios de salida y
   evidencia requerida;
4. #25 (paralelización) permanece separado y condicionado a benchmark.

No se estima ni cotiza la implementación desde los títulos de las issues
anteriores; se estima desde este diseño una vez completada la Fase 0.
