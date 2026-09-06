---
name: arquitectura-rafvisual
description: >-
  Genera, actualiza y valida mapas de arquitectura para el workspace Architecture de RAF o para
  RafVisual. Úsala siempre que el usuario pida diagramar, visualizar, mapear, documentar o regenerar
  la arquitectura de un sistema, analizar un repositorio para obtener components/connections/dataFlow,
  producir architecture.json o crear el JSON que abre raf-IDE/RafVisual.
---

<!-- Generado por raf-ai desde templates/commands/. No editar aquí: se sobrescribe en cada init/upgrade. -->

# Arquitectura RAF / RafVisual

Convierte una descripción o un repositorio real en un mapa de capacidades de
runtime. El resultado debe ser útil para entender el sistema, no un inventario
de carpetas ni herramientas de build.

## Selecciona el destino

1. Si el cwd contiene `.ai/project.json`, usa **modo RAF** salvo que el usuario
   pida explícitamente un JSON raw para RafVisual.
2. Si el usuario menciona el modal Cargar JSON, el MCP de RafVisual o el repo
   `rafvisual`, usa **modo RafVisual raw**.
3. Si el destino sigue siendo ambiguo, pregunta una sola vez.

Lee [references/contrato.md](references/contrato.md) antes de generar. Usa
[assets/ejemplo.json](assets/ejemplo.json) como molde, no como contenido.

## Analiza antes de modelar

Para una descripción, identifica actores, límites, datos y 4–8 capacidades
principales. Pregunta solo si falta el propósito o los actores esenciales.

Para un repositorio:

1. Lee manifests y despliegue primero: `package.json`, lockfiles, Cargo/go/pom,
   Docker/CMake y configuración de runtime.
2. Recorre el árbol ignorando dependencias, VCS, caches y outputs.
3. Confirma cada componente con entrypoints, rutas, schemas, workers o clientes.
4. Modela capacidades que existen al ejecutar. Agrupa archivos acoplados.
5. No incluyas TODOs, endpoints ausentes ni servicios solo mencionados.

## Modo RAF

No edites `.ai/architecture/architecture.json` directamente. El envelope,
`projectId`, `revision` y `updatedAt` pertenecen a raf-ai.

1. Lee el estado y conserva la revisión:

   ```text
   raf-ai architecture get --json
   ```

2. Genera un archivo temporal que contenga solo `ArchitectureData`:
   `components`, `connectionLabels` y, si aportan valor, `scenarios`.
3. Valídalo contra el mismo schema que usa raf-IDE:

   ```text
   raf-ai architecture validate <draft.json>
   ```

4. Corrige todos los errores y guarda usando la revisión leída:

   ```text
   raf-ai architecture set <draft.json> --expected-revision <revision>
   ```

5. Si aparece `ARCHITECTURE_CONFLICT`, vuelve a leer y no sobrescribas cambios
   ajenos. Elimina el draft temporal solo después de guardar correctamente.

## Modo RafVisual raw

Entrega `arquitectura.json` con `components` y `connectionLabels` en la raíz.
Limita `techDetails.type` a `frontend`, `backend`, `database`, `auth`, `queue`,
`external`, `infra` o `ai`. Si está disponible, valida además con:

```text
node .claude/skills/arquitectura-rafvisual/scripts/validate.mjs arquitectura.json
```

El MCP de RafVisual es solo transporte: analiza y valida antes de llamar
`set_diagram`. No lo uses en modo RAF.

## Reglas de calidad

- IDs únicos en kebab-case y conexiones únicamente hacia IDs existentes.
- Declara la conexión desde quien inicia la dependencia o llamada.
- `connectionLabels` describe la data, no el protocolo.
- Cada componente incluye tecnologías reales, `dataFlow`, propósito y detalle
  técnico verificable cuando exista.
- Usa posiciones `{ "x": 0, "y": 0 }` si no hay layout previo; el canvas puede
  ordenarlas. Conserva posiciones al actualizar un mapa existente.
- Los scenarios solo referencian componentes y conexiones reales.
- No inventes evidencia. Si una relación es una inferencia importante, indícala
  al usuario en el resumen final.

## Entrega

Informa el destino, cantidad de componentes/conexiones, revisión guardada en
modo RAF y cualquier inferencia relevante. No declares éxito si falló la
validación o la persistencia.
