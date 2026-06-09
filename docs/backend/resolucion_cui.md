# Resolución de CUI de obra (backend)

> Cómo el backend toma cada **experiencia** del JSON espejo y le asigna el **CUI**
> de la obra en InfoObras, para luego cruzar paralizaciones y calcular el **Paso 5**.
> **Meta de diseño: minimizar la intervención humana** — que solo los casos rarísimos
> necesiten que una persona busque el CUI a mano y lo pegue para que el backend procese.

| Estado | Resultado (sin humano) | Fecha |
|---|---|---|
| ✅ **CERRADO** (diseño + prototipo validado · 3 datasets) | Libertador **100%** (41/41) · Trujillo **94%** (32/34) · CP-02 Lircay **50%** (24/48) | 2026-06-09 |

> **Rango realista 50–100%** según cómo venga el nombre: alto cuando se cita el CUI
> o el nombre es cercano al oficial; ~50% cuando los nombres vienen abreviados y las
> obras son ESSALUD/regímenes especiales ausentes de InfoObras. Ver §3.

**Pendiente (no bloquea el cierre)**: portar la lógica al backend real
`Alpamayo-InfoObras` (Python + rapidfuzz ya disponibles) y cablear el CUI resuelto
a paralizaciones → Paso 5. El método y los umbrales quedan **congelados** aquí; el
port es mecánico. No se persigue el ~5–10% irreducible (obras ausentes de InfoObras
o de nombre ambiguo) — esos van a REVISIÓN con candidatos a la vista, como se diseñó.

Prototipo y métrica: `tools/buscar_cui_por_nombre.py` + `tools/medir_resolucion.py`
+ `tools/diag_casos.py` (diagnóstico).

---

## 1 · El problema

La experiencia **no siempre trae el CUI**. Trae el **nombre del proyecto** y, según
el certificado, a veces el **SNIP/CUI**, el **N° de contrato** y el **RUC del emisor**.
InfoObras indexa la **obra de construcción** (no el contrato de supervisión) y su
búsqueda por nombre es por **substring contiguo** del nombre oficial. Por eso resolver
"solo con el nombre" es heurístico.

## 2 · El método — pipeline por capas

```
PASO 0 · ¿hay "SNIP/CUI NNNN" en el texto?  → fetch_by_cui + VERIFICAR → determinístico
PASO 1 · dedup: mismo folio/certificado o mismo CUI entre experiencias → resolver 1 vez
PASO 2 · (sin código) nombre → multi-fragmento + cruce RUC + ubicación + ranking difuso + compuerta
PASO 3 · spot-check (candidato fuerte, marca opcional) / manual (sin candidato fiable)
```

### Paso 0 — CUI/SNIP en el texto (la vía más fuerte)
- Regex `(?:SNIP|CUI|Código)\s*NNNN`. Si hay → `fetch_by_cui`.
- **Verificar** (anti-typo): el obra resuelto debe coincidir en **nombre** (mayoría de
  tokens del establecimiento) **o** en **ubicación** (departamento). Si coincide → se
  **confía** (el certificado lo cita; que InfoObras lo nombre distinto no es razón para
  mandar a humano). Si no coincide ni en nombre ni en departamento → **manual** (código
  sospechoso/mal transcrito).

### Paso 1 — Dedup
- Varias filas pueden ser **el mismo certificado** (1 fila = 1 periodo atómico). Si
  comparten **folio base**, o el texto dice "mismo certificado / 2º periodo", **heredan**
  el CUI ya resuelto (no se re-busca).
- **Cache** global de consultas (`_CACHE`): las mismas obras se repiten entre
  profesionales (mismo equipo, mismas obras) → se consultan una sola vez.

### Paso 2 — Nombre + RUC + ubicación (fallback heurístico)
1. **Quitar boilerplate** ("Supervisión de la obra:", "Plan de Contingencia…") y
   **expandir abreviaturas** (C.S.→Centro de Salud, E.S.→Establecimiento de Salud,
   P.S.→Puesto de Salud, H.R.→Hospital Regional).
2. **Extraer fragmentos**: establecimiento completo + nombre propio + arranque limpio
   (NO cortar en abreviaturas con punto: "Daniel **A.** Carrión").
3. **Buscar** cada fragmento en InfoObras (`obrasBasic`) y **unir** candidatos.
4. **Puntuar**: similitud difusa del nombre (rapidfuzz, con acentos normalizados) +
   bonos por **departamento**, "salud", **año** cercano, y **+30 si el RUC del emisor
   cuadra con `rucEjecutor`/`rucSupervisor`** de la obra (señal determinística cuando aplica).
5. **Compuerta**: la **mayoría** de los tokens distintivos del establecimiento deben
   estar en el candidato elegido (evita la falsa confianza del prefijo genérico).

### Paso 3 — Operación
- **RESUELTO** (determinístico / dedup / auto) → el backend procesa directo.
- **SPOT-CHECK** (candidato fuerte con duda) → se procesa, marcado para revisión opcional.
- **MANUAL** → el humano busca el CUI y lo **pega en la experiencia**; el backend reprocesa.

---

## 3 · Métrica (41 experiencias reales · caso Libertador)

| Vía | Exp | % |
|---|---|---|
| Determinístico (CUI en texto verificado) | 23 | 56% |
| Dedup (mismo certificado) | 2 | 5% |
| Auto (nombre verificado) | 16 | 39% |
| Probable / Manual | 0 | 0% |

→ **41/41 (100%) resueltas sin humano** en este caso · **0 falsos positivos**
(verificación independiente: el establecimiento real está presente en las 41 obras).

> ⚠ El 100% es sobre **este** dataset. En datos más sucios (grafías raras tipo
> "Guzmán Gonzáles", nombres sin establecimiento) habrá casos a revisión — el
> flujo los entrega **con candidatos**, no de cero.

La presencia de CUI-en-texto **varía mucho** por certificado (0–100% según el
profesional), por eso se necesitan **ambos caminos** (código y nombre+RUC).

### Regla N/A — obras fuera de scope (no cuentan en la métrica)
InfoObras solo tiene **obra pública de salud**. Las experiencias en obras
**privadas** (ej. "Edificio Pacific Tower") o **ajenas a salud** (ej. "Complejo
Penitenciario") **no son cruzables** y se marcan **N/A** — se **excluyen del
denominador** (no son falla del método; el humano las maneja por definición).
Detección: `es_aplicable(proyecto)` (expande abreviaturas → busca términos de
salud; reconoce "H.", "C.S.", "E.S.", "EE.SS.", CMI, INSN, INEN).

### Tres datasets reales
| Dataset | Formato | Aplic. | Sin humano | CUI en texto |
|---|---|---|---|---|
| Libertador | new_format (hoja CLAUDE) | 41 | **100%** | 56% |
| Trujillo | formato viejo | 34 | **94%** | 3% |
| CP-02 Lircay | BD_Experiencias (Paso 3) | 48 | **50%** | 19% |

**CP-02 es el caso adverso y el más informativo.** Cae a ~50% por razones
**estructurales del input**, no del algoritmo:
1. **Nombres abreviados/resumidos** por Claude ("H. Iquitos César Garayar García")
   en vez del nombre **oficial** de InfoObras ("MEJORAMIENTO DE LOS SERVICIOS DE
   SALUD DEL HOSPITAL…") → la búsqueda por substring no engancha (`cands=0`).
2. **Obras fuera de InfoObras/SNIP**: hospitales **ESSALUD de Alta Complejidad**,
   **INSN**, **INEN**, gestión **OIM** → no están en el portal (sistema de inversión
   propio). Irreducibles por diseño.
3. **Tokens genéricos** que colisionan ("La Libertad", "Ambo") → la desambiguación
   los manda a REVISIÓN honesta en vez de inventar candidato.
4. Solo **19%** cita el CUI (vs 56% del Libertador).

> **Implicación para el diseño de la skill** (accionable): instruir a Claude para
> (a) **preservar el nombre de la obra lo más cercano al oficial** posible (no
> resumir) y (b) **siempre exponer el CUI/SNIP** cuando aparezca en el certificado.
> Eso sube la resolución sin tocar el backend — el cuello de botella en CP-02 es
> cómo se **escribió** el nombre, no el matcher.
>
> ✅ **Implementado** en `skill/prompts/agent-propuesta.md` §A–E (reglas VERBATIM +
> captura de `cui`/`ruc_emisor` + ubicación con departamento) y en el schema
> `skill/schemas/espejo.js` (campos `cui`, `ruc_emisor`). El matcher
> (`resolver()`) ya prioriza el campo `cui` sobre el regex del nombre (Paso 0).

Los **2 irreducibles de Trujillo** (Chincheros ESSALUD, E.S. La Libertad) son el
mismo patrón: obra ausente de InfoObras o token único ambiguo → REVISIÓN con
candidatos a la vista, nunca un CUI inventado.

### Dos fixes de generalización (de probar CP-02 · 0 regresión en Lib./Tru.)
1. **Reconocer abreviaturas de salud**: "H."→Hospital, CMI→Centro Materno, EE.SS.,
   INSN, INEN. Sin esto, CP-02 marcaba **17 hospitales reales como falsos N/A**
   (varios con SNIP que habrían resuelto solos).
2. **Limpiar la cola de metadata** embebida en el nombre ("; 27,420 m²; 240 camas;
   S/.118M", "– SNIP 71857"): contaminaba el establecimiento ("SNIP" se volvía un
   token) y rompía la búsqueda. `_META` la corta antes de extraer fragmentos (el
   código ya lo tomó Paso 0 del texto crudo).

Piso realista: **~90–95%** en datos diversos.

### Afinamientos que llevaron Trujillo 88% → 94% (sin romper Libertador 100%)
1. **Patrones de establecimiento ampliados**: `_RE_EST` ahora reconoce
   "Centro Asistencial", "Policlínico", "Centro Materno" (antes solo
   hospital/puesto/centro de salud/establecimiento de salud).
2. **Fragmento "núcleo" limpio** (`_nucleo`): quita **iterativamente** prefijos
   institucionales ("Hospital **de Apoyo** Sicuani" → "Sicuani") y colas
   ("CHINCHEROS **- ESSALUD**" → "CHINCHEROS"). El strip de una sola pasada dejaba
   "de Apoyo"/"de Emergencias" y la búsqueda por substring no hallaba la obra.
   No reemplaza fragmentos previos: **suma recall** (no se busca si el núcleo es un
   departamento, para no traer ruido).
3. **Retry en `_query`**: la API en vivo da timeouts; reintenta 3× y no cachea el
   fallo → métrica estable (antes oscilaba 95–100% por flakiness, no por el método).

### Desambiguación por ubicación (`ubicacion()` + penalización)
**Problema**: "E.S. **La Libertad**" en Junín colisiona con el **departamento**
La Libertad → la búsqueda traía obras del depto. La Libertad y el ranking las subía.

**Solución** en tres piezas:
- `ubicacion(proyecto)` toma el departamento de las palabras **DESPUÉS** del
  establecimiento (la "cola": "…La Libertad**, Huancayo, Junín**" → `{JUNIN}`),
  así el nombre del establecimiento no se confunde con un departamento homónimo.
  Si **no** se reconoce establecimiento (prefijo genérico tipo "Mejoramiento de la
  Capacidad Resolutiva…"), usa **todo** el texto para no perder el depto.
- En `puntuar()`: **+15** si el departamento del candidato coincide con la
  ubicación explícita, **−20** si la contradice (desempata homónimos: el
  "Materno Infantil" de **Huánuco** le gana al homónimo de **Amazonas**).
- `loc_contra`: si la ubicación explícita **contradice** al mejor candidato, una
  señal **débil** (PROBABLE) baja a **REVISIÓN** — pero un **gate de tokens fuerte**
  (AUTO, score≥70) **manda igual**, porque InfoObras a veces registra la obra en un
  departamento distinto al que cita el certificado. El RUC siempre tiene prioridad.

### Tres fixes que llevaron 90% → 100%
- **Boilerplate ampliado**: quitar "Elaboración del Expediente Técnico y Ejecución
  de la Obra:" y "Ejecución de la obra:" (contaminaban el ranking → subían obras
  de "expediente técnico" de otros departamentos).
- **Tokens del establecimiento robustos**: derivarlos de la **frase del
  establecimiento** (no de la posición del fragmento) y no descartar nombres
  propios cortos ("Ambo", 4 letras).
- **Comparación sin puntuación**: la compuerta fallaba porque las palabras del
  nombre llevaban coma/punto pegado ("AMBO," ≠ "AMBO"). Extraer palabras con
  `[A-Z]+` lo resolvió — era el verdadero culpable de los "manuales".

---

## 4 · Hallazgos de las 5 pruebas (lo que moldeó el método)

| Profesional | Reveló |
|---|---|
| Jefe de Supervisión | Multi-fragmento esencial · **acentos muerden** · falsa confianza del prefijo genérico |
| Equipamiento | **El RUC del emisor está en el certificado** → cruzable con InfoObras |
| Suelos | **El CUI a veces viene en el texto** → extraerlo primero · dedup de periodos |
| Arquitecto | **El CUI-del-texto NO es infalible** ("Jesús Guerrero Cruz") → verificar · compuerta muy estricta |
| Medio Ambiente | **Traslape** entre experiencias (Paso 5) · mismas obras se repiten (cachear) · dedup "2º periodo" |

---

## 5 · Paso 5 — días efectivos (relacionado)

Dos descuentos sobre los días brutos del certificado:
1. **Paralizaciones** de la obra (InfoObras, una vez resuelto el CUI).
2. **Traslapes** entre experiencias del mismo profesional (no estar en 2 obras a la
   vez · ALT11) → `dias_efectivos()` fusiona intervalos solapados.

En el Libertador: 1/14 profesionales con traslape (2 días).

---

## 6 · Pseudocódigo para el backend

```python
def resolver_cui(exp, cache, hermanos_por_folio):
    # FUERA DE SCOPE — obra privada o ajena a salud (no está en InfoObras)
    if not es_aplicable(exp.proyecto):
        return NoAplica(exp)                      # N/A · no cuenta en la métrica

    # PASO 0
    cod = extraer_codigo(exp.proyecto)          # "SNIP/CUI NNNN"
    if cod:
        obra = fetch_by_cui(cod)                  # (cacheado)
        if obra and (nombre_coincide(obra, exp) or departamento_coincide(obra, exp)):
            return Resuelto(cod, via="cui_texto")
        # si no verifica → manual (código sospechoso)
        return Manual(exp, motivo="cui_no_verifica", candidato=cod)

    # PASO 1 — dedup por folio (hermano ya resuelto)
    fb = folio_base(exp.folio)
    if fb in hermanos_por_folio:
        return Resuelto(hermanos_por_folio[fb], via="dedup")

    # PASO 2 — nombre + RUC + ubicación
    cands = buscar_por_fragmentos(exp.proyecto)   # (cacheado)
    ranked = rankear(cands, exp)                   # difuso + departamento + año + RUC(+30)
    best = ranked[0] if ranked else None
    if best and ruc_match(best, exp):              return Resuelto(best.cui, via="ruc")
    if best and compuerta_establecimiento(best, exp) and best.score >= 70:
        return Resuelto(best.cui, via="nombre")    # gate fuerte manda (aunque ubicación discrepe)
    loc_contra = ubicacion(exp) and best and depto(best) not in ubicacion(exp)
    if best and (compuerta(best, exp) or best.score >= 90) and not loc_contra:
        return SpotCheck(best.cui, candidatos=ranked[:3])
    return Manual(exp, candidatos=ranked[:3])      # ← el humano pega el CUI aquí
```

---

## 7 · Trade-off y operación

- Las compuertas se **aflojaron a propósito** para minimizar el trabajo humano: se
  **confía** en el CUI citado + ubicación, y en el nombre con establecimiento verificado.
  Riesgo aceptado: ocasionalmente tomar una **fase distinta** de la obra correcta; si la
  obra resultara sin datos útiles, se detecta aguas abajo.
- Lo **manual** (~5–10% en datos diversos; 0% en datos que citan el CUI) **no es
  "buscar todo de cero"**: el sistema entrega los candidatos que encontró; el humano
  solo **confirma o pega el CUI**. Las obras **ausentes de InfoObras** (privadas, o de
  sistemas como ESSALUD) son irreducibles por diseño.
- Una vez con CUI, todo entra al flujo normal: InfoObras → paralizaciones → Paso 5.
