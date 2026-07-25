# ADR-006 · Dos caminos de verificación (expediente vs obra) + modo forzado

- Fecha: 2026-07-21 · Estado: **parcialmente supersedido por ADR-010**
  (los DOS CAMINOS siguen vigentes; el mecanismo de selección del camino pasa
  de detección-por-texto/env-var a parámetro declarado por la skill)

## Contexto
Concurso real de expedientes (San Isidro): la skill guardaba `proyecto` sin el
envoltorio "Elaboración del Expediente Técnico:" y el clasificador por nombre
enrutó 51/68 expedientes como obra (les bajó valorizaciones de la construcción
posterior en vez del contrato/resolución del MEF). El cliente confirmó que un
concurso completo es de tipo A (expedientes) o B (obras).

## Decisión
1. `es_expediente_exp(exp)` clasifica por TODA la evidencia (proyecto + objeto
   + cargo_ocupado), no solo el nombre.
2. Modo por corrida `PIVOTE_FORZAR_EXPEDIENTES=1` (camino A): toda experiencia
   se trata como expediente; sin clamp por valorizaciones.
3. El prompt de la skill conserva el envoltorio del desempeño en `proyecto`
   (el resolver ya se lo quita para buscar con `_sin_prefijo`).

## Alternativas consideradas
- Dos skills hermanas A/B (propuesta del cliente): mismo backend; la decisión
  1-skill-parametrizada vs 2-skills sigue ABIERTA (comercial, no técnica).
- Clasificar por el tipo del concurso desde las bases (variante del modo; el
  parámetro puede viajar en el espejo en el futuro).

## Consecuencias
- Pendiente de pulir: en camino A aún se descargan/pintan secciones de obra
  (valorizaciones) y se emiten advertencias COBERTURA — ruido, no veredicto.
- Corridas históricas extraídas con el prompt viejo carecen del envoltorio: el
  modo forzado es la vía de reparación.
