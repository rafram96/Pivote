# EDA de los Datos Abiertos del MEF

> Fecha del análisis: **2026-07-29**
> Corte de los archivos: **2026-07-26**
> Alcance: perfilado local, en streaming y sin modificar los CSV.
> Propósito: diseñar el ETL desde los datos reales; las issues de la épica #12
> se consideran brainstorm, no especificación.

## 1. Resumen ejecutivo

Los tres archivos contienen **620,985 filas**, **95 columnas distintas** en su
unión y ocupan **640.7 MB**. Son tres snapshots de estados distintos, no tres
versiones superpuestas de las mismas inversiones:

- no hay ningún CUI compartido entre activas, cerradas y desactivadas;
- solo una identidad se repite en todo el corpus;
- 579,481 filas tienen CUI y las restantes se identifican por SNIP;
- el campo SNIP está presente en las 620,985 filas y solo hay una repetición.

Esto permite una capa canónica de una inversión por identidad sin una compleja
regla de precedencia entre fuentes. La fila cruda repetida debe conservarse en
el cold path, pero los campos calientes de esas dos filas son iguales.

El ETL actual no es todavía desatendido: tiene descarga, modo offline, gates,
metadata y publicación atómica en archivos, pero no tiene retry con backoff,
cron ni alerta operativa.

## 2. Inventario físico

| Fuente | Estado representado | Filas | Columnas | Tamaño |
|---|---|---:|---:|---:|
| `DETALLE_INVERSIONES.csv` | Activas | 149,179 | 68 | 245.2 MB |
| `CIERRE_INVERSIONES.csv` | Cerradas | 117,281 | 57 | 116.4 MB |
| `INVERSIONES_DESACTIVADAS.csv` | Desactivadas | 354,525 | 42 | 279.1 MB |
| **Unión** | — | **620,985** | **95 distintas** | **640.7 MB** |

La cifra de 68 campos repetida en la épica es incorrecta: corresponde solo al
archivo de activas.

## 3. Identidad, duplicados y relación entre fuentes

| Métrica | Resultado |
|---|---:|
| CUIs únicos | 579,481 |
| SNIPs únicos | 620,984 |
| Filas sin CUI | 41,505 |
| Filas sin CUI ni SNIP | 0 |
| CUIs presentes en más de una fuente | 0 |
| Identidades con más de una fila | 1 |
| Máximo de filas para una identidad | 2 |

La única repetición está dentro de `DETALLE_INVERSIONES.csv`. Ambas filas
difieren solo en `MONTO_ET_F8` (`466749379.0` frente a `0.0`); los campos que
usa hoy el resolver son idénticos.

### Clave recomendada

- Identidad lógica: `CUI:<codigo>` cuando existe CUI; en caso contrario,
  `SNIP:<codigo>`.
- La tabla raw no debe usar esa identidad como clave única: conserva
  `(carga_id, fuente, fila_origen)` para no perder duplicados.
- La capa canónica sí expone una fila por identidad y registra qué fila raw
  fue seleccionada.

## 4. Cobertura de los campos candidatos

Porcentaje no vacío dentro de cada fuente:

| Campo | Activas | Cerradas | Desactivadas | Lectura |
|---|---:|---:|---:|---|
| CUI | 99.96% | 97.06% | 89.28% | SNIP cubre el faltante |
| Nombre | ~100% | 100% | 100% | Campo base de búsqueda |
| Entidad | 100% | 99.84% | 98.85% | Útil; no asumir obligatoriedad |
| Departamento/provincia/distrito | 99.94%+ | 99.96% | 99.93% | Alta cobertura |
| Ubigeo | 99.85% | 99.96% | 99.93% | Preferible a coordenadas |
| Función | 99.99% | 100% | 100% | Mejor señal sectorial gruesa |
| Tipo de inversión | 100% | 100% | 100% | Tiene 7–12 valores, no es binario |
| Tipología | 81.13% | 34.73% | 28.27% | No sirve como requisito duro |
| Modalidad | 96.74% | 69.72% | 63.91% | Informativa, con variantes textuales |
| Monto viable | 99.84% | ~100% | 78.49% | Decimal consistente cuando existe |
| Costo actualizado | 100% | 100% | 99.98% | Decimal consistente |
| Fecha registro | 100% | 100% | ~100% | Formato ISO consistente |
| Fecha viabilidad | 99.84% | 100% | 78.50% | Formato ISO consistente |
| Expediente técnico | 100% | 100% | 100% | Falta EDA semántico del contenido |

### Unidades responsables y aliases

Las columnas cambian por fuente:

- SNIP: `CODIGO_SNIP` en activas/cerradas y `COD_SNIP` en desactivadas;
- activas: `NOMBRE_OPMI`, `NOMBRE_UF`, `NOMBRE_UEI`, `NOMBRE_UEP`;
- cerradas/desactivadas: `NOM_OPMI`, `NOM_UF`, `NOM_UEI`, `NOM_UEP`.

Cobertura después de unificar aliases:

| Unidad | Activas | Cerradas | Desactivadas |
|---|---:|---:|---:|
| OPMI | 95.52% | 79.46% | 35.46% |
| UF | 97.01% | 98.88% | 100% |
| UEI | 97.88% | 80.21% | 35.22% |
| UEP | 99.97% | 99.92% | 98.97% |

El catálogo actual solo busca variantes `NOMBRE_*`; por eso omite 12,102
entidades que aparecen como `NOM_*`.

## 5. Calidad y tipos

### Fechas

`FECHA_REGISTRO` y `FECHA_VIABILIDAD` usan fechas ISO de forma consistente.
Los campos mensuales `PRIMER_DEVENGADO` y `ULTIMO_DEVENGADO` usan `YYYYMM`.
Algunas fechas de cierre/liquidación incluyen hora distinta de `00:00:00`;
deben parsearse como timestamp y proyectarse a fecha cuando el consumidor no
necesite la hora.

### Montos

`MONTO_VIABLE` y `COSTO_ACTUALIZADO` son parseables como decimal en el 100% de
sus valores no vacíos. Hay montos de decenas de miles de millones, por lo que
el tipo debe ser al menos `numeric(18,2)` y no `float`.

`MONTO_LAUDO` contiene dos valores negativos en cerradas. No se deben rechazar
sin confirmar primero la semántica oficial del campo.

### Coordenadas

Aunque latitud y longitud tienen cobertura superior al 99%, contienen valores
fuera de cualquier rango geográfico válido, por ejemplo magnitudes de miles de
millones. No deben entrar al hot path como coordenadas confiables.

Decisión de diseño:

- conservar el valor original en raw JSONB;
- si se exponen, producir columnas saneadas opcionales solo cuando
  `latitud ∈ [-90,90]` y `longitud ∈ [-180,180]`;
- registrar la tasa rechazada como métrica de calidad.

### Celdas grandes

La celda más larga observada tiene 3,926 caracteres en `ALTERNATIVA`. El lector
mantendrá `csv.field_size_limit(10_000_000)` como defensa ante futuros cortes,
aunque este snapshot no alcance ese máximo.

## 6. Dimensión probable del cold path

Serializar una muestra de 1,000 filas por fuente como JSON compacto produjo:

| Fuente | Promedio por fila | p95 |
|---|---:|---:|
| Activas | 2,648 bytes | 3,954 bytes |
| Cerradas | 1,845 bytes | 2,028 bytes |
| Desactivadas | 1,145 bytes | 1,252 bytes |

Proyección del payload JSON completo de una carga: **~1.02 GB**, antes del
overhead de PostgreSQL, TOAST e índices. Este cold path quedó diferido: el
objetivo inmediato es el resolver mediante gzip + SQLite.

Si más adelante se implementa historia completa:

- conservar carga completa activa + anterior para rollback;
- conservar metadata, checksums y métricas de todas las cargas;
- no prometer varias semanas de payload completo hasta medir almacenamiento,
  backup y tiempo de restauración.

## 7. Implicaciones para el diseño del ETL

1. **EDA es una etapa del producto**, no un análisis único: cada carga compara
   esquema, cobertura, cardinalidad y volumen contra la anterior.
2. El contrato de columnas debe ser **por fuente y por aliases**. Una columna
   nueva es aviso; la desaparición de una requerida bloquea publicación.
3. La capa raw conserva todas las filas y columnas. La capa canónica tipa solo
   campos con consumidor y calidad conocida.
4. El índice RAM sigue siendo el camino de búsqueda por nombre; una SQLite
   local resuelve la ficha enriquecida por CUI/SNIP sin inflar la RAM.
5. El cron debe ejecutar el pipeline completo, emitir un `load_id` común para
   todos los artefactos y dejar fallo visible.
6. La búsqueda paralela no forma parte del diseño hasta medir la versión
   secuencial con el corpus grande disponible.

## 8. EDA pendiente antes de congelar el esquema hot

- Perfil semántico de `EXPEDIENTE_TECNICO`, `INFORME_CIERRE`,
  `TIPO_INVERSION`, `MARCO` y `DES_MODALIDAD`.
- Inventario de consultas de negocio: resolver, API, panel, cronología y
  reportes; cada columna hot debe tener al menos un consumidor.
- Tasa de coordenadas válidas y posibilidad de corregir escalas, sin adivinar.
- Tamaño, tiempo de construcción e índices con la SQLite completa.
- Benchmark del índice RAM sobre un concurso completo y el corpus de 1,042
  experiencias.
