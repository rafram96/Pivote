# Pivote InfoObras

Repo de **código del pivote**: Claude (en la PC del ingeniero) extrae y evalúa
propuestas OSCE, y el backend on-prem verifica, enriquece con cruces oficiales
(SUNAT/InfoObras) y persiste.

> 📐 Empezar por **[`docs/arquitectura.md`](docs/arquitectura.md)** — el mapa de
> las 4 piezas. El contrato técnico detallado está en
> [`docs/contrato/contrato_refactor.md`](docs/contrato/contrato_refactor.md).

## Las 4 piezas

| # | Pieza | Corre en | Código |
|---|---|---|---|
| 1 | **Skill** `analizar-licitacion-osce` | PC del ingeniero (Cowork) | [`skill/`](skill/) |
| 2 | **MCP server** local | PC del ingeniero | [`mcp-server/`](mcp-server/) |
| 3 | **Backend** (validador + scrapers + API) | Servidor on-prem | [`backend/`](backend/) |
| 4 | **Frontend** (panel) | Servidor on-prem | repo aparte `Panel-InfoObras` |

## Estructura del repo

```
skill/          Pieza 1 — código de la skill (corre en PC cliente)
mcp-server/     Pieza 2 — código del MCP local (client = Cowork, no se construye)
backend/        Pieza 3 — on-prem
    scraping/       base traída de Alpamayo-InfoObras (SUNAT, InfoObras)
    poc-conexion/   stand-in HTTP del POC de transporte (temporal)
    exploracion/    dumps de scraping (local, gitignored)
docs/           TODA la documentación de diseño
    arquitectura.md   mapa de las 4 piezas (empezar aquí)
    contrato/         schema + JSON espejo + contrato_refactor
    skill/ mcp-server/ backend/ frontend/   diseño por pieza
    presentaciones/   renders HTML para el cliente
    _historia/        diseño obsoleto del 1er pivote (3 JSONs)
fixtures/       datos del cliente para probar (gitignored)
tools/          scripts auxiliares (lectura de Excels, etc.)
```

## Constraints heredados

- ⛔ El **backend nunca llama a APIs cloud de IA**. Claude corre en la PC del
  cliente con su sub Max 5x.
- ⛔ **No subir datos del cliente** (PDFs, Excels) — viven en `fixtures/`
  (gitignored).
- 📦 PostgreSQL · 🇪🇸 código, docs y commits en español.

## Repos relacionados

| Repo | Rol |
|---|---|
| `Alpamayo-InfoObras` | Backend de producción original; base del scraping. |
| `Panel-InfoObras` | Frontend (pieza 4). |
| `motor-OCR` | Pipeline legacy OCR+LLM — fallback dormido. No tocar. |
