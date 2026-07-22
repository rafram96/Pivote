# ADR-002 · Base local del Banco de Inversiones como fuente primaria de candidatos

- Fecha: 2026-07-20 · Estado: vigente

## Contexto
El buscador web del MEF exige coincidencia casi exacta (falla con nombres
truncados — caso Chinchinga), tiene captcha en la Consulta Pública y el WS del
SSI es intermitente. Validación empírica: los 3 CSV de Datos Abiertos
(activas+cerradas+desactivadas, 452,793 CUIs) cubren 191/194 CUIs de la
auditoría real y toda la ventana temporal 2001-2026.

## Decisión
ETL semanal (`actualizar_base_mef.py`) → archivo compactado (~26 MB) → índice
en memoria (`base_mef.py`) como **generador de candidatos** (0.2 s/consulta,
sin red). Sin Postgres: el backend debe funcionar sin PG. Sin base → degradación
a InfoObras-solo con aviso.

## Alternativas consideradas
- Seguir con búsquedas web en vivo (frágil, lento, incompleto).
- Tabla en Postgres con pg_trgm (PG es opcional en el stack; puede reevaluarse).
- Resolver en la skill con búsquedas web (ADR-007 lo prohíbe: costo en tokens).

## Consecuencias
- ~370 MB de RAM y ~60 s de carga perezosa por proceso.
- El "Detalle de inversiones" solo trae ACTIVAS: unir los 3 CSV es obligatorio.
- Ojo: ~41k filas viejas son SNIP-only (CODIGO_UNICO vacío) — indexar por SNIP.
