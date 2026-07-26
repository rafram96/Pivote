# En progreso

*(Actualizar al iniciar cualquier trabajo; mover a completed.md al cerrar.)*

- **T-TAREA-ADR011 (Issue #26) — partida en 3 PRs.** Rama
  `rafram96/issue-26-t-multi-001` (sobre `demo`).
  - **PR-1 · skill + fixture — HECHO (2026-07-25).** El prompt ya desglosa el
    nombre compuesto de un paquete SIN CUI (antes el disparador exigía que cada
    sub-obra citara código, así que el caso HV ni llegaba al backend); fixture
    HV "Paquete 6" congelado en `backend/tests/test_etapas_reales.py`, validado
    por los DOS validadores del contrato (Pydantic + zod).
  - **PR-2 · resolución por sub-obra** — el delta real del ADR, en
    `cui.py:resolver_obras`. Decisiones a firmar antes de codear: (a) escalera
    CUI→nombre (un CUI citado que no existe NO debe caer a búsqueda por nombre:
    rompería `test_resolver_obras_multi_cui`, caso Talara); (b) `_exp_derivada`
    hereda entidad/fechas pero NO `ubicacion`, y hay que **neutralizar el veto
    geo que entra por `entidad_contratante`** (`ubigeo_cert`, `_muni_contradice`);
    (c) mapeo de estados ADITIVO (+`revision`, +`privada`) — los consumidores
    son solo `_EST_SUBOBRA` y 4 comparaciones `== "resuelto"`.
  - **PR-3 · candado multi-rubro (P1)** — rubro del NOMBRE del sub-proyecto,
    umbral ≥2 rubros, efecto = observación ADVERTENCIA que NO bloquea días.
- Ninguna otra tarea de código activa (2026-07-22).
- Fase comercial: preparar/realizar la reunión de cotización con el cliente
  (materiales listos en `docs/nuevos_modulos/` v3 + interno en
  `docs/comercial/planeacion-v2-para-rafael.md`, gitignored).
