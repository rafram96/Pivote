# Handoff — punto de continuación

> Actualizado: **2026-07-23**. Si eres un agente nuevo: lee esto completo,
> luego `context/current_state.md` y los ADRs. No necesitas ninguna
> conversación previa.

## Nota de mantenimiento (2026-07-23) — el checklist de deploy RECAYÓ una vez

La auditoría de migración de la base `.ai` (dos niveles) encontró que
`context/roadmap.md` y `context/current_state.md` volvían a resumir el
checklist de deploy — el mismo patrón que ADR-S002 ya había corregido — y
los resúmenes eran peligrosos: omitían el merge del Panel y la regla de
orden de ADR-007 (plugin SOLO después del backend nuevo). Fase 1 de la
corrección ejecutada: ambos quedaron reducidos a puntero a
`InfoObras/.ai/tasks/active.md` (fuente única; verificado que ahí la regla
de orden está literal y el paso del Panel existe). Si ves el checklist
copiado en cualquier otro archivo, es una regresión: bórralo y deja puntero.

Más tarde el mismo día: **merge fast-forward `sonda/refactor-cui` → `demo`**
(`c31f71a`, solo local — push pendiente de confirmación del desarrollador;
la sonda no recibe más commits) y **Fase 2 de la corrección cerrada** sobre
`demo` (commits `c7045a7…`): coexistencia overview↔topology declarada, lista
T-00x consolidada en `vision.md` (raíz), tareas reubicadas por nivel,
ADR-S004 en la raíz, conteo de la golden con fuente única en
`architecture/backend.md`.

## ¿Qué se estaba haciendo?

Semana 20-22 jul: **refactor completo del resolver de CUI** (rama
`sonda/refactor-cui`, 13 commits) — base local MEF, público-primero, camino
expedientes/obra, candados de abstención — validado con una auditoría golden de
277 casos (errores silenciosos 16→10, cero regresiones) y corridas reales.
Además: optimización de la skill (Paso 4.5), rescate del análisis San Isidro, y
actualización del paquete comercial de extras (T-003…T-008).

## ¿Qué falta? (en orden recomendado)

1. **Deploy como paquete** (cross-repo: backend + panel + plugin + server) —
   el checklist canónico vive en **`InfoObras/.ai/tasks/active.md`** (nivel
   sistema); aquí no se copia. Regla clave: NO entregar el plugin sin el
   backend nuevo (ADR-007).
2. Pulido camino A (filtro de secciones de obra en descargas/Excel).
3. Reunión de cotización (materiales: `docs/nuevos_modulos/*.html` v3).
4. Resto: `tasks/backlog.md`.

## Archivos clave

- Resolver: `backend/resolucion/cui.py` (+ `base_mef.py`, `texto.py`).
- Orquestación: `backend/orquestador/etapas_reales.py` (caller del resolver,
  camino A/B, clamps) y `motor.py`.
- Validación: `backend/scripts/golden_cui.py` + baselines en
  `backend/datos_pivote/golden_cui_*.json` (gitignored pero presentes local).
- Skill: `skill/SKILL.md` (Paso 4.5) y `skill/prompts/agent-propuesta-profesional.md`.
- Jobs de referencia local: `b4f385c31811` (San Isidro camino A, entregado),
  `c9c769976750` (replay BNP con `revision_manual.md`).

## Riesgos vivos

- Server en producción corre el código VIEJO hasta el deploy.
- Los baselines/caches de la golden viven solo en esta laptop (datos_pivote
  gitignored) — no borrarlos; sin ellos la re-validación exige corrida en vivo
  (~1.5 h contra InfoObras).
- Límite de gasto mensual de la cuenta Claude alcanzado (21-jul): subagentes
  pueden morir a mitad; preferir trabajo directo o esperar el ciclo.
- 2 verdades de auditoría dudosas (ver `tasks/backlog.md`).

## Regla de oro antes de tocar el resolver

Cualquier cambio se valida así, en este orden:
`pytest backend/tests -q` (offline) → `golden_cui.py --con-base --solo-cache`
→ comparar contra `golden_cui_baseline.json`. Criterio: mal-resueltos nunca
suben, cero correcto→incorrecto. Nunca relajar compuertas para "ganar" casos
(ADR-005).
