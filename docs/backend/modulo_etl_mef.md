# Módulo ETL del MEF — Planificación (Épica #12)

> **Fecha**: 2026-07-28
> **Épica**: [#12 Sistema ETL](https://github.com/rafram96/Pivote/issues/12)
> **Naturaleza**: **módulo nuevo, completo y cotizable** — no es mantenimiento del resolver
> **Rama de trabajo**: por definir (no arranca hasta cerrar ADR-009)

---

## 1. Qué es este módulo, y qué NO es

Este módulo construye una **capa de datos propia** sobre los Datos Abiertos del MEF:
persistencia consultable, control de calidad, scheduling desatendido y API de
búsqueda. Es un entregable nuevo con alcance, precio y plazo propios.

### Frontera con ADR-002 (importante — evita un debate falso)

[ADR-002](file:///C:/Users/Holbi/Documents/Freelance/proyectos/InfoObras/Pivote/.ai/decisions/ADR-002-base-local-mef.md)
decidió lo **mínimo** para que el resolver de CUI tuviera candidatos sin red: un
CSV compactado y un índice en memoria, sin Postgres. Esa decisión sigue siendo
correcta **en su alcance** y no se reabre.

Este módulo **no cae bajo ADR-002**: son alcances distintos, no posturas
enfrentadas.

| | ADR-002 (vigente, mínimo) | Módulo ETL (#12, nuevo) |
|---|---|---|
| Propósito | Que el resolver tenga candidatos sin red | Capa de datos del MEF consultable y mantenida |
| Datos | 10 campos, lo justo para puntuar nombres | 16 campos calientes + los crudos (unión de 95) |
| Persistencia | `inversiones.csv.gz` + índice en RAM | PostgreSQL (hot indexado + cold JSONB) |
| Consulta | Interna del resolver | API REST + panel + resolver |
| Operación | Manual (`python -m scripts.actualizar_base_mef`) | Cron semanal + metadata + gates |
| Naturaleza | Infraestructura mínima del pivote | **Entregable cotizable** |

**Consecuencia práctica**: lo construido bajo ADR-002 **no se tira** — se conserva
como está y el módulo nuevo lo absorbe o convive con él (§3).

### La motivación NO es la RAM

Decisión del desarrollador (2026-07-28): **la RAM no es problema, hay de sobra**.
Los ~370-400 MB del índice en memoria **no motivan** esta migración, y ningún
documento debe argumentar desde ahí.

La motivación es de **capacidad**, no de recursos: los 3 CSV traen 68 / 57 / 42
columnas (**unión de 95 distintas**, verificado 28-jul) y la ingesta se queda con
**10**. Las ~85 restantes se descartan en el momento de la ingesta y no son
recuperables sin volver a descargar ~480 MB y reprocesar. El cold path JSONB (#18) existe para que ningún
dato del MEF se pierda y todo quede consultable.

> ⚠ **[ADR-009](file:///C:/Users/Holbi/Documents/Freelance/proyectos/InfoObras/Pivote/.ai/decisions/ADR-009-migracion-postgres-mef.md)
> tiene la sección «Contexto» vacía y su decisión redactada como "migración por
> recursos".** Debe reescribirse con este encuadre —módulo nuevo, motivación de
> capacidad, PG confirmado por #18— antes de que la épica arranque. Es el único
> bloqueante real.

---

## 2. Inventario: qué YA está construido

`backend/scripts/actualizar_base_mef.py` (226 líneas) es un ETL funcionando en
producción. La épica, tal como estaba redactada, proponía construir de cero varias
piezas que ya existen. Estado verificado issue por issue:

| Issue | Pedido | Estado | Dónde está hoy |
|---|---|---|---|
| **#14** T-ETL-001 Ingesta streaming + reintentos | Chunks 1 MB, retry ×3 backoff | 🟡 **Parcial** | `_descargar()` — streaming 1 MB, `timeout=(30,600)`, guarda de tamaño mínimo (10 MB), escritura atómica por archivo. **Falta solo el retry con backoff** |
| **#15** T-ETL-002 Modo offline | `--desde-dir` | ✅ **Hecho** | `main()` — flags `--desde-dir` y `--destino`, documentados en el docstring de uso |
| **#17** T-ETL-003 Hot path 16 campos | 16 campos normalizados e indexados | 🟡 **Parcial (10 de 16)** | `_procesar()` extrae `cui, snip, nombre, estado_dataset, situacion, ubigeo, dpto, prov, dist, entidad`. **Faltan ~6** (monto, modalidad, tipología, función, fechas…) y la normalización persistida (`nombre_norm`/`entidad_norm` hoy se calcula al cargar, no se guarda) |
| **#18** T-ETL-004 Cold path JSONB | Payload crudo íntegro | ❌ **No existe** | Se descartan ~85 de las 95 columnas de la unión. **Requiere PG (confirmado)** |
| **#19** T-ETL-005 Catálogo entidades + siglas | Tabla 11k+ entidades | 🔴 **BUG confirmado** | Existe (`COLS_ENTIDAD` + `_RE_SIGLA` → `entidades_publicas.csv`) pero **pierde 12,102 entidades**: las 4 columnas de unidad se llaman `NOMBRE_*` en DETALLE y `NOM_*` en los otros dos → en el 76% de las filas solo se cosecha `ENTIDAD`. Medido 28-jul |
| **#21** T-ETL-006 Gate ≥ 400k filas | Sanity check de volumen | ✅ **Hecho** | `MIN_UNION = 400_000` y `MIN_POR_FUENTE = 50_000`, validados **antes** de sobrescribir |
| **#22** T-ETL-007 Swap atómico | Zero-downtime | ✅ **Hecho, con otra técnica** | `tmp + os.replace` de los 3 artefactos. El objetivo (nunca reemplazar la base buena por una mala) está cumplido. En PG se re-implementa como swap de tablas |
| **#24** T-ETL-008 Cron + metadata | Refresco desatendido | 🟡 **Parcial** | `metadata.json` **hecho** (fecha, filas por fuente, total, CUIs distintos, entidades, URLs). **Falta el cron** |
| **#25** T-ETL-009 Búsqueda paralela | N profesionales < 3 s | ❌ **No existe** | Hoy `base_mef.buscar_candidatos()` es secuencial. **Requiere medición previa** (§5) |

**Resumen**: 3 tareas hechas, 3 parciales, 1 con bug confirmado (#19), 2 sin construir.
Mantenerlas abiertas con el texto genérico anterior sugería 9 tareas de trabajo
donde hay ~4.

---

## 3. Qué se conserva, qué se extiende, qué se construye

**Se conserva tal cual** (no se reescribe por gusto):
- El contrato de fuentes: los 3 CSV y la unión obligatoria (el "Detalle" solo trae ACTIVAS).
- Los gates de volumen y la filosofía de "base corta = base sospechosa".
- La escritura atómica: si algo falla, la versión anterior queda intacta.
- El catálogo de entidades y la extracción de siglas.
- El modo offline (`--desde-dir`) — es lo que permite desarrollar sin red.

**Se extiende**:
- La extracción, de 10 a 16 campos calientes + el crudo íntegro (unión de 95).
- El destino: además de los artefactos en disco, las tablas de PG.

**Se construye de cero**:
- Persistencia PG (hot indexado + cold JSONB) y el swap de tablas.
- Cron semanal desatendido.
- Búsqueda paralela — **si la medición la justifica** (§5).
- API `GET /api/pivote/mef/buscar` (issue #27, independiente: se apoya en `base_mef.py` actual y no espera a PG).

**Convivencia a decidir en ADR-009**: si el índice en memoria se mantiene como
camino de lectura rápido con PG detrás, o si PG lo reemplaza. Como la RAM no es
restricción, la convivencia es viable y probablemente preferible (degradación
limpia si PG cae).

---

## 4. Trampas ya descubiertas — respetarlas o se repiten

Todas están documentadas en el código o en ADR-002. Ninguna aparecía en las issues
originales, y cada una costó una corrida en descubrirse:

1. **Celdas de hasta 10 MB.** Los CSV traen memorias descriptivas entrecomilladas
   con saltos de línea embebidos → `csv.field_size_limit(10_000_000)`. Sin eso,
   `csv` revienta con *"field larger than field limit"*.
2. **Los 3 archivos NO comparten esquema** — 68 / 57 / 42 columnas, unión de **95
   distintas** (extraído de los CSV reales, 2026-07-28). Variantes confirmadas:
   `CODIGO_SNIP` ausente en DESACTIVADAS · `CTRL_CONCURR` (D,X) vs `CONTROL_CONCURR` (C)
   · **`NOMBRE_OPMI/UF/UEI/UEP` (D) vs `NOM_OPMI/UF/UEI/UEP` (C,X)** — esta última
   está causando la pérdida de 12,102 entidades HOY (#19). Toda columna se resuelve
   por lista de candidatos (`_col()`), **nunca por nombre fijo**.
3. **Encoding `utf-8-sig`**, no `utf-8` — los archivos traen BOM.
4. **~41k filas son SNIP-only** (`CODIGO_UNICO` vacío): hay que indexar por SNIP
   además de por CUI, o se pierden inversiones viejas.
5. **El "Detalle de inversiones" solo trae ACTIVAS.** Unir los 3 CSV es
   obligatorio, no una optimización.
6. **La paralelización jamás va contra portales en vivo** — solo contra la base
   local. Advertido en `database.md` y en las reglas del proyecto.

---

## 5. Protocolo de medición (obligatorio para #25)

**Decisión del desarrollador (2026-07-28)**: la búsqueda paralela **no se
implementa a ciegas**. Exige tests de velocidad **de las dos versiones** —la actual
secuencial y la paralela— sobre una **cantidad de prueba grande**.

### Corpus de prueba

Volumen realista, no un puñado de casos. Fuentes disponibles en el repo:
- **1,042 experiencias reales** (el corpus contra el que se calibró el `_STOP` de `base_mef.py`).
- **641 experiencias auditadas** (validación del resolver local).
- **277 casos de la golden ancha** (`golden_cui_baseline.json`).

Mínimo exigido: el corpus de 1,042. Un concurso real completo (17 profesionales ×
N experiencias) como caso de extremo a extremo.

### Métricas, en ambas versiones y en la misma máquina

| Métrica | Por qué |
|---|---|
| Latencia por consulta: **p50 / p95 / máx** | La media esconde la cola, y la cola es la que duele |
| **Wall-clock de un concurso completo** | Es la cifra que el usuario percibe |
| Tiempo de carga inicial del índice | Hoy ~60 s perezosos; paralelizar no debe multiplicarlo |
| RAM pico | No es restricción, pero se registra para no llevarse sorpresas |
| **Consistencia de resultados** | La versión paralela debe devolver **exactamente** los mismos candidatos y el mismo orden que la secuencial |

### Criterio de decisión

- La medición de la **versión actual se toma primero** y se registra como línea base.
- La versión paralela **solo se acepta** si mejora el wall-clock del concurso
  completo por un margen que justifique la complejidad (asyncio + pool +
  concurrencia), **y** devuelve resultados idénticos.
- Si la secuencial ya cumple el objetivo (< 3 s por concurso), **#25 se cierra sin
  implementar** y se registra la medición como evidencia. Ese es un resultado
  válido y barato, no un fracaso.

> Contexto que hace la medición imprescindible: ADR-002 registra ~0.2 s por
> consulta en el índice actual. A ese ritmo, un concurso de 50 experiencias son
> ~10 s secuenciales — puede que ya esté cerca del objetivo, o puede que no.
> **Nadie lo ha medido.** Eso es precisamente lo que hay que resolver antes de
> escribir una línea de `asyncio`.

---

## 6. Orden de ejecución

| Paso | Qué | Bloqueante |
|---|---|---|
| **0** | **Cerrar ADR-009** con el encuadre de §1 (módulo nuevo, motivación de capacidad, PG confirmado, convivencia con el índice en memoria) | ⛔ Bloquea todo lo de PG |
| **1** | 🔴 **#19 — arreglar el catálogo de entidades** (12,102 perdidas; afecta el gate público/privado del resolver) | Ninguno — **lo más urgente de la épica** |
| **1b** | Cerrar #15, #21, #22 documentando su implementación actual | Ninguno — higiene |
| **2** | #14 (retry+backoff) y #24 (cron): huecos pequeños del ETL **que ya existe**, sin PG de por medio | Ninguno — hacerlos ya |
| **3** | #25 fase de **medición** (la línea base secuencial no necesita nada nuevo) | Ninguno — hacerlo ya |
| **4** | #17 (6 campos faltantes) + #18 (cold path) + #20/#22 (PG) | ADR-009 |
| **5** | #25 fase de implementación — **solo si §5 la justifica** | Medición del paso 3 |
| **⏸** | #23 (feature paralela+cron) queda como paraguas de #24/#25 | — |

**#27 (API `GET /api/pivote/mef/buscar`) es independiente de toda la épica**: se
apoya en `base_mef.py` tal como está hoy y puede avanzar en cualquier momento.

---

## 7. Nota de cotización

Este módulo es **cotizable como entregable aparte** — no entra en el contrato de
3 hitos ni se cubre con la bolsa de horas. El desglose de §2 sirve directamente
como base de la cotización: lo ya construido (4 tareas) no se cobra dos veces, y
lo cotizable es el paso 2 en adelante de §6, con #18 y #20 (Postgres) como el
grueso real del esfuerzo.

---

## 8. Referencia: columnas reales de los 3 CSV (verificado 2026-07-28)

Extraído de los archivos en `backend/datos_pivote/referencia/mef/tmp/`. **Esta tabla
reemplaza cualquier lista copiada de un plan** — es la fuente para cerrar #17 y #18.

| Archivo | Columnas | Filas (metadata 26-jul) |
|---|---:|---:|
| `DETALLE_INVERSIONES.csv` (ACTIVAS) | **68** | 149,179 |
| `CIERRE_INVERSIONES.csv` (CERRADAS) | **57** | 117,281 |
| `INVERSIONES_DESACTIVADAS.csv` | **42** | 354,525 |
| **Unión de columnas distintas** | **95** | 620,985 |

Presencia por archivo — `D` = Detalle, `C` = Cierre, `X` = Desactivadas:

```
DCX  NIVEL              DCX  SECTOR             DCX  ENTIDAD
DCX  CODIGO_UNICO       DC-  CODIGO_SNIP        DCX  NOMBRE_INVERSION
D--  NOMBRE_OPMI        D--  NOMBRE_UF          D--  NOMBRE_UEI
D--  NOMBRE_UEP         DC-  SEC_EJEC           DCX  ESTADO
DCX  SITUACION          DCX  MONTO_VIABLE       DCX  COSTO_ACTUALIZADO
D-X  CTRL_CONCURR       DCX  MONTO_LAUDO        DCX  MONTO_FIANZA
D--  ALTERNATIVA        DCX  FECHA_REGISTRO     DCX  FECHA_VIABILIDAD
DCX  FUNCION            DCX  PROGRAMA           DC-  SUBPROGRAMA
DCX  MARCO              DCX  TIPO_INVERSION     DCX  DES_MODALIDAD
D--  REGISTRADO_PMI     D--  PMI_ANIO_1..4      DCX  EXPEDIENTE_TECNICO
DCX  INFORME_CIERRE     DC-  TIENE_F9           DC-  FEC_REG_F9
DC-  ETAPA_F9           DC-  PRIMER_DEVENGADO   DC-  ULTIMO_DEVENGADO
D--  DEVEN_ACUMUL_ANIO_ANT   D--  DEV_ANIO_ACTUAL     D--  PIA_ANIO_ACTUAL
D--  PIM_ANIO_ACTUAL    D--  CERTIF_ANIO_ACTUAL D--  COMPROM_ANUAL_ANIO_ACTUAL
D--  SALDO_EJECUTAR     DC-  TIENE_F8           D--  ETAPA_F8
DC-  TIENE_F12B         D--  TIENE_AVAN_FISICO  D--  AVANCE_FISICO
D--  AVANCE_EJECUCION   D--  ULT_FEC_DECLA_ESTIM     DCX  DES_TIPOLOGIA
D--  IND_IOARR_EMERG    DCX  DEPARTAMENTO       DCX  PROVINCIA
DCX  DISTRITO           DCX  UBIGEO             DCX  LATITUD
DCX  LONGITUD           D--  FEC_INI_EJECUCION  D--  FEC_FIN_EJECUCION
D--  FEC_INI_EJEC_FISICA     D--  FEC_FIN_EJEC_FISICA
D-X  NUM_HABITANTES_BENEF    D--  MONTO_ET_F8   DC-  ANIO_PROCESO
-C-  CONTROL_CONCURR    -CX  NOM_OPMI           -CX  NOM_UF
-CX  NOM_UEI            -CX  RESPONSABLE_UEI    -CX  NOM_UEP
-C-  FEC_CIERRE         -C-  DES_CIERRE         -C-  CULMINADA
-C-  INICIO_EJEC_FISICA -C-  CULMINA_EJEC_FISICA
-C-  FEC_INI_OPER       -C-  DEVEN_ACUMULADO
-C-  TOTAL_LIQUIDACION  -C-  FEC_LIQUIDACION
```

### Variantes de nombre — la fuente de la trampa

| Concepto | DETALLE | CIERRE / DESACTIVADAS |
|---|---|---|
| SNIP | `CODIGO_SNIP` | ⚠ **ausente en DESACTIVADAS** |
| Control concurrente | `CTRL_CONCURR` (D, X) | `CONTROL_CONCURR` (C) |
| Unidades (OPMI/UF/UEI/UEP) | `NOMBRE_*` | `NOM_*` ← **causa la pérdida de 12,102 entidades, #19** |

### Los 10 campos que se extraen hoy

`cui` ← `CODIGO_UNICO` · `snip` ← `CODIGO_SNIP` · `nombre` ← `NOMBRE_INVERSION` ·
`estado_dataset` *(tag del script)* · `situacion` ← `SITUACION` · `ubigeo` ← `UBIGEO` ·
`dpto` ← `DEPARTAMENTO` · `prov` ← `PROVINCIA` · `dist` ← `DISTRITO` · `entidad` ← `ENTIDAD`

### Propuesta de los 6 faltantes (todos presentes en los 3 archivos)

| # | Columna | Alimenta |
|---|---|---|
| 11 | `DES_TIPOLOGIA` | Compuerta de rubro (ADR-013) y desempate de homónimos (#28) |
| 12 | `FUNCION` | Rubro grueso (SALUD / EDUCACIÓN) |
| 13 | `TIPO_INVERSION` | Proyecto vs IOARR → camino A/B de ADR-010 |
| 14 | `COSTO_ACTUALIZADO` | Corrobora el monto del certificado |
| 15 | `FECHA_VIABILIDAD` | Ventana temporal |
| 16 | `DES_MODALIDAD` | Modalidad de ejecución |

Alternativas también en los 3: `NIVEL`, `SECTOR`, `ESTADO`, `MONTO_VIABLE`,
`FECHA_REGISTRO`, `LATITUD`/`LONGITUD`, `EXPEDIENTE_TECNICO`.

⚠ **Trampa al elegir**: `FEC_INI_EJECUCION`, `FEC_FIN_EJECUCION`, `AVANCE_FISICO` y
todo el bloque presupuestal existen **solo en DETALLE** → darían null en el 76% de
las filas. Si se quieren, entran por el cold path (#18), no por el hot path.

---

## 9. Estado de las issues tras aplicar «documento primero» (2026-07-28)

Decisión del desarrollador: las issues se crean **cuando el trabajo está listo para
ejecutar**, no como descomposición de un plan. Catorce issues para ~4 tareas reales
no informaban.

**Abiertas — trabajo ejecutable hoy, sin depender de ADR-009:**

| Issue | Qué |
|---|---|
| **#19** 🔴 | BUG: el catálogo pierde 12,102 entidades (`NOMBRE_*` vs `NOM_*`) |
| **#14** | Retry con backoff en la descarga (~15 líneas) |
| **#24** | Cron semanal + que el fallo deje de ser silencioso |
| **#25** | Fase de medición: línea base secuencial |
| **#12** | Épica — índice que apunta a este documento |

**Cerradas — su contenido vive en este documento:**

| Issue | Motivo del cierre |
|---|---|
| #15, #21, #22 | Ya implementadas (§2) |
| #17, #18 | Planificación gated por ADR-009 → §8 tiene la referencia completa; se recrean cuando el ADR cierre |
| #13, #16, #20, #23 | Features sin información propia: eran un nivel de jerarquía sobre 2 tareas cada una |
