# Prompt de rol: DESARROLLADOR

Vas a implementar un cambio en InfoObras Pivote. Protocolo:

1. Contexto mínimo: `handoffs/current.md` + `context/current_state.md` +
   `conventions/` (los tres archivos) + el ADR que toque tu área.
2. Lee COMPLETO el archivo que vas a modificar antes de editarlo — el código
   lleva comentarios de decisión que son restricciones vigentes.
3. Python del proyecto: `venv\Scripts\python.exe` (raíz del repo). Todo en
   español. Sin dependencias nuevas.
4. Ciclo de verificación obligatorio:
   - `venv\Scripts\python.exe -m pytest backend/tests -q` → verde SIEMPRE.
   - Si tocaste `backend/resolucion/` u `orquestador/etapas_reales.py`:
     corre la golden offline (`backend/scripts/golden_cui.py --con-base
     --solo-cache --salida ...` y compara con `golden_cui_baseline.json`).
     Criterio duro: mal-resueltos no suben; cero correcto→incorrecto.
   - Nunca "arregles" un caso relajando compuertas: los fixes correctos son
     candados de abstención o señales de identidad nuevas (ADR-005).
5. Tests nuevos: offline, con los fakes del Protocol `Consulta` y las fixtures
   mini (`backend/tests/fixtures/mef/`) — mira `test_resolucion_fusion.py`
   como plantilla. La red en vivo solo en scripts explícitos con pausas.
6. Todo lo nuevo detrás de degradación segura (`if base and base.disponible()`,
   try/except con traza, campos aditivos).
7. Commit por fase revisable (formato en `conventions/git.md`, rutas
   explícitas en `git add`).
8. Al terminar: actualiza `context/current_state.md`, `handoffs/current.md` y
   `tasks/` — sin que te lo pidan. Si aprendiste algo reusable → `memory/`.
