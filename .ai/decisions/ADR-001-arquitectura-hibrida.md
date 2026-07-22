# ADR-001 · Arquitectura híbrida: Claude extrae, backend on-prem verifica

- Fecha: 2026-05 (pivote) · Estado: vigente

## Contexto
El pipeline local original (PaddleOCR + qwen2.5:14b) tocó techo (~90-95% vs
goldens, calibración por formato, OCR no determinístico). El cliente ya usaba
Claude (Max 5x) con mejores extracciones, y exige que su servidor jamás llame
APIs cloud ni exponga sus PDFs.

## Decisión
La extracción corre como skill de Claude en el entorno del cliente (Cowork,
plugin) y produce un espejo JSON; el backend on-prem solo verifica y enriquece
(InfoObras/SUNAT/MEF), genera Excel/ZIP y sirve el panel. El backend NUNCA
llama APIs de IA.

## Alternativas consideradas
- Seguir con el motor OCR local (techo de calidad; quedó de fallback en stand-by).
- Backend llamando a la API de Claude (viola el constraint on-prem del cliente).

## Consecuencias
- La calidad de extracción depende de la suscripción del cliente (tokens = costo
  real → optimizaciones como ADR-007).
- Contrato de datos espejo (Pydantic↔zod) es la frontera crítica del sistema.
