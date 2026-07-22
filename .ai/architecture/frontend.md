# Frontend (panel web)

El panel vive en un **repo hermano**: `Panel-InfoObras` (Next.js completo), NO en
este repositorio. Se conecta al backend vía `frontend/.env.local` →
`PIVOTE_API=http://127.0.0.1:8001` (usar 127.0.0.1, no localhost).

## Qué muestra

- Lista de concursos y jobs; detalle por análisis con progreso por etapas
  (StepperEtapas, endpoint `/progreso`).
- Cola **«Por confirmar»** (ItemRevision): CUIs sin resolver con candidatos
  clicables — terminología sin jerga para evaluadores NO técnicos.
- Descargas: Excel final y ZIP de sustento (el ZIP se construye al pedirlo).
- Representante de obra junto al emisor del certificado (cruce verde SUNAT).

## Sistema de UI compartido

Componentes TONO / Badge / Breadcrumbs / Dropzone / Skeleton + escala
nano/micro/dato. **NO hardcodear colores ni tamaños**. Palabras de evaluador en
todo lo visible (nada de "pipeline", "MCP", "espejo").

## Pendiente de documentar

Estructura interna de rutas/componentes del repo Panel-InfoObras (documentarla
allí o ampliar aquí cuando se trabaje el panel).
