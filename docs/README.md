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
- [`preparacion-pdfs-corrida.md`](preparacion-pdfs-corrida.md) — runbook: dejar bases (DOCX→PDF sin tachado) + propuesta listas antes de correr la skill.

### 🔌 `contrato/` — el contrato de datos Claude ↔ backend
- [`contrato_refactor.md`](contrato/contrato_refactor.md) — **contrato vigente (v1.2.0)**. El schema lo define el código: `backend/schemas/espejo.py` ↔ `skill/schemas/espejo.js`.
- `json_espejo_explicado.html` — explicación visual del JSON espejo *(local)*.

### ⚙ `backend/` — backend on-prem
- [`README.md`](backend/README.md) — entrada de la pieza backend.
- [`orquestador.md`](backend/orquestador.md) — pipeline de etapas.
- [`validador.md`](backend/validador.md) — validación del JSON espejo.
- [`resolucion_cui.md`](backend/resolucion_cui.md) — resolución de CUI / InfoObras.
- [`descarga_infoobras_experiencias.md`](backend/descarga_infoobras_experiencias.md) — scraping de experiencias.
- [`plan_calidad_resolucion.md`](backend/plan_calidad_resolucion.md) — plan de calidad de veredictos.
- [`auditoria_backend.md`](backend/auditoria_backend.md) — auditoría del backend.
- [`modelo_datos.md`](backend/modelo_datos.md) — **plan de PostgreSQL** (modelo plano "Base de Datos").
- [`futuro_modificaciones_plazo_excel.md`](backend/futuro_modificaciones_plazo_excel.md) — pendiente: modificaciones de plazo en Excel.
- `*.html` — visuales (arquitectura, orquestador, pruebas e2e, endpoints SUNAT) *(locales)*.

### 🖥 `frontend/` — panel (código en `Panel-InfoObras`)
- [`README.md`](frontend/README.md) — spec de pantallas del panel.
- [`plan.md`](frontend/plan.md) — plan del frontend MVP.

### 🚀 `despliegue/`
- [`manual_instalacion.md`](despliegue/manual_instalacion.md) — **manual completo** (servidor + PC del ingeniero).
- [`instalacion.md`](despliegue/instalacion.md) — referencia on-prem (Docker).

### 🏁 `finales/` — cierre del proyecto
- [`pendientes.md`](finales/pendientes.md) — **inventario único de pendientes (A–E)**.
- [`despliegue-runbook.md`](finales/despliegue-runbook.md) — runbook del despliegue al servidor.

### 👤 `cliente/` — material y reuniones con Manuel
- [`manual_usuario.md`](cliente/manual_usuario.md) — **manual de usuario** (flujo end-to-end).
- [`reunion_2026-06-07.md`](cliente/reunion_2026-06-07.md) — notas de reunión.
- `reunion_2026-06-20_claude-remoto.html` — prep de reunión *(local)*.
- [`skill-manuel/`](cliente/skill-manuel/) — la skill `propuestas` que Manuel ya tenía (reglas, OCR, formato).

### 💼 `comercial/`
- `addendum_constancias_embebidas.md` — addendum (constancias embebidas) *(local)*.
- `recotizacion_pivote.html` — recotización del pivote *(local)*.

### 🎬 `presentaciones/` — decks en HTML *(todos locales)*
- `avance_construccion_dev.html` — **cuaderno de obra · estado VIGENTE**.
- `arquitectura_modulos.html` — arquitectura por módulos del pivote.
- `pivote_presentacion.html` — pitch del pivote *(jun-01; conviene refrescar antes de presentar).*

> **Borrados por superados** (recuperables de git): `schema_canonico.md`,
> `schema_canonico_pydantic.md`, `skill_design.md`, `poc-conexion.md`,
> `_historia/plan_3jsons.md` — todos del modelo viejo **"3 JSONs / v2"**,
> reemplazado por el **1 JSON espejo v1.2.0**. (Antes ya: `plan_pivote`,
> `pivote_visual`, `demo_scraping`, `estado_proyecto`.)
