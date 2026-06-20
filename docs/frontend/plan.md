# Plan del frontend — Panel del pivote InfoObras

> Estado: **PLAN (aprobado para MVP)**. Decisiones tomadas con el cliente el
> 2026-06-16. El backend ya expone TODO el API necesario; no hay frontend previo
> que reusar (Alpamayo es solo backend Python).

## 0. Decisiones cerradas

| Decisión | Valor |
|---|---|
| Stack | **React + Vite (SPA)** — la opción más interactiva |
| Despliegue | El **propio FastAPI sirve el build** como estáticos (un solo proceso on-prem) |
| Audiencia | Manuel, **evaluador no técnico** → español, palabras de evaluador, sin jerga |
| Alcance v1 | **MVP útil**: subir → estado → revisión humana → descargar |
| Fase 2 | histórico filtrable + vistas de hojas embebidas + distinción Claude/backend |

## 1. Arquitectura

```
DEV:   vite dev (:5173)  --proxy /api-->  FastAPI (:8001)   [hot reload]
PROD:  FastAPI (:8001)
         ├─ /api/pivote/*        → JSON (ya existe)
         └─ /  (StaticFiles)     → build de la SPA (dist/)
```

- **Un solo proceso en producción**: se monta `StaticFiles` en FastAPI para servir
  `frontend/dist`. Nada de Node en el server.
- **Estado en vivo por polling**: el análisis corre como `BackgroundTask`; no hay
  websocket. El detalle hace `GET /jobs/{id}` cada ~3 s mientras `estado ==
  "en_proceso"` y se detiene al terminar.
- **Sin auth en el MVP** (LAN). Se deja el hook para token/allowlist (gap conocido,
  ver §9).

## 2. Mapa de pantallas (MVP)

1. **Inicio / Análisis** — lista de análisis (jobs) y concursos, con estado y
   acceso a cada uno. Botón "Nuevo análisis".
2. **Nuevo análisis** — elegir o crear concurso + **dropzone** (`espejo.json` +
   Excel). Es la alternativa manual al MCP; si Manuel subió por el MCP, el análisis
   ya aparece en la lista.
3. **Detalle del análisis** — el centro de todo:
   - **Cabecera**: postor, concurso, estado, barra de pasos (en palabras de
     evaluador).
   - **Resultados** (de `/resumen`): por profesional, qué dijo Claude vs qué
     verificó el backend (años brutos → años efectivos, con el motivo:
     paralizaciones/traslapes), factores y puntaje técnico.
   - **Casos por confirmar** (`items_revision`): la UI de **revisión humana**.
   - **Alertas**: marcar cada una relevante / no relevante para la evaluación.
   - **Descargas**: Excel enriquecido + ZIP de InfoObras.

## 3. Pantalla → endpoint (todo ya existe)

| Acción UI | Endpoint |
|---|---|
| Listar concursos / análisis | `GET /api/pivote/concursos` · `GET /api/pivote/jobs/{id}` |
| Crear concurso | `POST /api/pivote/concursos` |
| Subir análisis (dropzone) | `POST /api/pivote/analizar` (multipart: concurso_id, espejo, excel, origen=dropzone) |
| Estado en vivo del análisis | `GET /api/pivote/jobs/{id}` (polling) |
| Resultados (veredictos/factores) | `GET /api/pivote/jobs/{id}/resumen` |
| Extracción (profesionales/exp) | `GET /api/pivote/jobs/{id}/espejo` |
| **Resolver caso por confirmar** | `POST /api/pivote/jobs/{id}/revision` `{n_prof, n_exp, cui?|accion:"no_existe"}` |
| **Marcar alerta relevante/no** | `POST /api/pivote/jobs/{id}/alertas` `{alerta_id, relevante, razon?}` |
| Descargar Excel / ZIP | `GET /api/pivote/jobs/{id}/excel` · `/zip` |
| Salud de portales | `GET /api/pivote/salud` |

## 4. Lenguaje (mapa de términos — usuario NO técnico)

| Interno | En el panel |
|---|---|
| job / analisis_id | **Análisis** |
| espejo / JSON / contrato | (no se nombra) |
| MCP | (no se nombra; el dropzone dice "Subir archivos") |
| etapa `REGLAS` | "Cálculo de días efectivos" |
| etapa `SUNAT` / `INFOOBRAS` | "Verificación en SUNAT / InfoObras" |
| `items_revision` | **Casos por confirmar** |
| `cumple_backend` / `anios_efectivos` | "Resultado verificado" / "años que cuentan" |
| `observación / severidad` | **Alerta** (con color) |

Regla: en TODO lo visible se usan palabras del evaluador. (Memoria
`usuarios-no-tecnicos-ui-simple`.)

## 5. El corazón del MVP — revisión humana

**A. Casos por confirmar** (`items_revision` del job). Cada item trae:
`{n_prof, n_exp, motivo, candidatos[], accion_sugerida, profesional, cargo,
proyecto, fechas}`. La UI muestra una tarjeta por caso:
- Contexto: profesional, cargo, proyecto, fechas.
- Motivo legible (p. ej. "el código de la obra no coincide" / "sin candidato").
- **Candidatos** como opciones (CUI + nombre de obra + departamento + score), o
  campo "pegar CUI", o botón "no está en InfoObras".
- Al elegir → `POST /revision` → el caso se marca resuelto y se refresca el job.

**B. Alertas.** Lista de `alertas` (de `/resumen`). Cada una con su color
(advertencia/alerta) y un control "¿Relevante para tu evaluación?" Sí/No (+ razón
opcional) → `POST /alertas`.

## 6. Estructura de carpetas

```
frontend/
  package.json  vite.config.ts  index.html
  src/
    api/cliente.ts        # wrappers fetch tipados de los endpoints
    pages/               # Inicio, NuevoAnalisis, DetalleAnalisis
    components/          # TarjetaCaso, Alerta, BarraEstado, TablaVeredictos, Dropzone
    App.tsx  main.tsx
```
`node_modules/` y `dist/` van al `.gitignore`. El build (`dist/`) lo sirve FastAPI.

## 7. Pasos de implementación (orden sugerido)

1. Scaffold `frontend/` (Vite + React + TS) + proxy dev a `:8001`.
2. Cliente API tipado (un wrapper por endpoint del §3).
3. FastAPI: montar `StaticFiles` para servir `frontend/dist` (con fallback SPA).
4. **Inicio**: lista de análisis + concursos.
5. **Nuevo análisis**: crear/elegir concurso + dropzone → `POST /analizar`.
6. **Detalle**: estado + polling + Resultados (`/resumen`).
7. **Revisión humana**: casos por confirmar (`/revision`) + alertas (`/alertas`).
8. **Descargas** Excel/ZIP.
9. Pulido: estados de carga/error, copy no-técnico, responsive básico.

## 8. Fase 2 (fuera del MVP, anotado)

- Histórico filtrable por concurso / entidad / fecha.
- Vista embebida de las hojas (CLAUDE / Base de Datos) — o visor del Excel.
- Distinción visual Claude vs backend dentro del panel (no solo en el Excel).
- Autenticación (token o allowlist de IP).

## 9. Riesgos / decisiones abiertas

- **Auth**: el MVP queda sin login (LAN). Confirmar con el cliente si basta o se
  necesita un token simple antes de exponerlo.
- **Concurso**: en "Nuevo análisis" el panel puede **crear el concurso** si no
  existe (hoy el MCP lo crea); definir si la nomenclatura la teclea Manuel o sale
  del espejo (`_meta.concurso`).
- **Polling vs websocket**: MVP con polling (simple); si molesta, se añade WS luego.
- **Empaquetado**: decidir si el `dist/` se versiona o se construye en el deploy.
