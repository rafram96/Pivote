# ADR-008 · ALT-12 (firmante = representante legal) descartada como regla automática

- Fecha: 2026-06/07 (auditoría SUNAT en vivo) · Estado: vigente

## Contexto
El flujograma del cliente pide verificar que "el que firma el certificado es el
representante". Auditoría con datos reales: quien firma constancias de trabajo
casi nunca es el representante legal inscrito en SUNAT (gerentes de área, jefes
de RRHH, administradores) → la regla automática produce falsos positivos
masivos. El cliente la volvió a pedir en el spec V2 (2026-07-22).

## Decisión
NO se implementa como veredicto automático. El dato se muestra INFORMATIVO: el
panel exhibe el representante SUNAT junto al emisor del certificado (cruce
verde) para juicio del evaluador.

## Alternativas consideradas
- Regla dura (descartada: penalizaría certificados legítimos en masa).
- Lista blanca de cargos firmantes (inviable: no hay fuente estatal de poderes).

## Consecuencias
- Expectativa comercial a cerrar en reunión con la evidencia (documentado en
  plan-desarrollo-extras.html). Si el cliente insiste, requiere ADR nuevo con
  el diseño "informativo con alerta suave", nunca veredicto.
