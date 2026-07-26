# ADR-012 · Candado determinístico de correspondencia cargo ↔ bases (núcleo de especialidad + segunda puerta de funciones)

- Fecha: 2026-07-26 · Estado: **aprobado, implementado** (issue #31)

## Contexto

El Comité (Ing. Manuel + Marco Antonio Gonzales, 25-jul-2026, huachocolpa P4
«Especialista en Planeamiento y Costos») declaró **NO CUMPLE** cuatro
experiencias que el sistema había dado por buenas y pintado en verde:

| Cargo declarado | Por qué no acredita |
|---|---|
| Ing. de Costos y Presupuestos | costos sin planeamiento |
| Ingeniero de Costos y Valorizaciones | costos sin planeamiento |
| Especialista en Costos, Metrados y Valorizaciones | costos sin planeamiento |
| Especialista en Planificación | planeamiento sin costos |

Dos condiciones simultáneas fundaron el veredicto: (a) ningún cargo reúne el
núcleo completo, y (b) los certificados solo consignan cargo/fechas/obra, sin
funciones, y no se adjuntó documento que las acredite.

Causa raíz verificada en código:

1. `cargo_bases_valido` lo juzgaba **solo el LLM** (`agent-evaluador`), que
   matchea por tokens compartidos. Evidencia viva (espejo divino): *"SÍ —
   'Supervisor de Obra' figura en cargos_similares_validos"*. Trampa: «COSTOS»
   presente → falso CUMPLE.
2. El prompt del evaluador traía la regla anti-falso-negativo *"una discrepancia
   NUNCA convierte un CUMPLE en NO CUMPLE"* → sesgo estructural hacia CUMPLE.
3. `funciones_similares` estaba **hardcodeado a `null`** en
   `consolidar_espejo.js` → detectar "falta de funciones" era estructuralmente
   imposible.

`match_cargo.js` (candado ya validado) resuelve **otra** pregunta: a qué cargo
del Cuadro postula el profesional, no si la experiencia acredita.

## Decisión

### 1 · Semántica de `cargos_similares_validos`: OR entre alternativas, AND dentro

Verificado sobre 35 espejos reales (322 profesionales, 1421 experiencias): la
lista son **cargos alternativos aceptables**, no reformulaciones del mismo. Por
eso el cargo declarado acredita si reúne el **núcleo completo de alguna**
alternativa. Un primer diseño por *intersección* de variantes se descartó tras
medirlo: dejaba al candado sin núcleo derivable en 259 de 322 profesionales.

### 2 · El núcleo se exige COMPLETO

Núcleo = términos de la alternativa tras descartar (a) **sustantivos
intercambiables** (especialista/responsable/encargado/ingeniero/inspector…),
(b) **ruido** de la columna ("cargos similares:", "de obra"), (c)
**cualificadores** sin carga de especialidad (medio, trabajo) y (d) **sustantivos
de actividad o contenedor** (desarrollo, elaboración, diseño, expediente,
instalación…), que dicen qué se hace, no en qué se es especialista. Los cuatro
grupos salieron de medir el replay, no de intuición: (d) concentraba los
faltantes más reclamados (94× entre los cuatro primeros) contra especialidades
reales de 2-3×.

Equivalencias admitidas, **mínimas y conservadoras**: solo
`planificación ≈ planeamiento` (la que el Comité avaló en el caso) más la
familia derivativa por prefijo (supervisión↔supervisor, ambiente↔ambiental),
que evita falsos NO puramente morfológicos. **`costos ≈ presupuestos ≈
valorizaciones` NO se admite** — reabre exactamente el falso CUMPLE que este
candado ataja. Ampliar la tabla exige aval explícito del Comité.

### 3 · Segunda puerta: funciones

`agent-propuesta-profesional` extrae `funciones_similares` **solo si el documento
las lista textualmente**; un certificado que solo dice «desempeñando el cargo de
X, del … al …, en la obra Y» → `null`. El consolidador deja de hardcodearlo.
Cargo que no acredita **+** funciones `null` = el caso duro del Comité.

### 4 · Salida en dos niveles (calibrada con el replay)

| Situación | Observación | Celda del Excel |
|---|---|---|
| No acredita + sin funciones + **Claude dijo SÍ** | ALERTA | **roja** `NO (candado: …)` |
| No acredita + sin funciones + Claude sin veredicto | ADVERTENCIA | **amarilla** `POR VERIFICAR (candado: …)` |
| No acredita + sin funciones + Claude ya dijo NO | ADVERTENCIA | sin tocar |
| No acredita + **con** funciones listadas | ADVERTENCIA | sin tocar (la 2ª puerta la decide el Comité) |
| Acredita pero Claude dijo NO | INFO | sin tocar (posible falso negativo) |
| Sin núcleo derivable | INFO (1 por profesional) | sin tocar (abstención) |

El texto de Claude se conserva entre `⟦⟧` (traza). El color sale del prefijo del
texto vía `_fill_veredicto`: **cero cambios al formato congelado del Excel**.

### 5 · Lo que el candado NO hace

- **No toca el cómputo de días.** El descuento por `cargo_bases_valido == "NO"`
  que describe `docs/backend/validador.md` nunca estuvo implementado y no se
  implementa aquí: el sistema **señala, no juzga**. Si el Comité lo pide, es
  tarea aparte.
- **No marca NO por ausencia de datos**: sin lista de cargos válidos, sin núcleo
  derivable o con un cargo declarado sin términos distintivos → se abstiene.

### 6 · Ubicación

`backend/validacion/cargo_nucleo.py` — corre server-side en la etapa VALIDACIÓN,
**independiente de la versión de la skill instalada** en Cowork. La skill solo
aporta el hecho (`funciones_similares`) y deja de sesgar el juicio.

## Verificación (replay sobre 35 espejos reales de producción)

| | |
|---|---|
| experiencias evaluadas | 1421 |
| acreditan sin alerta | 1262 (89.1%) |
| marca **roja** (contradicción con un SÍ) | 15 (1.1%) |
| marca **amarilla** (por verificar) | 116 (8.2%) |
| con funciones listadas (solo observación) | 24 |
| posibles falsos negativos señalados | 2 |
| profesionales en abstención | 2 de 322 |

**Los 4 cargos del caso del Comité salen marcados en rojo sobre el espejo real
de producción.** Suite: 303 pytest + 16 asserts de `match_cargo.test.js`, verde.

## Alternativas consideradas

- **Núcleo por intersección de variantes**: descartado tras medirlo (80% de
  abstención) — la lista son alternativas, no sinónimos.
- **Marcar rojo también sin veredicto de Claude**: descartado; ahí no hay verde
  que desmentir y la precisión del candado es menor (172 marcas vs 15). Se pide
  confirmación en amarillo, vocabulario que el sistema ya usa.
- **Descontar días de las experiencias rechazadas**: descartado por ahora —
  mezcla un cambio de cómputo con uno de detección y arriesga los CUMPLE
  legítimos; además el veredicto duro es del Comité.
- **Admitir `costos ≈ presupuestos`**: descartado sin aval del Comité; convierte
  el caso 1 del Comité en un CUMPLE.
