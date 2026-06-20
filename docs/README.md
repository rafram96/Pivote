# Índice de `docs/` — Pivote InfoObras

> Mapa de toda la documentación del pivote. Cada carpeta agrupa una **pieza**
> del sistema o un tipo de documento. La organización sigue la arquitectura de
> las 4 piezas (ver [`arquitectura.md`](arquitectura.md)).

## Fuentes de verdad (leer primero)

| Doc | Qué responde |
|---|---|
| [`../README.md`](../README.md) | Visión general del repo |
| [`arquitectura.md`](arquitectura.md) | **Qué se construye y dónde corre cada pieza** |
| [`contrato/contrato_refactor.md`](contrato/contrato_refactor.md) | **Contrato técnico vigente** Claude ↔ backend |

> ⚠ El `.claude/CLAUDE.md` de la raíz quedó parcialmente desfasado; ante una
> discrepancia, mandan los 3 docs de arriba.

## Convenciones de esta carpeta

- **`.md` = documentación versionada** (en git).
- **`.html` y `.json` = artefactos locales** (visuales, dumps). Están
  **ignorados por git** a propósito (`*.html`/`*.json` en `.gitignore`); viven
  en la laptop, no se commitean.
- Notas de reunión: `cliente/reunion_AAAA-MM-DD[_tema].(md|html)`.

---

## Estructura

### 📐 Raíz
- [`arquitectura.md`](arquitectura.md) — las 4 piezas y su flujo end-to-end.

### 🔌 `contrato/` — el contrato de datos Claude ↔ backend
- [`contrato_refactor.md`](contrato/contrato_refactor.md) — contrato vigente (v1.2.0).
- [`schema_canonico.md`](contrato/schema_canonico.md) — schema canónico documentado.
- [`schema_canonico_pydantic.md`](contrato/schema_canonico_pydantic.md) — modelos Pydantic.
- `json_espejo_explicado.html` — explicación visual del JSON espejo *(local)*.

### 🧩 `skill/` — Pieza 1: la skill de Claude (máquina cliente)
- [`skill_design.md`](skill/skill_design.md) — diseño de `analizar-licitacion-osce` + subagentes.

### 🛰 `mcp-server/` — Pieza 2: MCP local
- [`poc-conexion.md`](mcp-server/poc-conexion.md) — prueba de conexión MCP → backend.

### ⚙ `backend/` — Pieza 3: backend on-prem
- [`README.md`](backend/README.md) — entrada de la pieza backend.
- [`orquestador.md`](backend/orquestador.md) — pipeline de etapas.
- [`validador.md`](backend/validador.md) — validación del JSON espejo.
- [`resolucion_cui.md`](backend/resolucion_cui.md) — resolución de CUI / InfoObras.
- [`descarga_infoobras_experiencias.md`](backend/descarga_infoobras_experiencias.md) — scraping de experiencias.
- [`plan_calidad_resolucion.md`](backend/plan_calidad_resolucion.md) — plan de calidad de veredictos *(movido aquí desde la raíz)*.
- [`auditoria_backend.md`](backend/auditoria_backend.md) — auditoría del backend.
- [`futuro_modificaciones_plazo_excel.md`](backend/futuro_modificaciones_plazo_excel.md) — pendiente: modificaciones de plazo en Excel.
- `*.html` — visuales (arquitectura, orquestador, pruebas e2e, endpoints SUNAT) *(locales)*.

### 🖥 `frontend/` — Pieza 4: panel (código vive en `Panel-InfoObras`)
- [`README.md`](frontend/README.md) — spec de pantallas del panel.
- [`plan.md`](frontend/plan.md) — plan del frontend MVP *(movido aquí desde la raíz)*.

### 🚀 `despliegue/`
- [`instalacion.md`](despliegue/instalacion.md) — instalación on-prem (Docker).

### 👤 `cliente/` — material y reuniones con Manuel
- [`reunion_2026-06-07.md`](cliente/reunion_2026-06-07.md) — notas de reunión.
- `reunion_2026-06-20_claude-remoto.html` — prep de reunión: Claude remoto + archivos en red *(local)*.
- [`skill-manuel/`](cliente/skill-manuel/) — la skill `propuestas` que Manuel ya tenía (reglas, OCR, formato).

### 💼 `comercial/`
- `recotizacion_pivote.html` — recotización del pivote *(local)*.

### 🎬 `presentaciones/` — decks en HTML *(todos locales)*
- `avance_construccion_dev.html` — **cuaderno de obra · estado VIGENTE** (componentes + lo que falta; actualizado).
- `arquitectura_modulos.html` — arquitectura por módulos del pivote.
- `pivote_presentacion.html` — pitch del pivote *(jun-01; conviene refrescar antes de presentar).*
- *(Borrados por superados: `plan_pivote`, `pivote_visual`, `demo_scraping`, `estado_proyecto`.)*

### 🗄 `_historia/` — documentos obsoletos (solo referencia)
- [`plan_3jsons.md`](_historia/plan_3jsons.md) — plan v1 de 5 fases / 3 JSONs. **Superado** por `contrato_refactor.md`.
