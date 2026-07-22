# Completado (más reciente primero)

## 2026-07-22
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
