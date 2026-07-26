# Estado actual del proyecto

> Última actualización: **2026-07-23** · rama de trabajo: `sonda/refactor-cui`

## Terminado y validado (sin desplegar)

- **Refactor del resolver de CUI (T-008)** — rama `sonda/refactor-cui`, 13
  commits (`a732936…f2bde36`): base local MEF + público-primero + vetos de
  identidad + candados de abstención + camino A/B. Golden 277 casos: errores
  silenciosos **16 → 10**, cero regresiones. 268 tests verdes.
- **Camino A (expedientes)**: clasificador por toda la evidencia + modo
  `PIVOTE_FORZAR_EXPEDIENTES=1`; validado con el concurso San Isidro.
- **Skill optimizada**: Paso 4.5 acotado (elimina fuga de ~3M tokens/corrida);
  prompt del extractor conserva el envoltorio "Elaboración del ET:".
- **Análisis San Isidro CP-01-2026 entregado** al usuario: job `b4f385c31811`
  (camino A), Excel 12.5 MB con imágenes, 44 CUIs, 28 verificados en MEF.
- **Documentos del paquete de extras v3** (docs/nuevos_modulos/): 4 HTML
  actualizados con T-008 + `arquitectura-sistema.html` nuevo.
- Cotización interna lista: `docs/comercial/planeacion-v2-para-rafael.md`
  (gitignored — no va al repo).

## En progreso

- **Issue #31 — candado cargo↔bases (ADR-012)**, rama
  `rafram96/issue-31-no-detecta-cargo`: `backend/validacion/cargo_nucleo.py`
  exige el núcleo de especialidad COMPLETO (OR entre alternativas, AND dentro)
  y usa las funciones como segunda puerta; marca rojo/amarillo en el Excel sin
  tocar el formato ni el cómputo de días. Replay: 15 rojas + 116 amarillas
  sobre 1421 experiencias, con los 4 casos del Comité detectados. Falta prueba
  viva + deploy (la skill cambió → rebuild del plugin).
- Fase comercial: presentar extras a Manuel
  (T-003+T-008 entregados S/5,400; T-004/005/006 por desarrollar S/4,400).

## Problemas abiertos

- Corridas camino A: aún se **descargan y pintan** secciones de obra
  (valorizaciones ~805 archivos) en expedientes — cosmético/pesado, no afecta
  veredictos. Advertencias COBERTURA se emiten para expedientes (no descuentan).
- 2 casos de la auditoría con "verdad" dudosa (2195439 Tocache/Loreto,
  2064566 Cotabambas/Antabamba) — re-revisar con Manuel.
- Divergencia schema.sql vs DDL real de Postgres (ver architecture/database.md).
- SUNAT con error_parcial intermitente en corridas largas (portal, no bug).

## Riesgos

- Hay un **deploy pendiente**: el refactor ya está mergeado a `demo`
  (fast-forward 2026-07-23, SOLO local — falta push), pero el server corre el
  código viejo. Los pasos y el ORDEN del deploy viven SOLO en
  `InfoObras/.ai/tasks/active.md` (fuente única).
- Límite de gasto mensual de Claude alcanzado el 21-jul (los subagentes pueden
  morir a mitad — el trabajo F8 se terminó a mano por eso).

## Siguiente prioridad recomendada

1. Deploy en paquete del refactor — checklist de deploy: ver
   `InfoObras/.ai/tasks/active.md` (fuente única).
2. Filtro de secciones de descarga/Excel en modo camino A.
3. Reunión de cotización con los 5 HTML de docs/nuevos_modulos/.
