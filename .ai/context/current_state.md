# Estado actual del proyecto

> Última actualización: **2026-08-10** · rama de trabajo: `demo`

## Archivos encontrados separados del estado de descarga (10-ago)

En las filas de valorización del Excel, `ARCHIVOS (ZIP)` consume ahora
`valorizaciones[].docs` y muestra `N archivo(s)`: expresa cuántos adjuntos halló
InfoObras, no cuántos llegaron a descargarse ni si la descarga está pendiente.
El inventario real y sus estados permanecen en `descargas_reales` para el
seguimiento operativo. Regresión explícita: 9 encontrados/2 descargados produce
`9 archivos`. Copia offline de `00a9816dc632`: P6 E4 conserva diez hitos con
`1 archivo` y no aparece `Pendiente`. Gate: **990 passed, 25 skipped**.

## Mínimos decimales y equivalencias explícitas corregidos (10-ago)

El parser compartido de mínimos ya reconoce decimales con punto o coma y, si
las bases escriben una equivalencia temporal explícita entre paréntesis, usa
esa unidad literal. Caso que destapó el defecto: job `00a9816dc632`, profesional
7, requisito `0.5 años (6 meses)`; antes quedaba `mínimo sin dato`, ahora se
normaliza a **180 días / 6 meses**. Un decimal sin equivalencia se convierte con
`Decimal` y redondeo hacia arriba para no crear un falso CUMPLE de borde.

Comprobación offline con reconciliación API y Excel temporal: mantiene `POR
VERIFICAR` y muestra `623 días provisionales contra un mínimo de 6 meses`; la
hoja `P7. Tic` contiene el mismo texto. El Uvicorn ya activo continuó durante la
auditoría las descargas diferidas del job y produjo su ZIP; no se restauró ni
sobrescribió ese avance. El `final.xlsx` real permanece generado por el proceso
viejo y todavía dice `mínimo sin dato`: requiere reiniciar backend y regenerar.
Gate: **990 passed, 25 skipped**; 140 focales + 1 skip.
`resolucion/cui.py` intacto, no aplica golden.

## Estado de versionado (7-ago)

El bloque P0 quedó registrado en ambos repos: Pivote en el commit que contiene
esta actualización y Panel-InfoObras en `1fcf2dd`. Gate final: **988 passed,
25 skipped**, TypeScript y build Next.js aprobados. Ambos árboles de trabajo
quedaron limpios; falta push y despliegue.

## Auditoría de lenguaje y alertas estructuradas del Panel (6-ago)

La interfaz aplica una capa común de lenguaje de evaluación sin alterar los
mensajes fuente. Códigos internos, nombres de etapas y referencias se convierten
en títulos, fuentes y ubicaciones legibles. `CARGO_NUCLEO` muestra cargo
declarado, función exigida, conceptos ausentes y necesidad de decisión del
comité; `RECALCULO`/`TOTAL` comparan días declarados y calculados; y
`FECHA_CONTRATO` muestra una secuencia de fechas y cuánto excede el margen de
15 días. También se retiraron menciones visibles a backend, Claude, espejo,
campos internos y servidor en las vistas principales.

Validación sobre CIBA `41a442cdcd81`: Brave + TypeScript + build Next.js
aprobados. El cambio es exclusivamente de presentación del Panel; no modifica
el job ni el resolver y no requiere golden. Panel dev activo en `:3002` y API
en `:8001` al cierre.

## Expediente técnico entendible en revisión y Profesionales (6-ago)

La revisión humana ya distingue la inversión (CUI) del servicio acreditado. Si
el certificado es de elaboración/supervisión de expediente, el Panel explica
qué verificará al confirmar y recomienda un candidato solo con señales
semánticas visibles (nivel educativo, unidad académica y ubicación), mostrando
también las diferencias de los demás; el puntaje interno nunca se presenta como
porcentaje ni como certeza.

Después de resolver, Profesionales muestra un bloque propio de **Verificación
SEACE/MEF del expediente**: empresa y firmante declarados por separado,
contratista, contrato, objeto, fecha, monto, aprobación, CUI y fuentes. La
ejecución física de InfoObras queda rotulada como referencia posterior que no
acredita quién elaboró el expediente. Jobs antiguos se renderizan con los datos
del espejo aunque su enriquecimiento no tenga los nuevos campos.

Se corrigió además `scraping/mef.py`: el contratista estatal se coteja primero
con `entidad_emisora` (empresa) y solo usa `nombre_emisor` como fallback para
persona natural/legado; el firmante queda informativo y separado. No cambió el
resolver CUI, por lo que no aplica golden. Gate: **988 passed, 25 skipped**;
Panel con TypeScript y build productivo aprobados; caso CIBA `1:9` revisado en
Brave sin resolver ni modificar el job.

## P0 del Panel: una sola verdad para resultado, alertas y salud (6-ago)

El backend reconstruye ahora el resultado efectivo desde `espejo.json` y
`enriquecimiento.json` para que `/espejo`, `/resumen`, la corrida normal y la
regeneración del Excel compartan el mismo cálculo. En jobs antiguos sanea las
paralizaciones que no aplican a expedientes/privadas y mantiene «Por confirmar»
si SUNAT o una fuente pública no sostienen la conclusión. El contrato añade
`estado_efectivo`, `veredicto_efectivo`, `total_efectivo` y
`conteo_alertas`; el Panel dejó de interpretar la prosa original de Claude.

También se eliminó el doble conteo visual de observaciones, la métrica principal
pasó a «Requieren atención» y `base_mef=stale/refresco_fallido` se presenta como
advertencia utilizable, no como portal caído. CIBA `41a442cdcd81`: 0 cumple / 0
no cumple / 9 por confirmar; alertas 21 atención + 55 advertencias + 61
informativas. `final.xlsx` fue respaldado en
`backups/pre-p0-panel-20260806-161623/` y regenerado sin red: 12 hojas, 129
imágenes. Gate backend: **987 passed, 25 skipped**; resolver intacto, no aplica
golden. Panel: typecheck y build productivo aprobados.

## Idea futura T-018: explorador SEACE por CUI (6-ago)

Registrada como trabajo cross-repo en Pivote #84 y Panel #2. Formatea OCDS en
una ficha determinística y permite descargar documentos desde el Panel; no usa
IA, no modifica análisis y no reemplaza T-016. Estado discovery, sin cotizar.

## Issue #83: RUC del emisor vía adjudicatario SEACE (6-ago)

Implementada y versionada localmente en `31572d3` como mejora incluida de
T-010/F5. El proceso SEACE
conserva nombre y RUC del adjudicatario; SUNAT puede verificar, confrontar o
enriquecer el RUC sin circularidad y se abstiene ante zona gris. Compatibilidad
con jobs antiguos y pre-2018 cubierta. Gate: 985 passed / 25 skipped; resolver
CUI intacto. Falta push, despliegue verificado y cierre de la issue.

## Documentación de entrega (6-ago)

Está preparado el borrador en `docs/entrega-final/`: manuales de skill, Panel y
base MEF, más setup de instalación. La guía comercial privada vive en
`docs/comercial/` y permanece fuera de git. Corresponde revisarlos durante el
smoke real y ajustar direcciones o capturas finales antes de entregar.

## Auditoría CIBA: privadas SUNAT + certificados multi-obra (6-ago)

- Ruta privada corregida: 26/40 experiencias con RUC SUNAT inequívoco quedan
  efectivas; 14/40 quedan provisionales y explícitamente etiquetadas como
  revisión privada/SUNAT pendiente.
- Excel real `41a442cdcd81` regenerado solo desde `espejo.json`,
  `enriquecimiento.json` y certificados ya descargados: 12 hojas, 129 imágenes.
- API del espejo ampliada con `sub_obras` y `multi_rubro`; Panel implementado y
  compilado. PANEL#1 pendiente únicamente de publicar cambios y desplegar.
- Gate local: 974 passed, 25 skipped; build Next.js aprobado; resolver intacto.

## Camino mixto: expedientes públicos y obras privadas ya no parecen fallos (6-ago)

Corregido el cruce que todavía enviaba expedientes a revisión cuando sus fechas
precedían las valorizaciones de la construcción: el camino A ya no hereda ni
`cobertura_baja` ni paralizaciones de la ejecución física. La marca `PRIVADA`
con RUC SUNAT inequívoco dejó de convertir los días en provisionales: es una
ruta distinta de verificación, visible en Base de Datos, hojas profesionales y
Cronología como «InfoObras/MEF/SEACE no aplican; SUNAT + certificado». Sin RUC
único se usa `PRIVADA_PENDIENTE` y el tiempo es provisional. El resolver CUI quedó
intacto; la clasificación auditada de la corrida real permaneció en su job
gitignored y no entró al repo. Gate: **971 passed, 25 skipped**.

## Camino A (expedientes) comprobado: núcleo OK, 2 huecos de enrutado (6-ago)

Comprobación offline con el código real (`docs/pruebas/camino-a-expedientes-
comprobacion.md`): la clasificación reconoce las 3 variantes (elaboración ET /
estudio de preinversión / supervisión del ET), la verificación MEF 08-A y la
aprobación InfoObras operan, y el gate anti-circularidad de la Regla B se
abstiene correctamente ante contratista en discrepancia. **Los 2 huecos**
(registrados como comentario en la #70): `tipo_esperado()` devuelve siempre
`expediente` para toda la familia, así que estudio de preinversión y
supervisión del ET caen en `sin_tipo` — abstención honesta, pero sin candado
F5, sin Regla A y sin Bases/Contrato en el ZIP. El fix se decide dentro del
diseño de #70 (toca el requisito «no cruzar de tipo»). Además quedó feedback
de presentación de Rafael: el bloque de cruces en las hojas P es difícil de
leer → T-TAREA-CRONOLOGIA-VERTICAL en el backlog (formato por diseñar).
Se generaron dos Excel de demostración sintéticos (camino B y camino A, 3
profesionales / 4 CUIs cada uno) con el generador real del backend.

## Backlog de issues consolidado: #49 + #71 → #82 (6-ago)

Por orden de Rafael se cerraron **#81, #5, #27, #24** (completadas, con commit y
evidencia) y **#25** como *not planned* (NO-GO medido, condiciones de reapertura
en la propia issue). Después, #49 y #71 —que se pisaban— se fusionaron en la
nueva **[#82 «Analisis Ahorro de Skill»](https://github.com/rafram96/Pivote/issues/82)**,
que junta el diagnóstico a nivel de código de #49 (inventario de la
implementación en sombra, medición 33/34 del divisor, conteo de prompts) con la
línea base y el diseño de #71 (Vitarte 1.59M por agente, `/cost` USD 31.12 con
35M cache reads, candidatos C1–C6 con numeración unificada, R0, metas y gates).
Toda mención anterior a #49/#71 en este archivo es histórica y apunta ahora a
#82 (= T-013 en el registro económico, ya actualizado). Quedan abiertas solo
**#70, #50 y #82** en Pivote + PANEL#1.

## El fallo del refresco del MEF deja de ser silencioso (#24, 5-ago)

Conservar la carga anterior cuando el ETL falla ya estaba bien (#21/#22); lo que
faltaba era que alguien se enterara. Cada corrida —termine bien o mal— se anota
ahora en `bitacora.json` (`resolucion/bitacora_mef.py`), con la causa del fallo
ya clasificada por `errores_red.clasificar()`. El umbral es
`PIVOTE_MEF_DIAS_FRESCURA` (**default 10 días**: la tarea es semanal, así que 10
delata UNA semana saltada al miércoles siguiente sin protestar por un domingo con
retraso), y el aviso sale por **tres superficies que ya existían**, sin vistas
nuevas: `/api/pivote/salud`, el buscador de #27 (HTTP y consola) y una
observación `BASE_MEF_DESACTUALIZADA` en el análisis. Con la base al día nadie es
molestado — es la condición para que el aviso se lea el día que aparezca.
`BaseMef.frescura()` es el punto único (barato: dos archivos, sin PG ni índice).
**Instalar el cron sigue siendo tarea del deploy**; el simulacro está en el
runbook §10.

## #25 medida: paralelizar N profesionales NO vale la pena (5-ago)

Recomendación **NO-GO**, esperando decisión de Rafael. Medido offline sobre los 7
concursos reales de `datos_pivote` (333 experiencias): el **97,9 %** del tiempo
de la etapa de resolución es espera del portal InfoObras; el bucle local cuesta
**0,6 ms por experiencia** y la base MEF **≤ 5,8 s por concurso** (p50 82 ms,
p95 204 ms) — o sea **0,4 %–1,7 %** de un análisis que dura de 3 a 21 minutos.
Techo de Amdahl de lo que la regla del proyecto permite paralelizar (solo base
local): ×1,004–×1,017. Y hoy `BaseMef` serializa `buscar_candidatos()` con un
`RLock` de instancia, así que un pool daría literalmente ×1. Evidencia y riesgos
en `docs/pruebas/issue25-medicion-paralelismo.md`; reproducible con
`backend/scripts/medir_paralelismo.py`. Donde sí está el tiempo: las descargas de
InfoObras y SUNAT — y ahí la palanca es **bajar menos**, no concurrir más.

## La base MEF se puede consultar, y el MCP sabe buscar y descargar (5-ago)

**Issues #27 y #5**, las dos aprobadas por Rafael. Un núcleo
(`resolucion/busqueda_mef.py`) con dos bocas —`GET /api/pivote/mef/buscar` y
`python -m scripts.buscar_mef`— saca el índice de 579.481 CUIs de dentro del
resolver: hasta ahora nadie más podía preguntarle nada. Un código exacto gana
sobre la búsqueda difusa; los filtros se aplican **también** al acierto por
código y **antes** de cortar por `limite`; la base ausente responde 200 con
`base_mef_no_disponible` (no un 500), y lo inválido de la consulta sigue siendo
400. `resolucion/cui.py` intacto: esto es consulta, no resolución de identidad.

La descarga por CUI **ya era** un trabajo asíncrono con estado en disco (eso no
hubo que inventarlo); lo que faltaba era decir algo mientras corría, y ahora
cada tramo se persiste apenas empieza (`paso`). El MCP ganó las tres tools que
el cliente pidió en la reunión del 06-jul —`buscar_cui`,
`descargar_documentos_cui`, `consultar_descarga_cui`— que contestan en
castellano de evaluador (`mcp-server/textos.js`, con prueba que prohíbe la
jerga) y **jamás mandan un archivo por el chat**: se devuelve la dirección del
ZIP. Comprobación a mano en `docs/pruebas/issue5-27-comprobacion-manual.md`.

Latencia medida y publicada en la respuesta (`ms`), en vez de prometida: 12 ms
por código, ~250 ms por nombre amplio, y ~66 s la primera consulta de cada
proceso porque carga el índice.

## Reintentos unificados (5-ago)

**T-REFACTOR-001** cerrada: los 15 bucles de reintento artesanales del scraping
pasaron a un único `con_reintentos()` en `scraping/errores_red.py`, con
`Resultado.respondio` separando «respondió vacío» (dato) de «no respondió»
(incógnita) — y `Resultado.__bool__` lanza `TypeError` para que el error del caso
6:1 no se pueda volver a escribir. Contratos externos intactos; `cui.py` sin
tocar. Decisión y alcance en `decisions/ADR-014-reintentos-unificados.md`.

## Nombres de empresa: el paréntesis del membrete ya no decide identidad (5-ago)

**T-REFACTOR-002 parte 1** (opción mínima, decisión de Rafael «la mínima ahora y
la doble corrida después»): el prelimpiado de nombres salió de
`etapas_reales._nombre_emisor_limpio` a `scraping/nombres_empresa.py` y ahora lo
usan también el candado SEACE y la verificación de expedientes del MEF; los dos
comparadores conservan su criterio y se puntúan ambas formas del nombre, así que
el cambio es monótono (ningún `ok` puede volverse `no_verificable`). Divergencias
entre comparadores 534 → 521 sobre 3.736 pares (25 → 18 en los 294 pares 100 %
reales). La **doble corrida** queda aprobada para post-deploy, con mini-golden de
~120 pares como pre-requisito — evidencia completa en `tasks/backlog.md`.

## ADR-009 cerrado: Postgres es OBLIGATORIO, y schema.sql ya no miente (5-ago)

Rafael cerró el estatus global (**T-REFACTOR-003** + **F-SCHEMA**): PostgreSQL es
obligatorio en el despliegue por la **base MEF** (uso principal; el respaldo
lógico de jobs es secundario), la degradación con gracia en código se conserva a
propósito —un PG caído no tumba nada, pero es un estado anormal— y el write-path
bloqueante (B02) y la falta de cola de re-sincronización (B01) quedan anotados
como deuda consciente, no como resueltos. `backend/db/schema.sql` pasó de
esquema aspiracional incompatible a **espejo documental** de los dos DDL reales
(`mef` primero), con un test offline que impide que vuelvan a divergir. Detalle
en el addendum de `decisions/ADR-009-migracion-postgres-mef.md` y en
`tasks/completed.md`.

## Deuda técnica del sondeo, saldada (5-ago)

Tres tareas chicas cerradas en un tren: **B03-fix** — un Postgres caído ya no
impide arrancar el backend (el pool y el DDL se abren en el primer uso, no en el
import de `app.py`; si la BD no responde queda UN warning y se opera 100% sobre
archivos); **T-TAREA-001** — saneo documental de la zona backend (el README de
`scraping/` era el de otra carpeta y daba ALT-12 por viva, la cabecera de
`cui.py` describía el resolver del prototipo, y «la vista SQL» que dos docs
listaban como consumidor del contrato no existe en ninguna BD real); y
**T-TAREA-002** — borradas las 483 líneas del segundo resolver de CUI por nombre
que dormía al final de `scraping/infoobras.py` (`min_score=15.0` y «aún así
retornamos el mejor», sin un solo caller). Gate: **866 passed, 25 skipped**
(base 865 + 3 pruebas nuevas de B03 − 2 que se fueron con el código borrado).
Detalle en `tasks/in_progress.md`.

## Pulido del entregable: el Excel ya no se contradice a sí mismo (5-ago)

Cuatro defectos salidos de leer celda por celda el Excel real de Vitarte
(`7e9306a321ac`) quedaron cerrados. Un factor cuyo puntaje se retira ya no deja
la celda muda —dice **POR CONFIRMAR**— y la NOTA de la PARTE 5 **se arma con las
mismas celdas que se imprimen**, en vez de repetir un texto redactado antes del
recálculo que decía «80/100» sobre una tabla que sumaba 40. La conclusión del
profesional y su PARTE 5 dicen **una sola cifra**: la prosa del evaluador se
conserva literal y se le antepone el total verificado, pero solo cuando la
diferencia es demostrablemente la del conteo de bordes (el verificado mayor y
por como mucho un día por periodo) — un recorte del Paso 5 no se explica como
conteo de días, se abstiene. La jerga desapareció del libro: `TOTAL EFECTIVO
VERIFICADO`, las marcas del cargo dicen en castellano qué pasa en vez de
«candado:», y un test de cierre exige **cero** apariciones de `backend`,
`candado:`, `espejo`, `⟦` y `agent-` en cualquier celda. Y el amarillo dejó de
significar dos cosas: FFFF00 queda para el dato declarado / la valorización en
periodo / separadores / encabezado CERT, y todo lo que significa «por verificar»
usa FFF2CC, con la leyenda de las hojas P declarando por fin ese color y el
verde. Quedan fuera por decisión explícita la leyenda de Base de Datos y los
tres rojos.

Alcance verificado regenerando el libro con `4157814` y con el código nuevo:
**105 celdas distintas**, todas de los cuatro arreglos (14 rótulos, 22
conclusiones, 14 leyendas, 50 fills y 5 de la PARTE 5 / saneo). Aparte,
`avance_descargas.py` y `redescargar_documentos.py` —que siguen escritos contra
el layout plano— **abortan** al detectar un job del layout por carpeta, con
`--forzar` para el caso histórico: antes trabajaban en un sitio que ni el Excel
ni el Panel miran. Gate: **865 passed, 25 skipped** (base 837/25), sin red,
`cui.py` intacto, Panel y skill sin tocar. Comprobación manual:
`docs/pruebas/pulido-excel-comprobacion-manual.md`.

## T-004 F5: candado de identidad CUI↔proceso construido (5-ago)

Elegir el proceso SEACE por CUI+tipo ya no basta para presentarlo como
verificado. `backend/validacion/candado_seace.py` cruza cinco señales —entidad
convocante, RUC del adjudicatario contra el emisor del certificado, objeto,
fechas y monto— y deja un veredicto ternario en `seace.candado`: `confirmado`
exige ≥2 señales fuertes a favor y cero en contra; una sola señal fuerte en
contra degrada a `contradice`; todo lo demás es `por_confirmar`. La zona gris de
similitud (60–84) se abstiene, nunca decide. La descarga NO se bloquea: los PDF
siguen yendo al ZIP y lo único que cambia es el rótulo del Excel y del índice.
El comparador de razones sociales es el de `scraping/sunat.py`, reutilizado.

La señal temporal es **día-exacta** con tolerancia de 15 días; jamás se trunca a
mes. El clamp del Paso 5 no se tocó.

Dos defectos reales salieron a la luz y quedaron corregidos: la ventana del
proceso se tomaba de `contracts[0]` (arbitrario — en el CUI 2343407 era una
adenda de dos días de 2024 y marcaba «NO COINCIDE» dos experiencias legítimas),
y los tres `*_ERROR.txt` de Bases Integradas del job Vitarte no eran caídas del
host sino `extension_documento` leyendo `format` sobre un bloque que persiste
`formato`; con la extensión correcta el ZIP y el RAR bajan sin problema.

Hallazgo del Paso 0: el CUI 2300016 (Hospital del Altiplano) publica 14 procesos
y los 14 son adquisición de equipamiento biomédico. No existe su proceso de
supervisión en datos abiertos con ninguna nomenclatura — el selector acierta al
abstenerse. Comprobación manual en `docs/pruebas/f5-comprobacion-manual.md` con
el CLI `backend/scripts/probar_candado_seace.py`. Gate: **789 passed, 25
skipped** (base 757/25), resolver intacto, sin golden y sin despliegue. Queda
pendiente la corrida integral en el servidor.

## T-011: cruces de fechas contrato/expediente ↔ certificado (5-ago)

Las fechas que F5 identificó ya se usan para preguntar dos cosas al motor de
alertas existente: **el inicio declarado no puede anteceder a la firma del
contrato** (tolerancia 15 días, la MISMA constante del candado — una sola vara)
y, en expedientes, **el término declarado no puede ser posterior a la resolución
que aprobó el expediente** (tolerancia propia de 30 días, que cubre el cierre
administrativo). Aritmética día-exacta: 05/01 contra una firma del 30/01 son 25
días sin respaldo aunque compartan enero. Motor puro en
`backend/reglas/cruces_fechas.py`; disparan `Observacion` ALERTA
(`FECHA_CONTRATO` / `FECHA_APROBACION_ET`) y nada más — una abstención se
persiste con su razón y jamás levanta alerta.

Lo que decide el diseño es el **gate anti-circularidad**: una regla solo habla
cuando la identidad de su fuente está confirmada por señales **independientes de
la fecha que va a cruzar** (entidad/adjudicatario/objeto para la A; que el MEF
confirme al proyectista para la B). Exigir literalmente `candado == confirmado`
habría dejado la regla A muda para siempre, porque la señal temporal del candado
usa esas mismas dos fechas: un desfase real deja el candado en `contradice` y la
regla no podría pronunciarse nunca. Con el gate por señales independientes, la
regla dispara justo ahí —proceso confirmado por lo demás, fechas que no
cuadran— y se abstiene ante cualquier otra contradicción. Es el CASO 0 de
`T-TAREA-RUC-ADJUDICATARIO` aplicado a fechas (familia ADR-005).

El entregable suma una hoja **ADITIVA** al final, «Cronología de expedientes»:
ficha por proyecto (proceso, firma, vigencia, resolución de aprobación con su
procedencia, modificaciones de plazo) y tabla comparativa por experiencia. Las
hojas del formato congelado no se movieron — comprobado regenerando Lircay
(`371fa5a1e704`, sin datos SEACE) con `HEAD` y con el código nuevo: 19 hojas
idénticas celda por celda. Un job sin fuentes genera la hoja igual, con la nota
«Sin procesos verificables». Replay Vitarte: 31 experiencias, 9 cuadran, 0 no
cuadran, 22 se abstienen (21 por cobertura pre-2018, 1 por identidad
insuficiente). Comprobación manual en
`docs/pruebas/t011-comprobacion-manual.md`.

Rafael revisó la hoja y aprobó el **híbrido**: la vista de conjunto se conserva
y, además, cada hoja P lleva bajo la PARTE 5 un bloque de cruces con una entrada
por experiencia (las que no tienen proceso publicado aparecen con su abstención
rotulada, no desaparecen). Las dos vistas leen `presentacion_cruces` — una sola
fuente de textos, fechas y colores. `CLAUDE` y `Base de Datos` siguen
byte-idénticas; las hojas P cambian por decisión explícita y solo por apéndice
(cero contenido preexistente perdido, verificado contra `70f39bf` sobre Lircay).
Gate: **826 passed, 25 skipped** (base 789/25), resolver intacto, panel sin
tocar, sin despliegue.

## ZIP #80 resuelta: caché por obra y árbol completo por experiencia (4-ago)

La deduplicación quedó en la **descarga**, no en la entrega. Cada job guarda el
corpus completo una sola vez en `cache_obras/{obra_id}/`, lo publica únicamente
con marca `.completa` y materializa cada P/E mediante hardlink con fallback a
copia atómica. Los informes de control se descargan completos y se filtran
localmente por el año inclusivo del certificado. SEACE conserva su caché global
separada por `fileCode`; InfoObras no cruza jobs porque su evidencia cambia.

El ZIP mantiene PDF reales navegables en cada experiencia, manifiesto SHA-256,
estados legibles e índice que compara compartidos solo dentro de la misma obra.
Replay offline Vitarte: **1,205 PDF, 29 manifiestos, cero almacén central**, ZIP
íntegro de 971,718,423 bytes. Gate consolidado y verificado de primera mano:
**748 passed, 25 skipped** (+5 pruebas de caché).

El manifiesto es opcional desde `PIVOTE_MANIFIESTOS_ZIP` (default `1` = se
genera, conserva el contrato de la #80; `0` = no se escribe ningún
`MANIFIESTO_DOCUMENTOS.txt` ni la línea que lo anuncia en el encabezado del
`indice.txt`). Es un documento de verificación TÉCNICA y el entregable lo
consume un equipo de evaluación no técnico; el SHA-256 se calcula siempre
porque los conteos de compartidos/propios del índice dependen de él.

El formato del índice se elige con `PIVOTE_INDICE_ZIP` (lista separada por
comas: `txt` default y byte a byte compatible, `md` legible por profesional con
el nombre completo de la obra, `json` estructurado; `0` = sin índice). El bucle
del ZIP arma un registro de datos por experiencia y cada formato se renderiza
desde ahí, así que agregar uno nuevo no duplica lógica.

Los documentos SEACE se llaman `BASES_INTEGRADAS.*` / `CONTRATO_FIRMADO.*` (sin
el prefijo `SEACE_01_`/`SEACE_02_`, que hacía que el recorte a 38 del ZIP
mutilara las notas `_NO_DISPONIBLE`/`_ERROR`); los nombres viejos se siguen
reconociendo en disco y los avisos del índice usan rótulo legible
("Bases Integradas (SEACE)"). Fuente única: `DOCUMENTOS_SEACE` en
`backend/orquestador/descargas_seace.py`.

Las 5 brechas de resiliencia registradas al cerrar la #80 quedaron **todas
resueltas o descartadas** (detalle abajo, «Bloque R»):

1. Marca `.completa` ante errores transitorios → **resuelta** (#81 R1).
2. Usabilidad del layout ZIP por Obra/Sección → **descartada**: el correctivo de
   la #80 (árbol completo por experiencia) ya la resolvió; no reintroducir
   `DOCUMENTOS_COMPARTIDOS/`.
3. Texto del índice para informes fuera de periodo → **resuelta** (#81 R3).
4. Recolección de `.part` huérfanas → **resuelta** (#81 R4).
5. Reuso de caché en `descargar_cui` → **resuelta** (#81 R5).

## Bloque R #81: la caché de descargas ya es reintentable (5-ago)

**R1 — una sección caída ya no se congela.** La entrada de `cache_obras/{obra}`
tiene dos estados: `.completa` (todo sano, se reutiliza sin tocar la fuente, y
las publicadas por versiones anteriores siguen siendo válidas tal cual) y
`.parcial` (alguna sección con `{"error": true}`). Ante una entrada parcial, el
siguiente pedido de esa obra **clona lo sano por enlace duro y re-descarga solo
las secciones fallidas**, fusionando el estado (avisos de una sección caducan
con ella). El corpus publicado se borra recién antes del `os.replace`, así que
un reintento que revienta deja intacto lo anterior. La sección principal también
se atrapa: un fallo suyo ya no tira el corpus entero. La experiencia cuyo corpus
quedó parcial **no** recibe su marca `.ok` — la siguiente pasada (otra
experiencia de la misma obra, una revisión o una reanudación) la completa, y
mientras tanto la barra del panel la cuenta como pendiente, que es la verdad.
Resolver una revisión llama a `purgar_secciones_en_error`: degrada la entrada a
`.parcial` y borra lo de las secciones caídas — también sobre una marca
`.completa` heredada, el caso que un evaluador no podía desatascar. Las entradas
de obras que cambiaron de resolución quedan huérfanas a propósito (no molestan y
se van con el job).

**R3 — textos de evaluador.** El índice distingue «no hay informes publicados»
de «los hay, pero de otros años»: el manifiesto guarda `publicados` (inventario
completo por año que ya traía la descarga) y la sección dice *«los informes de
control publicados no corresponden al periodo de este certificado (N publicados,
todos de otros años)»*, con singular propio. Una sección que ni pudo listarse
dice *«la fuente no respondió en esta corrida (se puede reintentar)»* en vez de
un `(0/0)`. Las notas SEACE son frases completas con fuente única
(`NOTA_SEACE_DESCARGA_FALLIDA` y `nota_seace_ausencia` en `descargas_seace.py`),
conservando la distinción reintentable/definitivo.

**R4** — `CacheDescargasInfoObras.recolectar_temporales()` borra los
`.{obra}.{uuid}.part` al arrancar la descarga del job.

**R5** — `descargar_cui` corre sobre la misma caché (alcance: **la descarga en
curso**, carpeta hermana de la de entrega; D3 de la #80 intacta: nada de caché
global con datos que caducan) y su reporte suma **todas** las secciones, con
`secciones`/`avisos` en el estado del endpoint. Antes decía «0 fallidos» aunque
se cayeran informes, cierre o aprobación enteros.

Gate: **837 passed, 25 skipped** (línea base 826), sin red, `cui.py` intacto.
Comprobación manual: `docs/pruebas/bloque-r-comprobacion-manual.md` +
`backend/scripts/probar_cache_descargas.py` (modos `notas`, `informes`,
`reintento`, `part`).

## Auditoría EsSalud y correcciones #32, #72–#79 (4-ago)

El pipeline ya no presenta como verificado el tiempo de una experiencia sin
cruce: persiste la abstención del resolver, propaga `POR VERIFICAR`, usa amarillo
en lugar de cyan y muestra una conclusión en cada hoja profesional. ALT04 usa el
histórico HABIDO para distinguir reinscripción de anomalía. La aritmética
inclusiva sobrescribe las cifras del evaluador después de auditar la diferencia.

Factor A cuenta únicamente `dias_efectivos - minimo_dias`, excluye provisionales
y retira el puntaje heredado cuando falta la rúbrica estructurada. La skill
transporta `factor_a_aplica`; su prompt exige la página del desarrollo del Factor
A, y Excel rechaza recortes con texto de otros factores. Base de Datos vuelca el
CUI resuelto con comentario de procedencia y explicita colegiatura pendiente.
También quedaron saneo visible de portal/SUNAT, controles de duplicados,
retrocesos, monto y fin de obra, detalle de descargas, deduplicación de fichas y
paleta sin colisiones semánticas.

Replay corregido en Descargas; no se tocaron los datos gitignored del job. Gate:
**742 passed, 25 skipped** + **54/54** Node. Sin golden por pérdida del corpus;
el resolver solo cambió en dirección resuelto/implícito → revisión explícita.

## Compatibilidad pre-push cerrada (3-ago)

Los cuatro defectos adversariales de la ronda de auditoría quedaron corregidos:

- un job anterior al campo `confiabilidad` ya no recibe una banda roja falsa al
  regenerar su Excel; solo un veredicto explícito produce la banda;
- el avance de descargas cuenta experiencias procesadas aunque legítimamente no
  tengan documentos y recupera jobs antiguos desde sus marcas `.ok` por fuente;
- SUNAT ambiguo muestra en el panel el número de coincidencias y sus candidatos,
  en vez de degradarse a «sin datos»;
- el ZIP individual por CUI omite archivos temporales `.part`, igual que el ZIP
  principal.

No cambió el resolver CUI; no aplica golden. Gate: **738 passed, 25 skipped**,
`compileall` y diff limpios; Panel con TypeScript y build productivo aprobados.
No hubo push ni despliegue.

## Cierre de auditoría de entregables y panel (3-ago)

La `demo` deja de presentar como completos resultados que solo estaban
inventariados o que no habían pasado el escudo de integridad:

- `Job` persiste `confiabilidad` y `hallazgos_criticos`; el resumen del panel y
  la hoja CLAUDE muestran explícitamente `revisar`, `no_confiable` o
  `no_revisable`. El Excel no queda con apariencia normal ante un crítico.
- Cada experiencia guarda `descargas_reales` en el enriquecimiento: archivos
  efectivos, conteo por hito, secciones y avisos. El Excel se regenera después
  de descargar; el ZIP fuerza `SIN_DOCUMENTOS.txt` si no quedó ningún documento
  utilizable y `indice.txt` enumera fallos y secciones incompletas.
- El panel muestra RUC, razón social, estado/condición, HABIDO e histórico SUNAT;
  incorpora RENIPRESS como novena etapa, muestra `en_revision` en Descargas y
  traduce errores/diagnósticos técnicos a lenguaje de evaluador.
- Excel sanea ambas marcas `⟦crudo:`/`⟦Claude:`, siempre hace visible un puntaje
  total ausente y extiende el violeta de procedencia a hitos y Parte 5.

No cambió `backend/resolucion/cui.py`; no aplica golden. La hipótesis de que un
`.part` entre al ZIP por el orden de `.ok` sigue descartada; adicionalmente el
empaquetador omite cualquier `.part` que aparezca por estado externo anómalo.
Gate: **736 passed, 25 skipped**, focales posteriores **5/5**, `compileall` y
`diff --check`; Panel: `tsc --noEmit` y build productivo aprobados.

## Cierre #54, #57 y #66; clasificación pendiente en #70

El commit `7593dea` completa tres correcciones auditables sobre `demo`:

- **#54:** `CUMPLE`/`NO CUMPLE` y `SÍ`/`NO` sin razón son críticos antes de
  consolidar y también al revalidar en backend; el prompt exige el sustento en
  el mismo valor textual.
- **#57:** `total` es la suma declarada determinística de filas y reemplaza el
  cálculo del LLM; `total_backend` muestra los descuentos y el efectivo aparte.
- **#66:** se captura un CUI etiquetado dentro del párrafo completo del servicio
  y el Excel distingue «citado y verificado» cuando coincide con el resolver.

Gate: **731 passed, 25 skipped** en backend y **54/54** scripts de skill;
compilación y diff limpios. Resolver intacto, sin golden y sin despliegue.

La #70 conserva como diseño abierto la clasificación por `tipo_concurso` y
`tipo_experiencia` (preinversión, expediente, supervisión y ejecución). #50 no
se implementa hasta cerrar ese contrato; #49 permanece pausada por ADR-S007.

## Fixes pre-deploy #68, #64, #42 y #65 completos

- **#68:** el recorte TDR usa el rango físico completo declarado y detecta
  folios sospechosamente repetidos; el Excel no lo presenta como un recorte
  individual exacto.
- **#64:** el cómputo efectivo empieza como mínimo en la fecha real de inicio
  de obra, sin cortar por la fecha final de ficha.
- **#42 (backend + Panel):** resolver una revisión responde `202`, persiste
  `en_curso/completada/error`, se consulta por polling y nunca deja la pantalla
  bloqueada sin una acción de reintento.
- **#65:** contrato espejo v1.3.0 con `supuestos` estructurados; el Excel pinta
  violeta solo la procedencia inferida y conserva amarillo para «por verificar».

Gate: **727 passed, 25 skipped**, 57 pruebas de entregables, 36 del
consolidador, 9 espejos históricos en paridad Pydantic/Zod, `compileall` y
`diff --check`. Panel: build productivo Next.js aprobado. No se tocó el
resolver CUI; no aplicó golden. No hubo despliegue.

## ADR-S007 y tren de rescates A–D COMPLETO

`demo` vuelve a ser la línea de producto; `refactor` queda congelada en
`65d41af`. El primer rescate parte del tag local `demo-pre-rescates`
(`5503082`) y corrige el WAF/timeout de Bases Integradas sin traer runtime v2.
La rama suma `d4d3612` (fix) y `6e37605` (pruebas y red offline). Suite:
**709 passed, 25 skipped**. La validación pública con CUI 2279396 descargó un
RAR válido de 1,561,634 bytes sin dejar `.part`. Actualmente no hay servicios
de Pivote corriendo en el servidor del cliente. A avanzó por fast-forward a
`demo` como `586f430`.

El tag local `demo-pre-B-atomicos` marca el retorno previo a B. En
`rescue/B-atomicos`, `c67e290` añade un reintento de unos 200 ms solo para
`PermissionError` de `os.replace` y lo conecta exclusivamente a la escritura
JSON del repositorio; los ZIP quedan fuera. Validación: **9 focales pasaron, 4
skips de PostgreSQL; 713 passed, 25 skipped** en suite completa, `compileall`
y `diff --check`. No hubo push ni despliegue.
B avanzó por fast-forward a `demo` como `3beb94b`.

El tag `demo-pre-C-ingesta` marca `90a3e1e`. C quedó integrado como `bb263c1`:
la API valida JSON, límites de Excel, ZIP y magia PDF antes de crear el job;
un ZIP roto ya no se ignora. Se mantuvieron `201 + job_id`, tareas en segundo
plano y layout. No entraron las defensas diferidas. Validación: **22 API; 717
passed, 25 skipped**, compilación y diff limpios.

El tag `demo-pre-D-cache-seace` marca `3156d26`. D quedó integrado como
`345c601`: una caché compartida por `fileCode` valida magia PDF/ZIP/RAR,
publica atómicamente y reutiliza el documento entre experiencias y jobs. La
descarga sigue secuencial y no trae piezas del runtime v2. Prueba clave: una
descarga de red, tres entregables idénticos. Gate final del tren: **34 focales;
721 passed, 25 skipped**, `compileall` y diff limpios. No se tocó el resolver.
No hubo push ni despliegue; actualmente Pivote no corre en el servidor.

## ReniPress integrado al orquestador (29-jul, `demo`)

El usuario reactivó ReniPress con una meta más amplia que la sonda original:
convertirla progresivamente en producto integrable. Primer corte construido
sobre `demo` vigente:

- `backend/scraping/renipress.py`: cliente inyectable y modelos estables, con
  configuración por entorno, reintentos y distinción entre búsqueda válida sin
  filas y portal no disponible.
- `GET /api/pivote/renipress`: contrato HTTP reusable; `200` para fuente sana
  (con o sin resultados) y `503` para caída de SUSALUD.
- `tools/renipress.py`: CLI de diagnóstico sobre el mismo módulo.
- `EtapaRenipressReal` es ahora la rama 3c del pipeline y corre en paralelo con
  InfoObras y SUNAT después de resolver el CUI. Consulta toda experiencia cuyo
  proyecto declara rubro salud, pública o privada, con caché por término.
- El contrato completo queda en
  `enriquecimiento["n_prof:n_exp"]["renipress"]`; la etapa aparece en el
  progreso del API y participa en checkpoints/reanudación.
- `encontrado` y `sin_resultados` son evidencia informativa.
  `portal_no_disponible` produce `ERROR_PARCIAL`, nunca “no existe”.
- No cambia veredictos ni crea revisión humana: la política de coincidencia
  automática sigue pendiente de un corpus auditado de homónimos, bajas y
  ausencias.
- Validación: **90 pruebas focalizadas** y suite completa
  **704 passed, 25 skipped**.

## Validación de CUI citado con ETL MEF (#69, 29-jul)

El resolver consume ahora `funcion` y nombre oficial de la ficha PostgreSQL
para contrastar un CUI citado en Paso 0. Una contradicción positiva de rubro
degrada a revisión; la ausencia de clasificación no veta. Caso real validado:
Hospital Abancay II + CUI 2105743 → ficha de redes eléctricas, función
`ENERGÍA` → revisión. No se relajó el candado de candidatos solo-MEF porque la
golden v4 aún no existe.

Paso 0 tampoco corta ya el flujo al detectar esa contradicción: descarta el
código como ancla, busca nuevamente por el resto de datos y conserva los
candidatos encontrados. El resultado permanece en revisión hasta confirmación
humana; recién entonces puede viajar al Excel un CUI sustituto.

## Replanificación ETL MEF v2 (29-jul)

Rama hija `plan/etl-mef-v2`. La primera revisión fue documental; luego se
implementó el diseño serving-first descrito abajo. Se descartó usar la
épica #12 como especificación: sus issues eran brainstorm. Se perfiló en
streaming el corte real 2026-07-26 de los tres CSV: **620,985 filas, 640.7 MB,
95 columnas, 579,481 CUIs**, 41,505 filas sin CUI pero ninguna sin CUI y SNIP,
ningún CUI cruzado entre estados y un solo duplicado lógico.

Documentos fuente:

- `docs/backend/eda_datos_abiertos_mef.md`: EDA, cobertura, aliases, tipos,
  anomalías y estimación de capacidad;
- `docs/backend/modulo_etl_mef.md`: plan reescrito desde cero;
- `ADR-009`: aceptado para planificación como capa PG que **convive** con el
  índice RAM de ADR-002.

Decisiones: tarea semanal del Programador de tareas de Windows → contenedor
one-shot; `load_id` común; raw JSONB + canonical tipado + serving versionado;
puntero de carga activa en vez de swap de tablas; carga completa activa +
anterior hasta medir almacenamiento real. La Fase 0 (EDA reproducible, carga PG
desechable y benchmark de capacidad) precede al DDL final y a la cotización.
Las issues de GitHub aún no se reescribieron.

### Decisión e implementación serving-first (continuación)

El objetivo se acotó al consumidor real: el resolver. Decisión final del
desarrollador: **índice RAM para búsqueda difusa + PostgreSQL obligatorio para
la ficha enriquecida por CUI/SNIP**. Raw histórico se difiere. Implementado:
retry/backoff, aliases `COD_SNIP`/`NOM_*`, cargas inmutables, manifest atómico,
retención de dos cargas, schema `mef`, carga por COPY, recarga sin reinicio y
health de frescura.

Validación real aislada (PostgreSQL 16 Docker, no base activa): 620,985 filas /
620,984 identidades en **117.5 s**; gzip 32.5 MB; tabla+índices PG 719.3 MB;
14,665 entidades. Lookup: primer pool 171 ms, siguientes 6–9 ms sin cargar RAM.
Diferencial: 100 fichas + 20 rankings, cero cambios en contrato legacy. Se
encontró una fila activa sin nombre: se conserva por CUI y se registra.
Suite: **685 passed, 25 skipped** + integración PostgreSQL explícita aprobada.

## Reunión con el cliente 29-jul — lo que cambió (fuente: transcripción)

- **El cliente está haciendo A MANO lo de bases+contratos**, certificado por
  certificado, con un prompt propio en su Claude (busca el contrato, lo abre,
  verifica el cargo del especialista, guarda por proyecto). Lo pidió «hace
  semanas». **T-004 pasa a prioridad máxima**; diseño listo en
  `docs/plan-integracion-bases-contrato.md` (v2, ajustado con la transcripción).
- **Confianza erosionada**: dijo que **no revisará más Excels** hasta que los
  resultados sean precisos — él ya trabaja su propio Excel; **lo que consume es
  el ZIP** de documentos. «Lo que no puede fallar es que me busque otro proyecto
  y me dé otro» (= exactamente #46/#51, ya corregidos, pero él aún no lo ha
  visto reflejado). Los documentos van primero; el candado, en segunda entrega.
- **Requisito N°1 de T-004, en sus palabras**: segmentar por tipo de proceso —
  un hospital puede tener hasta 4 juegos de bases (preinversión / expediente /
  supervisión / ejecución) con el MISMO CUI; solo valen las bases INTEGRADAS.
- **Pedido nuevo (resuelto 2-ago)**: marcar con color los datos SUPUESTOS del
  Excel → [#65](https://github.com/rafram96/Pivote/issues/65).
- **RENIPRESS despriorizado por él mismo** («ya olvidémonos», para no atrasar
  bases+contratos). Capturas de pantalla: pedidas y descartadas (aceptó).
  Firmante/representante legal: reconfirmó que NO va (ADR-008 se sostiene).
- **Web HK**: no la ha revisado (su red corporativa bloquea la página; por
  teléfono sí carga). Se le reenvía el link por WhatsApp. Rafael regaló el
  tiempo desplegado (~2 meses). El cobro queda pendiente de su revisión.
- ⚠ **Comercial**: NO se habló de precios ni adelantos — el cliente trata los
  extras como pendientes del flujograma. Manejo en `docs/comercial/`.

## T-004 en construcción (29-jul, rama `feat/seace-abierto`)

- **F1 HECHA** (`70c78e8`): `backend/scraping/seace_abierto.py` — cache CONOSCE
  (una vez, atómica, tolerante a fallos), cliente OCDS ([] = dato / None =
  portal caído), y `seleccionar_proceso` con el requisito N°1 del cliente:
  **jamás cruzar de tipo**; desempate por vigencia solo dentro del tipo; con
  varios candidatos sin fechas → el más reciente + flag `ambiguo`. 18 tests
  offline. Probado EN VIVO con el CUI 2279396 (Pichanaki): 5 procesos y
  clasificación correcta.
- **F2 HECHA, lista para PR** (Codex, 29-jul): selección integrada en
  `EtapaInfoObrasReal`, descarga diferida independiente de `obra_id`, marcas
  idempotentes separadas InfoObras/SEACE, archivos/notas dentro de cada
  experiencia del ZIP y bloque informativo en el Excel. No cambia veredictos
  ni el contrato espejo. Suite completa: **677 passed, 24 skipped**.
- **Hallazgo de validación viva F2 (CUI 2279396)**: el contrato descargó como
  PDF (1.45 MB); las Bases Integradas elegidas están publicadas como **RAR** y
  su host devolvió HTTP 403. El código conserva PDF/ZIP/RAR con su extensión
  real y, ante 403/HTML, deja `*_ERROR.txt` en vez de fingir un PDF válido.
  Reintento posterior al commit `d77d054`: mismo HTTP 403; simular navegador
  (`User-Agent`, `Referer` y sesión previa) terminó en timeout. No se creó un
  RAR parcial. Es una restricción/intermitencia del host de archivos, no una
  selección incorrecta del proceso.
- **Documentación de operación y contingencia**:
  - `docs/uso-manual-seace-abierto.md` — receta operable HOY por certificado
    (preparar caché, elegir tipo, descargar los documentos con los nombres del
    entregable, tabla de decisiones y problemas conocidos);
  - `docs/plan-integracion-bases-contrato.md` **ANEXO** — implementación F2,
    contratos internos y pendientes F3/F5.
- Falta: **F3** (fechas→T-005) y F5 (candado). Deploy/redeploy queda
  expresamente fuera de esta entrega y a cargo manual de Rafael.

## Arquitectura visual v3 (29-jul)

`docs/nuevos_modulos/arquitectura-sistema.html` fue rehecho como vista integral
para Manuel y Rafael. Parte del flujo horizontal de `para RAFAEL-V2.xlsx` y
explicita público-primero, SUNAT transversal y RENIPRESS como evidencia auxiliar
para toda experiencia de salud. Se corrigió el estado del ETL: hoy existe la
base mínima manual de 10 campos; cron, hot/cold PostgreSQL, API y paralelización
siguen en el roadmap. Incluye matriz de estado real y arquitectura actual/futura.

## Lo del 2026-07-28 (resumen — detalle en `handoffs/2026-07-28_claude.md`)

- **9 issues resueltas en la rama** `fix/identidad-lircay`: #58/#59/#60/#61
  (identidad: DEDUP exige emisor, tope al CUI citado, veto de fase ET,
  procedencia del CUI en el Excel — diagnóstico con certificados FÍSICOS del
  Tomo II de Lircay), #52/#53 completadas (parser de oferta conservador +
  candado `OFERTA_INCOMPLETA` + prompt multi-tomo) y #47 implementada
  (verificación folio↔emisor en la skill + `folio_verificado` en el contrato +
  el Excel no embebe sin confirmar). Suite: **637 passed**.
- **⚠ LA GOLDEN SE PERDIÓ** (corpus v3 + caché + baseline, irreversible).
  Sustituto: abstención pura + replay (`replay_enriquecimiento.py`, corrido:
  152 exps, solo cambian los 3 casos del ing.) + plan corpus v4
  (`exportar_verdades_panel.py` en el server). Ver nota en `handoffs/current.md`.
- **ETL re-planificado** "documento primero": 14→5 issues; bug confirmado
  #19 (12,102 entidades perdidas por `NOMBRE_*` vs `NOM_*`). Doc ancla:
  `docs/backend/modulo_etl_mef.md`.
- **Corrida viva de divino_nino EN CURSO** (Tesseract local = Camino A activo
  por primera vez). Al terminar: validar el tren + push/PR + redeploy.
- **DECISIÓN CERRADA (Rafael): la skill corre en Claude CODE — Cowork queda
  DESCARTADO como runtime.** Consecuencias: cambios de skill se despliegan con
  el merge (sin rebuild de plugin, sin "trenes de release"); `plugin/` +
  `build.ps1` quedan deprecados como referencia histórica; el setup de Manuel
  es Claude Code + MCP local (`.mcp.json`), no Cowork/Desktop.

## Lo del 2026-07-27 (documentación, entorno, alcance y un fix de veredicto)

- **FALSO CUMPLE cerrado** (#51, PR #56, `cf9804b` en `demo`). Auditando 3 análisis
  reales (156 experiencias) aparecieron **5 profesionales en verde con el tiempo
  efectivo por debajo del mínimo** — y el dato que los desmentía estaba en otra
  hoja del mismo archivo. La conciliación (`cumple_backend`) **ya existía** y estaba
  doblemente inhabilitada:
  - `_RE_MINIMO` solo leía «años» y las bases dicen «24/36 meses» → **0 de 44**
    mínimos captados en los 3 concursos. Ahora lee años/meses/días y compara en
    DÍAS (convertir a años y redondear volcaba los bordes): **44/44**.
  - `cumple_backend` solo llegaba a la API. Ahora viaja en el espejo (en vivo) y
    `regenerar_excel_final` lo reinyecta desde el enriquecimiento (regeneración).
    En el Excel, si contradice al veredicto la celda se pinta **roja** y el motivo
    va debajo.
  - Se cerró el **error inverso**: cobertura de valorizaciones casi nula recorta los
    días casi a cero y habría dado NO CUMPLE duro; la causa probable es obra mal
    emparejada (error nuestro) → entra a `veredicto_provisional` → POR VERIFICAR.
    De los 5 falsos CUMPLE: 1 traslape real (NO CUMPLE), 4 dato faltante (revisión).
  - 619 tests (5 nuevos con los casos reales BIM y P6 de Lircay).
- **Dos defectos de la skill arreglados** (`32017b7`): la PARTE 2 llegaba desalineada
  (el prompt del mapa nunca pedía `contrato` ni `proyecto`, y el juicio del evaluador
  no tenía dónde aterrizar → ahora se fusiona por la llave `n`), y el literal `null`
  se imprimía en celdas. De paso, `pick(x,"")` dejaba `observacion: null` en
  `formularios` — **invalidaba el espejo entero** cuando faltaba ese campo.

## Lo del 2026-07-27 (documentación, entorno y alcance — sin código de producto)

- **La skill instalada llevaba 13 días de atraso y le faltaba el escudo entero.**
  `~/.claude/skills/analizar-licitacion-osce` era una copia del 14-jul (rastreada
  al commit `1a2b5a2`): **cero** apariciones de `INCOMPLETO`, sin
  `process.exitCode = 1`, sin el bloque ⛔ GATE en `SKILL.md`. Es decir: no podía
  detener una corrida incompleta — exactamente la falla del 26-jul (veredictos
  corridos +1 y corrida sin evaluación, ambas subidas como buenas). El arreglo
  vivía en `demo` desde `0271ea7` y nunca llegó al entorno.
  **Resuelto de raíz**: la ruta instalada es ahora un **junction a `Pivote/skill/`**
  (ver `conventions/coding.md`) — la skill instalada ES la del repo, la deriva ya
  no es posible. 18/18 archivos en paridad, 31 tests verdes a través del enlace.
- **Alcance de T-008 corregido en el material comercial** (commit `27c8cde`):
  `plan-desarrollo-extras.html` y `arquitectura-sistema.html` vendían «Arquitectura
  Dual Hot/Cold Path JSONB», «swap atómico `mef_inversiones_staging`» y «pg_trgm».
  **Nada de eso existe en el código** (`grep` → cero): el ETL produce
  `inversiones.csv.gz` + `os.replace` sobre un archivo. Se reescribió describiendo
  lo real y el Postgres quedó como *evolución prevista, no construida y fuera del
  precio* — ADR-009 seguía EN CONSTRUCCIÓN en ese corte; fue revisado el 29-jul.
- **Cifras reales de la base MEF** (metadata del 26-jul): **620,985 filas →
  579,481 CUIs distintos** y **11,011 entidades**. Los docs decían 452,793 y 11,004.
- **Documento nuevo `docs/nuevos_modulos/caminos-a-b-estado.html`**: los 4 caminos
  del Excel (A/B × pública/privada) en cuadrícula con tablero de estado. Deja ver
  que una experiencia pública pasa por 7-9 verificaciones y una privada por 2-3 —
  por eso clasificar mal a privada es el error caro. Y que las 3 piezas sin
  desplegar (CUI, cargo↔bases, HABIDO) aparecen en los 4 caminos.
- **Cuarto estado en los diagramas**: «construido, falta desplegar» separado de «en
  producción». Antes el material decía «✔ en producción» sobre trabajo que vive
  solo en `demo`.
- **Issues nuevas**: [#49 Economizar Skill](https://github.com/rafram96/Pivote/issues/49)
  (con inventario de las responsabilidades que absorbió el backend) y
  [#50 parámetro de tipo de concurso](https://github.com/rafram96/Pivote/issues/50)
  (= implementación de **ADR-010**, ya decidido — ver la corrección en el hilo).
- **Corrección de un dato que este archivo daba mal**: `demo` **sí está pusheada**
  (`origin/demo` 0/0). El checklist decía «solo local, falta push» desde el 23-jul.

## Dos huecos del flujograma, abiertos con el cliente

Aparecieron al ordenar el Excel por camino (no se ven en su disposición original):

1. **RENIPRESS no se pide para expedientes privados** — solo para obra. Un
   expediente técnico de una clínica privada tiene el mismo problema de existencia.
2. **Los cruces de fechas solo se piden en el camino A** — en obra el Excel pide
   únicamente el cargo, aunque la misma regla aplicaría con el contrato de supervisión.

## Terminado y validado (sin desplegar)

- **Integridad de la evaluación + visibilidad del Excel** (#45/#46/#47, PR #48
  y ADR-013, en `demo`). Suite **565**. Lo que cambia para el evaluador:
  - el bloque InfoObras del Excel **muestra el nombre de la obra** (antes solo
    código y CUI: ninguna identificación era auditable de un vistazo);
  - la advertencia de revisión **ya no se esconde tras un `elif`** — eran 403
    de 999 ítems sin resolver (40%) invisibles, en 31 jobs;
  - **el backend calcula** días/meses/años, `anterior_colegiatura` e
    `incluye_covid` (etapa VALIDACIÓN): dejan de depender de que el LLM los
    mande, que es como salieron vacías las corridas del 26-jul;
  - el consolidador de la skill **falla ruidosamente** si la evaluación no
    cubre 1:1 lo declarado, y ya no imprime `OK` cuando hay críticos;
  - **veto por departamento contradictorio** + **candado de nombre genérico**
    (ADR-013): cierran el caso Tarapoto (Hospital EsSalud de San Martín contra
    una tomografía en Madre de Dios). Costo medido en el corpus: 0.6% a
    revisión, y las 6 experiencias del delta del veto son mal-resueltos.
  - `scripts/reparar_evaluacion.py` rellena jobs viejos sin re-correr la skill.
- **Golden regenerada** (corrida en vivo autorizada, 26-jul): baseline nuevo
  230 correctos / 10 incorrectos / 34 revisión, **cero `correcto→incorrecto`**.
  La caché quedó completa y `--solo-cache` volvió a funcionar offline.
  ⚠ **La golden es ciega a media regla del resolver**: sus casos solo llevan
  `proyecto` y `cui`, sin `ubicacion`/`entidad`/`ruc_emisor`, así que los vetos
  de ubigeo y el candado de nombre no se ejercitan (ADR-013 dio matriz
  diagonal: probó cero regresión, no validó nada). Ensancharla está en curso.

- **Issue #32 — factor de evaluación al final de cada hoja P** (`17b1e04`):
  cierra el punto 2 del feedback del 28-jul. Verificado e2e con PDFs
  sintéticos; **falta la corrida sobre un job real**. Toca skill (prompt
  `agent-bases`, consolidador, `extraer_certificados.js`) y backend
  (`excel_final.py`), pero es compatible en ambos sentidos de despliegue: un
  `P{n}_FACTOR.pdf` que llegue a un backend viejo se ignora, y un backend nuevo
  sin el archivo genera la hoja como antes. Arrastra un fix:
  `regenerar_excel_final` conservaba cero imágenes.
- **Issue #30 — emisor del certificado en SUNAT** (rama
  `rafram96/issue-30-mostrar-representante-legal`): representantes legales +
  información histórica (`getinfHis`, sondeada 25-jul) en el bloque emisor del
  Excel, con la respuesta calculada a "¿estaba HABIDO al emitir y durante la
  obra?" en el título del campo. Cuadro histórico nuevo en R:U (representante
  de obra corrido a W:Z). Una consulta por RUC por job. 276 tests verdes +
  prueba en vivo contra 6 RUCs. **Pendiente: render en el panel.**
- **Refactor del resolver de CUI (T-008)** — rama `sonda/refactor-cui`, 13
  commits (`a732936…f2bde36`): base local MEF + público-primero + vetos de
  identidad + candados de abstención + camino A/B. Golden 277 casos: errores
  silenciosos **16 → 10**, cero regresiones. 268 tests verdes.
- **Camino A (expedientes)**: clasificador por toda la evidencia + modo
  `PIVOTE_FORZAR_EXPEDIENTES=1`; validado con el concurso San Isidro.
- **Skill optimizada**: Paso 4.5 acotado (elimina fuga de ~3M tokens/corrida);
  prompt del extractor conserva el envoltorio "Elaboración del ET:".
- **Análisis San Isidro CP-01-2026 entregado** al usuario: job `b4f385c31811`
  (camino A), Excel 12.5 MB con imágenes, 44 CUIs, 28 verificados en MEF.
- **Documentos del paquete de extras v3** (docs/nuevos_modulos/): 4 HTML
  actualizados con T-008 + `arquitectura-sistema.html` nuevo.
- Cotización interna lista: `docs/comercial/planeacion-v2-para-rafael.md`
  (gitignored — no va al repo).

- **Issue #28 (T-MULTI-002) paso 1 — desempate por estado del MEF**, mergeado
  a `demo` el 2026-07-26 (PR #39, `14f9fe8`): `estado_dataset` ya viajaba en la
  base local desde F3 y **ningún consumidor lo leía** (229k de 494k filas son
  DESACTIVADAS y competían de igual a igual con las vivas). Ahora ordena el
  presupuesto de fetches, desempata el ranking a igual score y separa homónimos
  en el guard de empate — siempre como DESEMPATE, nunca como filtro (15 de 191
  verdades auditadas viven en filas DESACTIVADA: CUIs reformulados que el cert
  cita). Consultas al portal gastadas en desactivadas: 32.2% → 9.3%. Empate de
  Sullana 4 → 2 candidatos. 375 tests verdes. **Golden en vivo NO corrido** (el
  reordenamiento cambia qué CUIs se consultan → la caché no los tiene).

## En progreso

- **Fixtures listos para probar el backend nuevo** (2026-07-26): preparadas
  `Pronis_Sonitor/`, `Soritor2/` y `Consorcio-Lircay/` con `_prep/MAPA.md`
  (inventario, offsets de folio, tachado, descartes). Índice nuevo
  `fixtures/ing manuel/_CONCURSOS.md` = qué carpeta es qué concurso/postor.
  Herramientas reusables en `src/tools/`: `detectar_tachado_pdf.py` (validado
  contra el caso HuachoColpa: 10/10 páginas), `trocear_pdf.py` y
  `render_paginas.py`. **Mejor fixture para probar: `Soritor2/`** (born-digital,
  95 MB, sin troceo). Detalle en `handoffs/2026-07-26_claude.md`.

- **Issue #31 — candado cargo↔bases (ADR-012)**, mergeado a `demo` el
  2026-07-26: `backend/validacion/cargo_nucleo.py`
  exige el núcleo de especialidad COMPLETO (OR entre alternativas, AND dentro)
  y usa las funciones como segunda puerta; marca rojo/amarillo en el Excel sin
  tocar el formato ni el cómputo de días. Replay: 15 rojas + 116 amarillas
  sobre 1421 experiencias, con los 4 casos del Comité detectados. Falta prueba
  viva + deploy (la skill cambió → rebuild del plugin).
- Fase comercial: presentar extras a Manuel
  (T-003+T-008 entregados S/5,400; T-004/005/006 por desarrollar S/4,400).

## Problemas abiertos

- **Bases de Lircay (`Consorcio-Lircay/`) traen tachado pese a llamarse "sin
  tachas"**: 16 páginas, y lo eliminado toca equipamiento estratégico (pick-up
  2021+, software, miras, "Con Estación Total") y las funciones BIM del
  personal → leer `_prep/bases_texto.txt`, **nunca el PDF crudo**.
- **Falta la oferta económica de los 2 postores de Lircay** → sin límite
  inferior ni puntaje de precio. Pedírselas a Manuel.
- Corridas camino A: aún se **descargan y pintan** secciones de obra
  (valorizaciones ~805 archivos) en expedientes — cosmético/pesado, no afecta
  veredictos. Ya no generan cobertura baja ni descuentan paralizaciones de la
  construcción; filtrar esas descargas sigue siendo la deuda pendiente.
- 2 casos de la auditoría con "verdad" dudosa (2195439 Tocache/Loreto,
  2064566 Cotabambas/Antabamba) — re-revisar con Manuel.
- ~~Divergencia schema.sql vs DDL real de Postgres~~ **CERRADA 5-ago** (F-SCHEMA).
- SUNAT con error_parcial intermitente en corridas largas (portal, no bug).

## Riesgos

- Hay un **deploy pendiente**: el refactor ya está mergeado a `demo` y **pusheado**
  (verificado 27-jul: `origin/demo` 0/0), pero el server corre el código viejo.
  Los pasos y el ORDEN del deploy viven SOLO en `InfoObras/.ai/tasks/_active.md`
  (fuente única).
- **El repo `Pivote` es PÚBLICO.** Todo lo que se commitea se publica en internet
  de forma permanente (el historial no se borra). `docs/comercial/` está gitignored
  por eso — el 27-jul un dashboard con S/ 10,300 en cuentas por cobrar, precios por
  ticket y la IP del servidor del cliente llegó a estar a un `git add` de publicarse.
- **`ai-cli validate` falla en este nivel con 67 errores preexistentes**: los 13 ADR
  y los 3 índices de `tasks/` no tienen frontmatter YAML, y `counters.json` está en
  `{CAP:0, TSK:0, ADR:0}` con ADR-013 ya existiendo → **`ai-cli new` colisionaría**.
  El nivel InfoObras valida limpio. Reparación pendiente (ver handoff del 27-jul).
- Límite de gasto mensual de Claude alcanzado el 21-jul (los subagentes pueden
  morir a mitad — el trabajo F8 se terminó a mano por eso).

## Siguiente prioridad recomendada

1. Deploy en paquete del refactor — checklist de deploy: ver
   `InfoObras/.ai/tasks/active.md` (fuente única).
2. Filtro de secciones de descarga/Excel en modo camino A.
3. Reunión de cotización con los 5 HTML de docs/nuevos_modulos/.
