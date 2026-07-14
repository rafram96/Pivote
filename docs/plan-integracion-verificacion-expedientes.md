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

---

## 1 · Qué significa "integrado" (el objetivo)

Hoy (Opción A, construida): la skill verifica y deja el resultado como TEXTO en
`observaciones_claude` + archivos en la carpeta local del análisis. El evaluador lo
ve, pero el sistema no lo "entiende".

Integrado (Opción B): el resultado es **dato estructurado** que viaja por todo el
pipeline:

```
[Skill — Paso 4.6]                       [Backend on-prem]              [Entregables]
verifica en SEACE/MEF (navegador)   →    valida e ingesta el bloque  →  Excel: bloque
descarga bases/contrato/resolución  →    lo persiste en el           →  "VERIFICACIÓN
escribe verificacion_expediente     →    enriquecimiento (+Postgres) →  SEACE/MEF" ✅⚠️❌
en el espejo + adjunta archivos     →    copia archivos a descargas  →  ZIP: carpeta
                                                                        "Verificación"
                                         [Panel]
                                         badge por experiencia:
                                         "Contrato verificado ✓ SEACE"
```

**Principio arquitectónico (no negociable):** el scraping de SEACE/MEF vive en la
**capa Claude** (navegador, máquina del usuario). El backend **consume** el
resultado, jamás scrapea SEACE — esa web mató al cotizador E3 (JSF, anti-bot, sin
API estable) y el riesgo no cambió. El backend se mantiene determinístico y on-prem.

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
| **Automatizar el captcha** | Barrera anti-bot; no se debe ni se puede evadir | Si hace falta el PDF del Formato 08-A, habrá **una pausa humana** por caso. El flujo minimiza esto usando el SSI para los datos |
| **Scrapear SEACE desde el backend** | JSF con viewstates, anti-bot, sin API — lección E3 | La verificación requiere una corrida de skill (Claude + navegador); no hay "botón re-verificar" server-side |
| **Verificar obras/clientes PRIVADOS** | No existen en SEACE/MEF/InfoObras | Frente aparte (RENIPRESS/objeto social) — fuera de este módulo |
| **Garantizar encontrar TODO proceso** | La búsqueda de SEACE es por texto y los procesos muy antiguos o mal registrados pueden no aparecer | Veredicto ⚠️ "no verificable en línea" — el humano decide |
| **Corridas 100% desatendidas siempre** | El captcha del punto 1 | El análisis completo sí corre solo; solo el PDF de la resolución puede pedir una intervención |

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

### 3.2 Skill (Paso 4.6 — ya construido, se ajusta la salida)
- Además de `observaciones_claude`, escribe el bloque 3.1 en el espejo.
- Los archivos descargados van DENTRO del ZIP de certificados que ya viaja al
  backend (`verificacion/P{n}_E{m}/…`) — reutiliza el transporte existente
  (multipart / subida por disco para lotes grandes).

### 3.3 Backend (ingesta + persistencia)
- `schemas/espejo.py` + `skill/schemas/espejo.js`: bloque nuevo con validación de
  paridad (`tools/test_contrato.py` + espejo sintético).
- La etapa de ingesta copia `verificacion_expediente` al **enriquecimiento**
  (`enr["verificacion_expediente"]`) → write-through a Postgres gratis (ya existe).
- `_guardar_certificados` ya descomprime el ZIP; los archivos de `verificacion/` se
  copian a la carpeta de descargas de la experiencia para que el **ZIP InfoObras**
  los incluya bajo `P{n}/E{m}/Verificación SEACE-MEF/`.
- El backend NO re-verifica ni re-scrapea: confía en la skill (mismo principio que
  el Paso 4 de evaluación).

### 3.4 Excel final
- En la hoja del profesional, bloque nuevo **"VERIFICACIÓN SEACE / MEF"** para las
  experiencias de expediente: 3 filas (contratista / contrato / resolución) con
  ✅⚠️❌, el detalle y la fuente. Mismo estilo del bloque "OBRA EN INFOOBRAS".
- Terminología de evaluador, sin jerga (regla de siempre).

### 3.5 Panel (repo Panel-InfoObras)
- La vista de extracción (`/jobs/{id}/espejo`) ya expone el enriquecimiento →
  agregar el campo y un **badge por experiencia**: `Contrato verificado ✓ (SEACE)`
  / `Verificación parcial ⚠` / sin badge si no aplica.
- Detalle expandible con la tablita de contraste. Sin pantalla nueva — se monta en
  la ficha de experiencia existente.

## 4 · Plan de acción (fases y esfuerzo)

| Fase | Qué | Esfuerzo |
|---|---|---|
| **F1** | Contrato de datos: bloque en ambos schemas + test de paridad + ajuste del Paso 4.6 para emitirlo | 0.5 d |
| **F2** | Backend: ingesta → enriquecimiento → Postgres; copia de archivos al árbol de descargas/ZIP | 1 d |
| **F3** | Excel: bloque "VERIFICACIÓN SEACE/MEF" | 0.5 d |
| **F4** | Panel: badge + tabla de contraste en la ficha de experiencia | 1 d |
| **F5** | Pruebas: offline (schemas/ingesta/Excel con fixtures) + **e2e con 2 casos reales** (uno ✅ limpio, uno ⚠️ con captcha/no-verificable) + deploy al server | 1 d |
| | **Total** | **4 d** (+ colchón ya incluido en el precio) |

Precio cerrado (cotización T-003, Opción B): **S/ 4,600** — incluye la Opción A ya
construida. 50% adelanto / 50% entrega.

## 5 · Riesgos y mitigaciones

| # | Riesgo | Prob. | Impacto | Mitigación |
|---|---|---|---|---|
| R1 | **SEACE cambia su HTML/flujo** (histórico: mató a E3) | Media | La verificación deja de encontrar procesos | El scraping es vía Claude+navegador (se adapta al layout solo, no hay selectores frágiles); si aún así falla → ⚠️ pendiente, el análisis sigue. Mantenimiento vía bolsa mensual |
| R2 | **Captcha del MEF** | ~~Alta~~ **Baja** (tras la validación del 13-jul) | Pausa humana solo en el último recurso | La ruta SSI → `verFichaEjecucion/{CUI}` llega a datos + 08-A + PDF de resolución **sin captcha** (probado 13/13); la Consulta Pública (con captcha) queda solo como fallback excepcional |
| R3 | **La máquina de Manuel sin navegador/Chrome MCP** | Media | El 4.6 se omite | Instalarlo/verificarlo es parte del setup A6; el paso degrada con aviso, no rompe |
| R4 | **Citas incorrectas (alucinación)** | Baja | Grave (informe con dato falso) | Regla de evidencia: solo datos VISTOS en pantalla + archivos descargados como prueba; sin confirmación → ⚠️, nunca inventar |
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
