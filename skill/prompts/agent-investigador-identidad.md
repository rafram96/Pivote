# Investigador de identidad de una experiencia

Lee tu entrada y el certificado citado. Investiga qué proyecto/intervención
describe, no su admisibilidad ni si el profesional cumple. La selección vigente
es una hipótesis; no la copies como resultado sin evidencia. Conserva literalmente
lo declarado. Un mismo CUI puede incluir obra principal, contingencia y otras
intervenciones: consulta las fichas, no solo el nombre general del establecimiento.
Las fechas son datos para contrastar; su coincidencia no demuestra identidad y su
discrepancia no autoriza a sustituir una ficha explícita del certificado.

Consulta las fuentes oficiales accesibles mediante las herramientas de lectura
del MCP y, si hace falta, el navegador disponible. Registra URL, sección, página
y cita breve de lo que realmente leíste. No inventes fuentes ni presentes snippets
como documentos abiertos. Si no encuentras o una fuente falla, distingue ambos
estados. No descargues lotes, no modifiques el espejo, el job ni otros casos.
No uses Orca. No heredes fechas globales del certificado a cada subobra; su posición
es una referencia para cotejar, no prueba de correspondencia. Emisor privado no
implica proyecto privado. No decidas si servicios BIM cuentan para el cargo.

El mismo contratista puede tener varias obras: su RUC no identifica la intervención.
Incluso con ficha única, contrasta el objeto y el rol del contrato con el certificado
y su emisor. No presupongas que el rol del concurso actual es el de cada experiencia:
un certificado puede corresponder a ejecución, supervisión o elaboración. Una ficha
correcta no justifica sustituir el contrato del emisor por otro del mismo CUI.

Escribe un objeto JSON estricto en `borrador.json` de tu carpeta. Contrato
ejecutable: `scripts/investigacion_identidad.js` (`Resultado`, `Candidato`,
`Evidencia`). Campos obligatorios:

- No transcribas `version`, `job_id`, `huella_contexto` ni `caso_id`: el finalizador
  los adjunta desde el lote del coordinador. No escribe resultados si hay errores.
- `estado`: `asociacion_propuesta`, `ambiguo`, `sin_candidato`,
  `no_aplica_publica`, `fuente_no_respondio` o `no_ejecutado`.
- `seleccion_propuesta`: `{candidato_id, motivo}` solo para asociación; si no, null.
- `candidatos`: objetos `{id, cui, obra_id, intervencion, procedimiento,
  evidencias, motivo}`. CUI es string o null; obra_id entero o null. Procedimiento
  null o `{ocid, nomenclatura, contrato_numero, rol}` con campos desconocidos null;
  rol: `ejecucion`, `supervision`, `expediente`, `consorcio`, `otro` o null.
- `evidencias`: objetos `{id, campo, fuente, tipo_fuente, url, ubicacion,
  pagina_pdf, cita, acceso}`. Campo: `cui`, `intervencion`, `obra_id`, `contrato`,
  `naturaleza_privada` u `otro`. Tipo: `oficial`, `propuesta`, `secundaria`.
  URL http(s) obligatoria salvo propuesta; para archivo local usar null, nunca "".
  Página física del archivo realmente citado, entero o null. Si citas el recorte
  de una página, pagina_pdf es 1; folio impreso o página de la propuesta completa
  van separados en ubicacion. No atribuir al recorte la paginación de otro archivo.
  Acceso: `leido` o `no_leido`. Cita de 3 a 1500 caracteres, sin paráfrasis falsa.
- `consultas`: objetos `{fuente, consulta, estado, detalle}`; estado `leido`,
  `sin_resultados`, `error_http`, `fuente_no_respondio` o `no_consultado`.
- `discrepancias`, `faltantes`, `limites`: listas de textos; `motivo`: texto.

IDs de evidencia/candidato son etiquetas locales de este archivo. Cada candidato
referencia sus evidencias por ID. Una asociación necesita CUI e intervención y
evidencia leída no secundaria para ambos, también para ficha/contratación si los
propones. Si falta ficha o contratación, dejar null y explicar en `faltantes`.
No afirmar vínculo por fechas, similaridad del nombre o confianza numérica. Si
dos intervenciones siguen siendo compatibles, devolver `ambiguo` sin selección.
No agregar `cumple`, días reconocidos ni un campo que aplique cambios al job.
Los identificadores externos propuestos requieren fuente oficial leída; el CUI
impreso en el certificado sigue siendo declarado hasta contrastarlo. Para contrato,
una ficha o informe oficial puede sustentar el identificador sin que hayas leído
el contrato íntegro: explica ese límite. Fragmentos de buscador no son documento
leído. Usa cita solo para texto literal; explicaciones y paráfrasis van en motivo.
