---
description: Especificar QUÉ se construye y POR QUÉ — sin tecnología, con clarificaciones marcadas y auto-crítica antes de reportar
argument-hint: descripción de la feature | INV-xxx | IDEA-xxx graduada
---

<!-- Generado por raf-ai desde templates/commands/. No editar aquí: se sobrescribe en cada init/upgrade. -->

# /ai-spec — ¿qué exactamente?

Entrada del usuario: $ARGUMENTS

La spec define **QUÉ y POR QUÉ, nunca CÓMO**. Si escribiste el nombre de un
framework, una base de datos o un lenguaje, te equivocaste de documento — eso
va en el Plan (`/ai-plan`).

## Contexto previo (leer antes de actuar)

1. `.ai/manifest.md`, `.ai/context/vision.md`, `.ai/context/current_state.md`.
2. Si la entrada referencia `INV-xxx`: lee la investigación completa — en
   especial "Qué necesitaría la spec" y las limitaciones halladas. Anota el ID
   en `research_ref`.
3. Si referencia `IDEA-xxx`: lee la idea y su sparring; si además tiene
   `graduated_to` apuntando a una INV, lee ambas.
4. `.ai/specs/` — para no duplicar una spec existente.

## Pasos

### 1. Crear el documento

Crea con `raf-ai new spec "<título>"` (si la carpeta `.ai/specs/` no existe
aún, corre antes `raf-ai upgrade`). El archivo generado trae la estructura
completa; completa las fechas del frontmatter y las referencias
(`research_ref`, `ticket_ref`) que apliquen.

### 2. Escribir la especificación

- **Historias de usuario**: cada una con prioridad (P1/P2/P3), narrativa breve
  (quién, qué, para qué), criterios de aceptación en formato
  `Dado / Cuando / Entonces`, y una línea de **prueba independiente**: cómo se
  verificaría esta historia por sí sola. La P1 debe funcionar como MVP: valor
  entregable aunque no exista nada más.
- **Casos borde**: entradas vacías, errores externos, límites, concurrencia,
  datos malformados — qué debe pasar en cada uno.
- **Requisitos funcionales**: numerados `FR-01, FR-02…`, cada uno **verificable**
  (se puede demostrar que se cumple o no). Nada de "el sistema debe ser rápido";
  sí "la búsqueda responde en menos de 2 segundos con 10.000 registros".
- **Criterios de éxito**: medibles y agnósticos de tecnología — qué observaría
  el usuario/negocio para declarar esto un éxito.
- **Supuestos**: lo que asumes como razonable sin preguntarlo (alcance, datos
  disponibles, usuarios). Explícitos para que se puedan refutar.
- **Fuera de alcance**: lo que deliberadamente NO entra en esta spec.

### 3. Marcar lo que no se puede decidir

Cuando encuentres una decisión **crítica sin interpretación obvia**, tienes
prohibido rellenarla con una suposición. Márcala inline:

```
[NEEDS CLARIFICATION: ¿la búsqueda debe incluir registros históricos o solo activos?]
```

- Máximo **3** marcadores — elige las que de verdad cambian el producto.
- Las decisiones menores con un default razonable van a `## Supuestos`, no a
  marcadores.

### 4. Auto-crítica (antes de reportar)

Evalúa tu propia spec contra este checklist y corrige lo que falle. Itera hasta
3 veces:

- ¿Cada FR es verificable tal como está escrito?
- ¿Los criterios de éxito son medibles sin nombrar tecnología?
- ¿Cada historia tiene prueba independiente y la P1 funciona como MVP?
- ¿Los casos borde cubren al menos: error externo, entrada vacía y límite?
- ¿Se coló algún detalle de implementación? (framework, DB, librería, API interna)
- ¿`## Fuera de alcance` existe y no está vacío?

### 5. Actualizar referencias

Si venía de una IDEA: `graduated_to: "SPC-NNN"` en la idea. Si venía de una
INV: `research_ref: "INV-xxx"` en la spec.

## Cierre

1. `raf-ai index` y `raf-ai validate`; deben pasar (los warnings se reportan, los errores se corrigen).
2. Actualiza `.ai/handoffs/current.md`: estado y siguiente paso.
3. Reporta al usuario: resumen de la spec en 3-5 líneas y, si quedaron
   marcadores, preséntalos en una tabla con opciones concretas por cada uno y
   recomienda correr `/ai-clarify SPC-NNN`. Si no quedó ninguno, recomienda
   `/ai-plan SPC-NNN`.
