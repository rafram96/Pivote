# Plan del pivote — 5 fases

Estado al **2026-05-27**:

## 1 · Hacer JSONS a partir de los Excels y refinar la estructura  · ⏳ EN PROGRESO
- [x] Lectura de los 3 Excels reales (Lircay CP-02-2025) — celda × celda
  con `src/tools/leer_excels.py`
- [x] Lectura del Excel REAL del ingeniero (`10. Lircay 16.04.26.xlsx`) — formato del cliente
- [x] **Schema canónico v2** documentado → [`schema_canonico.md`](schema_canonico.md)
  - Modelo: Skill genera **3 JSONs (Paso 1+2+3)**; Backend genera Paso 4+5 + enriquecimiento + Excel Lircay
  - Sección `observaciones_claude` (cualitativa, con severidad y referencias)
  - Formato del ingeniero respetado al renderizar Excel (headers literales, 2 folios, "No disponible", etc.)
- [x] Mapeo Excel ingeniero → JSON canónico (sección 9)
- [x] Contrato de responsabilidades Claude vs backend (sección 8)
- [x] Discrepancias documentadas (sección 11)
- [x] **Pydantic en código** → [`schema_canonico_pydantic.md`](schema_canonico_pydantic.md) (v2, ejecutable)
- [x] **3 ejemplos JSON desde Excels reales** → `examples/lircay_{bases,profesionales,experiencias}.json` (generados con `src/tools/generar_ejemplos_json.py`)
- [ ] Validación mental contra goldens de URCOS (Huancavelica descartado)

## 2 · Planear la SKILL `analizar-licitacion-osce`  · ⏳ EN PROGRESO
- [x] **Diseño v2** → [`skill_design.md`](skill_design.md) (**2 subagentes, 3 JSONs**, backend hace P4+P5)
- [x] Prompts depurados para `agent-bases` y `agent-propuesta`
- [x] Orquestador con retry por subagente
- [x] Estrategia de validación con Pydantic (4 schemas: 3 individuales + cross-JSON)
- [x] Estructura del directorio `~/.claude/skills/analizar-licitacion-osce/`
- [x] Pydantic schemas reales en código → `schema_canonico_pydantic.md`
- [ ] Validar prompts contra el Excel del ingeniero (test mental ida y vuelta)

## 3 · Planear el MCP local  · ⏳ PENDIENTE
- Tools: `subir_analisis`, `consultar_estado`, `listar_jobs_recientes`
- Endpoint target: `Alpamayo-InfoObras:8000` (no Panel-backend)
- Auth on-prem (token / VPN — decisión pendiente con Manuel)

## 4 · Construir el panel frontend (no refactor — construir desde mockups HTML)  · ⏳ PENDIENTE
- Frontend vive en `Panel-InfoObras/` (repo separado, Next.js 15 + React 19 + Tailwind v3)
- Hay 7 mockups HTML en `public/design/`; solo 1 `.tsx` real (gallery)
- Decisiones: shadcn/ui sí/no; qué hacer con Panel-backend (port 8002)

## 5 · Recotización con Manuel  · ⏳ PENDIENTE
- Estimación ajustada con frontend en estado mockup: Plan A ~14-18d, Plan B ~8-10d

---

## Documentos producidos en este directorio

| Archivo | Contenido | Estado |
|---|---|---|
| `docs/plan.md` | Este archivo — tablero de progreso | actualizado |
| `docs/schema_canonico.md` | Fase 1 — schema JSON canónico | v1 |
| `docs/skill_design.md` | Fase 2 — skill + 3 subagentes con prompts | v1 |
| `docs/files/*.xlsx` | 3 Excels del cliente (Lircay CP-02-2025) | datos privados |
| `src/tools/leer_excels.py` | Utility — lectura/resumen de los 3 Excels | utility |
| `src/referencia/scraping_alpamayo/` | Snapshot read-only de `Alpamayo/src/scraping/` | snapshot 2026-05-27 |
| `venv/` | Python 3.12 + pandas + openpyxl | no commitear |

## Pendientes inmediatos

1. Cerrar Fase 1: producir `schema_canonico_pydantic.md` con clases Pydantic + 2 ejemplos JSON.
2. Cerrar Fase 2: test mental — pasar las bases de Lircay al prompt de `agent-bases` y verificar que el output cabe en el Excel real.
3. Arrancar Fase 3 (MCP).
