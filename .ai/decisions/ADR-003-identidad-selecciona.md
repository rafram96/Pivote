# ADR-003 · La identidad selecciona; las valorizaciones solo dictan veredicto

- Fecha: 2026-07-20 (decisión del cliente) · Estado: vigente

## Contexto
El resolver reordenaba candidatos por solape entre el periodo DECLARADO en el
certificado y las valorizaciones de cada obra. Circularidad: el periodo es el
dato bajo auditoría — un periodo falso podía hacer ganar a una obra homónima
conveniente (lavado silencioso) e incluso desplazar candidatos con ruc_match.

## Decisión
El solape se eliminó POR COMPLETO de la selección (ni como desempate). El
ranking es 100% identidad; las valorizaciones actúan solo en el veredicto
(cobertura/clamp), donde recuperan su valor probatorio.

## Alternativas consideradas
- Solape como desempate solo entre identidades equivalentes (diseño intermedio;
  el cliente lo descartó por simplicidad y pureza del principio).
- Mantener el tier (inaceptable: lava mentiras).

## Consecuencias
- El caso "homónimo viejo gana por nombre" (obra 4653) cae a revisión por
  cobertura — ruido seguro, nunca falso CUMPLE.
- Menos llamadas web en la selección (no se consultan rangos de valorizaciones).
- `_elegir_obra` SÍ conserva fechas: elige entre obras del MISMO CUI (la
  identidad ya está fijada por el código).
