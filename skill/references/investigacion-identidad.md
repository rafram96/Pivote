# Investigación de identidad (Paso 6)

Objetivo: datos correctos para el contraste humano, no decidir si una experiencia
cumple requisitos. El investigador no reemplaza al evaluador ni al ingeniero.

## Preparación del coordinador

1. Confirmar modelo, esfuerzo y presupuesto de esta investigación con el usuario
   si no están acordados. No reutilizar una autorización antigua de otro piloto.
2. Obtener `preparar_investigacion_identidad(job_id)` por MCP. Guardar la respuesta
   exitosa en `paquete.json`; un 409 significa resultado inicial no disponible.
   Si el MCP no expone esta herramienta, indicar actualización pendiente: no
   reconstruir a mano una respuesta ni inventar su huella.
3. Para cada CUI distinto con acción `comprobar_fichas`, llamar una vez a
   `listar_fichas_infoobras(cui)`. Guardar respuestas completas en `listados.json`,
   objeto cuyas claves son CUI. Registrar fallos tal como llegaron; no fabricar
   listados vacíos como si fueran consultas exitosas. Puede reutilizarse la misma
   respuesta para otros casos del CUI en este lote.
4. Ejecutar desde la skill:

   ```sh
   node scripts/investigacion_identidad.js preparar paquete.json listados.json investigacion_nueva
   ```

   La carpeta debe ser nueva. El script crea `plan.json`, `lote.json` y una entrada
   por P/E/subobra. Encola pendientes, señales de ambigüedad y positivos cuyo
   listado no permite descartar varias fichas. Identificaciones por RUC y contratos
   seleccionados requieren contraste de intervención/rol/emisor incluso con ficha
   única. No se cambia automáticamente la selección vigente. Los restantes quedan **sin alerta
   en el listado consultado**, no verificados. Las privadas también se encolan:
   cotejar naturaleza del proyecto, no la forma jurídica del emisor. Paquetes
   históricos con privadas en `omitidos` no acreditan esa revisión: obtener uno nuevo.
5. Entregar a cada investigador solo su `entrada.json`, el prompt y acceso al
   certificado correspondiente o sus páginas originales. No entregar la propuesta
   completa, datos del postor ni resultados de otros investigadores. El contexto
   incluye documentos prioritarios con URL/IDs y, cuando existe, huella de la
   copia entregada. Facilitar esas copias desde el ZIP o los artefactos locales;
   no asumir acceso al disco del servidor. Acordar límite
   de casos y concurrencia dentro del presupuesto; los no ejecutados quedan
   pendientes. No utilizar Orca.
6. Cada investigador escribe `borrador.json` sin metadatos del lote dentro de su
   carpeta P/E/subobra. El coordinador adjunta esos metadatos y ejecuta el validador
   real (ejemplo para caso 1:1):

   ```sh
   node scripts/investigacion_identidad.js finalizar investigacion_nueva 1:1
   ```

   Solo produce `resultado.json` si pasa. No sobrescribe borradores ni resultados.
   Ante error, devolver el error concreto al investigador, como máximo dos intentos
   dentro del presupuesto; si persiste, dejar sin resultado, pendiente y explicar.
   No arreglar citas ni aceptar otro contexto para lograr una salida. `ai-cli
   validate` y un JSON sintácticamente válido no prueban este contrato.
   Después reunir los resultados:

   ```sh
   node scripts/investigacion_identidad.js consolidar investigacion_nueva
   ```

   Exit 0: todas las tareas tienen respuesta estructural; exit 2: cobertura parcial;
   exit 1: error de contrato/archivo. No sobreescribe informes: para reanudar,
   proporcionar como tercer argumento una ruta nueva de salida JSON.
   Revisar además `pendientes_documentales`: exit 0 NO significa que todos los
   adjuntos estén leídos. Cada referencia exige consulta propia con lectura y cita
   o un motivo explícito de no lectura. No clasificar por metadatos ni copiar
   conclusiones de una revisión de otro encargo que comparte el CUI.

## Fuentes y límites

Usar búsqueda MEF y lectura de fichas por MCP; complementar con navegación a
fuentes oficiales cuando sea necesaria y esté disponible. Claude in Chrome es
una opción si está conectado, no un requisito ni una conexión que se pueda asumir.
No evadir CAPTCHA. Registrar consulta bloqueada sin convertirla en inexistencia.
Los snippets y candidatos son pistas; la evidencia debe proceder de contenido
realmente leído, con URL/página y cita. No usar `descargar_documentos_cui` aquí:
aplicar una asociación a descargas es una acción distinta y explícita, descrita abajo.

Antes de utilizar posteriormente este informe, volver a obtener el contexto y
comparar `job_id` y `huella_contexto`: una propuesta de un estado anterior no es
aplicable silenciosamente al nuevo. El validador vincula respuestas al lote, pero
no comprueba por sí mismo que una cita sea verdadera ni consulta el job actual.

Reportar: casos investigados, propuestas, ambiguos, sin candidato, fuentes fallidas,
no ejecutados, sin alerta en listado, naturaleza privada cotejada/pendiente y
documentos pendientes. `cobertura: completa`
solo significa respuestas para todas las tareas, **no identidad correcta de todas
las experiencias**. Confirmar siempre `aplicado_al_job: false`.

## Aplicación explícita, después de investigar

Solo si el usuario pide aplicar asociaciones al job: usar
`aplicar_investigacion_identidad(job_id, resultados)` con los resultados validados
de los casos autorizados. Un diagnóstico, prueba o autorización para investigar
no autoriza esta llamada. No pasar todo un lote indiscriminadamente.

El backend vuelve a comprobar huella vigente, ficha exacta, proceso exacto y rol;
rechaza el lote completo si no puede comprobar una asociación. No reemplaza por
otro candidato. `ambiguo`/`sin_candidato` con consultas y motivo retiran la selección
anterior y dejan pendiente; `fuente_no_respondio` no demuestra ausencia y no se aplica.
No inventar OCID/nomenclatura para superar un rechazo. Contratos fuera de la fuente
OCDS quedan pendientes; esta vía no permite adjuntar URLs arbitrarias para descarga.

202 significa asociación guardada y actualización iniciada, no entregables completos.
Consultar `revision_estado`: solo `completada` acredita que terminó la publicación;
`descargas_estado=listas` por sí solo no basta. Excel y ZIP devuelven 409 mientras
se actualizan o si la publicación falla. Se respaldan las fuentes anteriores fuera
del ZIP. El backend relee la ficha exacta y recalcula contraste/cálculos auxiliares
sin volver a elegir proceso por fechas. SUNAT se consulta nuevamente para el emisor;
MEF se consulta en expedientes y solo se asocia un contrato por número y proceso
exactos. Los documentos 08-A siguen siendo candidatos hasta identificar su contenido
y encargo; no afirmar aprobación comprobada por la etiqueta. Un fallo o una asociación
pendiente no prueba inexistencia ni incumplimiento. No presentar esto
como dictamen. El informe de investigación original sigue siendo histórico;
guardar aparte el recibo de aplicación.
