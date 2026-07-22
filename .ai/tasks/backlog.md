# Backlog

## Técnico (listo para ejecutar)

- [ ] **Deploy del refactor** (paquete): merge `sonda/refactor-cui` → `demo`;
  rebuild backend en server 192.168.100.5; copiar base MEF (~26 MB) a
  `datos_pivote/referencia/mef/`; crontab `0 3 * * 0` para
  `actualizar_base_mef.py`; rebuild plugin de la skill (`build.ps1`) y
  entregarlo al cliente. **Todo junto** (ADR-007).
- [ ] Camino A: no descargar ni pintar secciones de obra (valorizaciones,
  cronograma) en expedientes; silenciar advertencias COBERTURA para expedientes.
- [ ] Re-revisar con el cliente los 2 casos de verdad auditada dudosa:
  2195439 (Tocache vs Loreto) y 2064566 (Cotabambas vs Antabamba).
- [ ] Unificar `backend/db/schema.sql` con el DDL real de `repositorio_pg.py`
  (o marcar schema.sql como documental).
- [ ] Tool MCP `buscar_cui` servida por el backend (pedido cliente 06-jul) +
  endpoint de descarga por 1 CUI reutilizando el ZIP (hacerlo job).

## Extras cotizados (esperan aprobación del cliente — ver roadmap)

- [ ] T-004 SEACE datos abiertos (CONOSCE/OCDS) · T-005 fechas ET + cronología
  · T-006 RENIPRESS · T-007 SUNAT habido.

## Ideas (sin compromiso, evidencia parcial)

- [ ] Modo "local primero" del resolver (medir recall con golden antes).
- [ ] Skill: imágenes a media resolución para el agente-mapa cuando Camino B
  sea inevitable (el Camino A/Tesseract ya funciona en la laptop).
- [ ] Paquetes B/C/D de progreso fino del panel (ETA, timeline, cancelar, SSE).
