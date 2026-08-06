# Manual de usuario — Skill de análisis

## 1. Para qué sirve

La skill `analizar-licitacion-osce` lee las bases y la propuesta técnica de un
concurso, organiza la información del postor y sus profesionales y prepara:

- un **Excel de evaluación**;
- un **espejo JSON**, que permite al servidor verificar y recalcular;
- un **ZIP de constancias**, cuando la propuesta contiene los documentos que
  deben quedar como evidencia.

Después de la extracción, el servidor completa los cruces oficiales. La skill
no reemplaza esas verificaciones ni debe intentar resolverlas manualmente.

## 2. Antes de comenzar

Prepare una carpeta por concurso con las bases integradas y la propuesta
técnica completa. Los archivos deben ser legibles y no tener contraseña. Se
recomienda usar nombres simples como `bases.pdf` y `propuesta.pdf`, y no mezclar
documentos de concursos diferentes.

Confirme que Claude Code está abierto en la computadora autorizada, la skill
aparece disponible, el Panel responde en la red local y existe espacio libre
para los entregables.

## 3. Iniciar un análisis

En Claude Code, indique los archivos e invoque la skill. Ejemplo:

```text
/analizar-licitacion-osce C:\Concursos\Caso-01\bases.pdf C:\Concursos\Caso-01\propuesta.pdf
```

También puede solicitarlo en lenguaje natural. Si sabe que el concurso es de
**supervisión o elaboración de expediente técnico**, indíquelo como contexto;
el servidor aplicará las verificaciones compatibles con la evidencia.

No cierre Claude Code ni mueva los archivos durante la extracción. Una
propuesta extensa puede tardar porque cada profesional se revisa por separado.

## 4. Qué ocurre automáticamente

La ejecución:

1. comprueba si los PDF tienen texto y aplica OCR local si hace falta;
2. identifica requisitos, factores, postor y profesionales;
3. extrae periodos de experiencia y su ubicación documental;
4. compara la propuesta con las bases;
5. genera y valida los artefactos;
6. intenta subirlos al servidor por la red local.

El servidor continúa con los cruces aplicables:

- **ruta pública:** CUI/MEF, InfoObras o SEACE según el tipo, y SUNAT;
- **expediente público:** contrato, bases y resolución de aprobación cuando
  estén disponibles;
- **ruta privada:** constancia presentada y SUNAT; MEF, InfoObras y SEACE no
  aplican por el solo hecho de ser una obra privada;
- **establecimiento privado de salud:** puede añadirse RENIPRESS.

## 5. Si falla la subida automática

La corrida no se pierde. Ubique su carpeta en:

```text
%USERPROFILE%\InfoObras\analisis\<identificador-del-analisis>\
```

Allí deben quedar el espejo JSON, el Excel y, si corresponde, el ZIP. En el
Panel, abra el concurso, seleccione **Nuevo análisis** y use la carga manual.

Un error como `HTTP 401 token_expired` significa que venció la autenticación
del conector; no indica que el Excel o el backend estén dañados. Renueve la
sesión y reintente, o use la carga manual.

## 6. Cómo saber si terminó bien

La salida debe indicar consolidación y validación correctas. Luego, en el Panel,
el trabajo debe alcanzar un estado terminal. Revise:

- que estén todos los profesionales esperados;
- que las experiencias no se mezclen entre profesionales;
- que Excel y ZIP pertenezcan al mismo concurso;
- que **Por confirmar** tenga una razón comprensible;
- que una privada se rotule como ruta privada/SUNAT, no como búsqueda pública
  fallida;
- que un concurso mixto distinga cada subobra y su vía.

## 7. Significado de los estados

| Estado | Lectura correcta | Acción |
|---|---|---|
| Verificado | Las fuentes y candados sostienen la identidad | Revisar evidencia y continuar |
| Por confirmar | Falta identidad suficiente o hay contradicción | Resolver en la cola de revisión |
| Ruta privada / SUNAT | Las fuentes de obra pública no aplican | Confirmar constancia y RUC |
| Ruta privada / SUNAT pendiente | No existe un RUC único compatible | Mantener los días provisionales |
| Fuente no disponible | El portal no respondió tras reintentos | Reintentar; no asumir inexistencia |

## 8. Buenas prácticas

- Conserve los originales sin editar.
- No modifique el espejo JSON manualmente.
- No trate **Por confirmar** como incumplimiento automático.
- Descargue el Excel final desde el Panel: incorpora los cruces y recálculos del
  servidor y reemplaza al Excel inicial.
- Después de una revisión manual, vuelva a descargar el Excel.
