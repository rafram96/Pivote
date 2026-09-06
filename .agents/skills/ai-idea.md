---
description: Capturar una idea cruda y hacerle sparring honesto para decidir si escala, incuba o muere
argument-hint: descripción de la idea | IDEA-xxx para retomar una existente
---

<!-- Generado por raf-ai desde templates/commands/. No editar aquí: se sobrescribe en cada init/upgrade. -->

# /ai-idea — capturar y madurar una idea

Entrada del usuario: $ARGUMENTS

Tu rol en este comando es de **sparring honesto, no de porrista**. Una idea
descartada a tiempo es un éxito del embudo. Está permitido y esperado
recomendar congelar o descartar.

## Contexto previo (leer antes de actuar)

1. `.ai/manifest.md` — de qué va este proyecto.
2. `.ai/context/vision.md` y `.ai/context/current_state.md` si existen.
3. `.ai/ideas/` — revisa los títulos existentes: si la idea ya existe o se
   solapa con otra, trabaja sobre ese documento y dilo (una idea = un documento).

## Caso A — la entrada es un ID (`IDEA-xxx`): sesión de incubación

1. Lee el documento completo, incluido todo el sparring acumulado.
2. Incorpora lo nuevo que trae el usuario (o pregúntale qué cambió desde la última vez).
3. Agrega una entrada nueva a `## Sparring` con la fecha de hoy: qué cambió,
   qué se respondió, qué sigue abierto.
4. Re-evalúa el veredicto con la información nueva y actualiza `status` y `updated`.

## Caso B — la entrada es una idea nueva: capturar + sparring

### 1. Capturar

Crea el documento con `raf-ai new idea "<título corto>"` (si la carpeta
`.ai/ideas/` no existe aún en este proyecto, corre antes `raf-ai upgrade`).
El archivo generado trae la estructura completa.

En `## La idea` transcribe la idea tal como llegó. No la mejores todavía: el
documento debe conservar el punto de partida real. Completa las fechas del
frontmatter si quedaron en placeholder.

### 2. Sparring (el corazón del comando)

Evalúa la idea contra las preguntas ancla y escribe tu análisis como entrada
fechada en `## Sparring`:

- ¿Qué problema resuelve y quién lo tiene HOY? ¿Hay evidencia de que duele, o
  es un problema imaginado?
- ¿Qué existe ya que lo resuelva total o parcialmente? (buscarlo, no suponerlo)
- ¿Cuál es el MVP más pequeño que probaría la hipótesis central?
- ¿Por qué ahora, y por qué el usuario es la persona indicada para hacerla?
- ¿Cuál es el riesgo que la mata? (técnico, de adopción, de tiempo, de costo)

Sé específico y directo: si la idea es débil, dilo y explica por qué. Si es
fuerte, di qué la haría fracasar de todos modos.

Cierra tu análisis preguntando al usuario **solo las 1-3 preguntas cuya
respuesta más cambiaría el veredicto** — no un interrogatorio completo.

### 3. Veredicto

Registra en `## Veredicto actual` una de estas salidas y actualiza `status`:

- **Graduar a `/ai-investigate`** — la idea vale la pena pero hay una incógnita
  técnica o de viabilidad que resolver primero. (status: `graduada`)
- **Graduar a `/ai-spec`** — vale la pena y es claramente viable; a especificar.
  (status: `graduada`)
- **Incubar** — promete pero le falta madurar; deja escritas las preguntas
  abiertas que la harían avanzar. (status: `incubando`)
- **Congelar** — sin caso de uso real hoy. No se trabaja. (status: `congelada`)
- **Descartar** — con el porqué, para no re-discutirla en tres meses.
  (status: `descartada`)

Al graduar, anota el ID destino en `graduated_to` cuando el documento siguiente
exista (p. ej. `INV-004`).

## Reglas

- Nada de montos, precios ni datos de cliente en `.ai/` — eso vive en el panel
  (datos.json). Si la idea nació de un pedido comercial, sugiere crear el
  ticket en el panel y anota su ID en `ticket_ref`.
- No prometas viabilidad técnica sin evidencia: si la incógnita es técnica, el
  camino es `/ai-investigate`, no el optimismo.
- No conviertas la idea en compromiso: este comando termina en un veredicto,
  nunca en código ni en tareas.

## Cierre

1. Ejecuta `raf-ai index` y `raf-ai validate`; deben pasar (los warnings se
   reportan, los errores se corrigen).
2. Resume al usuario en 3-5 líneas: veredicto, las razones de más peso, y el
   siguiente paso concreto si lo hay.
