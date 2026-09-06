---
description: Resolver las ambigüedades de una spec preguntando al usuario con opciones concretas — nunca inventando respuestas
argument-hint: SPC-xxx
---

<!-- Generado por raf-ai desde templates/commands/. No editar aquí: se sobrescribe en cada init/upgrade. -->

# /ai-clarify — resolver ambigüedades

Entrada del usuario: $ARGUMENTS (debe ser un ID `SPC-xxx`; si no lo es, pide el ID y detente)

Tu trabajo aquí es **preguntar bien, no adivinar**. La respuesta a cada
ambigüedad la tiene el usuario; tu aporte es presentar opciones claras con sus
implicaciones.

## Pasos

### 1. Escanear la spec

Lee `.ai/specs/SPC-xxx_*.md` completa y junta:

1. Todos los marcadores `[NEEDS CLARIFICATION: …]`.
2. Ambigüedades no marcadas de alto impacto: adjetivos sin métrica ("rápido",
   "seguro", "fácil", "muchos"), sujetos indefinidos ("el sistema notificará" —
   ¿a quién, por qué canal?), cuantificadores vagos. Selecciona como máximo
   **2** de estas — las que más cambien el producto — y trátalas como
   clarificaciones adicionales.

Si no hay nada que clarificar: marca `status: "clarified"`, actualiza
`updated`, dilo al usuario y recomienda `/ai-plan SPC-xxx`. Fin.

### 2. Preguntar de a una

Para cada clarificación, **una a la vez** (no un cuestionario en bloque):

- Presenta la pregunta con contexto: qué parte de la spec afecta y por qué importa.
- Ofrece 2-4 opciones concretas en tabla, cada una con su implicación
  (alcance, esfuerzo relativo, riesgo). El usuario siempre puede responder
  otra cosa distinta a las opciones.

| Opción | Qué significa | Implicación |
|---|---|---|
| A | … | … |
| B | … | … |

- Espera la respuesta antes de pasar a la siguiente pregunta.

### 3. Integrar cada respuesta

No acumules las respuestas al final del documento: **reescribe la sección
afectada** para que la decisión quede incorporada en el texto y el marcador
desaparezca. Si la decisión aporta contexto útil para el futuro, agrega una
línea en `## Supuestos` con formato "Decidido (fecha): …".

Si el usuario no sabe la respuesta:

- Si es una incógnita de viabilidad → propón derivarla a `/ai-investigate` y
  deja el marcador con una nota "(pendiente de INV-xxx)".
- Si es una preferencia sin información → conviértela en supuesto explícito
  marcado como riesgo en `## Supuestos`, y quita el marcador.

### 4. Cerrar

Cuando queden **cero** marcadores: `status: "clarified"` y `updated` al día de hoy.

## Reglas

- Prohibido resolver un marcador con tu propia suposición, por razonable que
  parezca — para eso existen los supuestos explícitos aceptados por el usuario.
- No agregues alcance nuevo durante la clarificación: si el usuario pide algo
  nuevo en sus respuestas, anótalo en `## Fuera de alcance` como candidato a
  otra spec, y dilo.

## Cierre

1. `raf-ai validate`; debe pasar (los warnings se reportan, los errores se corrigen).
2. Actualiza `.ai/handoffs/current.md` si el estado de la spec cambió.
3. Resume: qué se decidió (lista corta), estado final de la spec, y el
   siguiente paso (`/ai-plan SPC-xxx` si quedó clarificada).
