# Convenciones de git

- **Ramas**: `demo` = rama principal de trabajo (todo lo reciente se mergea
  ahí; `dev` quedó atrás; `main` existe pero el flujo real es demo).
  Experimentos/sondas: `sonda/<tema>` (ej. `sonda/refactor-cui`). Features:
  `feat/<tema>`.
- **Commits en español**, estilo conventional: `feat|fix|refactor|perf|docs|
  chore(ámbito): resumen — cuerpo con el PORQUÉ y la evidencia` (números de
  golden/tests cuando aplique). Un commit por fase revisable.
- `git add` SIEMPRE con rutas explícitas — nunca carpetas enteras ni `-A`
  amplio (incidente real: `tools/_sonda_seace/` con XLSX de datos se coló y
  hubo que amendear).
- **Gitignored a propósito** (no forzar): `backend/datos_pivote/` (datos de
  cliente + baselines), `docs/comercial/` (precios), venvs, node_modules.
- ⛔ JAMÁS commitear PDFs/propuestas/datos del cliente ni credenciales.
- No amend/rebase de commits ya pusheados; amend local inmediato solo para
  corregir un commit recién creado no compartido.
- Los commits de agente llevan `Co-Authored-By: Claude ...`.
