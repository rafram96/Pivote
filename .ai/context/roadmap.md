# Roadmap

## Corto plazo (paquete de cierre + extras aprobados)

1. **Deploy del refactor**: merge `sonda/refactor-cui` → `demo` → rebuild
   backend en el server + base MEF + crontab; rebuild del plugin de la skill.
2. **Pulido camino A**: no descargar/pintar secciones de obra en expedientes;
   silenciar advertencias COBERTURA para expedientes.
3. **Hito final del contrato vigente**: validación en server, pruebas con
   propuestas reales, manual de usuario, capacitación 2 h (ver contrato).

## Extras cotizados (pendientes de aprobación del cliente)

- **T-004** — SEACE bases + contrato por datos abiertos (CONOSCE/OCDS) +
  candado de confirmación · S/2,400 · sonda GO hecha.
- **T-005** — Reglas de fechas del ET (inicio ≥ firma contrato · término ≤
  resolución) + hoja "Cronología de expedientes" · S/1,200.
- **T-006** — RENIPRESS establecimientos de salud · S/800 · sonda GO hecha.
- **T-007** — SUNAT condición HABIDO/ACTIVO · bolsa 8 h.
- Decisión pendiente del cliente: 2 skills hermanas (A/B) vs 1 skill que
  declara el tipo de concurso (el backend ya soporta ambos con el modo).

## Ideas con evidencia, sin compromiso

- Modo "local primero" del resolver (hoy fusión siempre): recortaría ~80% de
  llamadas web; medir costo en recall con la golden antes.
- pg_trgm / tabla de referencia MEF en Postgres (hoy índice en memoria).
- Paquete B/C/D de progreso fino del panel (ETA, timeline, cancelar, SSE).
