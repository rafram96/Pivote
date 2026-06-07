# Arquitectura del pivote — las 4 piezas

> **Fuente de verdad de alto nivel.** El contrato técnico detallado está en
> [`contrato/contrato_refactor.md`](contrato/contrato_refactor.md). Este doc
> responde una sola pregunta: **qué se construye y dónde corre cada cosa.**

## El flujo en una línea

Claude (en la PC del ingeniero) **extrae y evalúa** la propuesta → emite
**Excel + JSON espejo** → el **backend on-prem** verifica, enriquece con cruces
oficiales (SUNAT/InfoObras) y persiste → el **panel** lo muestra.

```
┌─ PC del ingeniero ──────────────────┐      ┌─ Servidor on-prem ───────────────────┐
│  Claude Cowork (Max 5x)             │      │  Backend InfoObras                    │
│                                     │      │                                       │
│  [1] SKILL                          │      │  [3] BACKEND                          │
│   · 3 subagentes                    │ Excel│   · validador determinístico          │
│     (bases, propuesta, evaluador)   │ +JSON│   · scrapers SUNAT + InfoObras        │
│   · emite Excel + JSON espejo       │ ─LAN→│   · API HTTP desacoplada              │
│                                     │      │   · recálculos (ALT03 25 años)        │
│  [2] MCP SERVER (local)             │ ←────│   · regenera Excel final              │
│   · transporte por LAN              │ rep. │   · PostgreSQL                        │
│   · client = Cowork (no se construye)│     │                                       │
└─────────────────────────────────────┘      └───────────────┬───────────────────────┘
                                                              │ sirve
                                              ┌─ Panel web (Next.js) ─────────────────┐
                                              │  [4] FRONTEND  (repo Panel-InfoObras) │
                                              │   · dropzone + vistas + histórico     │
                                              └────────────────────────────────────────┘
```

## Las 4 piezas

| # | Pieza | Dónde corre | Código en este repo | Estado |
|---|---|---|---|---|
| 1 | **Skill** | PC del ingeniero (Cowork) | [`skill/`](../skill/) | 🔨 diseñada, sin código |
| 2 | **MCP server** | PC del ingeniero | [`mcp-server/`](../mcp-server/) | 📐 POC funcional |
| 3 | **Backend** | Servidor on-prem | [`backend/`](../backend/) | scrapers ✅ probados, validador 🔨 |
| 4 | **Frontend** | Servidor on-prem (panel) | ❌ NO aquí → `Panel-InfoObras` | ⏳ mockups |

### El MCP: solo construimos el *server*

El **cliente MCP es Claude Cowork** (ya viene hecho, no se construye). Nosotros
solo construimos el **MCP server local**: un subproceso que Cowork lanza en la PC
de Manuel, que expone tools (`subir_y_validar`, `consultar_estado`…) y hace
`POST` por LAN al backend. Como corre en la PC del cliente, alcanza el servidor
on-prem **sin exponerlo a internet** (ver `contrato_refactor.md §4`).

## El contrato que pega todo: Excel + JSON espejo

Claude emite **dos artefactos** por análisis:

- **Excel** (formato Manuel) → para el humano.
- **JSON espejo** → para la máquina; incluye la evaluación de Claude + un bloque
  `_backend` con los campos en `null` que el servidor debe llenar (SUNAT,
  InfoObras, recálculos).

Schema en [`contrato/schema_canonico_pydantic.md`](contrato/schema_canonico_pydantic.md).
El servidor **regenera** el Excel final enriquecido (no parchea el de Claude).

## Regla de oro (constraint on-prem)

La PC hace lo **no-determinístico** (razonar sobre PDFs). El servidor hace lo
**determinístico**, lo que toca **fuentes oficiales** (portales públicos SUNAT/
InfoObras — salida, no exposición) y lo que **persiste**. El backend **nunca**
llama a APIs cloud de IA.

## Dónde vive cada pieza (mapa del repo)

```
skill/          ← [1] código de la skill (corre en PC cliente)
mcp-server/     ← [2] código del MCP local (corre en PC cliente)
backend/        ← [3] código on-prem: validador + scrapers + API
                    ├── scraping/      base traída de Alpamayo-InfoObras
                    ├── poc-conexion/  stand-in HTTP del POC (temporal)
                    └── exploracion/   dumps SUNAT (local, gitignored)
docs/           ← TODA la documentación de diseño (espejo por pieza)
fixtures/       ← datos del cliente para probar (gitignored)
tools/          ← scripts auxiliares (lectura de Excels, etc.)
```

[4] Frontend documentado en [`frontend/`](frontend/); su código está en el repo
`Panel-InfoObras`.
