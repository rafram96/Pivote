# Integración al sistema: Verificación de expedientes (SEACE + MEF)

> Plan de acción para llevar la verificación de expedientes de "paso de la skill"
> (Paso 4.6, ya construido) a **feature integrada de punta a punta**: resultados en
> el espejo → backend → panel → Excel → documentos en el ZIP. Corresponde a la
> **Opción B** de la cotización (T-003). Última actualización: 2026-07-13.

---

## 0 · VALIDACIÓN EN VIVO (13-jul) — corrida sobre 13 CUIs reales

Antes de integrar, el flujo MEF se probó en el navegador contra **13 CUIs reales
de los jobs de producción** (salud, educación, saldos de obra, viejos y nuevos):

| Métrica | Resultado |
|---|---|
| Formato 08-A responde (URL directa `verFichaEjecucion/{CUI}`, **sin captcha**) | **13/13** |
| Ficha completa (sección B + documentos descargables, 34-151 PDFs por ficha) | **11/13** |
| Descarga del PDF de resolución verificada (`%PDF-1.4`, 3.6 y 4.2 MB) | **2/2 probadas**, en CUIs distintos |
| **Cobertura efectiva** | **12/13 (92%)** |

Los 2 casos flacos, explicados:
- **2140959** = CUI viejo reformulado (Tintay Puncu) — su data vive bajo el CUI
  nuevo **2448758, que salió completo (89 PDFs)**. El Paso 4.5 ya maneja este caso
  (detección de CUI desactualizado) → se auto-recupera.
- **2148076** = la entidad nunca llenó el 08-A (ficha sin fechas) → "⚠️ por
  confirmar" legítimo: el dato no existe en el Estado.

**Hallazgos clave de la corrida:**
1. **El captcha quedó eliminado del flujo típico.** La Consulta Pública lo pide
   desde el PRIMER paso (el formulario de búsqueda), pero la ruta
   **SSI → `verFichaEjecucion/{CUI}`** llega a TODO — datos, Formato 08-A en HTML
   y el PDF de la resolución — sin ningún código. La Consulta Pública queda como
   último recurso.
2. **Los enlaces de descarga llevan token de sesión**: un `curl` externo devuelve
   "Acceso denegado"; el click/fetch **desde la sesión del navegador** funciona.
   Confirma la arquitectura: verificación en capa Claude, backend solo consume.
3. **La etiqueta del documento varía por entidad** ("APROBACIÓN DEL EXP. TEC" vs
   "RESOLUCIÓN JEFATURAL N° 07-2020-PRONIS-UED") → identificar por contexto de la
   sección, nunca por etiqueta fija (la skill ya lo instruye así).

Conclusión: **automatización 100% sin captcha (13/13); cobertura ~92% medida**, y
lo no verificable se marca en vez de inventarse. Esto adelanta parte de la F5.

**Sonda adicional (13-jul, por CÓDIGO):** el flujo MEF completo funciona con
`requests` puro, sin navegador: `GET verFichaEjecucion/2324482` devuelve el HTML
server-rendered (345 KB, sección B presente, 32 links de aprobación) y el PDF de
la resolución **descarga con la misma session de requests** (HTTP 200,
`application/force-download`, `%PDF-1.4`). El fallo del curl anterior era solo
falta de cookies de sesión. → **La verificación MEF se implementa EN EL BACKEND**,
mismo patrón que `scraping/infoobras.py`. El precio acordado quedó en **S/ 2,600**.

### ✅ F0 COMPLETADO (13-jul) — endpoints descubiertos + fixtures congelados

**El hallazgo grande: contratista/contrato salen por JSON, NO hay que tocar SEACE.**
El SSI expone un endpoint DWH con los contratos SEACE ya estructurados:

```
POST https://ofi5.mef.gob.pe/invierteWS/Ssi/traeContratoSeaceDWH
     data = { id: <CUI>, codsnip: <SNIP>, vers: "v2" }   (form-urlencoded, XHR)
     → application/json : lista de contratos, cada uno con
       NUM_CONTRATO · NOM_CONTRATISTA · MTO_TOTAL · DES_PROCESO ·
       NOMENCLATURA · VALOR_REFER · FEC_SUSCRIPCION · URL_CONTRATO (PDF directo)
```
Validado (CUI 2324482): 6 contratos, incluido `116-2017-GRH/GR · VELÁSQUEZ VÁSQUEZ
EMILIO FÉLIX · S/612,750 · 19/10/2017` — **coincide exacto con el certificado de
Yuyapichis**. El `URL_CONTRATO` (Oracle object storage) descarga el **PDF del
contrato** con requests (`%PDF-1.4`).

**Fuentes por código, definitivas (cero SEACE JSF):**
| Dato | Fuente (requests) |
|---|---|
| Estado, fechas ejecución, montos, sección B | `GET /invierte/ejecucion/verFichaEjecucion/{CUI}` (HTML) |
| PDF resolución de aprobación | link `downloadArchivoPublico` de esa misma página (session) |
| Contratista, N° contrato, monto, fechas, nomenclatura | `POST /invierteWS/Ssi/traeContratoSeaceDWH` (JSON) |
| PDF del contrato | `URL_CONTRATO` del JSON (Oracle storage, directo) |
| CUI/nombre/situación/UEI | ficha SSI / el mismo 08-A |

**El `codsnip` importa (corrección de F0, medido en F5):** el DWH devuelve MÁS
contratos con el SNIP real que con `codsnip=0` (ej. CUI 2303684/2107892/2088781:
0 contratos con `0` → 3/11/6 con el SNIP). El SNIP se toma del `codSnip` de la obra
de InfoObras (ya resuelta en el pipeline) y se pasa a `verificar_cui`. La descarga
reusa ese SNIP (guardado como `cod_snip` en el bloque).

→ **Se elimina el riesgo R3** (no dependemos del JSF de SEACE ni de prod4). El
único "no se puede" que queda es que la ENTIDAD no haya cargado datos (medido ~8%).

**Fixtures congelados** en `backend/tests/fixtures/mef/` (5 CUIs: completo,
flaco, reformulado, PRONIS, educación) — HTML del 08-A + JSON de contratos +
`INDEX.json`. Versionados (excepción en `.gitignore`; es data pública). Script
reutilizable: `backend/scripts/congelar_fixtures_mef.py`.

---

## 1 · Qué significa "integrado" (el objetivo)

Hoy (Opción A, construida): la skill verifica y deja el resultado como TEXTO en
`observaciones_claude` + archivos en la carpeta local del análisis. El evaluador lo
ve, pero el sistema no lo "entiende".

Integrado (versión POR CÓDIGO, S/ 2,600): la verificación corre **en el backend**,
determinística, en la misma etapa donde hoy se cruza InfoObras — sin navegador, sin
skill de por medio:

```
[Backend on-prem — etapa de verificación]                    [Entregables]
detecta expediente (_es_experiencia_expediente, ya existe) → Excel: bloque
GET verFichaEjecucion/{CUI}  (MEF, requests puro)          → "VERIFICACIÓN MEF" ✅⚠️❌
parsea 08-A (estado, fechas, montos, sección B)            → ZIP: carpeta
descarga PDF(s) de aprobación (misma session)              → "Verificación" con
contraste vs certificado → enr["verificacion_expediente"]     la resolución
        │
        ▼
[Panel]  badge por experiencia: "Expediente verificado ✓ MEF"
```

**Arquitectura (actualizada tras las sondas del 13-jul):**
- **MEF → por código en el backend.** Probado: HTML server-rendered + descarga del
  PDF con session de `requests`. Mismo patrón que `scraping/infoobras.py`
  (session, reintentos, throttle, `errores_red.corto`).
- **SEACE (JSF) → NO se scrapea. Nunca.** Ahí murió E3 y sigue igual. El dato de
  contrato/contratista se busca por vías determinísticas alternativas (F0):
  el SSI del MEF expone la sección "Contrataciones (fuente SEACE)" y el nuevo
  buscador `prod4.seace.gob.pe` es una SPA (probable API JSON detrás). Si F0 no
  encuentra endpoint estable → v1 entrega la verificación MEF completa y el
  contrato queda ⚠️ "verificable manualmente" (con el prompt de cortesía).
- **Bases Integradas de SEACE**: FUERA de v1 (viven en el JSF). Quedan por el
  prompt manual o como fase 2 si Manuel las exige dentro del ZIP.

## 2 · Qué SE PUEDE y qué NO (límites honestos)

### Se puede
- Verificar **contratista, N° de contrato, monto y fechas** contra SEACE (público, sin login).
- Obtener **CUI, estado, situación, unidad ejecutora y contrataciones** por el SSI del MEF **sin captcha**.
- Descargar **Bases Integradas, Contrato y la Resolución de aprobación** (Formato 08-A) y llevarlos al ZIP del análisis.
- Registrar el contraste como **dato estructurado** con veredicto por campo (✅ coincide / ⚠️ no verificable / ❌ discrepancia) y su fuente.
- Degradar con seguridad: sin navegador o sin resultados → la experiencia queda "verificación pendiente", nunca bloquea el análisis.

### NO se puede (y hay que decirlo al cliente tal cual)
| Límite | Por qué | Consecuencia |
|---|---|---|
| **Automatizar el captcha** | Barrera anti-bot; no se debe ni se puede evadir | Irrelevante en v1: la ruta por código (`verFichaEjecucion/{CUI}`) no pasa por captcha. La Consulta Pública (con captcha) simplemente no se usa |
| **Scrapear el JSF de SEACE (prod2)** | Viewstates, anti-bot, sin API — lección E3 | El contrato/contratista se busca por vías determinísticas (SSI/prod4, F0); las **Bases Integradas quedan fuera de v1** (prompt manual o fase 2) |
| **Verificar obras/clientes PRIVADOS** | No existen en SEACE/MEF/InfoObras | Frente aparte (RENIPRESS/objeto social) — cotización separada |
| **Garantizar que el 08-A esté cargado** | Depende de la entidad (medido: ~8% no lo llenó) | Veredicto ⚠️ "no verificable en línea" — el humano decide |
| **Parsers inmunes a cambios del MEF** | HTML puede cambiar (como InfoObras) | Mismo trato que InfoObras: fixtures + reintentos + fallo → ⚠️, nunca crash. Mantenimiento vía bolsa |

## 3 · Cómo se integra al sistema actual (pieza por pieza)

### 3.1 Contrato de datos (espejo) — la pieza que ancla todo
Nuevo bloque **opcional** por experiencia en `ExperienciaProf` (paridad Pydantic ↔ zod,
como `cui_fuente`):

```json
"verificacion_expediente": {
  "contratista":      {"valor": "AYEP CONTRATISTAS GENERALES EIRL", "veredicto": "ok"},
  "contrato":         {"numero": "076-2021-GRA-SEDECENTRAL-OAPF", "monto": 347539.50,
                       "fechas": "2021-06-12 → 2021-09-09", "veredicto": "ok"},
  "resolucion":       {"numero": "RGR 132-GRA/GGR-GRI", "fecha": "2023-04-21", "veredicto": "no_verificable"},
  "cui_confirmado":   "2340401",
  "fuentes":          ["SEACE", "MEF-SSI"],
  "archivos":         ["01_Bases_Integradas.pdf", "02_Contrato.pdf"],
  "verificado_en":    "2026-07-13"
}
```
`veredicto` ∈ `ok | discrepancia | no_verificable`. Campos ausentes = no se intentó.

### 3.2 Scraper nuevo: `backend/scraping/mef.py` (el corazón del módulo)
Mismo patrón que `infoobras.py` (session con UA, reintentos con backoff, throttle,
`errores_red.corto`, NO corre en tests offline):
- `fetch_ficha_ejecucion(cui, session=None) -> FichaMEF | None` — GET
  `https://ofi5.mef.gob.pe/invierte/ejecucion/verFichaEjecucion/{cui}` (HTML
  server-rendered, validado por requests el 13-jul).
- `parsear_ficha_08a(html) -> dict` — función PURA (testeable offline con fixtures):
  estado del registro, fechas de ejecución, montos (ET/supervisión/total),
  sección B presente, y los documentos `downloadArchivoPublico` con su etiqueta
  (identificar aprobación por CONTEXTO de sección, no por etiqueta fija — varía:
  "APROBACIÓN DEL EXP. TEC" vs "RESOLUCIÓN JEFATURAL…").
- `descargar_aprobaciones(session, docs, destino) -> int` — descarga con la MISMA
  session (los links llevan token de sesión: probado que requests lo maneja);
  streaming a `.part` + rename, reutilizando el helper de `zip_infoobras`.
- `verificar_expediente(exp, ficha) -> dict` — el contraste puro (testeable):
  fechas del certificado vs ejecución MEF, resolución (nº/fecha), montos; produce
  el bloque `verificacion_expediente` (3.1) con veredictos.
- **F0 decide** si se suma `contrataciones_por_cui()` (endpoint del SSI o API JSON
  de prod4) para contratista/contrato. Si no hay vía estable → ese campo queda ⚠️.

### 3.3 Orquestador (etapa)
- En `etapas_reales._procesar` (o etapa hermana): si `_es_experiencia_expediente`
  (helper ya existente) y hay CUI resuelto → `fetch_ficha_ejecucion` + contraste →
  `enr["verificacion_expediente"]` → write-through a Postgres gratis (ya existe).
- La DESCARGA de los PDFs se difiere a `descargar_documentos_job` (patrón actual)
  → carpeta `Verificación MEF/` de la experiencia → el ZIP la incluye solo.
- Cache por CUI (mismo esquema del fetch de InfoObras) y 2ª pasada para flakiness.

### 3.4 Schemas / contrato
- El bloque 3.1 entra al **enriquecimiento** (backend-only), NO al espejo → **no
  hay cambio del contrato skill↔backend** en v1 (el Paso 4.6 de la skill queda
  como fallback manual/cortesía). Menos superficie, menos paridad que mantener.

### 3.5 Excel final
- Bloque nuevo **"VERIFICACIÓN MEF (expediente)"** en la hoja del profesional:
  filas resolución / fechas / montos (y contratista si F0 lo habilita) con ✅⚠️❌ +
  fuente. Mismo estilo del bloque "OBRA EN INFOOBRAS". Sin jerga.

### 3.6 Panel (repo Panel-InfoObras)
- `/jobs/{id}/espejo` ya expone el enriquecimiento → añadir el campo y un **badge**:
  `Expediente verificado ✓ MEF` / `Verificación parcial ⚠` / nada si no aplica.
  Detalle expandible con la tabla de contraste en la ficha de experiencia existente.

## 4 · Plan de acción (fases y esfuerzo)

| Fase | Qué (archivos concretos) | Esfuerzo |
|---|---|---|
| **F0** | Descubrimiento: endpoint de Contrataciones del SSI y/o API JSON de prod4 (contrato/contratista); congelar **fixtures HTML reales** de 5 CUIs (ficha completa, flaca, reformulada) para los tests offline | 0.5 d |
| **F1** | `scraping/mef.py`: fetch + parser puro + descarga con session + contraste. Tests offline contra los fixtures | 1 d |
| **F2** | Etapa en `orquestador/etapas_reales.py`: detección → verificación → enriquecimiento; descarga diferida al árbol del ZIP | 1 d |
| **F3** | `entregables/excel_final.py`: bloque de verificación | 0.5 d |
| **F4** | Panel: badge + tabla de contraste | 0.5 d |
| **F5** | Regresión con los 13 CUIs (script `scripts/verificar_mef.py`, reusable en el server) + e2e + deploy | 0.5 d |
| | **Total** | **4 d** |

**F0–F5 IMPLEMENTADAS (rama `feat/verificacion-mef`)** — falta solo merge + deploy.
Regresión F5 (13 CUIs reales, con SNIP vía InfoObras): **11/13 (84%) verificados en
MEF · 8/13 con contrato de expediente · 7/13 con resolución**. Los no-verificados son
entidades que no cargaron el 08-A (medido, ~cae en ⚠️ "por confirmar", no es fallo).
Suite: 216 tests offline. Script reusable en el server: `python scripts/verificar_mef.py`.

**Precio cerrado (ACORDADO 13-jul): S/ 2,600** — en la línea del cruce
InfoObras+SUNAT del contrato original (S/2,400). 50% adelanto / 50% entrega.
Fase 2 opcional (cotización aparte si la pide): Bases Integradas de SEACE al ZIP.

## 5 · Riesgos y mitigaciones

| # | Riesgo | Prob. | Impacto | Mitigación |
|---|---|---|---|---|
| R1 | **El MEF cambia el HTML del 08-A** | Media | El parser deja de extraer | Mismo trato que InfoObras: parser puro + fixtures congelados (los tests avisan), reintentos, y fallo → ⚠️ "verificación pendiente", nunca crash. Mantenimiento vía bolsa mensual |
| R2 | **Captcha del MEF** | **Eliminado en v1** | — | La ruta por código (`verFichaEjecucion/{CUI}`) no pasa por captcha (probado 13/13 + sonda requests). La Consulta Pública no se usa |
| R3 | **F0 no encuentra vía estable para contratista/contrato (SEACE)** | Media | Ese campo queda ⚠️ en v1 | El módulo vale igual (resolución/fechas/montos verificados); el contrato se cubre con el prompt manual mientras tanto; se re-evalúa como fase 2 |
| R4 | **El MEF bloquea/limita la IP del server** | Baja | Verificaciones fallan temporalmente | Throttle + backoff (patrón InfoObras), volumen bajo (solo expedientes), cache por CUI |
| R5 | **Tiempo por análisis crece** (N expedientes × navegación) | Media | Análisis más lentos | Solo corre para experiencias de expediente (no todas); paralelizable a futuro; expectativa clara al cliente |
| R6 | **Procesos antiguos no aparecen en SEACE** | Media | ⚠️ frecuentes en certificados viejos | Es información, no fallo: "no verificable en línea" es un veredicto útil para el evaluador |
| R7 | **Scope creep** ("ya que verificas, agrega X") | Alta | Erosión del precio | El bloque 3.1 define el alcance EXACTO; lo demás = nueva cotización |

## 6 · Criterio de "terminado" (lo que valida el cobro)
1. Un análisis con expedientes muestra en el **panel** el badge de verificación y en
   el **Excel** el bloque con ✅⚠️❌ — sin intervención manual (salvo captcha si se
   quiere el PDF).
2. El **ZIP** trae bases/contrato/resolución de cada expediente verificado.
3. Un caso con discrepancia real se muestra como ❌ con el detalle (no se oculta).
4. Un caso no encontrado degrada a ⚠️ y el análisis termina normal.
