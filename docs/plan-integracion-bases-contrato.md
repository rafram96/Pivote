# Diseño — Descarga de Bases Integradas + Contrato firmado (T-004)

> **Estado: v2 — ajustado con la transcripción de la reunión del 29-jul.**
> Lo técnico está verificado por las sondas (18-21 jul, `tools/fuentes_estado/`);
> las prioridades y requisitos de esta versión salen de lo que el cliente dijo
> en la reunión (§0 y §11). Alias comercial: T-004 del plan v4 · ticket T-010.

## 0 · Lo que la reunión del 29-jul fijó (gobierna este diseño)

1. **Es LA prioridad, y es urgente.** El cliente lo está haciendo **a mano hoy**,
   certificado por certificado, con un prompt propio: busca el contrato del
   proceso, lo abre, verifica que el cargo del especialista exista, y guarda
   todo en directorios por proyecto. Cada día sin el módulo es trabajo manual
   suyo — y erosión de la relación («te lo he dicho hace semanas»).
2. **El requisito N°1 es la segmentación por tipo de proceso.** Literal:
   > «Si un hospital X: la preinversión se llamará preinversión del hospital X;
   > el expediente técnico, expediente técnico X; la supervisión, supervisión
   > del hospital X; la ejecución, construcción del hospital X. **Si estamos en
   > expediente, buscamos solo expediente. Si estamos en supervisión de obra,
   > de supervisión o de ejecución.**»
   Una obra puede tener **hasta 4 juegos de bases** — y confirmó que **el CUI es
   el mismo para los 4 procesos**: el CUI jamás discrimina; discrimina el objeto.
   Y solo valen las Bases **INTEGRADAS** («la administrativa es la previa»).
3. **El entregable que él consume es el ZIP.** Dijo que no revisará más Excels
   hasta que los resultados sean precisos; el Excel él ya lo trabaja a mano.
   → los **documentos al ZIP van primero**; el candado de confirmación puede
   entrar en una segunda entrega.
4. **RENIPRESS quedó despriorizado por él mismo** en esta reunión («ya
   olvidémonos» — para no atrasar esto). T-006 baja en la cola.
5. **Capturas de pantalla: descartadas y aceptadas** («si no se puede, no se
   puede» — priorizó precisión). La comparación de nombres InfoObras ↔
   certificado ya está cubierta (#46).
6. **Requisito transversal nuevo**: marcar con un **color** todo dato SUPUESTO
   en el Excel (va como issue aparte, no es de este módulo).
7. Rendimiento validado en la conversación: chequeo contra la base MEF
   0.1–0.2 s; análisis de 62 obras ≈ media hora; búsquedas específicas 20–40 s.

## 1 · Qué es y qué destraba

Por cada experiencia pública con CUI resuelto, el backend trae del Estado —
**sin captcha, sin navegador, por código** — los dos documentos que hoy el
evaluador busca a mano, y las fechas estructuradas del proceso:

| Pieza | Fuente | Qué habilita |
|---|---|---|
| **Bases Integradas** (PDF) | API OCDS · `tender.documents[biddingDocuments]` | Sustento: qué exigía ese proceso |
| **Contrato firmado** (PDF) | OCDS `contracts[].documents[contractSigned]` o CONOSCE `urlcontrato` | Sustento: quién firmó y cuándo |
| **Fechas estructuradas** | CONOSCE `fecha_suscripcion_contrato`, vigencias · OCDS `dateSigned` | **T-005 entero** (cruces de fechas sin OCR) |
| **Candado del CUI** | cascada RUC → nombre consorcio → miembros | Evidencia extra de que el CUI resuelto es el correcto |

Es la última fila del flujograma del cliente que quedaba sin fuente: «bajar
contrato y bases» aparece en los 2 caminos públicos (A y B) del Excel
«para RAFAEL». T-005 (cruces de fechas) **no puede empezar sin esto**.

## 2 · Decisiones previas que gobiernan el diseño (no reabrir)

- **ADR-010**: el tipo de concurso (`expedientes`/`obras`) es un parámetro del
  espejo. Este módulo lo consume para elegir QUÉ proceso del CUI descargar.
- **ADR-003**: la identidad selecciona; las fechas declaradas no eligen obra.
  Aquí el CUI ya llega fijado por el resolver — este módulo no lo cambia,
  solo lo **confirma o guarda silencio** (candado asimétrico, §6).
- **ADR-005 / regla de abstención**: proceso no encontrado (pre-2018) ≠ CUI
  malo. Nunca se penaliza por ausencia en la fuente.
- **Convenciones**: degradación segura (nada de esto puede tumbar un job),
  cambios de contrato solo aditivos, escritura atómica, tests offline.

## 3 · Arquitectura

```
backend/scraping/seace_abierto.py        ← módulo nuevo (hermano de infoobras.py / mef.py)
   ├─ capa CONOSCE  (Excel anuales, cache local, consulta offline)
   └─ capa OCDS     (API por proceso, en vivo, best-effort)

backend/datos_pivote/referencia/conosce/ ← cache local (mismo patrón que referencia/mef/)
   ├─ contratos_2018.xlsx … contratos_2026.xlsx
   ├─ convocatorias_*.xlsx · adjudicaciones_*.xlsx · consorcios_*.xlsx
   └─ metadata.json         (fecha de descarga por archivo, filas, fuente)
```

**Dónde corre**: dentro de `EtapaInfoObrasReal`, después de resolver la ficha
de la obra (ahí ya están CUI + camino A/B + periodo del certificado). No es una
etapa nueva del pipeline: es un enriquecedor más, como SUNAT — así hereda
checkpoint, reintentos y progreso sin tocar el motor.

### El principio rector: cache-first

**El 27-jul, mientras se diseñaba esto, `conosce.osce.gob.pe` estuvo caído
~1 hora** (TCP timeout en 443 y 80; `bi.seace.gob.pe` respondía normal). No es
anécdota: es el argumento de diseño. Los Excel anuales se descargan **una vez**
y se consultan offline para siempre; solo el año corriente se refresca
(mensual — el portal publica con ~3 semanas de rezago). La única llamada en
vivo por análisis es OCDS, y es best-effort.

```
consulta por experiencia:   cache local CONOSCE (offline, siempre disponible)
                          + 1 GET a OCDS records?projectID={CUI} (vivo, best-effort)
si OCDS no responde:        estado "Fuente no disponible — reintentar" (no tumba nada)
si el host CONOSCE no deja
descargar un año faltante:  se sigue con los años que hay + observación
```

## 4 · Flujo por experiencia

```
experiencia con CUI resuelto (del resolver, ya validado)
   │
   ▼
1. OCDS: GET records?projectID={CUI}
   → lista de procesos del CUI (ejecución, supervisión, expediente, saldo…)
   │
   ▼
2. SELECCIONAR el proceso correcto             ← §5
   │
   ▼
3. CANDADO: ¿el emisor del certificado         ← §6
   aparece en ese proceso? (cascada 3 niveles)
   │
   ▼
4. FECHAS: fecha_suscripcion / vigencias        → enriquecimiento (insumo T-005)
   (CONOSCE por codigoconvocatoria — offline)
   │
   ▼
5. DOCUMENTOS: bases integradas + contrato      → carpeta de la experiencia, al ZIP
   (best-effort, con estados honestos)
```

## 5 · Selección del proceso (un CUI tiene varios)

Un CUI típico tiene proceso de **expediente técnico**, de **ejecución**, de
**supervisión**, y a veces saldos de obra. Elegir mal = descargar el contrato
equivocado y cruzar fechas contra el proceso equivocado.

**Este es el requisito N°1 del cliente (§0.2), no un detalle técnico.** Su
taxonomía, mapeada a la selección:

| Proceso del CUI | ¿Cuándo se elige? |
|---|---|
| Preinversión / estudios previos | nunca (fuera del flujograma) |
| **Expediente técnico** (consultoría) | camino A |
| **Supervisión** (consultoría de obra) | camino B, experiencia de supervisión |
| **Ejecución** (obra) | camino B, experiencia de ejecución |
| Saldo de obra | como su proceso padre, desempatado por vigencia |

Selección en orden:

1. **Por objeto del proceso** según el camino del análisis (ADR-010) y el tipo
   de la experiencia — la nomenclatura y la descripción del proceso lo dicen
   («Contratación del servicio de supervisión…», confirmado en vivo con
   Pichanaki durante la propia reunión).
2. **Por solape de vigencia** con el periodo del certificado, solo como
   desempate entre procesos del MISMO objeto (p. ej. obra + saldo de obra).

> ⚠ **Trampa de circularidad, documentada a propósito**: el paso 2 usa el
> periodo DECLARADO — el dato bajo auditoría. Es tolerable aquí porque el CUI
> ya está fijado por identidad (no se está eligiendo obra, ADR-003) y el
> objeto filtró primero; pero por eso mismo el solape **jamás sube de
> desempate a criterio principal**, y toda selección por solape queda
> registrada en la observación («proceso elegido por vigencia entre N»).

Sin proceso del objeto esperado → estado «El proceso de {tipo} no está en
datos abiertos» + se conserva lo que sí haya (p. ej. solo el de ejecución,
marcado como tal). Nunca se descarga «el que haya» sin etiquetarlo.

## 6 · Candado de confirmación del CUI — asimétrico, ya medido

Cascada sobre los `parties` del proceso elegido (medición real:
`test_confirmacion_cascada.py`, 158 CUIs con proceso):

| Nivel | Llave | Confirma | Medido |
|---|---|---|---|
| 1 | RUC del emisor (11 díg) entre parties | empresas que postularon solas | 27/158 (17%) |
| 2 | Nombre del consorcio normalizado vs `name` | consorcios (nombres completos en OCDS) | +56/158 (35%) |
| 3 | CONOSCE `consorcios/AAAA`: RUC del emisor entre los MIEMBROS | consorcios con código interno | 0 en este universo (los problemáticos son pre-2018) |

**53% de confirmación dura automática.** La asimetría es la regla: confirmar
es evidencia (y detecta CUIs mal resueltos silenciosos — valor directo para
la golden); NO confirmar no penaliza jamás (casi siempre = proceso pre-2018,
fuera de la fuente). El resultado viaja como observación INFO/OK, no cambia
veredictos.

**Fase 2 (opcional, se cotiza aparte si la transcripción lo pide): ruta
inversa por RUC** — cuando el resolver no encontró la obra por nombre, filtrar
CONOSCE por `ruc_contratista` del emisor y proponer los `projectID` de sus
procesos como CUIs candidatos. Convierte esta fuente en un segundo camino de
resolución, independiente del nombre.

## 7 · Entregables al usuario

**Al ZIP** (mismo árbol Proyecto → Profesional → Experiencia de
`zip_infoobras.py`; los documentos SEACE entran a la carpeta de la
experiencia con prefijo propio):

```
<Experiencia>/
  SEACE_01_BASES_INTEGRADAS.pdf
  SEACE_02_CONTRATO_FIRMADO.pdf
  (o) SEACE_NO_DISPONIBLE.txt   ← motivo: pre-2018 / proceso no hallado /
                                   fuente caída — mismo patrón SIN_DOCUMENTOS.txt
```

**Al Excel** (hoja del profesional, bloque de la obra — aditivo):
- «Contrato del proceso: firmado el {fecha_suscripcion} · vigencia {ini}–{fin}»
- «Bases y contrato: ✔ descargados al ZIP» / «No disponibles en datos abiertos
  (proceso anterior a 2018)» — terminología sin jerga, «Por confirmar» donde
  aplique.
- El candado, si confirmó: «Emisor verificado como participante del proceso
  (SEACE)» — con borde azul de verificado-por-backend.

**Al enriquecimiento** (`ctx.enriquecimiento["n:m"]`, campos nuevos — el
espejo de la skill NO cambia, cero acoplamiento skill↔backend en esta tarea):

```python
"seace": {
    "codigoconvocatoria": …, "ocid": "ocds-dgv273-seacev3-…",
    "proceso_objeto": "supervisión", "seleccion": "objeto" | "objeto+vigencia",
    "fecha_suscripcion": "YYYY-MM-DD", "vigencia": ["YYYY-MM-DD","YYYY-MM-DD"],
    "candado": {"nivel": 1|2|3|None, "confirmado": bool},
    "docs": {"bases": "ok|no_disponible|error", "contrato": "ok|no_disponible|error"},
}
```

## 8 · Resiliencia y límites declarados

| Límite | Mitigación |
|---|---|
| `conosce.osce.gob.pe` intermitente (caído en vivo el 27-jul) | cache-first: los Excel se bajan una vez; descarga de años con reintentos + espaciado, tolerante a fallo parcial |
| OCDS/CONOSCE geobloquean fuera de Perú | irrelevante en producción (server del cliente en Perú); anotado para desarrollo remoto |
| Cobertura 2018+ (seacev3 con projectID) | pre-2018 → estado honesto, sin penalizar; seacev2 (~2008+) existe pero sin projectID — **fuera de alcance** (matching por nombre, riesgo de falso match) |
| Rezago mensual (~3 semanas) | procesos recientes → «aún no publicado en datos abiertos»; el buscador SEACE con reCAPTCHA queda como fallback futuro cotizable, NO en este alcance |
| PDFs de Alfresco a veces pesados | streaming + reintento (mismo patrón que `zip_infoobras.py`) |

## 9 · Evidencia que respalda el alcance (medida el 18-21 jul, corpus real)

- 194 CUIs únicos (641 experiencias) de 29 concursos de `datos_pivote`:
  **81% con proceso en OCDS**, **86% de experiencias cubiertas**,
  **80% con Bases Integradas descargables** (PDF directo verificado: bases
  7.4 MB, contrato 2.2 MB, sin captcha).
- Candado: 53% de confirmación dura (17+35+0).
- `fecha_suscripcion_contrato` presente como campo estructurado → T-005 sin OCR.

## 10 · Plan de implementación (reordenado por la reunión: documentos primero)

El cliente consume el ZIP (§0.3) → lo que él ve va adelante; el candado —que es
valioso para NOSOTROS (detecta CUIs mal resueltos)— pasa a la segunda entrega.

| Fase | Qué | Días | Entrega |
|---|---|---|---|
| F1 | `seace_abierto.py`: cache CONOSCE + cliente OCDS + **selección de proceso (§5, el requisito N°1)** | 1.5 | 1ª |
| F2 | **Bases Integradas + Contrato al ZIP** + estados honestos + bloque en el Excel | 1 | 1ª |
| F3 | Fechas estructuradas al enriquecimiento (insumo T-005) | 0.5 | 1ª |
| F4 | Prueba e2e con un concurso real de `datos_pivote` — con verificación explícita de que **ningún proceso se cruza de tipo** | 0.5–1 | 1ª |
| F5 | Candado cascada (§6) como observación | 1 | 2ª |

**Candidato a fase posterior (dimensionar aparte)**: lo que el cliente hace a
mano hoy incluye un paso más — abrir el contrato y **verificar que el cargo del
especialista figure** en el personal del proceso. Es análisis de contenido del
PDF (no descarga); se anota para no perderlo, no entra en este alcance.

**Pruebas**: offline con fixtures mini (un record OCDS real recortado + Excel
CONOSCE de 20 filas), como `tests/fixtures/mef/`. La golden del resolver **no
cambia** (este módulo no selecciona CUIs). La corrida real de F4 es la
validación de verdad.

**Regla comercial**: no se arranca sin OK + adelanto. Los montos y la forma de
presentación viven en `docs/comercial/` (fuera del repo), no aquí.

## 11 · Las preguntas del borrador, cerradas por la transcripción (29-jul)

| Pregunta | Respuesta de la reunión |
|---|---|
| ¿Aprobó T-004? ¿Adelanto? | **No se habló de precio ni adelanto.** El cliente lo trata como pendiente del flujograma que dio («¿ya lo tienes hecho o es una historia?»). El estado comercial se maneja en `docs/comercial/` — este diseño no lo resuelve. |
| ¿PDFs o cruces de fechas? | **PDFs al ZIP, sin duda** — «no voy a revisar ni un Excel; lo que voy a revisar es el zip». Cruces (T-005) después. |
| ¿Bases, contrato o ambos? | **Ambos**, y solo Bases **INTEGRADAS**. Con la segmentación por tipo como condición dura (§0.2). |
| ¿Algo nuevo? | Sí: **marcar con color los datos supuestos** del Excel (issue aparte) · capturas de pantalla pedidas y **descartadas** · verificación del cargo dentro del contrato (anotada como fase posterior, §10). |
| ¿Urgencia? | **Máxima** — lo está haciendo a mano y lo dijo sin rodeos. RENIPRESS despriorizado por él mismo para no atrasar esto. |

---
*Fuentes: sondas `tools/fuentes_estado/conosce.py` y `ocds.py` (verificadas en
vivo 18-21 jul) · `docs/nuevos_modulos/resolucion-cui-datos-abiertos.html`
(evidencia y cascada) · `backend/scraping/mef.py` (patrón de módulo hermano) ·
`backend/entregables/zip_infoobras.py` (patrón de ZIP y estados honestos).*

---

# ANEXO · Estado de implementación y guía de cableado

> Escrito el 29-jul para poder **continuar a mano** sin esta conversación.
> Uso manual del módulo (producir PDFs HOY sin cablear nada):
> **`docs/uso-manual-seace-abierto.md`**.

## A1 · Hecho — F1 (rama `feat/seace-abierto`, commit `70c78e8`)

| Pieza | Dónde | Estado |
|---|---|---|
| Módulo (CONOSCE cache + OCDS + selección) | `backend/scraping/seace_abierto.py` | ✔ 18 tests offline, suite 664 verde |
| Prueba en vivo | CUI 2279396 (Pichanaki): 5 procesos, clasificación correcta, bases+contrato descargables | ✔ 29-jul |
| Hallazgo 1 | Dos procesos del mismo tipo sin vigencias (2017/2022) → desempate determinista por recencia + flag `ambiguo` | ✔ endurecido con test |
| Hallazgo 2 | El sufijo del ocid **no siempre es numérico** (`2022-41-52`) → el cruce con CONOSCE puede no aplicar; las fechas salen igual de OCDS (`dateSigned`) | anotado |

API del módulo (lo que consume el cableado):

```python
CacheConosce(dir?).actualizar(datasets, anios?, session?)   # RED, una vez
CacheConosce(dir?).contrato(codigoconvocatoria) -> [dict]   # OFFLINE
procesos_por_cui(cui, session?) -> list | [] | None         # [] = dato, None = portal caído
tipo_esperado(es_expediente: bool, texto_experiencia) -> "expediente|supervision|ejecucion"
seleccionar_proceso(procesos, tipo, periodo?) ->
    {"elegido", "seleccion", "ambiguo"?, "motivo", "candidatos"}
doc_bases_integradas(comp) / doc_contrato_firmado(comp) -> dict | None
descargar_pdf(url, destino, session?) -> bool               # streaming, %PDF, atómico
codigo_convocatoria(comp) -> str | None
```

## A2 · Pendiente — F2: cablear al pipeline (guía paso a paso)

**Regla de arquitectura a respetar**: en `EtapaInfoObrasReal` las descargas de
documentos están **DIFERIDAS** — la etapa solo persiste ids/urls y los PDFs los
baja `descargar_documentos_job` después del pipeline (comentario en
`etapas_reales.py:~597`; así el Excel sale en ~1 min sin esperar GB). Los PDFs
SEACE deben seguir el mismo patrón.

1. **Selección (barato, dentro de `EtapaInfoObrasReal`)** — para cada
   experiencia pública con CUI resuelto:
   - insumos ya disponibles en la etapa: `_es_exped` (clasificador + modo
     forzado, `etapas_reales.py:~492`), periodo del certificado, y la clave de
     enriquecimiento `_clave(np_, ne)`;
   - llamar `procesos_por_cui` → `tipo_esperado` → `seleccionar_proceso`;
   - persistir en `ctx.enriquecimiento["n:m"]["seace"]` el dict del §7 del
     diseño (ocid, tipo, seleccion, ambiguo, motivo, urls de los 2 docs,
     `dateSigned`, codigoconvocatoria);
   - `None` (portal caído) → `{"estado": "fuente_no_disponible"}` + Observación
     ADVERTENCIA — jamás tumbar el job;
   - **inyectabilidad**: agregar un parámetro `consulta_ocds=None` a la
     factory `etapas_reales(...)` (`etapas_reales.py:1355`), mismo patrón que
     `consulta_cui`/`fetcher_infoobras`, para que los tests no toquen red.
2. **Descarga (diferida, en `descargar_documentos_job`,
   `etapas_reales.py:746`)** — junto a los documentos InfoObras: por cada
   experiencia con `enr["seace"]`, `descargar_pdf` de los 2 documentos a la
   carpeta de descargas de esa experiencia con los nombres
   `SEACE_01_BASES_INTEGRADAS.pdf` / `SEACE_02_CONTRATO_FIRMADO.pdf`; si un doc
   no está → escribir `SEACE_*_NO_DISPONIBLE.txt` con el motivo (patrón
   `SIN_DOCUMENTOS.txt` de `zip_infoobras.py`).
3. **ZIP** — `construir_zip_infoobras(espejo, descargas, salida, enriquecimiento)`
   (`zip_infoobras.py:735`) arma Proyecto → Profesional → Experiencia desde el
   dict `descargas {(n_prof, n_exp): Path}`: si los PDFs SEACE quedan en la
   misma carpeta por experiencia del paso 2, entran solos. **Verificar al
   implementar** que el recolector de archivos de la carpeta no filtre por
   prefijo.
4. **Excel** — bloque junto a «OBRA EN INFOOBRAS» (`excel_final.py`): estado de
   los 2 documentos («✔ descargados al ZIP» / «No disponible en datos abiertos
   (proceso anterior a 2018)») + fecha de firma; `ambiguo=True` → texto «Por
   confirmar» amarillo. Terminología sin jerga (nada de OCDS/API).
5. **Tests** — extender `test_etapas_reales.py` con un `consulta_ocds` fake
   (patrón `_SessionFake` de `test_seace_abierto.py`): caso feliz, portal
   caído, CUI sin procesos, sin proceso del tipo, y `ambiguo`.

## A3 · Pendiente — F3 (fechas a T-005) y F5 (candado)

- **F3**: las fechas ya viajan en `enr["seace"]` desde F2; lo que falta es que
  el motor de reglas las consuma (2 reglas nuevas: inicio ≥ firma · término ≤
  aprobación del ET) — eso ES T-005, alcance aparte.
- **F5 (candado cascada)**: portar `test_confirmacion_cascada.py` de la sonda;
  niveles RUC → nombre consorcio → miembros (dataset `consorcios` de CONOSCE,
  agregarlo a `actualizar(datasets=…)`). Solo observación INFO/OK — jamás
  cambia veredictos (asimetría del §6).

## A4 · Preparación del server (cuando esto se despliegue)

- Correr una vez `CacheConosce().actualizar()` en el server (o copiar la
  carpeta `referencia/conosce/` ya descargada — ~9 Excel, decenas de MB).
- Cron mensual opcional para refrescar el año corriente (mismo patrón que la
  base MEF semanal).
- El server del cliente tiene IP Perú → sin problema de geobloqueo.
