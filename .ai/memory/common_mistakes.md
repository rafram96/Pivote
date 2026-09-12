# Errores ya cometidos (no repetir)

- **Corregir datos ampliando el formato sin consultarlo**: trasladar trazas de
  fuentes y advertencias genéricas a filas por experiencia recargó el Excel.
  Preservar el diseño acordado; motivos concretos en campos existentes, detalle
  técnico en los datos internos/API/ZIP. Nuevas secciones requieren acuerdo.

- **Confundir rótulo del adjunto con tipo/alcance del acto**: un enlace de
  aprobación puede entregar una memoria, un acta de terreno o un archivo
  vacío con HTTP200. La aprobación real también puede ser un formato firmado
  dentro de un informe largo, sin «SE RESUELVE». Clasificar el contenido y su
  objeto antes de extraer fechas o atribuirlo a una experiencia; preservar
  las discrepancias. Consultar la investigación privada enlazada en el
  handoff del5-sep antes de diseñar la descarga ampliada de expedientes.

- **Numerar por fechas cuando el evaluador usa el escaneado**: produce un
  aparente intercambio de experiencias aunque los documentos correspondan.
  Asignar n por página física principal antes de evaluar, y conservarlo en
  todas las vistas. No reparar renumerando solo Excel/ZIP ni el espejo ya
  evaluado: juicios, recortes y enriquecimiento están unidos por ese número.

- **Clasificar por un solo campo**: el tipo expediente/obra se leía solo de
  `proyecto`; el certificado dice "Elaboración del ET: «X»" y la skill guardaba
  solo «X» → 51/68 expedientes tratados como obra. Clasificar por TODA la
  evidencia (proyecto + objeto + cargo).
- **Usar el dato bajo auditoría para decidir**: el solape con el periodo
  declarado elegía la obra → podía lavar mentiras (ADR-003). Revisar esta
  trampa en cada señal nueva.
- **Más candidatos sin más disciplina**: fusionar la base MEF sin candados
  SUBIÓ los mal-resueltos de 16 a 26 (F6). Toda ampliación de recall necesita
  su contrapeso de abstención.
- **Resolver CUIs desde la skill**: ~3M tokens quemados en una corrida
  investigando 60 CUIs por web — trabajo que el backend hace en milisegundos.
- **`git add` de carpetas**: se colaron XLSX de una sonda (`tools/_sonda_seace/`)
  a un commit; hubo que amendear. Rutas explícitas siempre.
- **Fiarse del departamento para desempatar homónimos**: viven en el mismo
  departamento; y el MEF a veces registra la sede de la entidad, no la obra —
  por eso el veto exige provincia declarada en AMBOS lados.
- **Cola geográfica de 2 niveles**: "…, HUARI, ANCASH" — el término previo al
  departamento puede ser distrito o localidad, no provincia; inferir provincia
  solo con 3 niveles.
- **Prints Unicode en Windows**: la consola cp1252 revienta con `→`/emoji;
  reconfigurar stdout a utf-8 o usar ASCII.
- **Asumir que la verdad auditada es perfecta**: al menos 2 casos de la
  auditoría humana apuntan al CUI equivocado (Tocache/Loreto,
  Cotabambas/Antabamba) — ante discrepancia sistemática, cuestionar también la
  referencia.
- **Documentos comerciales al repo**: `docs/comercial/` está gitignored a
  propósito; no forzar con `-f`. **Y el repo es PÚBLICO**: no es una preferencia
  de orden, es que publicarías precios y cuentas por cobrar en internet, de forma
  irreversible (el historial queda). Antes de commitear un HTML nuevo, mirar si
  tiene montos, IP del servidor o postura de negociación. El 27-jul un dashboard
  con S/ 10,300 por cobrar y `192.168.100.5:8001` estaba en `docs/nuevos_modulos/`
  — la carpeta que se le comprime al cliente.
- **Crear issues sin leer `.ai/decisions/` primero**: el 27-jul se abrió la issue
  #50 re-derivando ADR-010 (decidido el 25-jul), con vocabulario distinto
  (`_meta.tipo_concurso` vs el real `concurso.tipo_evaluacion`) y reabriendo una
  pregunta que el cliente ya había cerrado (el concurso es homogéneo). **Antes de
  proponer un diseño, buscar en `decisions/` por el tema.**
- **Asumir que la skill instalada es la del repo**: durante 13 días
  `~/.claude/skills/` corrió una copia del 14-jul **sin el escudo de integridad**
  — podía subir corridas incompletas, que es justo la falla que el escudo arregla.
  Nada avisa cuando derivan. Hoy es un junction al repo; si alguna vez se
  reinstala como copia, la deriva vuelve.
- **`rm -rf` sobre un junction de Windows**: se recorre hacia adentro y borra el
  DESTINO. Así se perdió `backend/datos_pivote`. Para quitar un enlace:
  `cmd //c rmdir "<ruta>"` (sin `/S`) o `(Get-Item ruta).Delete()` en PowerShell.
- **Guardar respaldos dentro de `~/.claude/skills/`**: esa carpeta se
  auto-registra, y un respaldo aparece como skill invocable con la misma
  descripción que la real. Los respaldos van fuera.
- **Un candado que nunca dispara parece un candado**: `cumple_backend` llevaba meses
  escrito y jamás se calculó, porque el regex del mínimo solo leía «años» y las
  bases dicen «meses» (0 de 44 en los 3 concursos auditados). Un mecanismo de
  seguridad sin una prueba sobre datos REALES es decoración. Al escribir un
  extractor de texto de bases, probarlo contra los requisitos de varios concursos.
- **Redondear antes de comparar contra un umbral**: `anios_ef < minimo` con
  `anios_ef = round(dias/365, 2)` deja pasar 2.996 años como si fueran 3. Los
  umbrales se comparan en la unidad más fina que se tenga (días), no en la
  redondeada que se muestra.
- **Asumir la polaridad al pintar un veredicto**: `_fill_veredicto(v, "neg")` pinta
  VERDE un «NO CUMPLE» (la polaridad describe si el SÍ es bueno, no si el texto es
  bueno). Verificar el color antes de dar por buena una celda de alerta.
- **Dar por abierta una decisión sin leer el código**: la issue #51 planteó como
  «decisión de diseño pendiente» la distinción NO CUMPLE / revisión, que ya estaba
  implementada y bien razonada («⚖ Regla legal» en `etapas_reales.py`). Leer la
  implementación antes de proponer el diseño.
- **Deduplicar el entregable cuando el problema está en la descarga**: un almacén
  plano por SHA redujo el ZIP de 971 a 405 MB, pero obligaba al evaluador a buscar
  documentos con prefijos hash fuera de cada experiencia. En entregables humanos,
  preservar la navegación; eliminar solicitudes repetidas mediante caché por obra
  y materializar el árbol con hardlinks/copias.
- **Una contradicción que dispara por AUSENCIA de dato**: la señal «el código calzó
  solo contra el SNIP» se definió como `codigo != codUniqInv`, y una obra antigua
  registrada SOLO con SNIP (sin CUI) la disparaba — dos tests reventaron y en
  producción habría mandado a revisión resoluciones legítimas. Una contradicción
  exige el dato en ambos lados (la obra TIENE otro CUI); la ausencia es
  desconocido, no contradicción. Es la misma regla del guard de estado MEF.
- **Comparar una etiqueta por igualdad literal**: `factor == "A"` dejó de encontrar
  el Factor A cuando el consolidador pasó a emitir «A — Experiencia…» (#88). El
  puntaje quedó mudo tres semanas sin que ningún test lo viera, porque los tests
  usaban la etiqueta corta. Cuando dos módulos comparten un identificador que
  también es texto para humanos, extraer la clave con una función tolerante y
  probarla con el formato REAL que produce el emisor.
- **Dos parsers de fecha para el mismo dato**: el recálculo deducía «mes completo»
  y el reconciliador de días solo leía ISO de 10 caracteres; la experiencia
  desaparecía del total sin más rastro que un «fecha sin leer» en el motivo. Un
  dato con regla de interpretación (fechas parciales, tipos, etiquetas) se lee
  desde UNA función y todos los consumidores la importan.
- **Emparejar razones sociales por palabras sueltas contra un documento que habla
  del mismo lugar**: los consorcios se llaman como la obra («Consorcio Santiago»,
  «Consorcio Salud Chocope») y la resolución de aprobación nombra ese lugar en
  cada párrafo. Un criterio por tokens dio 10 «aciertos» que eran topónimos; por
  frase completa junto al rol quedaron 2 reales. Comparar nombres de empresa
  siempre como frase, y cerca de la palabra que les da rol (consultor, contratista).
- **Mismo establecimiento, otra intervención**: al abrir la vía por número de
  institución, el replay resolvió «renovación de alcantarillado en la I.E. 14325»
  para un certificado de «construcción de la I.E. 14325». El número identifica el
  lugar, no la obra. Toda señal de identidad por lugar (número, nombre de colegio,
  topónimo) necesita que la obra no añada un rubro ausente en el certificado. Y
  antes de promover una vía nueva: replay offline sobre un job real, siempre.
- **Ficha final distinta de la que descarga el ZIP**: actualizar solo el código
  visible en el Excel deja al descargador leyendo la búsqueda inicial. Persistir
  la ficha consultada como selección activa y la inicial como procedencia; probar
  el recorrido hasta ZIP, no solo la respuesta de búsqueda. Una marca `P/E.ok`
  sin identidad tampoco acredita que el corpus pertenezca a la ficha actual.
  Al cambiarla, retirar el corpus anterior de forma recuperable, incluso si la
  fuente nueva falla. Esto no demuestra que la selección semántica sea correcta.
- **Identidad no se decide con las fechas que se van a contrastar**: fijado un
  ID, preservarlo aunque el periodo difiera. En SEACE, objeto+temporal no bastan
  para confirmar, ni para obtener por circularidad un RUC adjudicatario. Al
  debilitar temporal, seguir mostrando su discrepancia en Excel/ZIP; «identidad
  confirmada» no significa «fechas coincidentes».
- **HTTP 200 no significa datos válidos**: JSON de error/HTML/login no es lista
  vacía. InfoObras además incluye un título de layout antes del título de ficha;
  probar contra HTML real y rechazar IDs contradictorios. Nunca inferir ausencia
  documental ni causa de cobertura solo desde falta de resultados.
- **Guardas que no viajan y pruebas con contexto fabricado**: una pluralidad
  detectada en el resumen debe quedar persistida para que el consumidor de fechas
  la respete; probar la cadena completa, no dos funciones aisladas. Un paquete de
  prueba tampoco puede rellenar el CUI declarado desde el utilizado ni cambiarse
  después de calcular la huella. Probar declaración, identidad/hash de adjuntos y
  comandos reales de finalización; JSON válido no verifica fidelidad semántica.
