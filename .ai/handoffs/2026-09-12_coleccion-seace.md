---
timestamp: "2026-09-12"
agent: "Codex"
session_status: "clean"
---

# Handoff — colección documental SEACE

Se implementó `documentos_prioritarios(comp, contrato_id=None)` en
`backend/scraping/seace_abierto.py`. Conserva todas las bases integradas del
tender y los documentos `contractSigned`/`contractAnnexe` de todos los contratos,
con filtro exacto opcional, orden estable, deduplicación por contrato+ID+URL y
registros explícitos para enlaces faltantes. Los alias legacy no cambiaron.

Prueba focal offline: `pytest tests/test_coleccion_seace.py tests/test_seace_abierto.py`
→ 48 passed. No hubo red, jobs ni cambios históricos.

También se integró la colección en `etapa_seace` y en `_proceso_exacto`: queda
junto a los campos legacy `docs`, y la ruta de identidad usa una fuente con solo
el contrato comprobado. Continuación integrada por el coordinador:
[descargador, entregables y aceptación](2026-09-12_codex.md).
