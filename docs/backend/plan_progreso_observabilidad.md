# Plan — Progreso y observabilidad del pipeline (backend + panel)

> **Estado** (act. 2026-07-11):
> - **Paquete A — ✅ IMPLEMENTADO y mergeado a `demo`**: §1 progreso por ítem
>   (`orquestador/progreso.py` + `Contexto.reportar`) · §2a endpoint `/progreso` ·
>   §3 descargas con `obra_actual` · §8 panel (`StepperEtapas`, hook de polling,
>   TabDescargas). Validado en navegador con mock; falta verlo contra portales
>   vivos en el server del cliente.
> - **Paquetes B (§4 ETA, §5 timeline) · C (§6 cancelar) · D (§2b SSE) — ⏳ NO
>   implementados**: candidatos a bolsa de horas / extras
>   (ver `docs/comercial/estrategia-extras.html`).
> - §7 semáforo de salud: ya existía antes de este plan (quedó descartado aquí).
> **Repos afectados**: este (`backend/`) y `Panel-InfoObras/frontend/`.

---

## 0 · Punto de partida (lo que YA existe — no reinventar)

| Pieza | Dónde | Estado |
|---|---|---|
| Evento `ProgresoJob` (job_id, estado, etapa_actual, pct, mensaje) | `backend/schemas/pipeline.py:129` | ✓ modelo definido |
| Notificación tras cada checkpoint de etapa | `backend/orquestador/motor.py:267` (`_checkpoint` → `_notificar`) | ✓ pero cableado a **no-op** (`Motor(...)` en `app.py:52-54` no pasa `notificar`) |
| Métricas por etapa (`items_total/ok/error`, `reintentos`, `descargas`, `bytes`, `duracion_ms`) | `pipeline.MetricaEtapa` | ✓ se llenan al **cerrar** la etapa, no durante |
| `descargas_estado` (pendiente → en_progreso → listas \| error) | `pipeline.Job` + `GET /jobs/{id}/descargas` (`app.py:345`) | ✓ solo 4 estados, sin contador |
| Semáforo de salud de portales | `GET /api/pivote/salud` (`app.py:797`, caché 60 s) + route del panel + sondeo cada ~30 s | ✓ **HECHO end-to-end** — el punto 6 de la lista original queda descartado por ya existir |
| Panel: polling del detalle de job | `frontend/src/app/concursos/[id]/jobs/[jobId]/page.tsx` — `setInterval(cargar, 2500)` | ✓ polling 2.5 s |
| Panel: componentes reutilizables | `BarraProgreso.tsx`, `Badge.tsx`, `Skeleton.tsx`, `TabDescargas.tsx`, `TabPasos.tsx` | ✓ sistema TONO — no hardcodear colores/tamaños |

**Restricciones vigentes** (heredadas del proyecto):
- Backend on-prem, NUNCA llama a cloud. Panel habla con backend vía `PIVOTE_API` (127.0.0.1).
- Usuarios NO técnicos: todo texto visible en palabras de evaluador, sin jerga
  (nada de "pipeline", "scraping", "SSE" en la UI).
- Los scrapers en vivo NO se prueban en esta laptop; los tests offline
  (`PIVOTE_ETAPAS=esqueleto`, `backend/tests/`) sí.
- Repositorio de jobs = archivos JSON (`RepositorioArchivos`); evitar escrituras
  por-ítem a disco.

---

## 1 · Progreso granular por ítem dentro de cada etapa

### Problema
`ProgresoJob.pct` avanza en saltos de 12.5 % (1/8 etapas). Las etapas largas
(RESOLUCION_CUI, INFOOBRAS, SUNAT) iteran por experiencia (49+ ítems en Lircay)
y pueden pasar **minutos sin señal** → el usuario cree que se colgó.

### Diseño backend

**a) Estado de progreso en memoria (no en disco).**
Nuevo módulo `backend/orquestador/progreso.py`:

```python
class ProgresoVivo(_Model):
    """Snapshot en memoria del avance fino. Volátil a propósito: si el proceso
    muere, el job reanuda por checkpoints y el progreso se reconstruye."""
    job_id: str
    etapa: Etapa
    item_actual: int          # 1-based
    items_total: int
    descripcion: str          # "Verificando obra en InfoObras — Hospital de Lircay"
    actualizado_en: datetime

class RegistroProgreso:
    """Singleton simple (dict + threading.Lock) job_id → {etapa → ProgresoVivo}.
    Dict por etapa porque INFOOBRAS ∥ SUNAT corren EN PARALELO (motor.py
    _RAMA_PARALELA) → dos contadores simultáneos, nunca uno solo."""
```

- Vive como atributo del módulo `api/app.py` (proceso único uvicorn — mismo
  supuesto que `_SALUD_CACHE`). **No** se persiste en el repo de jobs: cero I/O extra.
- Se limpia al terminar el job (`estado` terminal) con TTL de ~1 h por si el
  panel llega tarde.

**b) Hook en las etapas.**
`Contexto` (en `etapas.py`) gana un callback opcional:

```python
class Contexto:
    ...
    reportar: Callable[[int, int, str], None] = lambda *_: None
    # reportar(item_actual, items_total, descripcion_corta)
```

El `Motor` lo inyecta al construir el `Contexto` (cerrando sobre `job_id` y
`nombre` de etapa → escribe en `RegistroProgreso`). Las etapas que iteran
experiencias llaman `ctx.reportar(i, total, desc)` al **inicio** de cada ítem
(no al final: así "12 de 49" refleja que el 12 está en curso).

Puntos de inserción en `etapas_reales.py` (los loops ya existen):
- `RESOLUCION_CUI`: loop por experiencia → desc = nombre corto del proyecto.
- `INFOOBRAS`: loop por experiencia/obra → desc = nombre de obra o CUI.
- `SUNAT`: loop por emisor/RUC → desc = razón social o RUC.
- `VALIDACION` y `REGLAS`: son rápidas; reportar solo `(0, 0, "…")` al entrar
  (basta el nombre de etapa). No instrumentar de más.
- Con fan-out concurrente por ítem (pool en `resolver_revision` / etapas con
  límite de concurrencia): `item_actual` = contador atómico de **completados+1**,
  y la descripción, la del último ítem iniciado. Aproximación honesta y barata.

**c) Textos sin jerga** (los emite el backend, el panel solo los muestra):

| Etapa | Texto visible |
|---|---|
| validacion | "Revisando la consistencia de la propuesta" |
| resolucion_cui | "Ubicando la obra {n} de {N} en el registro público" |
| infoobras | "Verificando la obra {n} de {N} — {nombre}" |
| sunat | "Consultando el RUC {n} de {N} — {emisor}" |
| reglas | "Calculando los días efectivos" |
| excel | "Armando el Excel de evaluación" |

Reusar/extender el mapa `ETAPA_FUENTE` de `app.py:53` → nuevo dict
`ETAPA_TEXTO` en el mismo lugar (una sola fuente de nombres visibles).

### Diseño panel
Ver §2 (el transporte) y §8 (componentes). La barra por etapa =
`BarraProgreso` existente con `valor = item_actual/items_total`.

### Riesgos y decisiones
- ⚠ Rama paralela: el panel debe poder pintar DOS barras (InfoObras y SUNAT) a
  la vez → por eso el registro es `{etapa → ProgresoVivo}`, no un escalar.
- ✓ Decisión: progreso fino **volátil** (memoria). El persistente sigue siendo
  el checkpoint por etapa. Si el server se reinicia a mitad, el panel ve el
  checkpoint (grueso) hasta que la etapa en curso vuelva a reportar.
- ✓ Decisión: no tocar la firma de `EtapaBase.correr()` — el callback va por
  `Contexto`, así las etapas esqueleto no cambian y los tests offline pasan sin edits.

### Tests (offline, corren en esta laptop)
- Unit de `RegistroProgreso` (concurrencia: 2 hilos escribiendo etapas distintas).
- Etapa esqueleto instrumentada de mentira que llama `ctx.reportar` → verificar
  que el endpoint (§2) refleja `item_actual/items_total`.
- TTL/limpieza al completar el job.

**Esfuerzo**: ~1 día backend.

---

## 2 · Endpoint unificado de progreso + transporte

### Decisión de transporte: **polling unificado primero, SSE como fase 2 opcional**

Razón: el panel YA pollea cada 2.5 s y funciona; SSE requiere validar en el
server del cliente (server "sin instalar" — decisión 2026-06-10) y con el
proxy interno de Next (`/api/pivote/*` re-expone el backend — un stream SSE a
través de un route handler de Next necesita streaming passthrough). El 80 % del
valor es **qué** se muestra, no cada cuántos ms llega.

### Fase 2a — `GET /api/pivote/jobs/{job_id}/progreso` (polling, obligatorio)

Respuesta (todo lo que el panel necesita en UN request, en vez de armar el
estado desde `GET /jobs/{id}` + `/descargas`):

```jsonc
{
  "job_id": "…",
  "estado": "en_proceso",
  "pct": 37.5,                      // el grueso por etapas (como hoy)
  "etapas": [                        // orden canónico, para el stepper
    {"etapa": "ingesta",    "texto": "Recepción", "estado": "ok", "duracion_ms": 420},
    {"etapa": "infoobras",  "texto": "Verificando la obra 12 de 49 — Hospital de Lircay",
     "estado": "en_curso", "item_actual": 12, "items_total": 49},
    {"etapa": "sunat",      "texto": "Consultando el RUC 8 de 21 — …",
     "estado": "en_curso", "item_actual": 8, "items_total": 21},
    {"etapa": "reglas",     "texto": "Cálculo de días efectivos", "estado": "pendiente"}
  ],
  "descargas": {"estado": "en_progreso", "descargados": 14, "total": 40,
                 "obra_actual": "Hospital de Lircay"},          // §3
  "eta": {"segundos_restantes": 210, "rango": [140, 480], "confiable": true},  // §4, null si no hay histórico
  "pendientes_humano": 3
}
```

Implementación: función `armar_progreso(job) -> dict` en `app.py` que fusiona
(1) checkpoints del job persistido, (2) `RegistroProgreso` en memoria,
(3) estado de descargas, (4) ETA (§4). `GET /jobs/{id}` NO cambia
(compatibilidad con MCP `consultar_estado` y el panel actual).

### Fase 2b — `GET /api/pivote/jobs/{job_id}/eventos` (SSE, opcional/extra)

- `StreamingResponse` FastAPI con `media_type="text/event-stream"`.
- Cola en memoria por suscriptor (`asyncio.Queue`), alimentada por el mismo
  `RegistroProgreso` (el que escribe también hace `put_nowait` a las colas
  suscritas) + evento por checkpoint (reusar el `Notificador` del Motor —
  **por fin se cablea** `Motor(..., notificar=publicar_evento)` en `app.py`).
- Heartbeat `: ping` cada 15 s (keep-alive de proxies).
- Panel: el route handler de Next debe hacer passthrough del stream
  (`fetch` + devolver `response.body` directamente); en el cliente, hook
  `useProgresoJob` que intenta `EventSource` y **cae a polling** si falla
  (mismo shape de datos → el fallback es trivial).

### Riesgos
- ⚠ SSE + Next route handler: probar el passthrough temprano; si el buffering
  molesta, alternativa: el `EventSource` apunta directo a `PIVOTE_API`
  (misma máquina, sin CORS drama en 127.0.0.1 — verificar en despliegue real).
- ✓ Decisión: SSE **nunca** es la única vía. Polling del endpoint unificado es
  el contrato mínimo garantizado.

### Tests
- Offline: `armar_progreso` con jobs sintéticos en cada estado (recién creado,
  rama paralela a medias, con revisión, completado, error).
- SSE: test con `httpx.AsyncClient` + `PIVOTE_ETAPAS=esqueleto` leyendo 2-3
  eventos del stream. Validación real de red → en el server del cliente.

**Esfuerzo**: 2a ~0.5 día · 2b ~1 día (incluye passthrough del panel).

---

## 3 · Progreso de descargas de documentos (el hueco más visible)

### Problema
Con `PIVOTE_MAX_DESCARGAS` sin cap, armar el ZIP puede ser lo más largo del
flujo, y el panel solo ve `en_progreso` → botón "preparando…" sin fin.

### Diseño backend
- `descargar_documentos_job` (en `etapas_reales.py`, invocada por
  `_asegurar_descargas` de `app.py:165`) gana el mismo callback `reportar` del §1
  (registrado bajo una pseudo-etapa `"descargas"` en `RegistroProgreso` — NO se
  agrega al enum `Etapa`, para no tocar el orden canónico ni los checkpoints).
- Reporta `(obras_completadas + 1, total_obras, nombre_obra_en_curso)` al inicio
  de cada obra. Total = nº de obras con CUI resuelto al momento de arrancar.
- **Reintentos del portal flaky**: un reintento NO resetea el contador global;
  solo la obra actual se mantiene como "en curso". Si una obra agota reintentos,
  cuenta como completada (con observación SIN_DOCUMENTOS, como hoy) y la barra avanza.
- `GET /jobs/{id}/descargas` (`app.py:345`) se extiende con
  `descargados`, `total`, `obra_actual` (aditivo — el shape actual se conserva;
  el flujo `/descargar-cui` de un solo CUI se beneficia gratis si comparte la función).

### Diseño panel
- `TabDescargas.tsx` ya pollea: cambia el spinner por `BarraProgreso` +
  "Descargando documentos de la obra 14 de 40 — {nombre}".
- El botón del ZIP sigue habilitándose SOLO con `estado === "listas"` (contrato
  actual intacto).

### Riesgos
- ⚠ El "total" puede diferir del final real (obras que resultan sin documentos):
  aceptable — la barra llega a 100 % igual porque cuentan como completadas.
- ⚠ La reanudación post-corte (`_reanudar` en `app.py`) relanza descargas: el
  contador debe partir de las ya bajadas a disco, no de 0 (la función ya sabe
  saltar lo descargado; solo hay que contar bien el punto de partida).

### Tests
- Offline con etapa de descargas fake: contador avanza, reintento no resetea,
  reanudación parte del punto correcto.

**Esfuerzo**: ~0.5 día backend + ~0.25 día panel.

---

## 4 · ETA suave por histórico de duraciones

### Diseño backend
- Fuente: `duracion_ms` por etapa ya se guarda en cada checkpoint (y
  `_log_resumen` lo loguea). Nuevo `backend/orquestador/eta.py`:
  - Al completar un job, registrar `{etapa: duracion_ms / max(items_total, 1)}`
    (normalizado por ítem) en un JSON pequeño del DATA_DIR
    (`estadisticas_etapas.json`), ventana móvil de las últimas ~20 corridas.
  - `estimar(job, progreso_vivo) -> {segundos_restantes, rango, confiable}`:
    suma sobre etapas pendientes + resto de ítems de la etapa en curso.
    `rango` = [p25, p90] de la ventana. `confiable = n_corridas >= 3`.
- Regla de presentación (la decide el backend, el panel obedece):
  - `confiable == false` → `eta: null` → el panel NO muestra nada.
  - Mostrar SIEMPRE como rango ("entre 3 y 8 min"), nunca un número exacto —
    el portal flaky hace que un puntual quede mal parado.

### Diseño panel
- Línea discreta bajo el stepper: "Normalmente esto toma entre 3 y 8 minutos".
  Estilo `micro` del sistema TONO. Sin countdown en vivo (genera ansiedad y
  queda mal cuando el portal se arrastra); se refresca con cada poll.

### Riesgos
- ⚠ Primeras corridas en el server del cliente: sin histórico → invisible por
  diseño (mejor nada que un estimado inventado).
- ⚠ Mezcla de jobs chicos y gigantes: la normalización por ítem lo mitiga;
  si aún así queda ruidoso, segmentar por tramo de tamaño es un refinamiento
  futuro, no de esta fase.

### Tests
- Offline: ventana móvil, percentiles, `confiable`, job sin histórico → null.

**Esfuerzo**: ~0.5 día. **Orden**: después de §1–§3 (les da su insumo de UI).

---

## 5 · Timeline de eventos del job (auditoría)

### Diseño backend
- Nuevo modelo en `pipeline.py`:

```python
class EventoJob(_Model):
    ts: datetime
    tipo: str        # etapa_inicio | etapa_fin | item_revision | reintento
                     # | descarga_inicio | descarga_fin | cancelacion | error
    etapa: Optional[Etapa] = None
    texto: str       # SIN jerga — es lo que ve el usuario
    detalle: Optional[str] = None   # técnico, colapsado tras "ver detalle"
```

- `Job.eventos: list[EventoJob]` con **cap de 200** (FIFO: al exceder, se
  descartan los más viejos de tipo `reintento` primero, luego los más viejos a
  secas). Razón del cap: el job vive como JSON en `RepositorioArchivos` y un job
  de 49 experiencias × reintentos puede acumular cientos de entradas.
- Emisores: `Motor._ejecutar` (inicio/fin de etapa — ya tiene el cronómetro),
  alta de `ItemRevision`, wrapper de reintentos de los scrapers,
  `_asegurar_descargas`, cancelación (§6).
- **Persistencia**: los eventos se escriben junto con el checkpoint que ya
  existe (no hay `guardar()` extra por evento). Los eventos entre checkpoints
  se acumulan en el objeto `job` en memoria del run — si el proceso muere se
  pierden los del tramo no checkpointeado: aceptable, es auditoría, no contabilidad.
- Exposición: incluidos en `GET /jobs/{id}` (campo nuevo, aditivo) o endpoint
  propio `GET /jobs/{id}/eventos-historial` si el payload molesta — decidir al
  medir tamaño real; default: campo en el job.

### Diseño panel
- En el detalle del job, sección colapsable "Historial" (debajo de las tabs):
  lista vertical ts + texto, `Badge` por tipo (reintento = ámbar, error = rojo,
  resto neutro). `detalle` técnico tras un toggle "ver detalle" — cumple la
  regla usuarios-no-técnicos.

### Riesgos
- ⚠ Crecimiento del JSON del job → mitigado por cap 200 + escritura solo en checkpoints.
- ⚠ Duplicación conceptual con `Observacion`: NO fusionar — `Observacion` es
  hallazgo de negocio (ALT04, NOTA1), `EventoJob` es traza operativa. El panel
  las muestra en lugares distintos (Alertas vs Historial).

### Tests
- Offline: cap FIFO con prioridad de descarte, eventos presentes tras un run
  esqueleto completo, orden cronológico.

**Esfuerzo**: ~1 día backend + ~0.5 día panel.

---

## 6 · Cancelación de job en curso

### Diseño backend
- `POST /api/pivote/jobs/{job_id}/cancelar`:
  - Marca bandera en memoria (`set` de job_ids cancelados en `app.py`, junto al
    `RegistroProgreso`) **y** persiste `job.estado = "cancelado"` — requiere:
    - `JobEstado.CANCELADO = "cancelado"` (nuevo miembro del enum).
    - Revisar TODO switch sobre `JobEstado` (backend, panel `types.ts`,
      MCP `consultar_estado`, `_reanudar` de `app.py:236` — un job cancelado NO
      se auto-reanuda al reiniciar el server).
- Chequeo cooperativo: `ctx.cancelado()` (nueva función en `Contexto`, cierra
  sobre la bandera) consultado por las etapas **entre ítems** y por
  `descargar_documentos_job` entre obras. Al detectarla: la etapa retorna
  limpiamente con lo hecho (checkpoint parcial válido — las etapas son
  idempotentes, reanudar después re-procesa solo lo faltante).
- El `Motor.correr` corta el loop de etapas si el job quedó cancelado y NO
  marca ERROR (evento `cancelacion` en el timeline §5).
- **Reanudación manual**: `POST /jobs/{id}/reanudar` (o reusar el mecanismo de
  `_reanudar` expuesto como acción) → `estado` vuelve a `en_proceso` y
  `motor.correr(job_id)` salta lo ya checkpointeado. Gratis gracias al diseño
  existente.

### Diseño panel
- Botón "Detener" en el header del job (solo visible si `estado == en_proceso`),
  con `ModalConfirmar` existente ("El análisis se puede retomar después desde
  donde quedó"). Job cancelado: `Badge` neutro "Detenido" + botón "Retomar".

### Riesgos
- ⚠ El mayor: **estado nuevo en el enum** se propaga a panel/MCP/scripts —
  auditar todos los consumidores de `JobEstado` (grep `en_proceso|JobEstado`)
  antes de mergear. Es la razón principal de que esto sea ~1 día y no ~0.25.
- ⚠ Cancelar a mitad de un ítem: el ítem en curso termina (cooperativo, no
  kill) — documentarlo en el modal ("puede tardar unos segundos en detenerse").
- ⚠ Rama paralela: ambas etapas ven la misma bandera; el join del motor debe
  tolerar que ambas retornen parciales.

### Tests
- Offline con etapa esqueleto lenta y cancelación entre ítems: checkpoint
  parcial válido, estado `cancelado`, reanudar completa el job, `_reanudar`
  del arranque NO lo relanza.

**Esfuerzo**: ~1 día backend + ~0.25 día panel.

---

## 7 · (Descartado) Semáforo de salud — YA EXISTE

`GET /api/pivote/salud` (`app.py:797`) + route del panel + sondeo cada ~30 s ya
están en producción. Único complemento opcional (5 min): en el formulario de
subida/dropzone, si algún portal está caído, aviso amable "El portal de
InfoObras está inestable en este momento; el análisis puede demorar más de lo
normal" — reusa el mismo endpoint, cero backend nuevo.

---

## 8 · Trabajo del panel (Panel-InfoObras) — consolidado

Todo con el sistema compartido (TONO, `Badge`, `BarraProgreso`, `Skeleton`,
escala nano/micro/dato; **no** hardcodear colores/tamaños).

1. **Hook `useProgresoJob(jobId)`** en `frontend/src/lib/pivote/`:
   - Fase 2a: polling de `/api/pivote/jobs/{id}/progreso` cada 2.5 s
     (reemplaza los múltiples fetch del detalle mientras el job corre; al
     llegar a estado terminal, corta el intervalo y dispara el fetch completo
     del job — hoy el intervalo vive en la page, moverlo al hook).
   - Fase 2b: si SSE disponible, `EventSource` con fallback automático al polling.
2. **Route handler nuevo** `app/api/pivote/jobs/[id]/progreso/route.ts`
   (proxy simple como los existentes) y, en fase 2b, `eventos/route.ts`
   con passthrough de stream.
3. **Componente `StepperEtapas`** (nuevo, en `components/analisis/`):
   stepper vertical de las 8 etapas con texto visible del backend; la(s)
   etapa(s) `en_curso` muestran `BarraProgreso` con `n de N` (dos a la vez en
   la rama paralela); estados con `Badge` (ok ✓ / en curso / pendiente /
   con revisión / error parcial). Sustituye el indicador actual del detalle
   mientras `estado == en_proceso`.
4. **`TabDescargas`**: spinner → barra `descargados/total` + obra en curso (§3).
5. **Línea de ETA** bajo el stepper (§4) — solo si `eta != null`.
6. **Sección "Historial"** colapsable (§5).
7. **Botón Detener/Retomar** + estado `cancelado` en `types.ts` y en los
   `Badge` de las listas de jobs (§6).
8. **Aviso de portal inestable** en el dropzone (§7, opcional).

Mock store (`lib/pivote/mock/store.ts`): agregar `progreso()` sintético que
simula avance por ítem — permite desarrollar y demo del panel sin backend vivo.

---

## 9 · Orden de implementación, dependencias y estimación

```
Paquete A (núcleo, mayor valor percibido)          ~2.5 días
  §1 progreso por ítem (backend)          1.0
  §2a endpoint unificado /progreso        0.5
  §3 progreso de descargas                0.75
  §8.1-4 panel (hook + stepper + tab)     (incluido arriba: 0.25 de §3 + resto en §1/§2a)

Paquete B (pulido)                                  ~1.5 días
  §4 ETA por histórico                    0.5
  §5 timeline de eventos                  1.0 (backend 1.0* + panel 0.5 → *solapa con §8)

Paquete C (control)                                 ~1.25 días
  §6 cancelar/retomar                     1.25

Paquete D (opcional/extra)                          ~1 día
  §2b SSE + passthrough Next              1.0
```

Dependencias duras: §2a depende de §1 (consume `RegistroProgreso`); §3 y §4
dependen de §1; §2b depende de §2a; §5 y §6 son independientes entre sí.

**Encaje comercial**: Paquete A es el candidato natural a la bolsa de horas
(≈ el valor de demo); B–D como extras cotizados. Nada de esto entra al
alcance cerrado del contrato.

---

## 10 · Plan de verificación

**En esta laptop (offline, `PIVOTE_ETAPAS=esqueleto`)**
- Todos los tests unitarios listados por sección (`backend/tests/`).
- `tools/test_contrato.py` sigue verde (los cambios al `Job` son aditivos;
  `EventoJob`/`cancelado` deben reflejarse en el espejo zod SOLO si el panel
  los tipa desde el contrato — revisar paridad Pydantic ↔ zod).
- Panel contra mock store con `progreso()` sintético: stepper, dos barras en
  paralelo, descargas, historial, cancelar.

**En el server del cliente (con portales vivos)**
- Job real chico: progreso fino visible, contadores coherentes con el log
  `_log_resumen`, descargas con barra, reanudación tras matar el proceso a
  mitad de InfoObras.
- SSE (si se hace 2b): stream estable ≥ 10 min, heartbeat, reconexión.

**Criterio de "listo" del Paquete A**: durante un análisis real, el panel
nunca pasa más de ~5 s sin cambiar algo visible (texto de ítem, contador o
barra) mientras el job está `en_proceso`.

---

## 11 · Decisiones tomadas en este plan (no reabrir sin razón)

| Decisión | Razón |
|---|---|
| Progreso fino en **memoria**, no persistido | cero I/O extra; el persistente sigue siendo el checkpoint |
| Polling unificado como contrato mínimo; SSE opcional encima | server del cliente sin instalar; passthrough Next sin validar |
| Callback vía `Contexto`, sin tocar firma de `EtapaBase.correr()` | etapas esqueleto y tests intactos |
| Descargas = pseudo-etapa en el registro, NO nuevo miembro de `Etapa` | no perturbar orden canónico ni checkpoints |
| ETA siempre en rango y solo con ≥3 corridas | portal flaky → un puntual exacto quema confianza |
| `EventoJob` ≠ `Observacion` (no fusionar) | traza operativa vs hallazgo de negocio |
| Cancelación cooperativa entre ítems (no kill) | checkpoints parciales válidos, reanudable |
| Cap 200 eventos por job, descartando `reintento` primero | job = JSON en disco, no inflarlo |
| Semáforo de salud: no se hace — ya existe | `app.py:797` + panel ya lo consumen |
