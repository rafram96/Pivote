---
id: "ADR-015"
title: "Candados de abstención sin golden: referencia por auditoría y orden con la vía MEF"
status: "accepted"
date: "2026-09-13"
authors:
  - "Raf"
---

# ADR-015: Candados de abstención sin golden: referencia por auditoría y orden con la vía MEF

- Aceptado por el desarrollador el 2026-09-13.
- Supersede a **ADR-005**. Conserva sus candados; retira la golden como criterio
  de calibración y fija el orden con la vía MEF de ADR-010.
- Precisa: ADR-004 (orden de la rama de privadas) y ADR-013 (asimetría de la
  ubicación). No toca ADR-003.

## Contexto

ADR-005 (2026-07-20) introdujo los candados de abstención del resolver de CUI y
cerró con: «umbrales calibrados contra la golden — recalibrar SOLO con la
golden». Esa golden se perdió en julio y el 2026-09-12 el desarrollador decidió
que no se reconstruirá. Desde entonces cualquier cambio del resolver quedaba
bloqueado por un criterio que ya no puede cumplirse.

Mientras tanto, la auditoría visual de una propuesta real (Tacna, 62
experiencias, 4 lotes leídos contra la imagen del certificado, 2026-09-12)
midió lo que los candados producen hoy: 42 identificadas, 42 correctas, 0
falsas; 20 pendientes, de las cuales 9 tenían el candidato correcto en su
propia lista, 6 eran privadas sin marcar y 5 eran ambiguas de verdad. La traza
del resolver mostró la causa de los falsos negativos que no eran de desempate:
el candado §1 de ADR-005 («solo-MEF no gana sin corroboración dura») se ejecuta
antes que la vía MEF de ADR-010 y demota al candidato correcto cuando llegó por
la fusión con InfoObras registrando la obra por código pero no por nombre; la
vía MEF, que tiene candados propios y más estrictos, termina evaluando a un
sustituto y falla con un motivo que cita un CUI ajeno (casos 12:3 y 16:1).

## Alternativas consideradas

- **Reconstruir una golden** (277 casos) y mantener ADR-005 intacto. Descartada
  por el desarrollador: costo alto, corpus original perdido, y no mide lo que
  Manuel ve (una propuesta entera con sus certificados).
- **Sumar la coincidencia de provincia/distrito como corroboración dura del
  candado §1** (usar `_corroborado` de ADR-013). Resuelve los mismos casos,
  pero relaja la sensibilidad del candado para obras y rompe el caso Chinchinga,
  cuyo patrón (InfoObras solo trae ruido, el MEF aporta nombre y ubicación) es
  exactamente el que §1 debe seguir frenando. Descartada.
- **Ordenar las compuertas**: para expedientes, el candidato MEF que encabeza el
  ranking pasa primero por los candados de la vía MEF; si los supera, resuelve
  por vía MEF; si no, se demota como hoy. Elegida.

## Decisión

1. **Los candados de ADR-005 siguen vigentes tal cual** para su ámbito: (a) un
   candidato de origen solo-MEF no gana por puro nombre sin corroboración dura;
   (b) empate ≤ 4 puntos entre CUI distintos sin señal dura → revisión; (c) vetos
   de ubicación por contradicción positiva, nunca por ausencia; `ruc_match`
   exime. Nunca se relajan compuertas para «ganar» casos.

2. **Orden con la vía MEF (expedientes).** En un concurso de camino A (ADR-010),
   cuando el primer candidato del ranking es de origen MEF, se evalúa ANTES del
   candado §1 con los candados de la vía MEF: puntaje MEF de nombre ≥ 95, el
   certificado contiene ≥ 80 % de las palabras del nombre oficial, sin
   contradicción de ubicación, sin rubro ajeno y sin otra ficha que empate. Si
   los supera, resuelve por vía MEF; si no, se demota y sigue el flujo actual.
   Para obras (camino B) nada cambia.

3. **Sin golden: la referencia son dos instrumentos, ambos obligatorios antes de
   fusionar un cambio del resolver.**
   - **Auditoría por propuesta**: archivo privado, fuera del repo, con el
     resultado esperado por experiencia (RESUELTO con CUI / PRIVADA / PENDIENTE)
     producido por lectura del certificado real; lo lee
     `tests/test_aceptacion_auditoria.py` (se salta si no existe). Un caso que el
     auditor marcó con confianza media no fija un CUI: se espera PENDIENTE.
   - **Replay sin red** sobre todos los jobs locales
     (`scripts/replay_enriquecimiento.py`, con el snapshot corregido el
     2026-09-12): ninguna experiencia resuelta cambia de CUI; cada paso de
     revisión a resuelto se lista y se revisa a mano.
   Un cambio que mejore la auditoría pero mueva un CUI resuelto en el replay no
   se fusiona hasta explicarlo.

4. **Resuelto por etapa cuenta como resuelto.** Las vías CONTRATO y RESOLUCION
   (etapa de verificación con red) no son reproducibles offline; la aceptación
   lee su resultado persistido y no las cuenta como fallo del resolver.

5. **La ubicación sigue asimétrica** (ADR-013): contradice y veta; coincidir no
   corrobora por sí sola. Cambiarlo requiere un ADR nuevo con medición sobre
   auditorías de al menos dos propuestas.

6. **ADR-004 se precisa**: la rama «posible obra privada» solo corre cuando la
   resolución pública terminó sin candidato fiable. Un candidato que ya ganó un
   desempate no puede ser pisado por esa rama, y la comparación de entidad
   pública mira también la entidad de la ficha MEF del candidato. El umbral 90
   no baja.

## Consecuencias

- Beneficios: los cambios del resolver vuelven a ser posibles con un criterio
  medible que refleja lo que el cliente ve; los casos 12:3 y 16:1 de Tacna se
  resuelven sin tocar la sensibilidad del candado; el mensaje de revisión cita
  siempre un candidato real.
- Costos: cada propuesta auditada exige lectura de certificados (agentes con
  visión o humano) y mantener un archivo privado por propuesta; el replay tiene
  límites documentados (sin fechas de obra, sin vías con red) y no reproduce
  bit a bit una corrida en vivo.
- ADR-005 pasa a `superseded`. ADR-013 y ADR-004 conservan su estado con la
  precisión anotada aquí. Las pruebas que citaban la golden como respaldo
  siguen vigentes como regresión sintética; ya no son el criterio de
  calibración.
