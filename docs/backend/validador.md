# Validador determinístico — spec de las 15 NOTAS

> **Status: 📝 borrador reconstruido — pendiente confirmar contra `references/reglas.md`
> de la skill de Manuel.** Fuentes de esta reconstrucción:
>
> 1. `propuesta-command.docx` (2026-06-09) — el SKILL.md real de la skill `propuestas`
>    que Manuel ya corre en su Cowork; cita las NOTAS por número en su flujo.
> 2. Excel Libertador (`fixtures/new_format/02. Formato de evaluacion COMPLETADO.xlsx`)
>    — output real de esa skill (14 profesionales); evidencia cómo se aplican.
>
> Cuando llegue `reglas.md`: hacer diff contra este doc, corregir numeración/detalle
> y subir el status a ✓. Las notas marcadas ⚠ tienen numeración o detalle incierto.

## 1. Qué es y dónde corre

El validador es el **componente 1** del pipeline backend (etapa `VALIDACION`, después
de `INGESTA` — ver [orquestador.md](orquestador.md)). Recibe el JSON espejo ya validado
de schema (Pydantic) y verifica **determinísticamente** que lo que Claude afirma es
internamente consistente: conteos, fechas, traslapes, órdenes, totales, campos
obligatorios de negocio.

**Qué NO hace**: no re-evalúa criterios de las bases (eso es de Claude, decisión
cerrada del pivote), y no toca portales externos (eso es de las etapas 3a/3b).

**Salida**: `Observacion[]` acumuladas (severidad info/advertencia/error) +
`ItemRevision[]` para lo que requiere humano. Un fallo de nota **no tumba el job**:
marca y sigue (contrato de etapa del orquestador).

## 2. Las 15 NOTAS reconstruidas

Resumen — verificable determinísticamente por el backend (✔), responsabilidad de
Claude que el backend solo re-chequea parcialmente (◐), o puramente del lado Claude (✘):

| # | Tema | Backend | Confianza |
|---|---|---|---|
| 1 | Cross-check conteo experiencias vs cuadro resumen Anexo 16 | ✔ | ✓ alta |
| 2 | Cargo y tipo de obra estrictos según bases (sin criterio propio) | ◐ | ✓ alta |
| 3 | ISOs: buscar en todo el documento, ≥4 variaciones de búsqueda | ✘ | ✓ alta |
| 4 | PMP: solo emitido por PMI, con vigencia de 2 años | ◐ | ✓ alta |
| 5 | Leer del certificado, no de la autodeclaración | ✘ | ✓ alta |
| 6 | Una fila por periodo atómico del certificado | ✔ | ⚠ numeración 6/8 |
| 7 | Orden: profesionales según documento; experiencias por fecha final asc | ✔ | ✓ alta |
| 8 | Sub-periodos de "experiencia efectiva" del certificado | ✔ | ⚠ numeración 6/8 |
| 9 | Traslapes entre periodos del mismo profesional → marcar (rojo) | ✔ | ✓ alta |
| 10 | Ventana COVID 16/03/2020–30/06/2020 → marcar (rojo) | ✔ | ⚠ numeración 10/11 |
| 11 | Incumplimientos / preguntas de validación que no cumplen → rojo | ✔ | ⚠ numeración 10/11 |
| 12 | Verde = por verificar; insistir hasta 4 veces antes de marcar | ◐ | ✓ alta |
| 13 | Fechas como fecha, montos como número | ✔ | ✓ alta |
| 14 | Consorcio: ISO puntúa solo si TODOS los consorciados acreditan | ✔ | ✓ alta |
| 15 | Partes 3–4 replicadas por cada profesional clave (ninguno omitido) | ✔ | ✓ alta |

### NOTA 1 — Cross-check de conteo vs Anexo 16

**Enunciado**: cada profesional declara en su Anexo 16 un cuadro resumen
("experiencia total acumulada es de X años"). El número de experiencias extraídas y el
total de días deben cuadrar contra esa declaración.

**Evidencia Libertador**: cada bloque Parte 4 tiene fila "Cross-check vs cuadro
resumen del Anexo 16"; algunos requirieron "2do/3er intento (re-OCR a 400/450dpi)".

**Verificación backend**:
- `len(experiencias)` del espejo == `cross_check_nota1.declaradas`.
- `sum(dias)` recalculado desde `fecha_inicial/fecha_final` == `total.dias` reportado
  (tolerancia ±1 día por convención de conteo inclusivo).
- Si `cross_check_nota1.cuadra == false` → `Observacion(advertencia)` con ambos números.

**Requiere**: que `cross_check_nota1` y `experiencia_total_declarada` existan en el
schema espejo (hoy NO están — gap confirmado, va en la unificación del contrato).

### NOTA 2 — Cargo y tipo de obra estrictos según bases

**Enunciado**: la validez del cargo desempeñado y del tipo de obra se juzga
**literalmente contra el texto de las bases** ("si las Bases piden 'Residente' y el
certificado dice 'Residente', es válido — no impongas criterio propio").

**Verificación backend (parcial)**: el juicio es de Claude (`cargo_bases_valido`,
`tipo_obra_valido`), pero el backend verifica **consistencia**: si
`cargo_bases_valido == "NO"` la experiencia no puede sumar al total usado en el
veredicto `cumple`. Recalcular el total solo-válidas y comparar.

### NOTA 3 — Búsqueda exhaustiva de ISOs

**Enunciado**: los certificados ISO (9001, 14001, 37001) pueden estar en cualquier
parte de la propuesta; buscar variando la consulta al menos 4 veces.

**Backend**: ✘ no verificable (es instrucción de búsqueda en PDF). Queda en el prompt
de `agent-propuesta-mapa`.

### NOTA 4 — PMP solo del PMI

**Enunciado**: una certificación PMP solo vale emitida por el Project Management
Institute, con sello PMI, fechas de inicio/expiración y vigencia de 2 años. No valen
capacitaciones, diplomados, horas ni PDUs.

**Verificación backend (parcial)**: si el factor B aplica y Claude reporta un PMP,
verificar que la vigencia declarada cubra la `fecha_presentacion_oferta`
(expiración ≥ fecha presentación). La autenticidad del emisor la juzga Claude.

### NOTA 5 — Certificado manda sobre autodeclaración

**Enunciado**: los datos de cada experiencia se leen del certificado/constancia, no
del cuadro autodeclarado del Anexo 16. El Anexo 16 solo sirve para el cross-check (N1).

**Backend**: ✘ no verificable directamente; es disciplina de extracción. El N1 es su
red de seguridad: discrepancias certificado↔autodeclaración salen como advertencia.

### NOTAS 6 y 8 — Atomicidad de periodos ⚠

**Enunciado (combinado en el docx)**: una fila por periodo de cada certificado. Si un
certificado detalla "experiencia efectiva" en sub-periodos (caso Consorcio Pentagono
en Libertador: 4 tramos dentro de 2021–2023), cada tramo es una fila.

**Verificación backend**:
- Ninguna fila con `fecha_final − fecha_inicial` absurda (> 15 años → advertencia,
  probable fusión de periodos).
- Filas del mismo certificado (mismo `folio`) no deben tener fechas idénticas
  duplicadas (duplicación accidental).

⚠ La partición exacta entre la 6 y la 8 se confirma con `reglas.md`.

### NOTA 7 — Orden canónico

**Enunciado**: profesionales en el orden del documento de la propuesta; dentro de cada
profesional, experiencias por **fecha final ascendente**.

**Verificación backend**: chequear monotonía de `fecha_final` dentro de cada
`profesional.experiencias[]`. Violación → `Observacion(info)` (no es error de datos,
es de presentación; el Excel final se regenera ya ordenado).

### NOTA 9 — Traslapes

**Enunciado**: detectar periodos solapados del mismo profesional y marcarlos (rojo en
el Excel). Los días traslapados no se cuentan dos veces.

**Verificación backend**: recalcular intersecciones de `[fecha_inicial, fecha_final]`
por profesional (lógica hermana del ALT11 de Alpamayo — fusión de periodos solapados).
Comparar contra los `traslape` que Claude marcó: traslape real no marcado →
`Observacion(error)`; marcado inexistente → `Observacion(advertencia)`.

**Requiere**: campo `traslape` en el schema espejo (hoy NO está — gap confirmado).

### NOTAS 10 y 11 — Marcado rojo: COVID e incumplimientos ⚠

**Enunciado (combinado en el docx)**: rojo = incumplimiento, advertencia, pregunta de
validación que no cumple, traslape, o experiencia que incluye la ventana COVID
(**16/03/2020–30/06/2020**).

**Verificación backend**:
- COVID: recalcular `intersecta([fecha_inicial, fecha_final], [2020-03-16, 2020-06-30])`
  y comparar contra `incluye_covid` de Claude. Discrepancia → `Observacion(error)`.
- La ventana vive en **un solo lugar configurable** del backend (no hardcodeada en
  N sitios — hoy está repetida en 3 prompts de la skill).

⚠ Qué dice exactamente la 10 vs la 11 se confirma con `reglas.md`. Ojo: el
`contrato_refactor.md` §3 menciona "15/03/2020" como inicio en un punto — el docx de
Manuel dice **16/03** (fecha del D.S. de emergencia). Confirmar y unificar.

### NOTA 12 — Verde = por verificar (tras insistir 4 veces)

**Enunciado**: un dato dudoso se marca "POR VERIFICAR" (verde) solo después de hasta 4
reintentos de lectura.

**Verificación backend (parcial)**: todo valor `"POR VERIFICAR"` en campos
verificables por fuentes oficiales (firmante, colegiatura, RUC) genera un
`ItemRevision` — y cuando la etapa SUNAT/InfoObras pueda resolverlo, lo resuelve.
Evidencia Libertador: firmantes ilegibles (prof. 3), fecha de colegiatura (prof. 6),
acreditación del certificador ISO 37001 — hoy mueren en la celda; con el backend se
convierten en cola de trabajo.

### NOTA 13 — Tipos de dato

**Enunciado**: fechas en formato fecha, montos/cantidades en formato número.

**Verificación backend**: garantizada por construcción — el schema Pydantic tipa
`date`/`float` y el Excel final se **regenera** con openpyxl (formatos correctos,
sin floats sucios tipo `61.019999999999996` que aparecen en el Excel actual).

### NOTA 14 — Consorcio: ISO de TODOS

**Enunciado**: en consorcio, un factor ISO (C/E/J) puntúa solo si **todos** los
consorciados lo acreditan.

**Verificación backend**: con la lista de consorciados (de la promesa de consorcio,
Parte 1) y los certificados ISO con su titular: si `factores[X].puntaje > 0` pero
el conjunto de titulares no cubre todos los consorciados → `Observacion(error)`.

**Requiere**: que el espejo relacione cada ISO con su consorciado titular (hoy el
schema no tiene ese vínculo explícito — gap confirmado).

### NOTA 15 — Ningún profesional omitido

**Enunciado**: las Partes 3–4 se repiten por cada profesional clave del listado de
las bases; ninguno puede faltar.

**Verificación backend**: `len(profesionales)` del espejo == número de cargos del
personal clave según bases (campo de `agent-bases`). Faltante → `Observacion(error)`
+ `ItemRevision`. El schema ya valida `n_prof` contiguo 1..N; esto agrega el cruce
contra el N esperado.

## 3. Validaciones adicionales (evidencia del Excel Libertador, no son NOTAS)

Huecos reales del output actual de la skill de Manuel que el validador debe atrapar:

| Check | Evidencia |
|---|---|
| **Veredictos obligatorios no vacíos** (`cumple`, años válidos) | Profesionales 12, 13 y 14 tienen "¿CUMPLE el requisito B.2?" **en blanco** y nadie lo notó |
| **Coherencia de factores**: todo factor del cuadro resumen de bases aparece en Parte 5 con puntaje o "NO APLICA" justificado | Factor B correctamente "NO APLICA" en Libertador — verificar que sea sistemático |
| **Folios presentes y plausibles** (numéricos o rango, dentro del total de folios) | Folios tipo "677 (B.2) y 745 (Factor A, idéntico)" — formato libre que hay que normalizar |
| **Puntaje total** == suma de puntajes de factores que aplican | Parte 5: 100 = 55+15+15+15 ✓ en Libertador; recalcular siempre |
| **Bloques Factor A duplicados del B.2** declarados como tales | Notas "bloque 693-701 es duplicado exacto del B.2" — si Claude lo afirma, los periodos deben ser idénticos |
| **Identidad consistente** (DNI igual en todas las menciones del profesional) | Prof. 14: DNI 32408330 en Anexo 16 vs 32408336 en certificado — Claude lo atrapó; el validador lo exige siempre |

## 4. Insumos que este doc le exige al contrato (espejo)

Campos que deben agregarse al schema en la unificación (paso 2 del plan en `dev`):

1. `profesional.cross_check_nota1 = {extraidas, declaradas, dias_declarados, cuadra, intentos}` (N1)
2. `profesional.experiencia_total_declarada` — texto literal del Anexo 16 (N1/N5)
3. `experiencia.traslape: bool` (N9)
4. `postor.consorciados[]` + titular por certificado ISO (N14)
5. `_meta.version_contrato` — para rechazar espejos de versión incompatible en INGESTA
6. `bases.n_personal_clave` o equivalente para el cruce de N15

## 5. Checklist al recibir `reglas.md` de Manuel

- [ ] Confirmar numeración exacta de 6 vs 8 y 10 vs 11
- [ ] Confirmar fecha de inicio de ventana COVID (15 vs 16/03/2020) y unificar en
      contrato_refactor.md + prompts de la skill
- [ ] Verificar si hay parámetros adicionales (límite inferior 90%, regla de redondeo
      del 2.º decimal) que pertenezcan al validador y no solo al prompt
- [ ] Diff completo de este doc vs reglas.md → subir status a ✓
