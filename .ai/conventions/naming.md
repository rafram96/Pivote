# Convenciones de nombres

- Python: snake_case en español (`buscar_candidatos`, `es_expediente_exp`);
  privados con `_`; constantes `_RE_*` para regex compilados.
- Claves de enriquecimiento por experiencia: `"n_prof:n_exp"` (ej. `"1:2"`).
- Vocabulario `via` del resolver (CERRADO, no inventar valores):
  `MANUAL · NO_EXISTE · MULTI_OBRA · PRIVADA · CUI_TEXTO · RUC · NOMBRE ·
  PROBABLE · DEDUP · PORTAL`.
- Estados de job: `recibido · en_proceso · completado · requiere_revision ·
  error` (terminal normal = requiere_revision).
- Carpetas de job: hash de 12 hex en `datos_pivote/`; artefactos con nombre
  fijo (`espejo.json`, `enriquecimiento.json`, `final.xlsx`, `infoobras.zip`).
- Descargas por experiencia: `P{n}_E{m}/` con secciones (`Valorizaciones/`,
  `Expediente técnico/`, `Verificación MEF/`…).
- UI/entregables: palabras de evaluador («Por confirmar», nunca jerga técnica).
- Extras comerciales: códigos `T-00x`. Alertas del motor: `ALT-xx`.
- Ramas: ver `git.md`. Documentos presentables: HTML en `docs/nuevos_modulos/`
  con el estilo/paleta compartida de los existentes.
