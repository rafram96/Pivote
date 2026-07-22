# ADR-007 · La skill NO resuelve CUIs; solo verifica los citados

- Fecha: 2026-07-21 · Estado: vigente (requiere backend con base MEF desplegado)

## Contexto
Logs reales del cliente: una corrida quemó ~3M de tokens y la mayor parte era
el Paso 4.5 de la skill — resolver 60 CUIs null sondeando MEF/InfoObras por
curl con protocolo de evidencia + 5 subagentes. Es el mismo trabajo que el
backend hace gratis y mejor (base local + candados; en la prueba de 105
experiencias, 9 de los 11 CUIs ganados por el resolver nuevo eran expedientes).

## Decisión
El Paso 4.5 queda acotado a verificar SOLO los CUIs **citados** en los
certificados (pocos curl: SNIP viejo → CUI canónico, reformulaciones). Los
`cui: null` viajan limpios al backend. "Cero búsquedas por nombre para
resolver nulls" es regla explícita del SKILL.md.

## Alternativas consideradas
- Tool MCP `buscar_cui` servida por el backend para la skill (pedido previo del
  cliente; sigue disponible como mejora — costo ~0 tokens por consulta).
- Mantener la resolución en la skill (insostenible en tokens y peor en calidad).

## Consecuencias
- La skill empaquetada (plugin/) debe REBUILDEARSE y re-entregarse; y el
  backend nuevo debe estar desplegado, o los nulls de expedientes se resuelven
  con la calidad vieja.
