# ADR-010 · El tipo de concurso (A/B) es un PARÁMETRO declarado por la skill, no una inferencia del backend

- Fecha: 2026-07-25 · Estado: **aprobado, pendiente de implementar**
- Supersede parcialmente a **ADR-006** (la detección por texto y el env var
  dejan de ser el mecanismo principal; quedan como fallback/override).

## Contexto

ADR-006 introdujo dos mecanismos para distinguir expediente vs obra: la
detección por texto (`es_expediente_exp`: proyecto + objeto + cargo) y el modo
global `PIVOTE_FORZAR_EXPEDIENTES=1`. Ambos tienen problemas estructurales:

- La detección por texto es frágil: depende de que el certificado (y la
  extracción de la skill) conserven frases como "elaboración del expediente
  técnico" — el caso San Isidro demostró que se pierden (51/68 mal enrutadas).
- El env var es operativo (se fija al arrancar el backend), no viaja con el
  análisis: dos concursos de tipo distinto no pueden convivir en el mismo
  backend sin reiniciarlo.
- El dato REAL existe aguas arriba: la skill lee las bases del concurso y sabe
  desde el inicio si el objeto es A (expediente/estudio/supervisión de
  expediente) o B (supervisión/ejecución de obra). El cliente confirmó que un
  concurso completo es de un solo tipo.

## Decisión

1. **La skill declara el tipo** al producir el espejo: campo nuevo ADITIVO
   `concurso.tipo_evaluacion` con vocabulario cerrado
   `"expedientes"` (camino A) | `"obras"` (camino B), leído de las bases
   (objeto de la convocatoria). El campo entra al contrato espejo en sus 3
   copias (Pydantic `espejo.py` ↔ zod `espejo.js` ↔ TS `espejo.ts`) y al
   validador. Opcionalmente el endpoint `/api/pivote/analizar` lo acepta
   también como form-field (override manual desde el panel/dropzone).
2. **El backend enruta TODA la verificación por ese parámetro**: camino A →
   verificación MEF (contrato + resolución 08-A), hito de aprobación, sin
   exigencia/clamp de valorizaciones, descargas de secciones de expediente;
   camino B → InfoObras (valorizaciones, paralizaciones, días efectivos),
   descargas de secciones de obra.
3. **Precedencia**: parámetro del espejo > form-field > env
   `PIVOTE_FORZAR_EXPEDIENTES` (queda como override operativo y para replays
   de espejos viejos) > detección por texto (`es_expediente_exp`, último
   fallback para espejos sin el campo).
4. **El resolver de CUI se GENERALIZA**: es independiente del tipo. Su único
   trabajo es la IDENTIDAD del proyecto a partir del nombre de la experiencia
   y las señales duras (N° institución, RUC, ubigeo, entidad, rubro) — igual
   para A y B. El tipo solo gobierna la verificación posterior, jamás la
   selección (coherente con ADR-003). La normalización que quita el envoltorio
   ("Elaboración del ET: …") se mantiene como limpieza de texto, no como
   señal de enrutamiento.

## Alternativas consideradas

- **Solo detección por texto** (statu quo de ADR-006): frágil ante
  extracciones sin envoltorio; obliga al modo forzado como parche.
- **Solo env var**: no viaja con el análisis; imposibilita concursos de tipo
  mixto en paralelo y replays correctos.
- **Dos skills hermanas A/B** (propuesta del cliente): compatible — ambas
  desembocan en declarar este mismo parámetro; si se adopta, cada skill lo
  fija constante. La decisión 1-skill vs 2-skills sigue siendo comercial, no
  técnica.
- **Clasificar por experiencia individual dentro del concurso**: el cliente
  confirmó que el concurso es homogéneo; la clasificación por experiencia
  reaparecería solo si un caso real lo desmiente (requeriría ADR nuevo).

## Consecuencias

- Cambio de contrato espejo (aditivo): tocar las 3 copias + validador +
  consolidador de la skill; los espejos viejos siguen válidos (campo ausente →
  cadena de fallbacks del punto 3).
- La skill suma una instrucción barata (leer el objeto de la convocatoria en
  las bases — el agent-bases ya lo extrae) y el prompt debe fijar el
  vocabulario cerrado.
- `EtapaInfoObrasReal` deja de consultar `es_expediente_exp` por experiencia
  cuando el parámetro está presente; el clasificador por texto queda como
  fallback y para telemetría (discrepancia parámetro↔texto = observación
  INFO, útil para detectar bases mal leídas).
- El Excel/panel pueden mostrar el tipo del concurso (rótulo, no jerga).
- La golden del resolver NO cambia (la selección de CUI no depende del tipo).
- Pendiente al implementar: el filtro de secciones de descarga por camino
  (hoy camino A aún baja secciones de obra — tarea ya en backlog) se engancha
  a este mismo parámetro.
