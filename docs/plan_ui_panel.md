# Plan de mejoras de estilo y UX/UI — Panel-InfoObras

> Fecha: 2026-07-02 · Basado en auditoría completa del frontend
> (`Panel-InfoObras/frontend/src`) + sistema de diseño Stitch
> "Precision Engineering Framework" + regla de lenguaje sin jerga.
> Repo destino de los cambios: `Panel-InfoObras` (NO este repo).

## Diagnóstico en una línea

La base es sólida (tokens M3 claro/oscuro bien montados, flujo de revisión
"una tarjeta a la vez", responsive decente). Lo que falta es **consistencia**
(componentes y estilos duplicados, colores semánticos hardcodeados),
**orientación** (sin breadcrumbs, terminología no unificada) y **jerarquía**
(el detalle del análisis no dice de entrada "qué requiere tu acción ahora";
TabProfesionales es demasiado densa).

---

## Fase 1 — Quick wins de consistencia (≈1 día)

Bajo riesgo, alto orden. Solo refactor visual, sin tocar lógica.

1. **Borrar `ConfirmModal.tsx`** (duplicado en inglés, 0 imports) y quedarse
   con `ModalConfirmar.tsx` como único modal. Agregarle `aria-modal="true"`,
   `role="dialog"` y cierre con Escape.
2. **Unificar `Zona` (página /nuevo) + `PdfDropzone`** en un
   `components/Dropzone.tsx` genérico (props: `accept`, `validar`, textos).
   Mismos estados visuales: reposo / arrastrando / error / aceptado.
3. **Extraer tonos semánticos a un solo lugar** — `src/lib/ui.ts` con mapas
   tipo `TONO = { ok, error, revision, pendiente, neutro }` que devuelven
   clases completas (fondo/texto/ícono, light+dark). Hoy TabVeredictos lo hace
   bien (VEREDICTO_UI) pero TabFactores, TabAlertas, TabPasos y las páginas
   hardcodean `bg-green-100 dark:bg-green-950…` cada una a su manera.
4. **Componente `<Badge>`** (píldora semántica) que consuma esos tonos:
   CUMPLE / NO CUMPLE / Por confirmar / En proceso / Claude / manual.
   Reemplaza los ~10 badges ad-hoc de páginas y tabs.
5. **Escala tipográfica**: eliminar los `text-[0.6875rem]` / `text-[0.8125rem]`
   inline. Definir en `tailwind.config.ts` dos tamaños con nombre
   (`text-etiqueta`, `text-dato` o simplemente normalizar a `text-xs`/`text-sm`)
   y hacer el reemplazo global.

## Fase 2 — Orientación y lenguaje (≈0.5–1 día)

6. **Componente `<Breadcrumbs>`** y usarlo en las 4 vistas profundas:
   `Concursos → {concurso} → {postor} → Casos por confirmar`.
   Con `aria-current="page"` en el último. Reemplaza los "← Atrás" sueltos.
7. **Unificar terminología visible** (glosario sin jerga ya vigente):
   - "A revisión" / "Cola de revisión" / "revisión" → **"Por confirmar"**
     en todo lo visible (encabezado de tabla, métricas, pestaña, página).
   - Verificar que ningún texto visible diga job/pipeline/espejo/MCP/backend
     (la auditoría confirma que hoy la exposición es baja; dejarlo asegurado
     con un barrido final).
8. **Títulos de pestañas según el diseño Stitch**: orden
   `Resultados (Veredictos) · Profesionales · Factores · Por confirmar/Alertas · Pasos de la verificación · Descargas`
   — Resultados primero: es lo que el evaluador viene a ver.

## Fase 3 — Jerarquía del detalle de análisis (≈1–1.5 días)

La vista `jobs/[jobId]` es la más usada y hoy obliga a entrar pestaña por
pestaña para saber si hay algo pendiente.

9. **Banner "Requiere tu atención"** arriba de las pestañas cuando haya
   alertas críticas o casos por confirmar: texto en lenguaje de evaluador
   + CTA directo ("Resolver 3 casos por confirmar →", "Ver 2 alertas críticas →").
   Si no hay nada: banner verde discreto "Verificación completa, Excel listo"
   con botón de descarga.
10. **TabProfesionales — bajar densidad**:
    - Por defecto colapsado todo; chips de resumen por profesional
      (n experiencias · años efectivos · n observaciones).
    - Expandir automáticamente solo los que tienen observaciones.
    - Comparación emisor SUNAT vs representante de obra: apilada (una debajo
      de otra con ✓/✗ de coincidencia) en vez de lado a lado — elimina el
      escaneo horizontal y arregla el móvil.
    - Ocultar CUI original cuando coincide con el resuelto (mostrar solo
      cuando difieren, con etiqueta "corregido").
11. **Skeletons de carga**: el keyframe `shimmer` ya existe en globals.css y
    no se usa — componente `<Skeleton>` para tabla de concursos, métricas y
    detalle mientras cargan (hoy hay saltos de layout con el polling).

## Fase 4 — Pulido visual según el design system Stitch (≈1 día)

12. **Convención interactivo vs informativo** (la clave del sistema
    "Precision Engineering Framework"): todo lo clickeable en azul primario
    + ícono; todo lo informativo en neutro con badges píldora. Auditar
    tablas y tarjetas para que nada informativo "parezca botón" ni viceversa.
    Agregar la **leyenda** discreta (footer o tooltip "?" en el header).
13. **Radios y elevación consistentes**: 4–8px según el DS (el `rounded`
    default de Tailwind es 2px y convive con `rounded-lg`/`rounded-xl`
    mezclados). Fijar `borderRadius` en tailwind.config y normalizar.
14. **Focus visible**: `focus-visible:ring-2 ring-primary` en botones,
    inputs, dropzones y filas clickeables (hoy hay transición pero no ring).
15. **Estados vacíos con acción**: en vez de "Sin concursos" centrado, ícono
    + frase + botón ("Crea tu primer concurso" / "Los análisis llegan solos
    desde Claude cuando Manuel corre la evaluación").

## Fase 5 — Accesibilidad mínima (≈0.5 día, transversal)

16. `aria-label` en todos los botones solo-ícono (editar, borrar, expandir,
    tema, cerrar modal).
17. `scope="col"` en `<th>`, `aria-expanded` en filas/grupos expandibles
    (TabProfesionales, TabAlertas, TabPasos).
18. `aria-current` en Sidebar/BottomNav activos.

## Explícitamente FUERA de alcance (no vale la pena ahora)

- ❌ Storybook / catálogo de componentes — overhead para un panel de 1 cliente;
  la página `/design` con mockups estáticos se elimina o se deja como archivo
  histórico fuera del build.
- ❌ i18n — todo es español, único idioma.
- ❌ Rediseño estructural de rutas o del shell (sidebar/topnav funcionan).

## Orden y estimación

| Fase | Contenido | Días |
|---|---|---|
| 1 | Consistencia: modal único, dropzone único, tonos+Badge, tipografía | 1 |
| 2 | Breadcrumbs + terminología "Por confirmar" + orden de pestañas | 0.5–1 |
| 3 | Banner "requiere atención" + densidad Profesionales + skeletons | 1–1.5 |
| 4 | Interactivo/informativo + radios + focus + estados vacíos | 1 |
| 5 | Accesibilidad (transversal, puede ir dentro de 1–4) | 0.5 |
| **Total** | | **4–5 días** |

Las fases 1–2 son mecánicas y seguras; la 3 es la de mayor impacto percibido
por Manuel (es la pantalla de la demo); la 4 es la que hace que el panel se
vea "de producto". Si hay que recortar: hacer 1 → 3 → 2 y dejar 4–5.

**Opcional antes de codear la Fase 3**: generar en Stitch la pantalla
"vista de análisis con banner + pestañas reordenadas" (projectId
`8766173455847316667`, DS `9a08cbe7747c49b39366aa94b1edae26`) para validar
el layout con Manuel antes de portarlo a código.
