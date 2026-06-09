# Pieza 1 · Skill `analizar-licitacion-osce`

Código de la skill de Claude Code / Cowork que corre en la **PC del ingeniero**.

> ⚠ **Entorno del cliente: Node** (`exceljs`, `zod`) para todo el código
> client-side. **Única excepción:** el **Paso 0 (OCR)** usa **Python + Tesseract**,
> y solo corre si la propuesta es un escaneo sin capa de texto. Los gemelos en
> Python (generador/validador) viven en el **backend** (`../backend/scripts/`,
> `../backend/schemas/`), que regenera el Excel final enriquecido.

Orquesta subagentes (`agent-bases`, `agent-propuesta-mapa`, N ×
`agent-propuesta-profesional`, `agent-evaluador`), consolida y emite **Excel
(Formato de Evaluación, 5 partes) + JSON espejo** (contrato en
[`docs/contrato/`](../docs/contrato/)).

## Estructura

```
skill/
├── SKILL.md                          # orquestador: Paso 0 OCR + flujo subagentes + transporte
├── prompts/
│   ├── agent-bases.md                # lee bases.pdf → requisitos/factores/personal clave + límite inferior
│   ├── agent-propuesta-mapa.md       # 1 pasada: datos postor + bundle de folios por profesional
│   ├── agent-propuesta-profesional.md# 1 por profesional: extrae su bundle (1 fila/periodo) + cross-check NOTA 1
│   └── agent-evaluador.md            # cruza requisitos × experiencia → evalúa con razón literal
├── references/
│   └── salida.md             # contrato de salida: Excel 5 partes + JSON espejo + _backend
├── schemas/
│   └── espejo.js             # zod: schema del JSON espejo (forma vigente)
├── scripts/
│   ├── ocr_propuesta.py      # Paso 0: OCR Tesseract (spa) reanudable de PDFs escaneados (port del flujo manual)
│   ├── generar_excel.js      # exceljs: genera el Excel de 5 partes desde el JSON espejo
│   └── validar_espejo.js     # zod: valida el JSON espejo (CLI, para el retry)
└── package.json              # deps Node: exceljs, zod
```

## Uso (en la PC del ingeniero)

```
cd ~/.claude/skills/analizar-licitacion-osce
npm install                                  # una sola vez
node scripts/validar_espejo.js <espejo.json> # valida (OK / INVÁLIDO + errores)
node scripts/generar_excel.js <espejo.json> <salida.xlsx>
```

## Estado

- ✅ Patrón validado en PoC (`prueba-subagentes-mcp`): skill → subagentes ‖ → MCP.
- ✅ SKILL.md + prompts de los subagentes + contrato de salida.
- ✅ Topología en dos niveles: `agent-propuesta-mapa` (bundles por profesional) →
  `agent-propuesta-profesional` ×N (profundidad por profesional, cross-check NOTA 1).
- ✅ Reglas de dominio portadas del flujo manual: límite inferior (90%), tramos del
  Factor A, PMP (PMI/sello/2 años/no-PDU), ISOs 14001/37001/9001, consorcio (todos),
  traslapes en rojo, COVID 16/03–30/06/2020, "NO APLICA" para factores inexistentes.
- ✅ `scripts/generar_excel.js` (Node/exceljs) — 5 partes con estilo del ingeniero,
  filas variables, resaltado Claude/backend. Round-trip validado contra Trujillo (13 prof.).
- ✅ `schemas/espejo.js` + `scripts/validar_espejo.js` (Node/zod) — validación del
  JSON espejo cableada al retry. Valida el caso Trujillo real.
- ⏳ `scripts/ocr_propuesta.py` (Paso 0) — pendiente de portar desde el flujo manual
  (Tesseract `spa`, `OMP_THREAD_LIMIT=1`, reanudable). Solo se usa con escaneos.

## Despliegue

En despliegue, el contenido de esta carpeta se copia/symlinkea a
`~/.claude/skills/analizar-licitacion-osce/` en la máquina del cliente (Cowork),
y se corre `npm install` ahí una vez.

> Diseño: [`docs/contrato/contrato_refactor.md`](../docs/contrato/contrato_refactor.md)
> (**autoritativo**: 3 subagentes, Claude evalúa, Excel + JSON espejo).
