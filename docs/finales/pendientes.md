# Pendientes finales

> Recopilación de los cabos sueltos detectados al cerrar la fase de demos
> (sesión 2026-06-23). Ordenados por prioridad. Marcar con ✓ al cerrar.

## 🔴 Operativos — desbloquean cosas ya hechas

### P1 · Reiniciar el backend
El proceso `uvicorn` que corre tiene **código viejo en memoria**. Hay dos fixes
commiteados que **solo toman efecto al reiniciar**:
- `b1554ed` — armado **atómico** del `/zip` + lock → mata el error
  `h11 Too much data for declared Content-Length` en descargas concurrentes.
- `6d3499b` — **nombres cortos** en el ZIP (`P08 Estructuras/E1/…`) → cabe en el
  límite de 260 de Windows al extraer.

> Los ZIP **ya generados** en disco (Vitarte, 2× Pichanaqui) ya están con nombres
> cortos; reiniciar es para que **los análisis NUEVOS** también salgan bien y para
> el fix atómico del `/zip`. **Cómo:** detener y relanzar el uvicorn del backend.

## 🟡 Skill — mejoras de robustez

### P2 · Cruce de conteo contra las BASES (validador del orquestador)
El blindaje anti-contaminación de `agent-propuesta-mapa` ancla el roster a **B.1**
(el cuadro de calificaciones de la **propuesta**). Falta el cruce contra el
**Cuadro de Personal Clave de las BASES** (cuántos cargos exige el concurso). Eso
NO puede ir en el mapa (corre en paralelo a `agent-bases`, no tiene las bases) →
va en el **validador del orquestador**, que sí tiene ambas salidas. Emitir alerta
si `#profesionales(propuesta) ≠ #cargos(bases)`. *Extra opcional.*

### P3 · Re-empaquetar el plugin de Cowork
Los blindajes (`agent-evaluador`, `agent-propuesta-mapa`) están en `skill/` y
sincronizados a `~/.claude/skills`, pero **no** se re-empaquetó el plugin de
Cowork. Si se despliega allí, correr `build.ps1`. Ver [[cowork-plugin-y-frontmatter]].

### P4 · Los blindajes aplican a análisis NUEVOS
`agent-evaluador` (veredicto coherente) y `agent-propuesta-mapa`
(anti-contaminación) corrigen de cara al futuro. Los jobs **ya corridos** no se
re-evalúan salvo **re-run**. (El veredicto P1 de Vitarte se corrigió a mano en el
dato; el resto de jobs ya está limpio.)

## 🔵 Decisiones de alcance — requieren a Manuel

### P5 · Experiencia del postor (requisito 3.4) — ¿manual o automatizada?
Hoy el backend **NO computa** la experiencia del postor (`etapas_reales.py:447`);
es tarea del Comité/evaluador. La tabla del Excel ya lo dice sin jerga (`_sin_jerga`).
Decisión: dejarla **manual** (estado actual) **o** construir el cómputo real
(input fecha SEACE + conversión €→S/ SBS + filtro 20 años + % de participación de
consorcio). Lo segundo es **alcance nuevo no cotizado**. Ver
[[postor-experiencia-manual-no-backend]].

## ⚪ Backlog técnico (no urgente)

### P6 · Descarga diferida — seguimientos
La descarga de documentos InfoObras (~90% del tiempo, ~1 GB) ya se **desacopló del
camino crítico** (corre en background tras el pipeline; el veredicto/Excel quedan
en ~1 min). `Job.descargas_estado` (pendiente→en_progreso→listas|error) refleja el
avance. Quedan tres mejoras (no bloquean single-user):
- **`/zip` aún bloquea el request** si la descarga no terminó (es la red de
  seguridad: baja en vivo y luego arma). Lo normal es que el background ya terminó
  → es rápido. Fix de fondo: devolver **202 "en preparación"** si
  `descargas_estado != "listas"` y que el **panel haga polling** de ese campo
  (requiere cambio en `Panel-InfoObras`).
- **Race del backfill de métrica** (multi-usuario): si `/zip` y `/revision` del
  MISMO job corren a la vez, el backfill de `metrica` de InfoObras podría pisar un
  checkpoint del motor. Inofensivo single-user; el fix es un lock compartido
  motor↔API por job.
- **Orden de locks**: hoy `_descargas_locks` y `_zip_build_lock` NO se anidan (se
  libera uno antes de tomar el otro) → sin deadlock. Documentar el orden si se
  agregan más locks.
