# ETL MEF — plan serving-first para el resolver

> Estado: implementación en curso en `plan/etl-mef-v2`
> Fecha: 2026-07-29
> Evidencia: [`eda_datos_abiertos_mef.md`](eda_datos_abiertos_mef.md)

## 1. Objetivo

Actualizar semanalmente la base MEF que ya consume el resolver y enriquecer la
ficha consultable por CUI/SNIP en PostgreSQL.

```text
Tres CSV públicos
       │
       ▼
descarga + perfilado + gates
       │
       ▼
 carga inmutable con load_id
   ┌───────────┴───────────┐
   ▼                       ▼
gzip compacto          PostgreSQL `mef`
búsqueda por nombre    lookup load_id + CUI/SNIP
   └───────────┬───────────┘
               ▼
            BaseMef
               ▼
            resolver
```

## 2. Arquitectura

### Índice RAM

`inversiones.csv.gz` conserva el contrato actual utilizado para:

- búsqueda difusa por nombre;
- fusión de candidatos con InfoObras;
- datos mínimos que necesita el scoring vigente.

La búsqueda ya validada no se reescribe.

### Fichas PostgreSQL

`mef.investments` se consulta por `load_id` y CUI/SNIP exacto. Evita cargar en
RAM campos que solo se necesitan después de identificar un candidato.

Campos v1:

- CUI, SNIP, nombre y fuente;
- estado del dataset, estado y situación;
- entidad, nivel, sector y función;
- tipo de inversión, tipología y modalidad;
- monto viable y costo actualizado;
- fechas de registro y viabilidad;
- expediente técnico;
- OPMI, UF, UEI y UEP.

Tipología, modalidad y unidades son opcionales. Las coordenadas se excluyen. Los
campos geográficos del archivo compacto se conservan por compatibilidad mientras
el resolver vigente los utilice, no como ampliación del ETL.

### Publicación

```text
<referencia>/mef/
  manifest.json
  cargas/
    <load_id>/
      inversiones.csv.gz
      entidades_publicas.csv
      metadata.json
```

Los archivos se construyen en `cargas/.<load_id>.tmp`. Solo después de completar
transformación, volumen, carga PostgreSQL y checksums se renombra el directorio
y se reemplaza `manifest.json` mediante `os.replace`. PostgreSQL usa:

- `mef.loads`;
- `mef.investments`;
- `mef.active_load`.

Se conservan inicialmente dos cargas válidas. Rollback consiste en volver a
publicar el manifest de la anterior.

## 3. Contrato de las fuentes

Fuentes obligatorias:

- `DETALLE_INVERSIONES.csv`;
- `CIERRE_INVERSIONES.csv`;
- `INVERSIONES_DESACTIVADAS.csv`.

Aliases confirmados:

- `CODIGO_SNIP` / `COD_SNIP`;
- `NOMBRE_OPMI` / `NOM_OPMI`;
- `NOMBRE_UF` / `NOM_UF`;
- `NOMBRE_UEI` / `NOM_UEI`;
- `NOMBRE_UEP` / `NOM_UEP`.

Una fila necesita nombre y al menos CUI o SNIP. Raw histórico de las 95 columnas
no forma parte de esta primera implementación.

## 4. Gates

Antes de publicar:

1. existen las tres fuentes;
2. están presentes identidad, nombre y entidad;
3. cada fuente supera su mínimo y la unión supera el mínimo global;
4. ninguna fila carece simultáneamente de CUI y SNIP;
5. las filas sin nombre se conservan para lookup exacto y se contabilizan;
6. montos seleccionados son decimales válidos;
7. PostgreSQL contiene exactamente una fila por identidad canónica;
8. se registran filas, identidades, duplicados, columnas y checksums;
9. todos los artefactos pertenecen al mismo `load_id`.

El EDA comparativo de drift se añadirá antes de activar el cron en producción:
variación de volumen, cabeceras y cobertura respecto de la carga anterior.

## 5. Uso desde BaseMef

- `buscar_candidatos(nombre)` carga/reutiliza el índice RAM y retorna las fichas
  enriquecidas de sus candidatos.
- `existe_cui(codigo)` consulta primero PostgreSQL y no carga el índice RAM;
- si PostgreSQL no responde, se mantiene fallback a la ficha mínima del gzip;
- si cambia el `load_id`, la siguiente consulta de nombre recarga de forma
  sincronizada el índice;
- si no existe ninguna base válida, el resolver conserva su degradación a
  InfoObras.

Los campos nuevos inicialmente son informativos. Usarlos como señales de
scoring es trabajo posterior y exige pytest + golden.

## 6. Automatización

El servidor es Windows 11 con Docker Desktop. El Programador de tareas ejecuta
los domingos a las 03:00 un wrapper PowerShell que:

- impide ejecuciones simultáneas mediante lock;
- ejecuta un contenedor one-shot;
- registra stdout/stderr y código de salida;
- no reinicia el backend: `BaseMef` adopta la nueva carga al consultar.

Comando interno:

```powershell
docker compose -f deploy/docker-compose.yml run --rm backend `
  python scripts/actualizar_base_mef.py
```

El contenedor exige `PIVOTE_DB_URL` y arranca con el servicio `db`; el wrapper
no usa `--no-deps`.

## 7. Fases

### F1 — núcleo serving-first

- aliases corregidos;
- schema PostgreSQL `mef` y carga por `COPY`;
- carga/manifest versionados;
- compatibilidad y recarga de `BaseMef`;
- tests offline.

### F2 — operación

- retry/backoff;
- wrapper y registro de la tarea Windows;
- drift contra carga anterior;
- estado de frescura visible.

### F3 — validación real

- construir una carga con los tres CSV;
- medir duración, tamaños y lookup;
- correr suite y golden vigente;
- activar cron primero en modo supervisado.

### F4 — enriquecimiento del resolver

Inventariar campos extraíbles por la skill y definir señales una por una.
Coincidencia puede sumar confianza; contradicción fuerte puede forzar revisión;
ausencia nunca debe interpretarse como contradicción.

## 8. Fuera de alcance inmediato

- raw histórico de las 95 columnas;
- historia semanal indefinida;
- API analítica;
- coordenadas;
- paralelización del resolver;
- cambios de scoring sin golden.
