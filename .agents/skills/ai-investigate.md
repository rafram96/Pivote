---
description: Investigar viabilidad con evidencia real (spikes desechables, fuentes citadas) y cerrar con veredicto y esfuerzo estimado
argument-hint: pregunta a investigar | IDEA-xxx graduada | INV-xxx para continuar
---

<!-- Generado por raf-ai desde templates/commands/. No editar aquí: se sobrescribe en cada init/upgrade. -->

# /ai-investigate — ¿se puede?

Entrada del usuario: $ARGUMENTS

Este comando produce **evidencia documentada, nunca producto**. Todo código que
escribas aquí es un spike desechable; la salida es un documento con veredicto.

## Contexto previo (leer antes de actuar)

1. `.ai/manifest.md` y `.ai/context/current_state.md`.
2. Si la entrada referencia una `IDEA-xxx`: lee ese documento completo — la
   investigación hereda su contexto y sus preguntas abiertas.
3. Si la entrada es un `INV-xxx` existente: lee el documento y continúa desde
   "qué falta por probar".
4. `.ai/research/` — por si algo ya se investigó antes (reutilizar > repetir).

## Pasos

### 1. Crear (o retomar) el documento

Crea con `raf-ai new investigation "<título>"` (si la carpeta `.ai/research/`
no existe aún, corre antes `raf-ai upgrade`). El archivo generado trae la
estructura completa; si venía de una idea, anota `idea_ref: "IDEA-xxx"` y
completa las fechas del frontmatter.

### 2. Descomponer la pregunta

Antes de investigar, escribe en `## Pregunta` las 2-5 sub-preguntas **falsables**
que responden la pregunta central. Ejemplo para "¿se puede scrapear el portal X?":
¿requiere autenticación?, ¿tiene captcha o anti-bot?, ¿qué dicen sus términos de
uso?, ¿existe una API o dataset oficial que lo haga innecesario?, ¿qué frecuencia
de acceso tolera?

### 3. Investigar con evidencia

Usa las herramientas disponibles: búsqueda y lectura web, documentación oficial,
y **spikes locales** (un fetch de prueba, leer `robots.txt`, inspeccionar una
respuesta HTTP, probar un endpoint). Reglas del método:

- **Cada hallazgo lleva su fuente**: URL, código de estado + fragmento de
  respuesta, cita textual del documento oficial, o el comando ejecutado y su
  salida. "Parece que tiene captcha" no vale; "el POST a /buscar devuelve 403
  con header cf-mitigated: challenge" sí.
- Distingue **hecho** (lo que probaste/leíste) de **suposición** (lo que
  infieres) — márcalo en el texto.
- Busca activamente la alternativa que haga innecesario el camino difícil
  (dataset abierto, API oficial, servicio existente) y regístrala en
  `## Alternativas` aunque contradiga la idea original.
- Respeta legalidad y términos de servicio: si un camino los viola, documéntalo
  como limitación — no lo "resuelvas" con evasión.
- Los spikes van en un directorio temporal o quedan transcritos en el documento;
  no se commitean como código del proyecto.

### 4. Cierre obligatorio con veredicto

Una investigación sin conclusión es un chat perdido. Completa:

- `## Recomendación`: veredicto (`viable` / `viable-con-limites` /
  `no-viable` / `hay-mejor-alternativa`) + el camino sugerido en 2-4 líneas.
- `## Esfuerzo estimado`: rango en horas o días con los supuestos que lo
  sostienen. (Es insumo directo para cotizar; el monto en dinero NO va aquí.)
- `## Qué necesitaría la spec`: las decisiones abiertas que `/ai-spec` deberá
  resolver si esto avanza.
- Frontmatter: `status: "concluded"`, `verdict` con el valor elegido, `updated`.

Si honestamente no se puede concluir aún, deja `status: "open"` con una sección
final "Qué falta por probar" — pero dilo explícitamente al usuario, con qué se
necesita para cerrar (acceso, tiempo, una prueba específica).

### 5. Si venía de una idea

Actualiza la `IDEA-xxx`: `graduated_to: "INV-NNN"` y una línea en su sparring
con el resultado.

## Cierre

1. `raf-ai index` y `raf-ai validate`; deben pasar (los warnings se reportan,
   los errores se corrigen).
2. Actualiza `.ai/handoffs/current.md`: estado y siguiente paso.
3. Resume al usuario: veredicto, las 2-3 evidencias decisivas, esfuerzo
   estimado, y si corresponde el siguiente paso (`/ai-spec INV-NNN` o cerrar aquí).
