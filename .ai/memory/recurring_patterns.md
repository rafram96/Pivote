# Patrones que funcionan (reusar)

- **Golden antes de refactor**: congelar el comportamiento actual (con caché de
  respuestas web en disco) ANTES de tocar nada; cada fase se compara contra esa
  vara. Las re-corridas quedan offline y toman minutos. (`golden_cui.py`)
- **Fases pequeñas con criterio de aceptación**: F2 = refactor puro con
  comportamiento idéntico (detecta rupturas estructurales antes de cambiar
  semántica); recién después las fases de comportamiento.
- **Candados determinísticos sobre lo no determinístico**: la skill (LLM) falla
  distinto cada vez; se atrapa con validadores/matchers por código
  (match_cargo.js, validar_espejo.js), no con más prompt.
- **Portales estatales flaky**: reintentos con backoff + señal explícita
  `PortalNoResponde` ≠ lista vacía; caches por clave de consulta; pausas entre
  llamadas; secuencial, nunca paralelo contra el mismo portal.
- **Costura inyectable + default None**: `resolver(exp, consulta, base=None)` —
  los fakes de tests no se enteran de features nuevas; todo lo nuevo tras
  `if base and base.disponible()`.
- **Datos abiertos > scraping de buscadores**: MEF (CSVs), CONOSCE (Excel),
  OCDS (API) esquivan captchas y son consultables offline; el buscador web
  queda de fallback. Sondear SIEMPRE antes de cotizar (GO/NO-GO con evidencia).
- **Rescate de corridas caras de la skill**: los pasos post-extracción son
  determinísticos (consolidar, generar Excel, extraer certificados, subir) —
  una corrida cortada se termina por scripts sin gastar tokens.
- **Trampas fuzzy**: umbral alto (≥90) + señales exactas (siglas, números de
  institución) para catálogos; el score alto entre nombres genéricos NO es
  identidad.
