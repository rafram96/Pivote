# Pieza 4 · Frontend — spec de pantallas del panel (pivote)

> ⚠ **El código del frontend NO vive en este repo.** Vive en `Panel-InfoObras`
> (Next.js 15 + React 19 + Tailwind). Esta carpeta es documentación de diseño.
> Los modelos que el panel consume son los de `backend/schemas/pipeline.py`
> (Job, ResultadoEtapa, ItemRevision, Observacion, ProgresoJob) y
> `backend/schemas/enriquecimiento.py`.

## ✅ Estado de implementación (actualizado 2026-06-19)

> **El panel YA ESTÁ CONSTRUIDO y cableado al backend real.** Vive en
> `Panel-InfoObras` (Next.js 15 + React 19 + Tailwind), proxya `/api/pivote/*`
> al backend vía `PIVOTE_API`, abre en **modo oscuro** por defecto, y los flujos
> (concursos, expediente, detalle, revisión humana de las 3 vías, descargas
> Excel/ZIP) están **probados end-to-end** contra el backend real.
> Pendiente: portar el rediseño limpio (Stitch) pantalla por pantalla.
>
> La tabla de abajo es **histórica** (de cuando el panel estaba pendiente); hoy
> esas pantallas existen y consumen los endpoints reales.

**Backend listo vs. panel pendiente** (endpoints reales bajo `/api/pivote/…`):

| Pantalla | Endpoint backend | ¿Backend? | ¿Panel? |
|---|---|---|---|
| P1 Expediente de concursos | `GET/POST /concursos`, `GET /concursos/{id}` | ✅ | ❌ |
| P2 Análisis nuevo (dropzone) | `POST /analizar` | ✅ | ❌ |
| P3 Job en vivo | `GET /jobs/{id}` (polling) | ✅ | ❌ |
| P3 progreso en vivo | `WS /ws/jobs/{id}` | ❌ **falta** | ❌ |
| P4 Cola de revisión ⭐ | `POST /jobs/{id}/revision` | ✅ | ❌ |
| P5 Resumen + diff | `GET /jobs/{id}/resumen`, `/espejo` | ✅ | ❌ |
| P5 decidir alertas | `POST /jobs/{id}/alertas` | ✅ | ❌ |
| P5 descargar Excel | `GET /jobs/{id}/excel` | ✅ | ❌ |
| P5 descargar ZIP sustentos | `GET /jobs/{id}/zip` | ✅ (on-demand) | ❌ |
| Banner salud portales | `GET /salud` | ✅ | ❌ |

**Alcance objetivo extendido** — capacidades nuevas (sesión 2026-06-15) que el
panel debe superficiar y que el spec original no contemplaba:

1. **Veredicto provisional / EN REVISIÓN como estado de primera clase.** El
   backend ya marca `veredicto_provisional` cuando el clamp de Paso 5 invierte a
   NO CUMPLE, cuando una obra no se pudo verificar (`sin_verificar`), o cuando hay
   fechas POR VERIFICAR (`fechas_invalidas`). P4/P5 deben distinguir visualmente
   *"NO CUMPLE confirmado"* de *"NO CUMPLE provisional — falta confirmar dato de
   InfoObras"* (un rechazo provisional es impugnable; no debe verse como final).
2. **Descarga del ZIP de sustentos** (P5): botón *"Descargar sustentos (ZIP)"* —
   se arma on-demand la primera vez (puede tardar: descarga documentos del portal
   flaky). La UI debe mostrar progreso/estado, no congelarse.
3. **Visibilidad documental por hito** (P5 o detalle de experiencia): el Excel ya
   trae la columna **ARCHIVOS (ZIP)** (`Sí (N)`/`—`) por valorización. El panel
   puede reflejar lo mismo: qué hitos tienen sustento descargable antes de bajar
   el ZIP.
4. **Modificaciones de plazo** (ampliaciones/suspensiones): dato nuevo por
   experiencia; mostrarlo junto al cuadro de valorizaciones en el detalle.
5. **Progreso en vivo real** (P3): hoy el backend es polling (`GET /jobs/{id}`).
   El `WS /ws/jobs/{id}` del spec **aún no existe** — o se implementa el websocket,
   o el panel hace polling con backoff. Decidir antes de construir P3.

El resto del spec (abajo) sigue vigente como objetivo; las pantallas no cambian,
se enriquecen con lo de arriba.

## Principios (por qué el panel es así y no de otra forma)

1. **Un solo usuario** (Manuel, 100–200 análisis/mes). Nada de roles, multi-tenant
   ni onboarding. Usabilidad = encajar en SU flujo, no en uno genérico.
2. **El concurso es la unidad mental, el job es plomería.** Manuel evalúa
   concursos con N postores; el panel se organiza por concurso, no por job.
3. **El panel nunca edita la evaluación.** La evaluación la hace Claude; las
   correcciones van por re-run de la skill. El panel registra *decisiones
   humanas sobre alertas* (auditable), no permite reescribir veredictos.
4. **Cada dato enriquecido es defendible**: fuente + fecha de consulta visibles.
   Las evaluaciones OSCE se impugnan; la trazabilidad es valor de negocio.
5. **LAN only** (decisión cerrada del pivote — el backend no se expone a internet).

## Modelo mental

```
Concurso (nomenclatura, entidad, fecha)
   ├── Bases (referencia)
   ├── Análisis = 1 postor = 1 job   ← dropzone crea esto
   │      ├── 8 etapas (checkpoints)
   │      ├── items_revision (cola humana)
   │      └── Excel final + espejo enriquecido
   └── Cuadro comparativo (todos los postores del concurso)
```

---

## Pantallas del MVP (en orden de construcción)

### P1 · Expediente de concursos (home + histórico)

| | |
|---|---|
| **Propósito** | Punto de entrada: ver concursos activos y pasados, entrar a uno. |
| **Muestra** | Lista de concursos (nomenclatura, entidad, fecha, n.º de postores analizados, pendientes de revisión). Filtros: texto, entidad, rango de fechas. |
| **Datos** | `GET /api/concursos` (lista) — agregado de `Job.concurso/postor/estado/pendientes_humano`. |
| **Acciones** | Crear concurso · entrar al expediente. |
| **Hecho cuando** | Manuel encuentra cualquier análisis pasado en <10 s. |

### P2 · Análisis nuevo (dropzone)

| | |
|---|---|
| **Propósito** | Transporte Camino B: subir Excel + JSON espejo dentro de un concurso. |
| **Muestra** | Dropzone de 2 archivos. Validación **al soltar**: schema espejo (v1.2.0), `_meta.version_contrato`, y que Excel y JSON refieran al mismo `analisis_id`. Rechazo = lista de errores concretos (los del validador Pydantic), no un error genérico. |
| **Datos** | `POST /api/analizar` (multipart: excel + json + concurso_id) → `{job_id}`. La validación de ingesta es la etapa 0 del pipeline. |
| **Acciones** | Subir → redirige a P3. |
| **Hecho cuando** | Un espejo inválido explica sus errores campo por campo; uno válido arranca job sin paso extra. |

### P3 · Job en vivo

| | |
|---|---|
| **Propósito** | Ver el pipeline avanzar sin ansiedad (jobs tardan minutos por throttling de portales). |
| **Muestra** | Las 8 etapas (`Etapa.orden()`) con su `EstadoEtapa` y `MetricaEtapa` (items ok/revisión/error, reintentos, duración). `ERROR_PARCIAL` se presenta como "3 de 41 fallaron, el resto siguió" — **no** como job roto. Banner de salud de portales si hay diagnóstico (`captcha_real` / `estructura_desconocida` de los scrapers). |
| **Datos** | `GET /api/jobs/{id}` (estado completo: `Job`) + `WS /ws/jobs/{id}` (`ProgresoJob`: estado, etapa_actual, pct, mensaje). |
| **Acciones** | Cancelar · re-run (existe hoy, se mantiene) · ir a revisión (si `pendientes_humano > 0`). |
| **Hecho cuando** | Manuel puede cerrar la pestaña y volver: el job siguió y el estado es fiel (checkpoints). |

### P4 · Cola de revisión humana ⭐ (la pantalla más importante)

Con resolución de CUI al 50% en el caso adverso (Lircay), esta pantalla decide
si el sistema se siente fluido o roto.

| | |
|---|---|
| **Propósito** | Resolver los `ItemRevision` en minutos, no en una sesión de arqueología. |
| **Muestra** | Por item: la experiencia (proyecto, entidad_contratante, fechas, profesional), el `motivo`, la `accion_sugerida`, y los **`candidatos[]` con score** que el sistema encontró (nombre oficial de la obra, departamento, CUI). |
| **Datos** | `Job.items_revision` (filtrado `resuelto == false`). |
| **Acciones** | (a) Elegir un candidato → confirma su CUI. (b) Pegar CUI manual. (c) Marcar "no existe en InfoObras" (queda documentado). Cada resolución → `POST /api/jobs/{id}/revision/{n_prof}/{n_exp}` → el backend **re-ejecuta solo esa experiencia aguas abajo** (INFOOBRAS → REGLAS → EXCEL). |
| **Hecho cuando** | 20 items pendientes se despachan en ~10 min de clics y el Excel final se regenera solo. |

### P5 · Resumen del análisis (veredicto + diff)

| | |
|---|---|
| **Propósito** | El veredicto sin abrir Excel — y el "diff" Claude → backend como narrativa. |
| **Muestra** | Arriba: cumple/no-cumple por profesional + puntaje total + alertas por `Severidad` (críticas primero). El diff por experiencia donde el backend cambió algo: *"Claude: SÍ CUMPLE (3.96 años) → Backend: NO CUMPLE (1.55 años efectivos — 2 paralizaciones, obra CUI 2338373)"* con link a los periodos. Cada dato `_backend` con fuente + fecha ("SUNAT · 09/06/2026"). Alertas (ALT04/ALT12/vinculación) con botones **relevante / descartada porque…** → decisión registrada en el expediente. |
| **Datos** | espejo enriquecido (`GET /api/jobs/{id}/espejo`) + `Job.observaciones` + `EnriquecimientoExperiencia` (resolucion · infoobras · sunat · reglas). |
| **Acciones** | Descargar Excel final (`GET /api/jobs/{id}/excel`) · descargar espejo · decidir alertas. |
| **Hecho cuando** | Manuel sabe si hay bombas en 30 segundos, sin descargar nada. |

### P6 · Comparador de postores (cierra el MVP+)

| | |
|---|---|
| **Propósito** | El trabajo real: comparar todos los postores de un concurso. |
| **Muestra** | Tabla postor × puntaje técnico × profesionales que cumplen × n.º de alertas (por severidad) × estado del job. Exportación del cuadro. |
| **Datos** | agregado de los jobs del concurso. |
| **Hecho cuando** | El cuadro comparativo que Manuel arma a mano hoy sale solo. |

---

## API que el backend expone (prefijo real `/api/pivote/`)

✅ = implementado en [backend/api/app.py](../../backend/api/app.py) · ❌ = pendiente

```
✅ GET  /api/pivote/concursos?q=&entidad=&desde=  · POST /api/pivote/concursos
✅ GET  /api/pivote/concursos/{id}
✅ POST /api/pivote/analizar                 (multipart excel+json+concurso_id) → {job_id}
✅ GET  /api/pivote/jobs/{id}                → Job (etapas, observaciones, items_revision)
❌ WS   /ws/jobs/{id}                         → ProgresoJob   ← NO existe aún; hoy es polling
✅ POST /api/pivote/jobs/{id}/revision        {n_prof, n_exp, cui|accion} → re-dispara aguas abajo
✅ POST /api/pivote/jobs/{id}/alertas         {ref, relevante, razon} (auditoría)
✅ GET  /api/pivote/jobs/{id}/resumen         → veredictos + diff + alertas (P5)
✅ GET  /api/pivote/jobs/{id}/excel · GET …/espejo
✅ GET  /api/pivote/jobs/{id}/zip             → ZIP de sustentos (se arma on-demand)
✅ GET  /api/pivote/salud                     → diagnóstico sunat/infoobras (banner P3)
```

> Nota: el spec original usaba `/api/jobs/…` y rutas con `{n_prof}/{n_exp}` en el
> path; la implementación real las lleva en el body bajo el prefijo `/api/pivote/`.
> El único hueco de backend es el **websocket de progreso** (P3 va por polling).

## Nivel 3 — lo que lo hace *realmente* útil (fase 2, ⚠ comercial)

- **Memoria institucional cross-concurso**: profesionales/emisores/obras ya vistos.
  Habilita: "este profesional presentó en CP-02 un certificado del mismo periodo
  con otro cargo", "este emisor ya disparó ALT04 antes", y un **cache de obras
  resueltas** que mejora la resolución de CUI con el uso. Es lo que convierte el
  panel en activo que se aprecia con el tiempo.
- **Exportación consolidada del expediente** del concurso (cuadro + anexos).
- **Paquete probatorio por experiencia** (modo impugnación): certificado folio X
  + consulta SUNAT fechada + periodos InfoObras, en un PDF/carpeta.

## Anti-alcance (❌ no construir)

- ❌ Editor de la evaluación (rompe trazabilidad; correcciones → re-run de skill).
- ❌ Visor completo del Excel recreado en web (P5 resume; el xlsx es el entregable).
- ❌ Multi-usuario / roles / auth compleja.
- ❌ Exponer el backend a internet.

## Decisiones

| Decisión | Status | Razón |
|---|---|---|
| **Concurso = entidad central desde el día 1** | ✓ recomendado | Barato ahora, carísimo de retrofitear. Implica: modelo `Concurso` en backend + FK en `Job` (hoy `Job.concurso` es un string suelto — cambiar al implementar el orquestador). |
| Memoria cross-concurso: ¿alcance cotizado o fase 2 facturable? | ⚠ Manuel/comercial | No bloquea el MVP; el modelo por concurso del día 1 la deja preparada. |
| Cola de revisión = prioridad de UX sobre cualquier otra pantalla | ✓ | Es donde el 0–50% no-automático se vuelve trabajo humano fluido o fricción mortal. |

## Se mantiene del panel actual

Re-run, job detail y debug tools existentes (decisión heredada del plan original).
