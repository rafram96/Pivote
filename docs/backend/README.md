# Backend on-prem — mapa de componentes

> **Qué es esto**: el índice ordenado de TODO lo que corre en el servidor del
> cliente después de que Claude emite el JSON espejo. El backend toma ese JSON,
> **verifica** lo que Claude afirma, **resuelve** cada obra, la **cruza** contra
> las fuentes oficiales (SUNAT/InfoObras) y **regenera** el Excel final.
>
> 🖼 **Diagramas**: [`arquitectura_backend.html`](arquitectura_backend.html) (los 8 componentes)
> · [`orquestador.html`](orquestador.html) (el plano de control) — ábrelos en el navegador.
> 📐 **Diseño del orquestador**: [`orquestador.md`](orquestador.md)
> · Contrato de datos: [`../contrato/contrato_refactor.md`](../contrato/contrato_refactor.md) §3
> · Visión de las 4 piezas: [`../arquitectura.md`](../arquitectura.md)

> **Dos planos.** Los 8 componentes de abajo son el **plano de datos** (qué se hace);
> el **orquestador** ([orquestador.md](orquestador.md)) es el **plano de control**: los
> secuencia con checkpoint por etapa, reintentos, fan-out por experiencia y
> human-in-the-loop. Empieza por ahí si quieres el “cómo se coordina todo”.

Leyenda de estado: ✅ probado · 📐 diseñado/decidido · 🔨 por construir · ⏳ pendiente detalle.

## El flujo (8 componentes en orden)

```
0 Ingesta/API  →  1 Validador  →  2 Resolución de CUI  ─┬─► 3a InfoObras (vía CUI)
                                                        └─► 3b SUNAT (vía RUC)
                                                              │
                          6 Persistencia ◄─ 5 Excel final ◄─ 4 Motor de reglas
```

| # | Componente | Qué hace | Llena en `_backend` / produce | Estado | Doc |
|---|---|---|---|---|---|
| 0 | **Ingesta / API HTTP** | Recibe Excel + JSON espejo (LAN), valida schema (Pydantic), crea job. Mismo endpoint para dropzone y MCP. | `job_id` | 📐 | [contrato_refactor §4](../contrato/contrato_refactor.md) |
| 1 | **Validador determinístico** | Verifica lo que Claude **afirma** (15 notas): experiencias omitidas, ISOs, solapes, fechas, conteo de periodos, postor vs consorcio. No re-evalúa. | observaciones | 🔨 pieza central | [contrato_refactor §6-7](../contrato/contrato_refactor.md) |
| 2 | **Resolución de CUI** *(el “selector”)* | Cada experiencia → CUI de obra. Paso 0 (CUI citado) → dedup → nombre+RUC+ubicación. Lo dudoso va a REVISIÓN con candidatos. | CUI por experiencia | ✅ prototipo | **[resolucion_cui.md](resolucion_cui.md)** |
| 3a | **InfoObras** (vía CUI) | `fetch_by_cui` → ficha de la obra + paralizaciones. Subcomponente: descarga de archivos → ZIP por experiencia. | `codigo_ciu`, `codigo_infoobras`, `paralizaciones` | ✅ scraping · ⏳ ZIP | [descarga_infoobras_experiencias.md](descarga_infoobras_experiencias.md) |
| 3b | **SUNAT** (vía RUC emisor) | `consultar_ruc` (ALT04) + `getRepLeg` (ALT12) + tabla equivalencias de cargos + vinculación postor↔emisor. | `fecha_creacion_emisor`, `alerta_antiguedad_emisor`, `firmante_facultado_sunat`, `vinculacion_postor_emisor` | ✅ probado | [sunat_endpoints.html](sunat_endpoints.html) · [contrato_refactor §5](../contrato/contrato_refactor.md) |
| 4 | **Motor de reglas / recálculos** | Paso 5: días efectivos = brutos − paralizaciones − traslapes (ALT11). ALT03: recálculo cutoff **25 años** (Claude usó 20). | `alerta_experiencia_antigua`, días efectivos | 🔨 | [resolucion_cui.md §5](resolucion_cui.md) (Paso 5) |
| 5 | **Excel final enriquecido** | **Regenera** el Excel formato Manuel (no parchea) + hojas por profesional. Resalta Claude (amarillo) vs backend (naranja). | Excel final + reporte | 🔨 | [../contrato/contrato_refactor.md §3](../contrato/contrato_refactor.md) |
| 6 | **Persistencia + panel** | PostgreSQL (histórico/jobs) + websocket notifica al panel. | job listo → descarga | 📐 base reusable | [../frontend/README.md](../frontend/README.md) |

## Regla de oro (constraint on-prem)

El servidor hace lo **determinístico** y lo que toca **fuentes oficiales** (SUNAT/
InfoObras son portales públicos — requests **salientes**, sin exponer el servidor).
**Nunca** llama a APIs cloud de IA. Lo no-determinístico (razonar sobre PDFs) ya lo
hizo Claude en la PC del cliente.

## Dónde vive el código (referencia, en `Alpamayo-InfoObras`)

| Componente | Archivo base a reusar |
|---|---|
| 2 · Resolución CUI | prototipo en `tools/buscar_cui_por_nombre.py` (este repo) → portar a `src/scraping/infoobras/` |
| 3a · InfoObras | `src/scraping/infoobras/` (fetch por CUI, paralizaciones) |
| 3b · SUNAT | `src/scraping/sunat.py` (`consultar_ruc`, `getRepLeg`) |
| 4 · Motor de reglas | `src/validation/rules.py` (ALT01-ALT11; ALT11 = fusión periodos) |
| 5 · Excel | `src/reporting/` (openpyxl) + `backend/scripts/generar_excel.py` (este repo) |
| 0/6 · API/persistencia | `src/api/main.py` (jobs, websockets) + PostgreSQL |

## Modelos de datos (Pydantic v2 · `backend/schemas/`)

| Archivo | Qué modela |
|---|---|
| `espejo.py` | El **JSON espejo** que emite Claude (contrato de entrada · `_backend` vacío). |
| `enriquecimiento.py` | Lo que el backend **produce** por experiencia: `ResolucionObra` (comp. 2), `InfoObrasResultado`+`Paralizacion` (3a), `SunatResultado`+`Representante` (3b), `ReglasResultado`+`DiasEfectivos` (4). El `EnriquecimientoExperiencia` es el `_backend` **tipado** (filled). |
| `pipeline.py` | El **orquestador**: `Job` (registro), `Etapa`, `JobEstado`/`EstadoEtapa` (máquina de estados), `ResultadoEtapa` (checkpoint), `Observacion`, `ItemRevision` (human-in-the-loop), `ProgresoJob` (websocket). |

> Mapa completo concepto → modelo en [`orquestador.md`](orquestador.md) §7.

## Contratos relacionados

- **Schema del JSON espejo** (incl. campos `cui`, `ruc_emisor` que alimentan #2/#3):
  `backend/schemas/espejo.py` (Pydantic) ↔ `skill/schemas/espejo.js` (zod) · contrato v1.2.0.
- **Qué extrae Claude** para que #2 resuelva bien (nombre verbatim + CUI):
  `skill/prompts/agent-propuesta-mapa.md` y `agent-propuesta-profesional.md`.
