# Roadmap

## Corto plazo (paquete de cierre + extras aprobados)

1. **Deploy del refactor** — checklist de deploy: ver
   `InfoObras/.ai/tasks/active.md` (fuente única).
2. **Pulido camino A**: no descargar/pintar secciones de obra en expedientes;
   silenciar advertencias COBERTURA para expedientes.
3. **Hito final del contrato vigente**: validación en server, pruebas con
   propuestas reales, manual de usuario, capacitación 2 h (ver contrato).

## Extras cotizados (pendientes de aprobación del cliente)

- Lista canónica T-00x con estado comercial: `InfoObras/.ai/context/vision.md`
  (fuente única, nivel sistema). Precios y estrategia: `docs/comercial/`
  (gitignored a propósito).
- Decisión pendiente del cliente: 2 skills hermanas (A/B) vs 1 skill que
  declara el tipo de concurso (el backend ya soporta ambos con el modo).

## Ideas con evidencia, sin compromiso

- Modo "local primero" del resolver (hoy fusión siempre): recortaría ~80% de
  llamadas web; medir costo en recall con la golden antes.
- pg_trgm / tabla de referencia MEF en Postgres (hoy índice en memoria).
- Paquete B/C/D de progreso fino del panel (ETA, timeline, cancelar, SSE).
