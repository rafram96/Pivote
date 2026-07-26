# Completado (más reciente primero)

## 2026-07-26
- **Issue #32 — factor de evaluación embebido** (`17b1e04`, rama
  `rafram96/issue-32-embeber-el-factor-2`): la página del Cuadro de Factores
  (4.2 A) cierra cada hoja de profesional, junto al TDR y el Anexo 16 que ya
  se embebían. Cadena: `agent-bases.pagina_factores` → `_meta` → recorte
  `P{n}_FACTOR.pdf` (misma página replicada por profesional, para no tocar el
  filtro `P*` del ingest ni el reparto por `n_prof`) → `excel_final`.
  De paso: **`regenerar_excel_final` ya no arranca los embeds** — nunca pasaba
  `certificados`, así que el backfill de cargos devolvía el entregable sin
  ninguna imagen. Falta la verificación sobre un job real (huachocolpa).

## 2026-07-25
- **T-TAREA-ADR011 · certificados multi-obra** (Issue #26), en 3 PRs sobre
  `demo` — rama `rafram96/issue-26-t-multi-001`, SIN pushear todavía:
  - **PR-1** (`74cc80e`): la skill desglosa paquetes SIN CUI (antes el
    disparador exigía código por sub-obra, así que el caso HV ni llegaba al
    backend); fixture HV congelado, válido en Pydantic y en zod.
  - **PR-2** (`ed26628`): escalera CUI→nombre + `_exp_derivada` + mapeo aditivo
    de estados. Detalle que no estaba en el ADR: no heredar `ubicacion` NO basta
    — la geografía de la madre entra igual por `entidad_contratante`
    (`ubigeo_cert`, `_muni_contradice`), y hay que apagarla con
    `_solo_geo_propia`.
  - **PR-3**: candado multi-rubro, contradicción exigida ENTRE dos sub-obras.
  - Golden 277 casos con **cero drift** en las dos corridas (PR-2 y PR-3).
  - Bug colateral corregido: `EtapaResolucionCui.correr` descartaba TODAS sus
    observaciones (`MULTI_OBRA`/`PROBABLE`/`PRIVADA`) por no pasar `obs` a
    `_res`.
  - Pendiente del ADR: P2 (Escenario B con sub-fechas por anexo) sigue
    pospuesto — el contrato ya lo modela, falta un cert real que lo exija.

## 2026-07-22
- Base de conocimiento de NIVEL SISTEMA creada en la raíz `InfoObras/.ai/`
  (repo git propio; ADR-S001): panel documentado, contratos cross-repo,
  legacy inventariado; `CLAUDE.md` del Panel reescrito como puntero.
- Base de conocimiento `.ai/` creada.
- Documentos del paquete de extras actualizados a v3 (T-008 incorporado) +
  `arquitectura-sistema.html` nuevo (commits `5025ccb`, `f2bde36`).
- Análisis del spec "para RAFAEL-V2.xlsx" → matriz + cotización interna.

## 2026-07-21
- **F8**: vetos de ubicación (provincia/distrito/entidad municipal) + guard de
  empate geo; golden 10 mal-resueltos, cero regresiones (`3ec1581`). Terminado
  a mano tras corte del subagente por límite de gasto.
- **Camino A**: clasificador por toda la evidencia + `PIVOTE_FORZAR_EXPEDIENTES`
  + fix del prompt de la skill (`90b25be`); San Isidro re-corrido (28
  expedientes verificados en MEF, cero clamps indebidos).
- **Skill Paso 4.5 acotado** (`df053ee`): fin de la fuga de ~3M tokens.
- Rescate completo del análisis San Isidro sin gastar tokens de skill (espejo
  sobreviviente + scripts determinísticos + backend): job `b4f385c31811` con
  Excel de imágenes embebidas + 249 MB de sustento + ZIP.
- Auditoría manual de las 105 experiencias del replay BNP
  (`datos_pivote/c9c769976750/revision_manual.md`): 4 CUIs mal → origen del F8.
- Tesseract habilitado en la laptop (spa tessdata) → OCR Camino A local.

## 2026-07-20
- **F0-F7 del refactor del resolver** (commits `a732936…b341a22`): golden
  baseline (277 casos), base local MEF (ETL + índice), refactor estructural,
  fusión de candidatos, solape eliminado de la selección (ADR-003),
  público-primero + catálogo de entidades (ADR-004), candados F7 (ADR-005).
- Pruebas vivas: replay 9 exps y 105 exps de punta a punta.
- Validaciones empíricas previas: cobertura CSVs MEF 191/194; precisión fuzzy
  (top-1 67%, candidatos 82-85%); análisis de entidades contratantes (1042).

## Antes del refactor (hitos mayores, ver git log de `demo`)
- T-003 verificación de expedientes MEF (cerrado S/2,600) + fix aprobación ET.
- Deploy on-prem inicial (2026-07-12). Postgres respaldo. Progreso fino
  (paquete A). Sondas SEACE/CONOSCE/OCDS (GO) y RENIPRESS (GO).
