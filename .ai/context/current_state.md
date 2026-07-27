# Estado actual del proyecto

> Última actualización: **2026-07-26** · rama de trabajo: `demo`

## Terminado y validado (sin desplegar)

- **Integridad de la evaluación + visibilidad del Excel** (#45/#46/#47, PR #48
  y ADR-013, en `demo`). Suite **565**. Lo que cambia para el evaluador:
  - el bloque InfoObras del Excel **muestra el nombre de la obra** (antes solo
    código y CUI: ninguna identificación era auditable de un vistazo);
  - la advertencia de revisión **ya no se esconde tras un `elif`** — eran 403
    de 999 ítems sin resolver (40%) invisibles, en 31 jobs;
  - **el backend calcula** días/meses/años, `anterior_colegiatura` e
    `incluye_covid` (etapa VALIDACIÓN): dejan de depender de que el LLM los
    mande, que es como salieron vacías las corridas del 26-jul;
  - el consolidador de la skill **falla ruidosamente** si la evaluación no
    cubre 1:1 lo declarado, y ya no imprime `OK` cuando hay críticos;
  - **veto por departamento contradictorio** + **candado de nombre genérico**
    (ADR-013): cierran el caso Tarapoto (Hospital EsSalud de San Martín contra
    una tomografía en Madre de Dios). Costo medido en el corpus: 0.6% a
    revisión, y las 6 experiencias del delta del veto son mal-resueltos.
  - `scripts/reparar_evaluacion.py` rellena jobs viejos sin re-correr la skill.
- **Golden regenerada** (corrida en vivo autorizada, 26-jul): baseline nuevo
  230 correctos / 10 incorrectos / 34 revisión, **cero `correcto→incorrecto`**.
  La caché quedó completa y `--solo-cache` volvió a funcionar offline.
  ⚠ **La golden es ciega a media regla del resolver**: sus casos solo llevan
  `proyecto` y `cui`, sin `ubicacion`/`entidad`/`ruc_emisor`, así que los vetos
  de ubigeo y el candado de nombre no se ejercitan (ADR-013 dio matriz
  diagonal: probó cero regresión, no validó nada). Ensancharla está en curso.

- **Issue #32 — factor de evaluación al final de cada hoja P** (`17b1e04`):
  cierra el punto 2 del feedback del 28-jul. Verificado e2e con PDFs
  sintéticos; **falta la corrida sobre un job real**. Toca skill (prompt
  `agent-bases`, consolidador, `extraer_certificados.js`) y backend
  (`excel_final.py`), pero es compatible en ambos sentidos de despliegue: un
  `P{n}_FACTOR.pdf` que llegue a un backend viejo se ignora, y un backend nuevo
  sin el archivo genera la hoja como antes. Arrastra un fix:
  `regenerar_excel_final` conservaba cero imágenes.
- **Issue #30 — emisor del certificado en SUNAT** (rama
  `rafram96/issue-30-mostrar-representante-legal`): representantes legales +
  información histórica (`getinfHis`, sondeada 25-jul) en el bloque emisor del
  Excel, con la respuesta calculada a "¿estaba HABIDO al emitir y durante la
  obra?" en el título del campo. Cuadro histórico nuevo en R:U (representante
  de obra corrido a W:Z). Una consulta por RUC por job. 276 tests verdes +
  prueba en vivo contra 6 RUCs. **Pendiente: render en el panel.**
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

- **Issue #28 (T-MULTI-002) paso 1 — desempate por estado del MEF**, mergeado
  a `demo` el 2026-07-26 (PR #39, `14f9fe8`): `estado_dataset` ya viajaba en la
  base local desde F3 y **ningún consumidor lo leía** (229k de 494k filas son
  DESACTIVADAS y competían de igual a igual con las vivas). Ahora ordena el
  presupuesto de fetches, desempata el ranking a igual score y separa homónimos
  en el guard de empate — siempre como DESEMPATE, nunca como filtro (15 de 191
  verdades auditadas viven en filas DESACTIVADA: CUIs reformulados que el cert
  cita). Consultas al portal gastadas en desactivadas: 32.2% → 9.3%. Empate de
  Sullana 4 → 2 candidatos. 375 tests verdes. **Golden en vivo NO corrido** (el
  reordenamiento cambia qué CUIs se consultan → la caché no los tiene).

## En progreso

- **Fixtures listos para probar el backend nuevo** (2026-07-26): preparadas
  `Pronis_Sonitor/`, `Soritor2/` y `Consorcio-Lircay/` con `_prep/MAPA.md`
  (inventario, offsets de folio, tachado, descartes). Índice nuevo
  `fixtures/ing manuel/_CONCURSOS.md` = qué carpeta es qué concurso/postor.
  Herramientas reusables en `src/tools/`: `detectar_tachado_pdf.py` (validado
  contra el caso HuachoColpa: 10/10 páginas), `trocear_pdf.py` y
  `render_paginas.py`. **Mejor fixture para probar: `Soritor2/`** (born-digital,
  95 MB, sin troceo). Detalle en `handoffs/2026-07-26_claude.md`.

- **Issue #31 — candado cargo↔bases (ADR-012)**, mergeado a `demo` el
  2026-07-26: `backend/validacion/cargo_nucleo.py`
  exige el núcleo de especialidad COMPLETO (OR entre alternativas, AND dentro)
  y usa las funciones como segunda puerta; marca rojo/amarillo en el Excel sin
  tocar el formato ni el cómputo de días. Replay: 15 rojas + 116 amarillas
  sobre 1421 experiencias, con los 4 casos del Comité detectados. Falta prueba
  viva + deploy (la skill cambió → rebuild del plugin).
- Fase comercial: presentar extras a Manuel
  (T-003+T-008 entregados S/5,400; T-004/005/006 por desarrollar S/4,400).

## Problemas abiertos

- **Bases de Lircay (`Consorcio-Lircay/`) traen tachado pese a llamarse "sin
  tachas"**: 16 páginas, y lo eliminado toca equipamiento estratégico (pick-up
  2021+, software, miras, "Con Estación Total") y las funciones BIM del
  personal → leer `_prep/bases_texto.txt`, **nunca el PDF crudo**.
- **Falta la oferta económica de los 2 postores de Lircay** → sin límite
  inferior ni puntaje de precio. Pedírselas a Manuel.
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
