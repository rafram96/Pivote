# Manifest — Pivote

## Identidad

- Perfil documental: `repo`.
- Creado: 2026-08-20.
- Proyecto padre: Ninguno.

## Propósito

Pivote audita propuestas técnicas de concursos públicos OSCE para reducir falsos
cumplimientos en la experiencia declarada por profesionales. Claude, en la PC
del ingeniero, extrae y evalúa los documentos; el backend on-prem verifica el
resultado contra fuentes oficiales, conserva la trazabilidad y produce el Excel
y el sustento documental para el evaluador.

## Mapa del proyecto

- Mapa visual canónico: `architecture/architecture.json`, administrado mediante
  `raf-ai architecture`; `../arquitectura.json` queda como referencia histórica.
- Skill de análisis: `../skill/`; corre en Claude Code/Cowork en la PC del cliente.
- Puente MCP local: `../mcp-server/mcp.js`; conecta la PC con la API por LAN.
- API y pipeline on-prem: `../backend/api/app.py` y
  `../backend/orquestador/motor.py`.
- Resolver CUI: `../backend/resolucion/cui.py`, respaldado por la base MEF local.
- Persistencia: archivos por job como fuente de verdad y PostgreSQL para la base
  MEF y el respaldo lógico.
- Panel web: repositorio hermano `Panel-InfoObras`; consume la API de Pivote.
- Despliegue: `../deploy/docker-compose.yml` con backend, panel y PostgreSQL.

## Restricciones inquebrantables

- No versionar secretos ni datos sensibles.
- El backend on-prem nunca llama APIs cloud de IA.
- Los PDFs, Excels y demás datos del cliente nunca se versionan.
- Ante identidad insuficiente o fuentes caídas, el sistema se abstiene y deriva
  a revisión; nunca inventa un CUI, documento o confirmación.
- Los archivos por job son la fuente de verdad de los análisis; PostgreSQL no
  reemplaza esa autoridad.
- Marcar como «Pendiente de documentar» todo dato no verificado.
- Mantener una sola fuente oficial por concepto; enlazar en vez de duplicar.
