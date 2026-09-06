<!-- Generado por raf-ai desde templates/commands/. No editar aquí: se sobrescribe en cada init/upgrade. -->

# Contrato canónico de arquitectura RAF

La autoridad ejecutable es `raf-ai/core`; esta referencia guía la generación.

## ArchitectureData

```ts
interface ArchitectureData {
  components: ArchitectureComponent[]
  connectionLabels: Record<string, string>
  scenarios?: ArchitectureScenario[]
}
```

Cada componente requiere:

- `id`: string único; usa kebab-case.
- `title`, `icon`, `color`, `borderColor`.
- `technologies`: objeto string → string.
- `connections`: IDs destino existentes, sin self-loop ni duplicados.
- `position`: `{ x: number, y: number }` finito.
- `dataFlow`: `{ sends: string[], receives: string[] }`.
- opcionales: `purpose`, `techDetails`, `annotations`, `flow`.

Tipos RAF para `techDetails.type`:

```text
frontend backend database auth queue external infra ai pipeline engine module
```

RafVisual raw solo comprende los ocho primeros; mapea `pipeline`, `engine` y
`module` al tipo compatible que describa mejor su implementación.

## Conexiones y etiquetas

Si `web.connections` contiene `api`, añade normalmente:

```json
{ "web-api": "Consultas del usuario" }
```

La etiqueta nombra el payload o intercambio: `Órdenes y resultados`, `Eventos
de pago`, `Token de sesión`. No uses `HTTP`, `SQL`, `JWT` o `WebSocket`; esas
tecnologías pertenecen a `technologies`.

## Scenarios

Cada scenario tiene `id`, `name`, `steps` y descripción opcional. Un step tiene
`title` y puede incluir `narration`, `focus`, `edges` y `duration`. Todo ID de
focus debe existir y cada edge debe corresponder a una conexión real.

## Envelope persistido por RAF

El agente no lo construye ni modifica manualmente:

```json
{
  "schemaVersion": 1,
  "projectId": "proyecto-raf",
  "revision": 3,
  "updatedAt": "...",
  "architecture": { "components": [], "connectionLabels": {} }
}
```

`raf-ai architecture set` crea el envelope, incrementa revision y escribe de
forma atómica después de validar el schema y la revisión esperada.

## Límites prácticos

El schema protege tamaños máximos amplios para no perder mapas existentes. Para
un diagrama legible genera normalmente 4–8 componentes, 2–4 tecnologías y 2–4
ítems de flujo por componente. Supera ocho nodos solo cuando fusionarlos ocultaría
límites de runtime relevantes.
