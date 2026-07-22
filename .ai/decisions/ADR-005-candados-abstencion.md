# ADR-005 · Candados de abstención sobre el resolver (F7/F8)

- Fecha: 2026-07-20/21 · Estado: vigente

## Contexto
La primera integración de la base MEF EMPEORÓ el sistema (26 mal-resueltos vs
16 del viejo): más candidatos homónimos de nombre oficial limpio + compuertas
calibradas para el pool chico de InfoObras = sobre-compromiso. Además el fuzzy
por nombre tiene techo (~84% de precisión incluso a score 100: el Estado
registra proyectos distintos con nombres idénticos).

## Decisión
Candados de abstención (nunca relajar compuertas para "ganar" casos):
1. Candidato origen=solo-MEF no puede ganar sin corroboración dura
   (ruc_match | N° de institución | entidad ≥90) — se demota visible.
2. Empate ≤4 pts entre CUIs distintos sin señal dura separadora → revisión.
3. Vetos de ubicación (F8): provincia contradictoria declarada en ambos lados =
   veto; solo distrito = −25; entidad municipal distinta = veto; gemelo VETADO
   por ubicación a ≤4 pts del ganador = revisión (el veto pudo apartar al
   correcto). Exención total por ruc_match. El departamento NO desempata
   homónimos (viven en el mismo).

## Alternativas consideradas
- Subir umbrales de score (no discrimina homónimos: fallan con score 100).
- Guard de empate "ingenuo" sin señales (habría costado ~14 correctos — medido).

## Consecuencias
- Golden final: 10 mal-resueltos / cero regresiones (viejo: 16).
- Costo aceptado: ~6 correctos pasaron a revisión con candidatos visibles.
- Umbrales calibrados contra la golden — recalibrar SOLO con la golden.
