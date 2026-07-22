# ADR-004 · Público-primero: la clasificación de privadas va AL FINAL

- Fecha: 2026-07-20 (directiva del cliente) · Estado: vigente

## Contexto
El gate de privadas era léxico ("privada/particular/I.E.P.") y cortaba ANTES de
buscar. Medido en 1042 experiencias reales: 55.7% sin entidad contratante,
7.5% ambiguas — públicas no reconocibles por regex (IMARPE, INEN, SENCICO…) y
privadas reales sin la palabra "privada" (Orden de San Agustín, S.A.C., ONGs).

## Decisión
Se agota SIEMPRE toda la resolución pública; solo la rama final "sin candidato
fiable" clasifica privada: (1) léxico → `na/PRIVADA`; (2) entidad no vacía y NO
reconocida en el catálogo de 11,004 entidades públicas (de los CSV MEF, umbral
fuzzy ≥90 + siglas exactas) → revisión con `posible_privada`. Candado extra: la
vía PROBABLE exige entidad pública reconocida o vacía.

## Alternativas consideradas
- Engordar el regex (nunca cubre IMARPE/ONGs; mantenimiento infinito).
- SUNAT por RUC del contratante (determinante pero requiere el RUC — queda como
  extensión señalizada, no implementada).

## Consecuencias
- Umbral 90 es DURO: "Orden de San Agustín" matchea 82 con la Municipalidad de
  San Agustín — bajar el umbral reintroduce falsos públicos.
- Una privada ahora sí genera búsquedas web antes de clasificarse (costo
  aceptado a cambio de no perder públicas exóticas).
