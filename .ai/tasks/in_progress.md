# En progreso

*(Actualizar al iniciar cualquier trabajo; mover a completed.md al cerrar.)*

- T-TAREA-ADR011 (Issue #26) CERRADA el 2026-07-25 — ver `completed.md`.
  PR #35 REVISADA Y MERGEADA a `demo` (2026-07-26, merge `506815d`); issues #26 y #30 cerradas.
- **Issue #31 — candado de correspondencia de cargo**: código MERGEADO a `demo`
  (2026-07-26) e issue cerrada. Queda **prueba viva** (correr un concurso
  end-to-end con la skill nueva — es lo único que ejercita
  `funciones_similares` de verdad) y **deploy**: la skill cambió, así que va
  con rebuild del plugin de Cowork. Ver
  `.ai/decisions/ADR-012-candado-cargo-nucleo.md`.
- **Panel: las sub-obras no se ven** → rafram96/panel-infoObras#1. El hueco es
  de dos lados: el backend no expone `sub_obras` en
  `GET /jobs/{id}/profesionales` (`api/app.py:674-681`, ~2 líneas) y el panel no
  lo lee. Hoy una experiencia multi-obra se renderiza SIN información de obra,
  en silencio.
- Ninguna otra tarea de código activa.
- Fase comercial: preparar/realizar la reunión de cotización con el cliente
  (materiales listos en `docs/nuevos_modulos/` v3 + interno en
  `docs/comercial/planeacion-v2-para-rafael.md`, gitignored).
