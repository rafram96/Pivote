# Plan de implementación — Calidad de resolución y veredictos

> Continúa el trabajo de robustez de CUI/InfoObras (commits `52256fb`…`d4126f9`).
> Lo ya hecho: filtro exacto + `codUniqInv`, selección por valorizaciones reales,
> bypass + caché por `obra_id`, reintentos en 3 capas + 2da pasada, flag de
> cobertura. Este plan cubre lo que sigue: **que el veredicto CUMPLE/NO CUMPLE
> sea correcto**, cerrar 2 residuales, y hacer accionable la cola de revisión.

Status: ✓ hecho · ⏳ pendiente · ⚠ requiere decisión

---

## Fase 1 — Días efectivos (Paso 5): clamp a la ventana de valorizaciones ✓ (b580fd6, 377dc98)

**Es la fase de mayor impacto: decide el veredicto.** Validado contra la
auditoría: prof 1 → 1.64, prof 5 → 0.80 (exactos). Las tres guardas en su sitio
(clamp genuino / obra sin valoriz / fetch fallido) + flag de fecha POR VERIFICAR.

### Problema (hallazgo concreto)
`dias_efectivos_profesional` ([backend/reglas/calculo.py:119](backend/reglas/calculo.py:119))
calcula `brutos − paralizados − traslape`. Los "paralizados" incluyen las
paralizaciones explícitas **y** los huecos internos entre valorizaciones
(`periodos_inactividad`). Pero el periodo del certificado que cae **fuera** del
rango de valorizaciones de la obra **NO se descuenta**:

- Caso Valdizán 1:1 — cert 2016-06→2017-05, obra 33900 valoriza solo hasta
  2016-07. El tramo ago-2016→may-2017 (≈10 meses) **no es un hueco interno** →
  hoy se cuenta como días efectivos, aunque no hay valorización que lo respalde.
- Esto contradice la regla del proyecto "sin valorización = no cuenta"
  ([[reunion-2026-06-07-hallazgos]]) y puede inflar `años efectivos` → veredicto
  CUMPLE falso (el espejo de los NO CUMPLE que sí vimos).

### Cambio propuesto
Mantener `reglas/` puro; meter la lógica InfoObras en la etapa.
En `EtapaInfoObrasReal._procesar` ([backend/orquestador/etapas_reales.py](backend/orquestador/etapas_reales.py)),
al armar las paralizaciones de la experiencia, **añadir los tramos del
certificado fuera de `[primera_valoriz, última_valoriz]`** como intervalos de
descuento (cabeza y cola). Así `dias_efectivos_profesional` los resta sin tocar
su firma. Persistir esos tramos en `enr["paralizaciones"]` con un `tipo` nuevo
(p.ej. `"fuera_de_ventana"`) para que el Excel los muestre.

### Verificación
- **Auditoría manual de 1 caso de punta a punta** antes de tocar código: tomar
  un profesional con cobertura parcial real (prof 1 / Valdizán, o el invertido
  prof 7) y recalcular a mano brutos → descuentos → años → veredicto, comparando
  contra el cuadro de hitos del Excel. Confirmar el bug antes de arreglarlo.
- **Tests** (`backend/tests/test_reglas*.py` o `test_etapas_reales.py`):
  - cert que excede la ventana de valorizaciones por ambos extremos → solo
    cuenta el tramo cubierto.
  - cert totalmente dentro de la ventana → sin cambios (no regresión).
  - interacción con paralización dentro del tramo cubierto (no doble descuento).
- **Manual**: re-correr el job y confirmar que los `años efectivos` de los casos
  de cobertura parcial bajan al valor correcto.

### Guardas críticas (sustentadas por la auditoría del run 4816fbdf3bea)
El clamp solo es un **número final** cuando la ventana de valorizaciones es
**conocida y no vacía**. Distinguir tres casos (no colapsarlos a "0 días"):
1. **Obra OK + cobertura parcial** (prof 1: Egoavil paralizada, Valdizán hueco)
   → clamp genuino al tramo cubierto. ✅
2. **Obra OK + `Sin Ejecución` / 0 avances** (prof 5: Ayancocha 10056) → ventana
   indefinida → **no clampar a 0-final**; revisión "obra sin valorizaciones, no
   verificable". El 0 se muestra pero **flagueado**, no como auto-rechazo.
3. **Fetch falló** (prof 11 Exp 2: caída de red) → ventana DESCONOCIDA → **nunca
   clampar** (traducir "no sé" a "0 días" produce NO CUMPLE falso — el bug
   espejo). Va a revisión "el portal no respondió" (ver Fase 2b).

→ El clamp lee la ventana de `enr["obra_ficha"]`/valorizaciones **solo si la
experiencia se procesó con éxito**; las que quedaron en `err`/sin-avances no se
clampan, se marcan a revisión.

### Riesgo
⚠ Puede cambiar veredictos de CUMPLE→NO CUMPLE (correcto, pero avisar a Manuel).
**Cuando el clamp invierte a NO CUMPLE, marcar a revisión** (un rechazo por
datos faltantes de InfoObras es impugnable en licitación — lo confirma un humano).
Cuidar el **doble descuento**: el tramo "fuera de ventana" es disjunto de los
huecos internos (uno es complemento de `[1ª,última]` valoriz, el otro está
dentro) → test que lo verifique.

---

## Fase 2 — Cerrar los 2 residuales de correctitud ✓ (ece2900, efcfe9d)

> Hallazgo nuevo (no cubierto por 2a): la resolución por NOMBRE puede dar **CUIs
> distintos entre corridas** (prof 10: 2160319 que cubre vs 2193936 que no), por
> el límite de 20 resultados del portal. Lo atrapa el flag de cobertura (0% →
> revisión), así que es seguro, pero es **no-determinístico**. Tratamiento
> propio pendiente (búsqueda más estable, o flag de "match por nombre ambiguo").

### 2a · Bypass por `obra_id` validado por cobertura
**Problema:** el bypass ([fetch_by_cui](backend/scraping/infoobras.py)) confía en
el `obra_id` que eligió el resolver. Para obras de **nombre idéntico** (Valdizán
33900/71173) el representante del resolver sale por orden de iteración, no por
diseño; si el orden cambia, el bypass traería la obra equivocada.

**Cambio:** que el bypass **valide** que la obra elegida solapa el certificado;
si su cobertura es ~0 pero un hermano del mismo CUI sí cubre, caer a
`seleccionar_obra` (que ya es correcta con la ventana real). Alternativa: hacer
que el representante del resolver en PASO 2 sea consciente del solape.

**Test:** dos obras mismo CUI, nombres idénticos, distinto periodo de
valorizaciones; el bypass con el `obra_id` "equivocado" debe corregir a la que
cubre.

### 2b · `_query`: distinguir fallo-de-red de resultado-vacío
**Problema:** `ConsultaInfoObras._query` ([backend/resolucion/cui.py](backend/resolucion/cui.py))
devuelve `[]` tanto si la búsqueda no tuvo resultados como si la red agotó los 3
reintentos. El resolver no distingue → degrada al fragmento genérico → revisión
con motivo engañoso ("la ubicación contradice") en vez de "el portal no
respondió" (caso 6:1/3:2 según el run).

**Cambio:** que `_query` señale el fallo de red de forma distinta (excepción
propia `PortalNoResponde`, o un centinela). En `resolver()`, si una búsqueda por
nombre falla por red, no degradar: marcar la experiencia a revisión con motivo
**"el portal no respondió — reintentar"** y candidatos vacíos.

**Test:** fake de consulta que lanza error de red → la experiencia va a revisión
con el motivo correcto, sin candidatos basura.

---

## Fase 3 — Cola de revisión accionable (usuario no técnico) ⏳

Encaja con [[usuarios-no-tecnicos-ui-simple]]: el evaluador debe entender y
accionar cada pendiente sin jerga.

### 3a · Mensajes de revisión específicos por causa
Hoy el motivo es genérico ("solo solapa X%"). Diferenciar en
`EtapaInfoObrasReal` según el patrón detectado:
- Periodo en hueco entre obras → *"el periodo cae entre la obra X (fin AAAA-MM)
  y la Y (inicio AAAA-MM) — posible obra complementaria no registrada"*.
- Obra sin valorizaciones (`Sin Ejecución`, 0 avances) → *"la obra está
  registrada pero sin valorizaciones ejecutadas — no verificable en InfoObras"*.
- Cert posterior a la última valorización → *"la obra dejó de valorizar en
  AAAA-MM; el certificado es posterior"*.

**Test:** cada patrón produce su `ItemRevision.motivo` correspondiente.

### 3b · Hoja del profesional en revisión (no vacía)
**Problema:** P6 (experiencia en revisión, sin obra) sale en blanco en el Excel
→ confunde. **Cambio:** en `entregables/excel_final.py`, cuando una experiencia
está en revisión, renderizar *"Experiencia en revisión — elegir obra entre N
candidatos"* + la lista de candidatos, en vez del bloque vacío.

**Test:** Excel de un job con experiencia en revisión muestra el texto y no un
bloque "OBRA EN INFOOBRAS" vacío.

---

## Fase 4 — Secundario ⏳

### 4a · Robustez SUNAT
El run dejó `err` en SUNAT (RUC 20607105615, `estructura_desconocida`). Aplicar
el mismo tratamiento que a InfoObras a `scraping/sunat.py`: distinguir flakiness
(reintentar) de formato no soportado (loguear el HTML para diagnosticar y
ampliar el parser). ALT04/ALT12 dependen de esto.

### 4b · Umbral / prorrateo de cobertura ⚠
Con la Fase 1, la cobertura parcial **ya se prorratea** (el clamp resta el tramo
sobrante y computa los años sobre lo cubierto). Entonces el flag de cobertura
deja de ser "all-or-nothing al 50%". Disparador de revisión propuesto —**la
inversión de veredicto, no el % a secas**:

revisión **si** `(el clamp cambia el veredicto a NO CUMPLE)` **ó** `(cobertura
< 20%)` **ó** `(fetch falló / obra sin valorizaciones)`.

Así un profesional a 46% que **sigue CUMPLE** tras prorratear no genera revisión
(objetivo del cliente), pero uno que **cae a NO CUMPLE** sí se confirma a mano
(evita el falso rechazo). Requiere validar el umbral 20% con Manuel.

---

## Orden recomendado y criterio de "listo"

1. **Fase 1** — primero la auditoría manual (confirmar el bug), luego el clamp +
   tests. Es lo que vuelve los veredictos confiables.
2. **Fase 2** — correctitud; ambas son acotadas y de bajo riesgo.
3. **Fase 3** — calidad del entregable para Manuel.
4. **Fase 4** — cuando 1-3 estén estables.

**Listo** = suite verde + re-corrida del concurso real donde: (a) los años
efectivos de cobertura parcial reflejan solo el tramo válido, (b) ningún motivo
de revisión es engañoso, (c) ninguna hoja de profesional sale vacía.
