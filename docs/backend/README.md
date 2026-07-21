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
| 0 | **Ingesta / API HTTP** | Recibe Excel + JSON espejo (LAN), valida schema (Pydantic), crea job. Mismo endpoint para dropzone y MCP. | `job_id` | ✅ probado (e2e con MCP y panel) | [contrato_refactor §4](../contrato/contrato_refactor.md) |
| 1 | **Validador determinístico** | Verifica lo que Claude **afirma** (15 notas): experiencias omitidas, ISOs, solapes, fechas, conteo de periodos, postor vs consorcio. No re-evalúa. | observaciones | ✅ probado | [contrato_refactor §6-7](../contrato/contrato_refactor.md) |
| 2 | **Resolución de CUI** *(el “selector”)* | Cada experiencia → CUI de obra. Paso 0 (CUI citado) → dedup → nombre+RUC+ubicación. Lo dudoso va a REVISIÓN con candidatos. | CUI por experiencia | ✅ probado en vivo | **[resolucion_cui.md](resolucion_cui.md)** |
| 3a | **InfoObras** (vía CUI) | `fetch_by_cui` → ficha de la obra + paralizaciones. Subcomponente: descarga de archivos → ZIP por experiencia. | `codigo_ciu`, `codigo_infoobras`, `paralizaciones` | ✅ scraping + ZIP + informes de control | [descarga_infoobras_experiencias.md](descarga_infoobras_experiencias.md) |
| 3b | **SUNAT** (vía RUC emisor) | `consultar_ruc` (ALT04) + resolución de RUC por nombre + vinculación postor↔emisor. **ALT12 descartada** (falsos positivos firmante vs rep. legal — auditoría en vivo). | `fecha_creacion_emisor`, `alerta_antiguedad_emisor`, `vinculacion_postor_emisor` | ✅ probado | [sunat_endpoints.html](sunat_endpoints.html) · [contrato_refactor §5](../contrato/contrato_refactor.md) |
| 4 | **Motor de reglas / recálculos** | Paso 5: días efectivos = brutos − paralizaciones − traslapes (ALT11). ALT03: recálculo cutoff **25 años** (Claude usó 20). Clamp a la ventana de valorizaciones. | `alerta_experiencia_antigua`, días efectivos | ✅ probado | [resolucion_cui.md §5](resolucion_cui.md) (Paso 5) |
| 5 | **Excel final enriquecido** | **Regenera** el Excel formato Manuel (no parchea) + hojas por profesional. Resalta Claude (amarillo) vs backend (naranja). Certs embebidos + Mejora Paso 5 (fechas Certificado vs InfoObras). | Excel final + reporte | ✅ probado | [../contrato/contrato_refactor.md §3](../contrato/contrato_refactor.md) |
| 6 | **Persistencia + panel** | Archivos = fuente de verdad (carpeta por job) + PostgreSQL como respaldo lógico write-through (`PIVOTE_DB_URL`). El panel se entera por polling (`/progreso`). | job listo → descarga | ✅ archivos · ⏳ respaldo pg por validar en server | [../frontend/README.md](../frontend/README.md) |

## Base local MEF (resolución de CUI)

El componente **2 · Resolución de CUI** se apoya en una **base local del MEF** (el
Banco de Inversiones) para no depender solo de la búsqueda por substring de
InfoObras. Es un espejo consolidado de las inversiones públicas (~490k filas, 452k
CUIs distintos) que vive en `<PIVOTE_DATA_DIR>/referencia/mef/` como tres
artefactos: `inversiones.csv.gz`, `entidades_publicas.csv` y `metadata.json`.

**Para qué sirve** (tres usos, todos en `resolucion/base_mef.py`):
- `buscar_candidatos(nombre)` — índice invertido token→filas + `rapidfuzz`: propone
  CUIs cuyo nombre oficial se parece al del certificado (que suele venir abreviado).
  El resolver **fusiona** esos candidatos con los de InfoObras antes de rankear.
- `existe_cui(codigo)` — ficha oficial de un CUI/SNIP citado que InfoObras no tenga
  (se usa como **pista** en el motivo de revisión, no para resolver).
- `es_entidad_publica(nombre)` — catálogo de entidades del Estado: si la entidad
  contratante **no** se reconoce como pública, la experiencia sin candidato fiable
  se marca `posible_privada` en la clasificación final.

**Cómo generarla / refrescarla**:
```
python backend/scripts/actualizar_base_mef.py                 # descarga desde el MEF
python backend/scripts/actualizar_base_mef.py --desde-dir DIR # usa CSV locales (sin red)
```
La escritura es **atómica** (tmp + `os.replace`) y valida el volumen: si la descarga
falla o queda corta, la versión anterior queda intacta. Refresco recomendado en el
**host** (no en el contenedor) vía crontab semanal, p. ej. domingos 03:00:
```
0 3 * * 0  cd /ruta/backend && python scripts/actualizar_base_mef.py
```

**RAM / carga**: ~370 MB residentes, **carga perezosa ~60 s** en el primer uso (se
comparte como singleton por proceso — ver `base_mef.instancia()`). Diseño de memoria
en `base_mef.py` (columnas paralelas + `sys.intern` + `array('i')` en el índice).

**Degradación**: si los artefactos no existen, `disponible()` es `False` y todos los
métodos devuelven vacío/None **sin lanzar** — el resolver sigue funcionando
**solo con InfoObras en vivo** (sin fusión MEF ni candado de entidad). La base es una
mejora, no una dependencia dura.

**Flujo público-primero (5 líneas)**: (1) si el certificado cita un CUI/SNIP, se
verifica contra InfoObras y manda si calza (autoritativo). (2) Si no, se busca por
nombre en InfoObras **y** en el MEF, y se **fusionan** los candidatos. (3) Se rankea
100% por **identidad** (nombre + RUC + ubicación); el solape de valorizaciones ya
**no** entra en la selección (evita circularidad). (4) Las compuertas (veto de rubro,
gate de tokens, candado de entidad) protegen contra falsos positivos. (5) Solo al
**final**, agotada la vía pública, se clasifica lo privado (léxico o entidad no
pública) — todo lo demás cae a revisión con candidatos a la vista.

## Regla de oro (constraint on-prem)

El servidor hace lo **determinístico** y lo que toca **fuentes oficiales** (SUNAT/
InfoObras son portales públicos — requests **salientes**, sin exponer el servidor).
**Nunca** llama a APIs cloud de IA. Lo no-determinístico (razonar sobre PDFs) ya lo
hizo Claude en la PC del cliente.

## Dónde vive el código (referencia, en `Alpamayo-InfoObras`)

| Componente | Archivo base a reusar |
|---|---|
| 2 · Resolución CUI | `backend/resolucion/cui.py` (resolver) + `base_mef.py` (base local MEF) + `texto.py` |
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
