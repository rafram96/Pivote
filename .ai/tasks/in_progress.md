# En progreso

*(Actualizar al iniciar cualquier trabajo; mover a completed.md al cerrar.)*

- **T-TAREA-ADR011 (Issue #26) — partida en 3 PRs.** Rama
  `rafram96/issue-26-t-multi-001` (sobre `demo`).
  - **PR-1 · skill + fixture — HECHO (2026-07-25).** El prompt ya desglosa el
    nombre compuesto de un paquete SIN CUI (antes el disparador exigía que cada
    sub-obra citara código, así que el caso HV ni llegaba al backend); fixture
    HV "Paquete 6" congelado en `backend/tests/test_etapas_reales.py`, validado
    por los DOS validadores del contrato (Pydantic + zod).
  - **PR-2 · resolución por sub-obra — HECHO (2026-07-25).** Las tres decisiones
    quedaron firmadas en código: (a) **escalera** — con CUI citado se resuelve
    por código y si no existe se queda en `no_encontrado`, SIN caer a nombre
    (adivinar sobre evidencia que ya contradice era el falso positivo del ADR;
    guardado por test propio, caso Talara); sin CUI va `resolver()` completo.
    (b) **`_exp_derivada`** hereda entidad/emisor/RUC/fechas, NO `ubicacion`, y
    marca `_solo_geo_propia` para apagar las DOS puertas por las que la geografía
    de la madre entraba igual (`ubigeo_cert` lee `entidad_contratante`;
    `_muni_contradice` la lee sola) — el nombre de la sub-obra es su única
    autoridad geográfica. (c) **mapeo ADITIVO** (+`revision`, +`privada`, +`via`
    por sub-obra) — los 4 estados viejos siguen significando lo mismo.
    Golden: 277 casos, **cero drift** (matriz diagonal; el cambio es inerte para
    experiencias normales porque el flag solo existe en la exp derivada).
  - **PR-3 · candado multi-rubro (P1)** — rubro del NOMBRE del sub-proyecto,
    umbral ≥2 rubros, efecto = observación ADVERTENCIA que NO bloquea días.
- Ninguna otra tarea de código activa (2026-07-22).
- Fase comercial: preparar/realizar la reunión de cotización con el cliente
  (materiales listos en `docs/nuevos_modulos/` v3 + interno en
  `docs/comercial/planeacion-v2-para-rafael.md`, gitignored).
