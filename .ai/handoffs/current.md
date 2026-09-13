---
timestamp: "2026-09-12"
agent: Codex
---

## 12-sep — Hoja del profesional de vuelta al formato compacto

[Limpieza de diez puntos](2026-09-12_claude-opus-excel.md): sin filas de servicio,
estado de fuentes, «Fuente: MEF-…» ni sub-bloques informativos de SUNAT; rótulos
cortos de candado y SEACE, documentos y emisor en lenguaje de evaluador, y la
observación de fechas solo con una fecha comparada. **2173 → 1998 filas** en las
17 hojas del job de Tacna, **cero celdas numéricas o de fecha cambiadas**; API,
ZIP y cálculo intactos. 1871 pruebas pasan, 31 omitidas; el único fallo es ajeno
(`zod` sin instalar en el árbol de trabajo). Rama `excel/limpieza-texto`, sin
regenerar entregables del cliente.

## 12-sep — Retiro de ampliaciones visuales no acordadas

[Simplificación autorizada](2026-09-12_codex.md#retiro-de-añadidos-de-presentación-no-acordados):
sin tres filas de servicio ni advertencia documental genérica. Diferencias reales
en campo existente; SUNAT resumido. Conserva resumen/Gantt, identidad, cálculos
y detalle API/ZIP. Comparación sintética y visual de ambas rutas; jobs intactos.

## 12-sep — Excel sin bloque repetitivo de fuentes

[Cambio de presentación solicitado](2026-09-12_codex.md#bloque-de-estados-retirado-del-excel):
retiradas las filas «Estado de fuentes y documentos» en ambas rutas, sin dejar
su espacio vacío. Estados internos/API/ZIP y explicaciones de identidad intactos.
No se modificaron los Excel existentes ni se reinició el servicio.

## 12-sep — Alertas de montos y veredicto ajeno

[Correcciones de integridad](2026-09-12_codex.md#dos-alertas-falsas-de-integridad-corregidas):
importes v1.4 reconocidos; nombres propios de experiencias no se interpretan
como especialidades ajenas. Cálculo acreditable sin cambios. **1790 tests pasan,
25 omitidos**; contrato de la corrida nueva válido. El script global rechaza
una muestra QA anterior parcial (cero divergencias). No se modificó el job
ni se reinició el backend; los 71 errores documentales previos se conservan.

## 12-sep — Estados de fuente y documento separados

[Punto 2 implementado](2026-09-12_codex.md#estados-de-consulta-y-documento-separados):
portal no disponible, respuesta vacía reconocida y desconocida conservadas por
recurso; descarga y correspondencia no se confunden. API/Excel/ZIP/Panel comparten
la explicación. Código `1194ff6`; 1764 tests pasan, 25 omitidos; Panel `9c575f6`
y TypeScript limpio. Punto 3 real todavía no iniciado. Documentación raíz válida;
Pivote conserva 71 errores previos de metadatos.

## 12-sep — Checkpoint antes de estados de fuente

[Cinco commits de código](2026-09-12_codex.md#checkpoint-de-los-tramos-terminados)
hasta `2f44a33`. Continúa la corrección de estados; la comprobación real de ambas
rutas (punto 3) no está iniciada. Las notas «sin commit» inferiores son históricas.

## 12-sep — SUNAT y checkpoint por fuente integrados

[Implementación y medición](2026-09-12_codex.md#consultas-repetidas-y-checkpoint-por-fuente):
20 búsquedas repetidas → 1 en sonda offline con las mismas salidas; vacíos/errores
no se cachean. Fuentes con entradas aisladas, fusión por campo y guardado al
terminar cada rama. Reanudación y fallos de disco probados; no hay corridas reales,
reinicio ni commit. No confundir esta medición con latencia real de los portales.
Regresión final: 1715 pruebas pasan, 25 omitidas; 29 tests nuevos.

## 12-sep — Cálculo independiente del generador Excel

[Implementación y aceptación](2026-09-12_codex.md#cálculo-separado-de-la-generación-excel):
mínimos, Factor A, conciliación e inyección en reglas; conclusiones independientes
del renderer. Misma conducta en ambas rutas frente a copias previas; imports en
frío sin Excel ni etapas. No cambian criterios, jobs ni entregas históricas.
Regresión final: 1686 tests pasan, 25 omitidos; validación documental raíz válida,
Pivote conserva los 71 errores previos de metadatos.
La optimización acotada de consultas/persistencia está en el tramo superior.

## 12-sep — Proyección compartida de identidad integrada

[Implementación y aceptación](2026-09-12_codex.md#proyección-compartida-de-identidad):
Excel, ZIP y API usan la misma preparación de identidad; ficha Excel conserva
contexto original sin persistirlo. 1664 pruebas backend pasan; comparación offline
de las dos rutas conserva API, Excel y ZIP. Sin jobs, reinicio ni commit.
La separación cálculo/presentación está en el tramo superior; no afirmar precisión global de CUI.

## 12-sep — Primer tramo de eficiencia implementado

[Montos y fallo del selector](2026-09-12_codex.md#primer-tramo-de-eficiencia-y-fallos-silenciosos):
importe existente respetado, rango exacto y procedencia conservados; fallo de
selección a revisión con candidatos, sin elección automática ni herencia por
dedup. Pruebas y límites de replay en el cierre fechado. Sin jobs, restart o
commit. La proyección de identidad se implementa en el tramo superior;
la separación cálculo/presentación se cerró en el tramo superior.

## 12-sep: identidad y lectura prioritaria (bloque anterior)

[Continuación y aceptación](2026-09-12_codex.md#continuación-identidad-y-lectura-prioritaria).
Procedimientos múltiples sin elección por calendario; entidad+tipo insuficientes
para confirmar encargo; conflicto de naturaleza va a revisión conservando pistas.
La investigación incluye privadas y documentos prioritarios con lectura/pendiente
registrados. Son guardas de abstención, no nuevas promociones ni un dictamen.

## 12-sep: adjuntos SEACE integrados al flujo

[Implementación, aceptación y límites](2026-09-12_codex.md).
Colección completa, selección exacta, manifiesto con hash, retiro recuperable y
entregables que separan datos del proceso de contenido pendiente. No se cambió
resolver ni A/B, no hubo nueva corrida ni regeneración de entregas históricas.

## 12-sep: componente de colección SEACE (antecedente)

Implementada y probada `documentos_prioritarios`, con bases integradas y
adjuntos contractuales completos, filtro exacto por contrato, orden estable,
dedupe lógico y enlaces faltantes preservados. Ver
[handoff fechado](2026-09-12_coleccion-seace.md). Sin red, jobs ni migración.

# Handoff — punto de continuación

## 11-sep: correcciones directas integradas

[Cierre de controles de extracción](2026-09-11_codex.md#cierre-directo-de-controles-de-extracción).
Preparación común integrada al Paso 2.6 y consolidador; instalada vía junction.
125 tests Node y 1597 backend pasan; relectura focal y transporte real comprobados.
No volver a diagnosticar los mismos defectos ni repetir propuestas completas.
Los apartados siguientes son historia previa a este cierre local.

## 11-sep: prueba adicional del control factual

[Resultado y límites](2026-09-11_codex.md#prueba-adicional-del-control-factual).
Ensayo de prompt, no cambio instalado. Persiste evento temporal mal atribuido;
la validación de tipos también encuentra errores. No relanzar jobs para retomarlo.

## 11-sep: rótulo CUI corregido y prueba multirruta

[Cambio local y comprobación con Luna medium](2026-09-11_codex.md#corrección-del-rótulo-cui-y-prueba-multirruta).
Supera el pendiente de presentación CUI de la prueba anterior; siguen defectos
de extracción y motivos de ausencia. No hubo job, red ni cambios de entregas.

## 11-sep: prueba focal nueva con Luna

[Prueba real acotada y pendientes reproducidos](2026-09-11_codex.md#prueba-focal-posterior-extracción-con-luna).
No relanzar extracción ni jobs para recuperar contexto. La muestra conserva el
contraste de servicio; aún no da por buenos todos los rótulos ni datos de entrada.

## 11-sep: esperado frente a declarado

[ADR-S013 implementado y probado en aislamiento](2026-09-11_codex.md#servicio-esperado-y-declarado-adr-s013).
Ruta A/B global preservada; evidencia literal nueva no se toma del evaluador.
No usar el tipo de búsqueda para sumar señal fuerte. Excel, API/Panel y ZIP
explican el mismo contraste. No se ha corrido la skill completa ni alterado jobs.

## 11-sep: bloque documental MEF

[Continuación](2026-09-11_codex.md#continuación-coherencia-documental-y-rol-del-servicio):
lectura indivisible, actos contractuales conservados aparte y tipo SEACE sin
ejecución presumida por título. Medido sobre dos jobs sin modificarlos. Consorcio
no identificado por metadatos de anexos; lectura semántica pendiente.

[Implementación y límites](2026-09-11_codex.md): descarga por selección de
experiencia, independiente de ficha, sin reselección. Pruebas aisladas; no migración
histórica ni reconocimiento semántico de aprobación. Sin commit ni despliegue.

## Checkpoint de implementación etiquetado

Lote autorizado para commit y tag `checkpoint-identidad-documental-20260910`.
Revalidación: 49 backend y 34 Node pasan; no es release desplegada ni validación
documental integral. [Detalle](2026-09-10_codex.md#checkpoint-de-implementación-con-tag).


## Checkpoint documental

Por pedido del usuario se commitea primero `.ai/`; código e instrucciones de la
skill quedan pendientes. [Alcance](2026-09-10_codex.md#checkpoint-documental-solicitado).


## Actualización: piloto documental en datos aislados

Tres adjuntos reales y constancia leídos con texto/visión; tipo de documento no
equivale a correspondencia con el encargo. Resultado trazable privado en
`backend/datos_pivote/piloto-documental-20260910/INFORME.md`. No integración productiva
nueva. Ver handoff fechado «Piloto de documentos reales sin aplicación».

## Actualización: MEF y SUNAT recontrastados en código

El tramo posterior ya reconsulta ambas fuentes, con caché y sin heredar cruces.
Contrato MEF solo si es el exacto; aprobación 08-A permanece por identificar por
contenido/encargo. Sin aplicación histórica ni prueba viva. [Detalle](2026-09-10_codex.md#recontraste-mef-y-sunat).

## Actualización: recontraste y publicación de entregables

Cerrado en código el bloqueo permanente del tramo anterior: relectura de ficha
exacta, contrato explícito, recálculos auxiliares y publicación conjunta Excel/ZIP.
Si falla publicación siguen bloqueados; MEF/SUNAT no recontrastados son faltantes
explícitos, no datos heredados. Solo validación aislada, sin tocar jobs del cliente.
[Detalle, pruebas y límites](2026-09-10_codex.md#recontraste-posterior-y-publicación-conjunta-validación-aislada).

## Actualización: asociaciones conectadas con descargas

Aplicación explícita POST/MCP implementada y probada en carpetas temporales: fuente
exacta, huella vigente, respaldo fuera del ZIP y diario anti-entregas obsoletas.
Ningún job real modificado. Falta recontraste derivado; por seguridad el Excel se
bloquea después de aplicar (no reutiliza cálculos previos). Ver
[detalle y pruebas](2026-09-10_codex.md#aplicación-de-identidad-y-descargas-validación-aislada).

## Actualización: filtros y finalizador corregidos

Implementación local: RUC y contrato seleccionado impiden omisión por ficha única;
finalizador adjunta IDs y valida borradores. Fuentes oficiales obligatorias para
identificadores externos. Replay real sin red confirma que el control omitido ya
entra a investigación. No se corrige automáticamente el resolver, ni jobs ni
descargas. Ver handoff fechado «Corrección posterior al ensayo».

## Actualización: investigador ensayado con fuentes reales

Ocho ejecuciones Luna medium con/sin prompt; contexto/planificador local, no MCP
desplegado. Investigación útil, sin superioridad consistente del prompt; 2/4
salidas especializadas válidas. Filtro omite caso con ficha correcta y contrato de
otro rol. Job intacto por SHA256 de 3196 archivos. Sin cambios productivos aquí.
Ver informe sistema `.ai/experiments/2026-09-10_evaluacion-investigador-integrado.md`
y workspace privado `backend/datos_pivote/eval-identidad-20260910/`.
Supersede «sin nueva corrida IA» solo para investigador, no integración desplegada.

## Actualización: investigación integrada en código

El lote previo quedó en `382ee7b` (raíz `ad04b12`). Después se implementó el punto 2,
sin commit nuevo: contexto de lectura API/MCP, paso 6 de la skill, investigador por
caso y JSON separado validado. No aplicado al job ni a sus descargas; sin reinicio
del servidor, sin nueva corrida IA. Ver el handoff fechado, sección siguiente.

[Lote posterior de identidad y lectura](2026-09-10_codex.md#ficha-explícita-estable-y-lectura-investigativa):
ID explícito sin sustitución por fechas, SEACE sin certeza temporal, observaciones
visibles y consultas nuevas API/MCP de solo lectura. Pruebas offline; sin reinicio
ni regeneración real, sin commit. Investigación y asociación documental siguen
pendientes. El piloto previo sí se ejecutó (ver nivel sistema); esta nota
supersede las menciones históricas de «piloto sin ejecutar/modelo pendiente».

## 2026-09-10 — Identidad SEACE (Codex seace_identidad)

Plan cerrado implementado: bienes (`mainProcurementCategory=goods`) quedan en
`otro` aunque el texto mencione el proyecto; `works` mantiene ejecución con
equipamiento. La señal temporal reporta las fechas exactas pero es siempre
`DEBIL`; solo dos señales fuertes no temporales pueden confirmar y el helper
anticircular ignora temporal también en metadatos antiguos. Focal:
**79 passed** (`test_candado_seace.py` + `test_seace_abierto.py`). Sin jobs,
servicios, red ni cambios fuera del ámbito. Ver
`2026-09-10_seace_identidad.md`.

[Identidad de ficha y descarga corregida localmente](2026-09-10_codex.md#identidad-única-entre-ficha-y-descarga):
una selección activa y procedencia inicial conservada, también en subobras;
marcas ligadas a la ficha y retiro recuperable del corpus anterior. No cambia
scoring ni promueve candidatos. Suite 1425/25; entrega real aún sin regenerar.
Piloto separado preparado, sin ejecutar agentes; modelo/presupuesto pendientes.

Job Pucallpa **97ffb97a308e** terminado, requiere revisión; Excel generado y
ZIP con errores. [Continuidad y comprobación limitada](2026-09-10_codex.md#nueva-corrida-autorizada).
No usar el job anterior como si ya contuviera estas correcciones ni confundir
archivo generado con contenido validado. Backend del usuario sin reinicio.

Backend local detenido por petición del usuario, sin borrar datos ni tocar
PostgreSQL/Panel. [Cierre operativo](2026-09-10_codex.md#parada-local-posterior).

Correcciones 1 y 2 implementadas localmente: rubro indeterminado ya no confirma
identidad por lugar; mínimos estructurados y formato `(6)/(5) años` se leen.
[Pruebas, replay focal y límites](2026-09-10_codex.md#correcciones-1-y-2-identidad-de-establecimiento-y-mínimos-profesionales).
No reiniciado backend ni regenerado el job; sin commit. Golden sigue ausente.

Pucallpa `9c1409a6e9ba` reanudado por autorización: Excel OK tras corregir
el formateo de límites nulos; 135 pruebas focales pasan / 1 omitida. No se
repitieron etapas previas; ZIP descargando. [Continuidad técnica](2026-09-10_codex.md#excel-con-límite-de-puntaje-nulo-y-reintento).
Esto supersede el estado sin reintento siguiente; no hay commit del fix.

Preparativos autorizados completados: backend actual iniciado y MEF actualizado.
No se ejecutó Pucallpa ni se regeneraron entregables; [continuidad operativa](2026-09-10_codex.md#preparación-operativa-autorizada).
Esto supersede las menciones históricas de no reinicio siguientes.

Código del 10-sep versionado: **8c6c43c** privadas, **c665c0d** multiobra.
1371 pruebas pasan / 25 omitidas. Sin push/reinicio ni nueva corrida;
[preparación y límites](2026-09-10_codex.md#commits-solicitados-y-preparación-de-pucallpa).

## 2026-09-10 — Multiobra llega a descarga y ZIP

Corregida omisión del descargador: destinos por sub-obra identificada, caché
compartida, estados separados y notas propias en ZIP. No hereda fechas del
padre ni le asigna un CUI. Replay Pucallpa aislado con fuentes simuladas y
regresiones; [evidencia y límites](2026-09-10_codex.md#descarga-multiobra-implementada-tras-diagnóstico-de-pucallpa).
Sin relanzar jobs, reiniciar backend ni regenerar entregables del usuario.

## 2026-09-10 — Detector de institutos privados corregido

Calificadores educativos cerrados reconocidos sin relajar identificación de
CUI ni confundir emisor privado con cliente privado. Comparación sobre 925
entradas y regresiones dirigidas; [detalle y límites](2026-09-10_codex.md).
Sin regeneración de entregables ni reinicio de servicios.

## 2026-09-09 — Corrida real Puerto Firmeza (Ucayali) + 2 defectos en producción

Primera corrida completa de la skill sobre el concurso CP CON-SM-27-2026-GRU-GR-C-1 (GORE Ucayali,
supervisión de obra educativa). 7 profesionales / 15 experiencias, espejo válido, gate en verde,
backend `confiable` sin críticos. Job final **3f94d1bf3636**. [Detalle](2026-09-09_claude.md).

Salieron **dos defectos de código, no corregidos**: (1) `montos_postor.js` barre con margen e invade
el rango del contrato vecino, eligiendo montos ajenos y reportándolos como éxito — afecta al
requisito 3.4, que es de admisión; (2) `consolidar_espejo.js` no hace fallback de
`cuantia`/`limite_inferior` desde `bases.json`, y el backend rechaza con `OFERTA_INCOMPLETA`
(obligó a resubir). Ambos se sortearon a mano en la corrida, con trazabilidad en el espejo.

`base_mef` del servidor **stale a 33 días** (umbral 10). Quedan 3 ítems en revisión en el panel,
todos CUI de obra privada donde la respuesta correcta es "ninguno"; **el ZIP no se libera** hasta
resolverlos.

## 2026-09-08 — Entrada fiable y guardas de cálculo

Primer lote implementado y versionado a pedido del usuario, sin push/despliegue: mínimo desde bases,
auditoría preevaluación y al consolidar, baremo A sin defaults cuando faltan
reglas, fechas con evento y fuente en crudo. **1364 backend / 85 Node** pasan,
contrato 21 espejos. [Detalle y límites](2026-09-08_codex.md).
Prueba de extracción IA pendiente de elegir modelo. La corrida instrumentada
de sistema usa 6c28aab congelado y no estos cambios. Resolver intacto; golden
histórica ausente, sin inventar su resultado. Las entradas siguientes son históricas.

## 2026-09-06 — Mensajes y procedencia de expedientes

Implementada la primera corrección autorizada. Detalle, pruebas y limitaciones
en [handoff fechado](2026-09-06_codex.md). Sin cambiar resolver, cálculo ni
numeración; sin corridas nuevas ni regeneraciones. Cierre en commit solicitado
por el usuario; matriz consolidada en la arquitectura de nivel sistema. Próximo bloque:
guardas de origen/páginas, según el diagnóstico de nivel sistema.
Las entradas siguientes son históricas.

Última petición: commitear los pendientes de Pivote atómicamente. Separados por
tema: hoja ET, Gantt, orden de escaneo, ZIP, privacidad, scaffolding documental y
cierre de contexto. No se implementa el especialista ni se integra la sonda OCR.
Pruebas focales: backend 133 passed / 1 skipped; Node 54 passed. Ocho pruebas
adicionales sobre índice exportado verifican independencia del primer commit.
Validación documental local sigue con deuda de frontmatter histórica; no se
omitieron hooks ni se reformaron ADRs. Sin push/deploy. Detalle en handoff fechado.
Las entradas siguientes son históricas.

Última petición: orden procedural de ambas rutas mapeado por lectura de código.
Fuente canónica: [mapa actual](../../../.ai/architecture/mapa-procedural-actual.md).
No implementar sin distinguirlo del plan backend/skill. El mapa incluye autoridad
de conciliación, tres usos del juicio documental y secuencia Excel/descargas.
Sin cambios funcionales ni corridas. Véase primera entrada del handoff del día.
Validación local de conocimiento pendiente por frontmatter de tareas/ADR históricos;
detalle en handoff fechado. El mapa y la validación de sistema están correctos.

Plan posterior listo, no implementación: `../../../.ai/architecture/plan-expedientes-backend-skill.md`.
ADR-S010 propuesto. Backend sin preselección documental, entrega de texto íntegro
ordenado por MCP, especialista de skill solo en expedientes, retorno trazable y
reanudación. No promover el clasificador del sondeo. Véase primera entrada del
handoff de hoy; las entradas siguientes son históricas.

Última petición: sondeo de flujo Tesseract en worktree concluido, no integrado.
Registro canónico: `../../../.ai/experiments/2026-09-05_ocr-expedientes.md`.
Código y datos privados en worktree hermano del sistema `InfoObras-ocr-local`,
rama `sonda/ocr-expedientes` desde `328d780`. No fusionar como verificador:
la prueba respalda preprocesamiento, no asociación ni acreditación autónoma.
Véase primera sección del handoff de hoy. Lo que sigue es histórico.

Última consulta: recomendación de flujo económico, no implementación.
Fuente canónica: `docs/indicaciones_chat/busqueda/PROPUESTA_FLUJO_EXPEDIENTES.md`.
El usuario pregunta dónde consumir la evidencia; no ha autorizado esta nueva
implementación. Mantener lectura/verificación en backend y reutilizar resultados
para entregables; no remitir todos los PDF a la skill.

Investigación MEF ampliada a21 CUI. Informe canónico privado:
`docs/indicaciones_chat/busqueda/estudio_b_18_cuis_2026-09-05/INFORME_PATRON_APROBACION.md`.
Descarga completa de adjuntos disponibles directosB y de fichas de controversias
enlazadas desdeB; lectura por página, hashes y clasificación documental.
Continuación: convertir evidencia en plan de implementación, no adoptar un
selector por título ni por «SE RESUELVE» solamente. No se tocaron producto,
jobs o entregables ni se midió acierto automático. Sin Orca. Véase también
[handoff de investigación](2026-09-05_codex.md). Lo siguiente es histórico.

Nuevo requerimiento MEF: alcance confirmado solo B. Descargados todos los
adjuntos del caso2355382 y analizado patrón de aprobación; evidencia y límites
en `docs/indicaciones_chat/busqueda/cui2355382_seccion_b/ANALISIS_APROBACION.md`.
5 PDF/8 enlaces, lectura por página con OCR local y comprobación visual sin
Orca. No implementación general, no cambios de producto, jobs ni veredictos.

Organización posterior: notas e imágenes del usuario ahora viven en
`docs/indicaciones_chat/errores_encontrados/`; carpeta hermana `busqueda/`
creada vacía. Movimiento verificado por SHA-256 de los cuatro archivos.
Todo `docs/indicaciones_chat/` excluido de Git; sin cambios del sistema.

## Identidad de experiencias por escaneado implementada (Codex)

La numeración antigua por fecha final explicaba la discrepancia del reporte.
Nuevas extracciones asignan n contiguo según página física principal, y orden
de aparición entre periodos de una misma página. `auditar_orden_experiencias.js`
comprueba sin mutar: antes de evaluar (Paso 2.6) y dentro del consolidador.
Inversión comprobada o numeración inválida = crítico/exit 1. Página ausente =
advertencia explícita (no usa folio como sustituto, no certifica el orden).
No reordenar juicios ya emitidos: corregir extracción y repetir evaluación.

ZIP: carpetas `E{n} {proyecto abreviado}` (36 caracteres de nombre, saneados);
claves `n_prof:n_exp`, descargas `P#_E#` y recortes no cambian. Panel ya consume
n/proyecto del espejo; Gantt ordena visualmente por inicio conservando n/CUI.
No cambios de schema, resolver, jobs guardados, recortes reales ni Excel/ZIP
existentes. El junction local de la skill apunta al repo y recibe el ajuste;
no se reconstruyó paquete de distribución ni se desplegó nada.

Pruebas: 69 Node aprobadas (incluye gate CLI, unión por n y recortes PDF reales
sintéticos con anexos). Backend completo: 1296 passed / 25 skipped y un fallo
en el filtro del test NUEVO del Gantt (incluía también encabezados). Filtro
corregido, sin cambio de producto: repetición `--lf` 1 passed; gate de Excel,
Gantt y ZIP 125 passed / 1 skipped. No se repitió toda la suite después de
corregir ese test. Auditoría de solo lectura sobre el caso reportado detecta
las inversiones; no se guardó renumeración.
Decisión transversal registrada en ADR-S009 del nivel sistema. Sin Orca,
subagentes ni commit. Lo siguiente es historia de las presentaciones.

Presentación vigente: **Gantt continuo bimestral**, sin dividir trayectorias.
Conserva ambas ubicaciones (profesional/general), fechas Inicio/Fin, C/R,
supuestos, leyenda y cálculo. Retirada segmentación de tres años. 70 focales
aprobadas; Excel más reciente regenerado con respaldo, valores anteriores al
Gantt y JSON intactos. Muestra real inspeccionada en memoria, sin Orca/scratch.
No nueva corrida, cambios de resolver ni commit. Lo siguiente es histórico.

Última intervención (Codex): Gantt de expedientes con meses completos, años,
Inicio/Fin y C/R fechados, leyenda explícita y tramos de hasta 36 meses.
Preserva avisos de fechas deducidas, valores anteriores al Gantt y cálculos.
Suite completa 1293 passed / 25 skipped; último ajuste del contador cubierto
por gate de 69 focales. Excel más reciente regenerado con respaldo, JSON intactos.
Investigación privada de cobertura: referencias contractuales desaprovechadas,
rutas privadas, recuperación/geografía de candidatos, identidad de emisor y
cola multiobra. NO se implementó nada del resolver ni se promovieron decisiones.
Véase [informe privado y plan](../../docs/comercial/auditorias/2026-09-05-rutas/investigacion-identificacion-expedientes.md).
Sin Orca/deploy/commit nuevo. Las entradas siguientes son históricas.

Último ajuste: checkpoint `328d780` antes de retirar las tarjetas de cruces
independientes SOLO en expedientes. Las incidencias/motivos y fechas inferidas
quedan junto al certificado; Parte 5 y conclusión conservan contenido/formato,
y los Gantt conservan imágenes idénticas en la muestra real. Obras sin cambios
en el control antes/después. **159 pruebas focales aprobadas**; ocho regresiones
nuevas en `test_expedientes_sin_tarjetas_cruces.py`. Excel más reciente
regenerado con respaldo, fuentes originales intactas; scratch propio a Papelera.
Sin Orca, push/deploy ni suite completa nueva. Cambios posteriores al checkpoint
sin commit. Las entradas siguientes son históricas.

Actualización posterior: leyenda explícita del Gantt con cinco muestras de
color, C/R/≈, meses/trimestres y lectura de cruces, compartida entre imagen y
cronología general mediante `entregables/leyenda_gantt.py`. **60 pruebas
focales aprobadas**; comprobación de límites a 1100/1800 px y render sintético
revisado. Regeneración del Excel más reciente con respaldo y fuentes intactas.
Sin Orca, cambios de cómputo ni despliegue; no se repitió suite backend completa.

Último resultado: expedientes implementado con tres Sol nativos, bajo plan
cerrado y revisión de Codex; sin Orca. Parte 5 declarada/computada simplificada,
Gantt final por profesional y correcciones de fechas, fuentes y estados.
Gate completo: **1281 passed, 25 skipped**; dos rutas regeneradas offline,
obras conserva valores/formato en la muestra; Excel nativo inspeccionado.
Sin migrar jobs ni alterar UI Panel, sin commit/push/deploy. Regenerar los Excel
guardados para ver el formato nuevo. Scratch propio retirado a Papelera.
Detalle y límites: [cierre privado](../../docs/comercial/auditorias/2026-09-05-rutas/cierre-expedientes-sol.md).
Las entradas siguientes conservan la secuencia histórica anterior al cierre.

Última petición: [plan privado de corrección de expedientes](../../docs/comercial/auditorias/2026-09-05-rutas/plan-correccion-expedientes.md)
preparado por Codex, sin Orca ni delegación. Solo planificación; implementación
pendiente. Cubre los siete defectos del Excel, coherencia API y regresiones de
obras/Gantt; la interfaz del Panel y la normalización de tipo histórico quedan
fuera de este paquete.

Limpieza posterior del 5-sep, a pedido del usuario: se retiraron las cinco
corridas de auditoría (a Papelera) y seis scripts auxiliares. Informes, plan,
código, tests y fuentes originales preservados. El cierre privado documenta
la verificación realizada antes de limpiar, no artefactos aún presentes.

## Cierre del Gantt supervisado por Codex (2026-09-05)

Luna implementó el plan cerrado del coordinador. Admisión C/R alineada con
evidencia estructurada; cruces visibles, período declarado, años y alturas
legibles; impresión A3 de expedientes con escala y saltos por profesional.
Gate integrado final: **75 passed**. Dos rutas regeneradas offline sin cambiar
fuentes; obras conserva valores/colores salvo fecha de generación. Render
nativo final comprobado. Los fallos parciales de abajo quedaron resueltos.
Sin push/deploy; los demás hallazgos originales no se declaran cerrados.
Detalle: [cierre privado](../../docs/comercial/auditorias/2026-09-05-rutas/cierre-correcciones-gantt.md).

## Entrega `luna_hitos` (2026-09-05)

Se corrigió la admisión de `C` y `R` en `entregables/cronologia.py`: la firma
SEACE usa el mismo candado estructurado de los cruces; contratos MEF atados al
emisor siguen permitidos; fechas de resolución descartadas o atribuidas a otro
consultor no se dibujan. Test nuevo: **5 passed**. Gate focal junto a
`test_cronologia_gantt.py`: **28 passed, 1 failed** por la expectativa de ancho
concurrente (`ws.max_column == 4` vs `MIN_COLUMNAS == 80`); no se editó el test.
Pytest avisó que no pudo escribir `.pytest_cache` (`WinError 5`). Handoff
completo en [`2026-09-05_luna_hitos.md`](../../.ai/handoffs/2026-09-05_luna_hitos.md).

## Auditoría de rutas (5-sep, Codex)

Actualización posterior al Gantt `fcf362c`: regeneradas ambas rutas, 51 pruebas
focales y exportación nativa de Excel inspeccionada. Hallazgos y límites en
[`revisión privada de cronología`](../../docs/comercial/auditorias/2026-09-05-rutas/revision-cronologia.md).
Sin correcciones de producto; las hojas profesionales conservan valores/colores
de la auditoría inicial. Esta comprobación visual corresponde al Excel, no al Panel.

El usuario pide claridad por separado para expedientes y ejecución, Excel
primero. Hay diagnóstico reproducible, sin correcciones de producto, en
[`informe privado de rutas`](../../docs/comercial/auditorias/2026-09-05-rutas/informe.md).
El informe separa problemas actuales del generador, compatibilidad de jobs
históricos y oportunidades de rendimiento. Gates focales: 118 passed;
TypeScript limpio. Comprobación del Panel por código/API; captura visual
no completada por desconexión del runtime de Orca.

> Actualizado: **2026-08-20**. Si eres un agente nuevo: lee esto completo,
> luego `context/current_state.md` y los ADRs. No necesitas ninguna
> conversación previa.

## Nota (2026-09-05, Claude) — ADR-010 implementada en su versión mínima

Motivo: el cliente validará por su cuenta una propuesta de EXPEDIENTES y no se
puede depender de `PIVOTE_FORZAR_EXPEDIENTES`. Se implementó el parámetro
`_meta.tipo_evaluacion` en las tres copias del contrato, un único punto de
decisión `es_expediente_exp(exp, tipo, forzar)` con precedencia parámetro > env
> texto, estampado en memoria para el resolver, form-field opcional en
`/analizar`, y `consolidar_espejo.js --tipo` con inferencia determinística y
crítico bloqueante si no se determina. `agent-bases` debe emitir
`metadata_concurso.tipo_evaluacion`. Gate: 1037 passed / 25 skipped; skill 60
tests; Panel `tsc` limpio. Resolver intacto; golden no aplica. Detalle y lo que
quedó fuera: cola de `decisions/ADR-010`.

## Nota (2026-09-05, Claude) — un CUI mal transcrito ya no adquiere autoridad sola

El Paso 0 resolvía cualquier código citado que existiera en InfoObras aunque el
nombre no compartiera un solo término; solo lo frenaban la contradicción triple
de #59 o la función MEF de #69. Las sub-obras por código se aceptaban sin cotejo.
Ahora `_cotejo_codigo` + `_codigo_dudoso` mandan a revisión, con la obra del
código a la vista, cuando no hay afinidad de nombre Y además (a) el código calzó
solo contra el SNIP de una obra que tiene otro CUI, o (b) la obra contradice el
departamento o el rubro que el certificado declara. Abstención pura; Fortaleza
(componente sin departamento) y COAR (afinidad ≥ 1) siguen resolviendo, con
tests. Auditabilidad de #50: `enr["camino"]` y `enr["camino_fuente"]` por
experiencia; la hoja CLAUDE rotula el tipo de concurso. Gate: **1046 passed, 25
skipped**. Lección: una señal de contradicción no puede disparar por AUSENCIA de
dato (obra sin CUI propio ≠ CUI distinto); se anotó en `memory/common_mistakes.md`.

## Nota (2026-09-05, Claude) — puntaje mudo y días perdidos en la corrida real

Revisión del Panel sobre el job real de expedientes (12 profesionales). El Panel
no estaba desactualizado: mostraba fielmente dos defectos del backend.
1. **Factor A nunca se recalculaba**: `_recalcular_factor_a` y
   `_participantes_factor_a` buscaban `factor == "A"` literal y el consolidador
   emite `"A — Experiencia específica…"` desde #88 (16-ago). Resultado: puntaje
   None, total condicionado para siempre, Panel «—» y tarjetas de factores en
   blanco. Nuevo `_letra_factor` tolera letra sola, «Factor A» y «A — nombre».
2. **Fechas de solo mes y año descartadas en silencio**:
   `reconciliar_resultados_profesionales` (alimenta `/resumen`, Panel y Excel) y
   el Paso 5 leían solo ISO completo; el recálculo sí deducía el mes completo
   autorizado por las bases (`periodos_sin_dia`), pero nadie lo consumía. Dos
   profesionales bajo el mínimo por eso (439 de 759 días; 534 de 838). Nuevo
   `validacion.recalculo.fechas_calculo` es el único criterio de fechas para
   contar días, usado por pipeline, Excel y API.
3. `/resumen` ahora expone `aplica`, `estado_puntaje`, `puntaje_confirmado` y
   `puntaje_maximo_posible` por factor y el rango total; el Panel pinta «Por
   verificar» con el rango en vez de casilla vacía. `reconciliar_puntajes` trata
   como piso 0 al factor condicionado con máximo conocido (el del Comité).
Reproducido sobre el job real: prof. 5 pasa de 439 a 759 días, prof. 9 de 534 a
838, Factor A a 60 definitivo. Gate: **1065 passed, 25 skipped**; Panel `tsc`
limpio. Para ver el efecto hay que reiniciar el backend y resubir el análisis.

## Nota (2026-09-05, Claude) — un expediente ya no muestra ni baja valorizaciones

Caso real (prof. 2, exp. 1): enrutado como `expediente/declarado`, pero la hoja P
decidía el bloque por «¿hay verificación MEF?» y el MEF no publicaba contrato para
ese CUI → pintó 62 valorizaciones de la construcción; la descarga bajó 208
archivos de la obra sin mirar el camino. Ahora `render_obra` decide por el
`camino` del enriquecimiento o el tipo declarado; sin fuente MEF ni aprobación
escribe «POR VERIFICAR» y no pinta la fase de ejecución. La descarga aplica
`secciones_descarga_por_camino`: obra citada solo por expedientes → únicamente
«Aprobación del expediente» y «Verificación MEF», con aviso en el índice. La skill
pregunta el tipo de concurso al inicio si el usuario no lo dijo con los PDF. Gate:
**1068 passed, 25 skipped**. Cierra el pendiente de ADR-010 «filtro de secciones
de descarga por camino».

## Nota (2026-09-05, Claude) — la resolución de aprobación del expediente ya se lee

Prioridad alta de Rafael. El backend descarga la resolución del 08-A del MEF de
cada expediente verificado y la lee (capa de texto u OCR local: `scraping/ocr_local.py`,
mismo Tesseract y modo que la skill). `validacion/resolucion_aprobacion.py`
extrae fecha oficial, consultores nombrados y cita del CUI, y contrasta al emisor
por frase completa junto a un rol. Efectos: la Regla B usa la fecha leída (gana a
la deducida de InfoObras); si la resolución nombra a otro consultor la regla se
abstiene con la razón escrita y se emite ADVERTENCIA `RESOLUCION_ET`; la hoja P
muestra fecha y consultor con ✔/✗; los cruces se recalculan al regenerar si la
lectura es posterior; `contrato.veredicto` ya no es «ok» por mera existencia. La
skill captura la resolución citada en el certificado (`resolucion_aprobacion_numero/fecha`,
contrato aditivo en 3 copias). Tesseract entra al Dockerfile. Gate: **1083 passed,
25 skipped**; skill 60; Panel `tsc` limpio. Job real regenerado: 11 resoluciones
leídas; la Regla B dispara en dos experiencias que declaran término posterior a la
aprobación. Pendientes en `tasks/backlog.md` (T-TAREA-RESOLUCION-APROBACION).

## Nota (2026-09-05, Claude) — candidatos con su resolución y checkpoint de fase

Segunda entrega de la lectura de resoluciones. (1) Las experiencias de expediente
que quedan en revisión leen la resolución de aprobación de sus candidatos (máx. 2,
sin repetir CUI) y lo dicen en el ítem de revisión y en el bloque «EXPERIENCIA EN
REVISIÓN» de la hoja P: «la resolución del candidato X nombra a Y, no al emisor» /
«nombra al emisor» / «no nombra a quien elaboró». No resuelve (regla de oro).
(2) `_checkpoint_fase`: un certificado de ELABORACIÓN DEL EXPEDIENTE con CUI
citado y confirmado por el MEF ya no cae a revisión porque InfoObras solo registre
la contingencia/ejecución; se conserva la identidad y se anota qué registra
InfoObras (caso real 7:1). (3) Extracción de nombres endurecida: sin verbos ni
prosa, sin nombres de una letra, quitando roles pegados. Privadas: sin cambios,
por decisión de Rafael. Gate: **1087 passed, 25 skipped**. Job real actualizado
(motivos de revisión y Excel).

## Nota (2026-09-05, Claude) — tres vías nuevas de resolución automática (decisión de Rafael)

Rafael: «no hay golden ni habrá; tiene que bajar mucho más de 21 a 15». Se
promueve con fuente oficial y condiciones estrictas:
- **NUMERO** (resolver, `_compuertas`): el N° de I.E./C.E. del certificado coincide
  con la obra, ninguna otra obra del ranking lo comparte, el candidato viene de
  InfoObras, sin contradicción de ubicación (nombre o `ubicacion`), la obra no añade
  un rubro ausente en el certificado, puntaje ≥ 70.
- **CONTRATO** y **RESOLUCION** (etapa InfoObras, pre-pase sobre expedientes en
  revisión): contrato DE EXPEDIENTE del MEF a nombre del emisor, o resolución de
  aprobación que lo nombra. Solo si exactamente un candidato recibe señal.
- Nueva abstención: si la obra hallada añade un rubro que el certificado no
  menciona (alcantarillado en la I.E. X vs construcción de la I.E. X) → revisión.
- `_RE_EST` reconoce «clínica»: RENIPRESS deja de buscar con la frase entera.
Vocabulario `via` ampliado en enriquecimiento, Excel y Panel. Replay offline del
job real: NUMERO rescata 1:2 y 12:5 y NO toma 12:3 (otra intervención). Gate:
**1097 passed, 25 skipped**; Panel `tsc` limpio.

**Para la corrida de expedientes**: invocar la skill diciendo que el concurso es
de expedientes y pasar `--tipo expedientes` al consolidar; revisar a mano las
vías CODIGO y PROBABLE; en la verificación MEF mirar el veredicto del
contratista, no el del contrato. Ver `InfoObras/.ai/handoffs/2026-09-04_claude.md`.

## Nota (2026-08-20, Codex) — arquitectura ejecutiva detallada

La arquitectura canónica se amplió a la revisión **2** para mostrar el valor
técnico y operativo real de Pivote: **20 componentes**, **39 conexiones
etiquetadas** y **7 escenarios**. El mapa separa el análisis documental en la
PC, el contrato espejo y MCP, el control on-prem, las nueve etapas, el escudo de
integridad, el resolver CUI, los cruces y reglas, cada familia de fuente estatal,
la plataforma MEF local, la trazabilidad, Excel, ZIP y operación.

Se asignaron posiciones y colores Catppuccin por capa. La mayor granularidad no
representa microservicios nuevos: son capacidades verificadas en entrypoints,
módulos, clientes, schemas y despliegue. La revisión se guardó mediante
`raf-ai architecture set --expected-revision 1` después de validar el draft;
el envelope canónico no se editó a mano.

## Nota (2026-08-20, Codex) — adopción RAF y arquitectura visual

Se ejecutó `raf-ai init` con perfil `repo` y soporte para Claude, Codex y Agy;
la operación creó únicamente los archivos RAF ausentes y conservó la base de
conocimiento y los cambios locales existentes. El proyecto quedó registrado con
ID `pivote`.

La arquitectura canónica se generó desde el código y se guardó por la API de
revisión de RAF en `.ai/architecture/architecture.json`, revisión **1**:
9 componentes, 13 conexiones etiquetadas y 3 escenarios. Incluye los límites de
runtime de Skill, MCP, Panel, API, motor, resolver CUI, fuentes oficiales, datos
y entregables. `arquitectura.json` en la raíz es solo una referencia histórica.

Para regenerarla desde este checkout: leer primero el estado actual con
`raf-ai architecture get --json`, producir solo `ArchitectureData`, validar el
borrador y guardarlo con `raf-ai architecture set <archivo>
--expected-revision <revision>`. Nunca editar directamente el envelope canónico.

## Nota (2026-08-16, Codex) — correcciones RUC/CUI y trazabilidad en Panel

Se añadió `POST /api/pivote/jobs/{job_id}/correcciones/ruc`: valida el RUC,
actualiza `ruc_emisor` en el espejo y ejecuta solo SUNAT → reglas → Excel →
persistencia para esa experiencia. No llama InfoObras, no altera descargas y no
reinicia el ZIP. Tanto esta acción como la resolución CUI registran una entrada
persistente en `Job.correcciones_humanas` con estado consultable.

En Panel-InfoObras, Profesionales muestra/edita el RUC por experiencia; Revisión
se reorganizó como mesa de decisiones ancha y explícita; y Resultados/Descargas
indican que el Excel incorpora las correcciones, distinguiendo el efecto sobre
el ZIP. El mock cubre el mismo contrato. Gate: backend **1004 passed, 25
skipped**; Panel `npx tsc --noEmit` y `next build` aprobados. El resolver CUI no
cambió, por lo que no aplica golden. Sin datos de cliente en los repos.

## Nota (2026-08-14, Codex) — plan #89–#100 implementado y verificado

La corrección quedó versionada localmente en `6a005d3`; no hubo push.
El contrato espejo subió a v1.4 y separa reglas oficiales, hechos literales,
campos calculados y estados condicionados. El backend asumió como autoridad:
fechas inclusivas (incluido mes completo si lo dicen las bases), formación por
vía documental, experiencia monetaria del postor, Factor A, vigencia/titularidad
ISO, reconciliación de puntajes, cronología e inventario documental.

Frontera de fuentes: **no se implementó scraping ni llamada a MINEDU, SUNEDU,
INACAL ni a otra fuente estatal nueva**. La comprobación registral académica es
manual del Comité. Las fuentes preexistentes del producto no se ampliaron.

Descargas: un ledger persistente marca cada fuente lógica antes de red; el
resultado parcial es terminal, GET `/zip`, reinicios, revisiones y regeneración
del Excel no vuelven a descargar. El Excel solo muestra `No se encontraron
documentos`, `1 archivo encontrado` o `N archivos encontrados`; el Panel admite
`listas_con_errores` como ZIP descargable con faltantes.

Gate ejecutado:

- `pytest backend/tests -q`: **1000 passed, 25 skipped**.
- `node --test skill/scripts/consolidar_espejo.test.js`: **39 passed**.
- contrato legado de referencia: válido.
- Panel `npx tsc --noEmit`: válido.
- `next build`: no se pudo ejecutar porque el dev server activo bloquea
  `.next/trace` (`EPERM`); no se detuvo ni se borró ese entorno.
- Resolver CUI intacto; no aplica golden perdida.

Las issues #89–#100 recibieron comentarios de implementación. #98 se corrigió
para que la completitud sea **analítica** e independiente del ZIP. Su estado
remoto no se modificó como parte de este commit.

## Nota (2026-08-14, Codex) — auditoría generalizada en issues #89–#100

Una nueva auditoría local de un entregable real detectó once defectos de reglas,
reconciliación y presentación. La evidencia y los datos del cliente no se
publicaron: los reportes se redactaron como regresiones generalizables y sin
identificadores. Quedaron abiertos en GitHub: acreditación académica [#89],
Factor A [#90], narrativa contradictoria [#91], semántica de cronología [#92],
periodos mes/año [#93], conteo inclusivo [#94], corte temporal [#95], fecha
oficial e ISO [#96], experiencia mixta del postor [#97], gate de completitud
del Excel [#98] y equivalencias de cargo [#99].

El criterio funcional de documentos quedó aclarado en [#100]: cada documento
se descarga una sola vez; el Excel solo informa cero, uno o N archivos
encontrados y no muestra estados operativos ni provoca redescargas.

[#89]: https://github.com/rafram96/Pivote/issues/89
[#90]: https://github.com/rafram96/Pivote/issues/90
[#91]: https://github.com/rafram96/Pivote/issues/91
[#92]: https://github.com/rafram96/Pivote/issues/92
[#93]: https://github.com/rafram96/Pivote/issues/93
[#94]: https://github.com/rafram96/Pivote/issues/94
[#95]: https://github.com/rafram96/Pivote/issues/95
[#96]: https://github.com/rafram96/Pivote/issues/96
[#97]: https://github.com/rafram96/Pivote/issues/97
[#98]: https://github.com/rafram96/Pivote/issues/98
[#99]: https://github.com/rafram96/Pivote/issues/99
[#100]: https://github.com/rafram96/Pivote/issues/100

## Nota (2026-08-14, Codex) — auditoría local de un entregable real

Se documentó una auditoría completa de consistencia, reglas, cómputo de días,
trazabilidad y presentación de un entregable real. El detalle contiene datos del
cliente y quedó únicamente en
`docs/comercial/auditorias/2026-08-14-auditoria-entregable.md`, ruta gitignored;
**no versionar ni trasladar a issues públicas**. No hubo cambios de producto,
resoluciones ni datos del job.

## Nota (2026-08-13, Claude) — aprendizajes de una corrida extensa

Una corrida end-to-end de consultoría de obra confirmó cuatro fricciones
reutilizables de la skill. El corpus, los resultados y los identificadores del
concurso permanecen fuera del repositorio. El detalle técnico anonimizado está
en [`2026-08-13_claude.md`](2026-08-13_claude.md):

1. `_veredictoSinSustento` puede dar un falso positivo cuando existe un
   paréntesis explicativo antes de la raya que introduce el sustento.
2. `resumen_evaluacion.factores[]` exige `factor`, pero el prompt permite que
   el evaluador produzca naturalmente `codigo` y `nombre`.
3. `_meta.fecha_presentacion_oferta` no debe depender de una sola ubicación
   del mapa cuando la fecha también puede estar estructurada en las bases.
4. Las propuestas extensas necesitan salidas segmentadas
   (`_eval/eval_NN.json`) y una fusión determinística con control de cobertura.

También se confirmó que los títulos presentados solo como imagen necesitan una
segunda lectura visual y que las constancias emitidas por el postor o por otro
integrante del plantel requieren un candado determinístico de afiliación.

## Nota (2026-08-12, Claude) — diseño anonimizado de posibles Pasos 6 y 7

Se analizaron materiales locales del cliente para dos extensiones potenciales:
**Paso 6**, constatación nominal del profesional en Informes de Control CGR, y
**Paso 7**, contraste del cargo certificado contra las bases o especificaciones
de la obra de origen más un resumen por proyecto. Los documentos y entregables
reales permanecen fuera del repositorio y su carpeta está gitignored.

Parte de la adquisición ya existe: bases y contrato SEACE, aprobación del
expediente, informes CGR y datos CUI/RUC/MEF. El alcance nuevo es interpretar
los informes y contrastar el cargo contra la fuente de la obra de origen. La
ausencia de un nombre no prueba inasistencia, por lo que esta señal debe ser
auxiliar y abstenerse ante ambigüedad. Detalle técnico anonimizado en
[`2026-08-12_claude.md`](2026-08-12_claude.md).

## Nota (2026-08-10, Codex) — `ARCHIVOS (ZIP)` muestra archivos encontrados

La columna por valorización dejó de depender de `descargas_reales.por_hito` y
de mostrar `Pendiente`: ahora usa `valorizaciones[].docs`, el número de adjuntos
encontrados por el parseo de InfoObras, exista o no una descarga iniciada o
completa. El estado operativo sigue separado en el seguimiento de descargas.
Validado con una regresión 9 encontrados/2 descargados y con una copia offline
del job `00a9816dc632`; P6 E4 muestra 1 archivo en cada uno de sus diez hitos y
ninguna celda `Pendiente`. Gate: **990 passed, 25 skipped**. Resolver intacto;
no aplica golden. El `final.xlsx` activo no se sobrescribió.

## Nota (2026-08-10, Codex) — mínimo `0.5 años (6 meses)` corregido

El job `00a9816dc632`, profesional 7, reveló que `_minimo_exigido()` solo
aceptaba enteros: `0.5 años (6 meses)` terminaba como `mínimo sin dato`. El
parser acepta ahora punto/coma decimal, prioriza la equivalencia explícita de
las bases (`6 meses` = 180 días) y redondea hacia arriba cuando solo existe un
decimal. La corrida y la reconciliación del API/Excel consumen la misma función.

Comprobación sin red mediante reconciliación API y Excel temporal: muestran
`623 días provisionales contra un mínimo de 6 meses`; el estado permanece `POR
VERIFICAR`. El Uvicorn ya activo continuó a la vez las descargas diferidas del
job y completó su ZIP; ese avance no se revirtió. El `final.xlsx` real aún fue
generado con el proceso viejo y conserva `mínimo sin dato`: reiniciar backend y
regenerar después. Gate: **990 passed, 25 skipped**; 140 focales + 1 skip.
Resolver intacto, no aplica golden. No hubo commit, push ni despliegue.

## Nota (2026-08-07, Codex) — cierre versionado del bloque P0

Los cambios acumulados de verificación mixta, entregables y documentación
quedaron versionados en Pivote en el commit que contiene esta nota. Las mejoras
de claridad, alertas, revisión, experiencias y compatibilidad con `sub_obras`
de jobs antiguos quedaron versionadas en Panel-InfoObras como `1fcf2dd`.
Validación final: **988 passed, 25 skipped**, TypeScript y build Next.js
aprobados; ambos repos limpios. No hubo push ni despliegue.

## Nota (2026-08-06, Codex) — lenguaje del Panel y alertas legibles

El Panel dejó de exponer al evaluador códigos y vocabulario interno como
`CARGO_NUCLEO`, `RECALCULO`, `FECHA_CONTRATO`, «backend», «Claude», «espejo» y
«recálculo determinístico». La traducción vive solo en presentación: los datos
originales del análisis no se reescriben. Alertas ahora enfrenta cargo de la
constancia vs requisito y conceptos faltantes; compara días declarados vs
calculados con diferencia; y presenta inicio vs firma del contrato con margen
de 15 días. El resto de códigos conocidos tiene nombre y explicación para el
evaluador, con fallback legible para códigos futuros.

La misma capa se usa en Proceso, Resultados, Profesionales, revisión humana,
mensajes de salud y errores visibles. Se validó CIBA `41a442cdcd81` en Brave:
los 9 casos de cargo, 7 recálculos y 3 fechas se renderizan estructurados, sin
modificar ni resolver el job. Gate Panel: `npx tsc --noEmit`, `git diff
--check` y `npm run build` aprobados. No hubo cambio de resolver/backend, por lo
que no aplica pytest/golden. Panel dev quedó activo en `:3002`; API siguió
activa en `:8001`. Cambios locales, sin commit/push/deploy.

## Nota (2026-08-06, Codex) — expediente técnico visible y contraste corregido

La revisión CUI explica ahora que el candidato identifica la inversión, no el
servicio, y muestra recomendación/diferencias semánticas sin porcentajes. En
Profesionales se renderiza el bloque SEACE/MEF del expediente separado de la
ejecución física. El backend coteja al contratista con la empresa emisora y no
con la persona firmante; mantiene fallback para consultores persona natural y
jobs antiguos. CIBA `1:9` se comprobó visualmente sin resolverlo. Gate: **988
passed, 25 skipped** + build Next.js; resolver intacto, no aplica golden.
Cambios locales, sin commit/push/deploy. El Uvicorn que ya estaba corriendo no
se reinició: debe reiniciarse antes de resolver casos para cargar el backend
nuevo.

## Nota (2026-08-06, Codex) — P0 del Panel implementado

Se cerraron localmente los cuatro bloqueadores de exactitud hallados en la
auditoría: Profesionales y Resultados consumen `estado_efectivo` del backend;
las observaciones ya no se duplican ni se mezclan como una sola cifra; MEF
desactualizado usa el mensaje real y color de advertencia; y API/Excel comparten
una reconciliación offline compatible con jobs antiguos. La herramienta
`tools/utils/regenerar_excel_final.py` dejó el camino paralelo y usa el helper
canónico con certificados y confiabilidad.

Validación real CIBA `41a442cdcd81`: 9/9 «Por confirmar» en `/espejo` y
`/resumen`; 21 requieren atención, 55 advertencias y 61 informativas. Excel
respaldado y regenerado con 12 hojas/129 imágenes. Gate: **987 passed, 25
skipped**, sin cambio en `resolucion/cui.py` (no aplica golden); Panel compila y
construye producción. Cambios locales en Pivote y Panel, sin commit/push/deploy.

## Nota (2026-08-06, Codex) — T-018 registrada como idea cross-repo

Rafael propuso convertir el JSON OCDS de SEACE en un explorador legible por CUI
en el Panel, con procesos clasificados y descarga selectiva de bases, contrato y
otros documentos. No duplica T-016: esta última es MCP/descarga puntual; T-018
es contrato normalizado + superficie visual. Quedó en discovery, sin precio ni
aprobación, en Pivote #84, Panel #2, `InfoObras/.ai/tasks/_backlog.md` y
`projects-list` como oportunidad no sumable.

## Nota (2026-08-06, Codex) — issue #83 implementada

El cruce RUC emisor ↔ adjudicatario SEACE quedó implementado localmente. F5
persiste ahora `adjudicatarios` con nombre/RUC/origen y conserva la lista
histórica de RUC. SUNAT aplica los casos 0–3 solo si el candado tiene ≥2 señales
fuertes independientes de `adjudicatario`: igualdad de RUC se verifica; nombre
de integrante se rotula sin sustituir; discrepancia declarada alerta sin
corregir; sin RUC y score ≥85 enriquece, 60–84 conserva el flujo, <60 bloquea la
contaminación. Jobs antiguos y cobertura pre-2018 permanecen iguales. Gate:
**985 passed, 25 skipped**, 91 focales, compileall/diff-check limpios;
`backend/resolucion/cui.py` intacto, no aplica golden. Cambio versionado
localmente en `31572d3`; falta push, despliegue verificado y cierre de #83.

## Nota (2026-08-06, Codex) — paquete documental de entrega preparado

Se creó `docs/entrega-final/` con índice, manual de la skill, manual del Panel,
manual de uso/operación de la base MEF y setup coordinado de servidor + equipo
del evaluador. Los documentos públicos usan marcadores de red y no contienen
precios, secretos ni datos de concursos. La guía interna para presentar extras
quedó en `docs/comercial/guion-presentacion-extras-entrega-final.md`, ruta
gitignored: incluye discurso de valor, demostraciones, objeciones y el mapa
comercial vigente, por lo que no debe commitearse. El setup refleja el compose
actual de tres servicios (`db`, `backend`, `panel`) y el runtime vigente de
Claude Code con skill enlazada; no revive el plugin histórico.

## Nota (2026-08-06, Codex) — privadas SUNAT y subobras visibles

Se cerraron localmente los puntos 1 y 2 de la auditoría CIBA. La regla privada
ahora exige un RUC SUNAT inequívoco para considerar efectivo el tiempo: sin
coincidencia o con varias coincidencias el Excel rotula **«REVISIÓN — RUTA
PRIVADA / SUNAT PENDIENTE»** y conserva los días como provisionales. La misma
clasificación alimenta la corrida normal, la regeneración posterior a descargas
y el endpoint `/excel`; no hay tres implementaciones divergentes. Replay real
`41a442cdcd81`: **40 privadas = 26 identificadas + 14 pendientes** (11 sin
coincidencia, 3 ambiguas), 12 hojas y 129 imágenes conservadas. Los tres Excel
corregidos son byte a byte idénticos; respaldo previo en
`backend/datos_pivote/41a442cdcd81/backups/pre-privadas-sunat-20260806-140726/`
(todo gitignored).

El contrato `GET /api/pivote/jobs/{id}/espejo` expone además `sub_obras` y
`multi_rubro`. El Panel muestra el resumen «N de M obras identificadas», nombre,
CUI, estado, vía, decisión y advertencia de rubros mixtos. Gate: **974 passed,
25 skipped** en backend y `next build` productivo aprobado. Resolver CUI
intacto, por lo que no aplica golden. Cambios todavía locales, sin push ni
deploy; PANEL#1 debe cerrarse recién al publicar ambos repos.

## Nota (2026-08-06, Codex) — ruta privada explícita y cobertura de expedientes

En un concurso mixto apareció una contradicción del camino A: el clamp externo
ya excluía expedientes, pero `cobertura_baja` y las paralizaciones internas de
la construcción todavía podían llegar a REGLAS. Se cerraron ambas puertas:
elaboración/supervisión de expediente se verifica por contrato/aprobación, no
por valorizaciones de la ejecución. Además `[PRIVADA]` con RUC SUNAT inequívoco
ya no significa revisión provisional: el Excel la rotula en Base de Datos, hoja
P y Cronología como ruta SUNAT + certificado, declarando que
InfoObras/MEF/SEACE no aplican. Sin RUC único se usa `[PRIVADA_PENDIENTE]` y el
tiempo sí es provisional. Resolver
intacto (sin golden); **971 passed, 25 skipped**. El replay real y sus respaldos
siguen únicamente en `backend/datos_pivote/` (gitignored).

## Nota (2026-08-06, Claude) — limpieza del backlog de GitHub

Por orden de Rafael se cerraron **#81, #5, #27, #24** (completadas) y **#25**
(*not planned*, NO-GO medido). Luego **#49 y #71 se fusionaron en la nueva
[#82 «Analisis Ahorro de Skill»](https://github.com/rafram96/Pivote/issues/82)**
y ambas se cerraron apuntando allí. #82 concentra: diagnóstico de código de #49
(implementación en sombra, 33/34 del divisor, prompts medidos), baseline de #71
(Vitarte 1.59M, `/cost` USD 31.12 / 35M cache reads), candidatos **C1–C6 con
numeración unificada** (C6 = tiering de modelo, nacido del `/cost`), R0, metas
ponderadas por categoría de token y gates. Es extra cotizable (= T-013 en
`projects-list`, referencia ya actualizada a #82); no bloquea el cierre del
contrato. Abiertas en Pivote: **#70, #50, #82** (+ PANEL#1 en el panel).
Menciones a #49/#71 más abajo en este archivo son históricas.

## Nota (2026-08-05, Claude) — #24 cerrada e #25 medida (NO-GO)

Dos issues aprobadas por Rafael, un commit cada una. Lo que un agente nuevo debe
saber:

1. **#24 · el fallo del refresco MEF ya no es silencioso.** `bitacora.json`
   (`resolucion/bitacora_mef.py`) guarda cada corrida del ETL con su causa
   clasificada; `BaseMef.frescura()` es el punto único de verdad de la frescura
   (barato: no toca PG ni el índice RAM) y `estado_operativo()` = frescura + PG.
   Umbral `PIVOTE_MEF_DIAS_FRESCURA`, default **10**. Estados: `missing` →
   `invalid` → `stale` → `refresco_fallido` → `ok`.
2. **Nada de vistas nuevas**: el aviso viaja por `/api/pivote/salud`, por el
   buscador de #27 (`base_desactualizada` + `aviso_frescura`, campos aparte de
   `aviso`) y por una observación `BASE_MEF_DESACTUALIZADA` del análisis. **Solo
   si hay algo que decir** — con la base al día ninguna de las tres habla.
3. **Lo que #24 NO incluye, a propósito**: instalar el cron. Es del deploy. El
   runbook §10 gana el simulacro para comprobarlo en el server del cliente.
4. **#25 · veredicto NO-GO, decide Rafael.** NO se implementó nada: el
   entregable es la medición. Números en
   `docs/pruebas/issue25-medicion-paralelismo.md`, reproducibles con
   `backend/scripts/medir_paralelismo.py` (offline, no toca producción). Titular:
   97,9 % de la etapa de resolución es espera de InfoObras; lo paralelizable por
   regla son ≤ 5,8 s de un job de hasta 21 minutos.
5. **Dos hallazgos del inventario de #25 que valen aunque no se paralelice**:
   `BaseMef` mantiene su `RLock` de instancia tomado durante TODO
   `buscar_candidatos()` (cualquier pool sobre ella daría ×1), y la herencia por
   folio de `resolver_con_dedup` depende del orden de iteración — es regla de
   negocio, no detalle. Antes de tocar concurrencia en cualquier parte del
   backend, leer la sección 7 de ese doc: hay cinco piezas con estado compartido
   (caché de `ConsultaInfoObras`, `threading.local` de las estadísticas de
   descarga, `ContextVar` de la traza, el progreso «i de n»).

Gate: **967 passed, 25 skipped** (base 949; +18 de #24), sin red ni PG real,
`resolucion/cui.py` intacto, compileall y `git diff --check` limpios. Sin push,
panel y skill sin tocar.

## Nota (2026-08-05, Claude) — ADR-009 cerrado y schema.sql consolidado

`T-REFACTOR-003` y `F-SCHEMA` quedaron cerradas. Lo que un agente nuevo debe
saber:

1. **Postgres YA NO es opcional.** Decisión de Rafael, en el addendum de
   `decisions/ADR-009-migracion-postgres-mef.md`: obligatorio en el despliegue,
   **por la base MEF** (uso principal); el respaldo de jobs es secundario.
2. **Pero la degradación en código NO se tocó, y no se toca.** `BaseMef` cae al
   índice RAM/CSV y el respaldo se desactiva con un warning (B03-fix).
   Obligatorio operacionalmente ≠ frágil ante una caída transitoria: un PG caído
   no tumba nada, pero es un estado ANORMAL que el operador corrige.
3. **Lo que sigue abierto, y está escrito así en el ADR**: el write-path
   bloqueante con PG caído a mitad de job (B02) y la ausencia de cola de
   re-sincronización (B01). Único mitigador: `scripts/migrar_a_postgres.py` a
   mano. No dar por resuelto lo que la decisión no resolvió.
4. **`backend/db/schema.sql` ya no es aspiracional**: es espejo documental de
   los DOS DDL reales (`mef` primero, luego las 3 tablas del respaldo), con las
   vistas fantasma eliminadas. **No es fuente de verdad — el código lo es.** Si
   cambias un DDL en el código, `tests/test_schema_sql.py` te obliga a
   actualizar el archivo (compara texto normalizado, sin PG ni red).
5. **Pendiente anotado, no implementado**: `healthcheck` + `depends_on` de
   Postgres en el compose → `docs/despliegue/despliegue-runbook.md` §12.
6. El backlog tenía **160 líneas pegadas dos veces** (B01–B06, F01, T-TAREA-003,
   T-REFACTOR-001/002/003). Se borró una copia tras verificarlas idénticas.

Gate: **870 passed, 25 skipped** (base 866), sin red ni PG real, `cui.py`
intacto → no aplica golden. Sin push, panel y skill sin tocar.

## Nota (2026-08-05, Claude) — pulido del Excel entregable

Cuatro contradicciones que el evaluador veía (halladas celda por celda sobre el
Excel real de Vitarte, `7e9306a321ac`) quedaron cerradas. Lo que un agente nuevo
debe saber:

1. **La NOTA de la PARTE 5 ya no viene del análisis**: la arma `nota_parte5()`
   con las mismas celdas que se imprimen. Si alguien vuelve a pintar ahí un
   texto pre-armado, reaparece la contradicción («80/100» sobre una tabla de 40).
2. **`conciliar_conclusion()` (en `scripts/generar_excel.py`) se ABSTIENE por
   defecto**: solo antepone la cifra verificada cuando la diferencia es la del
   conteo de bordes (verificado mayor, y por como mucho un día por periodo). No
   ampliarla para «explicar» recortes del Paso 5 — eso ya se explica en sus
   propias filas y llamarlo conteo de días sería mentir.
3. **El color del veredicto se clasifica con el texto ORIGINAL**, no con el
   compuesto (`Builder.kv(..., valor_veredicto=…)`). Sin eso la celda pierde el
   verde justo al arreglarla.
4. **FFFF00 tiene UN solo significado**: dato declarado / valorización en
   periodo / separador / encabezado CERT. Todo «por verificar» es `FILL_PEND`
   (FFF2CC). Hay un test que recorre el libro y lo exige.
5. **`_MARCA_NO` / `_MARCA_PEND` cambiaron de texto** (fuera «candado:»). Sus
   consumidores las leen por símbolo (`validacion/integridad`) o por prefijo
   (`_clasificar_veredicto`); la skill y el Panel no las matchean por literal.
6. **`avance_descargas.py` y `redescargar_documentos.py` abortan** sobre un job
   del layout por carpeta (`scripts/layout_legado.py`, flag `--forzar`).
   Actualizarlos al layout vigente sigue pendiente: es mantenimiento.

Gate: **865 passed, 25 skipped** (base 837), sin red, `cui.py` intacto → no
aplica golden. Sin push. Comprobación manual:
`docs/pruebas/pulido-excel-comprobacion-manual.md`.

## Nota (2026-08-05, Claude) — #81 (bloque R) cerrada en código

Las 5 brechas de resiliencia que dejó la #80 quedaron resueltas (la 2 estaba
descartada de antes). Lo que un agente nuevo debe saber:

1. **`cache_obras/{obra}` ahora tiene dos marcas**: `.completa` y `.parcial`.
   Una sección caída publica PARCIAL y el siguiente pedido de esa obra
   re-descarga **solo lo fallido** (lo sano viaja por enlace duro). El callback
   de descarga cambió de firma: `descargar(ruta, pendientes)`.
2. **Una experiencia con corpus parcial no recibe su `.ok`** — a propósito: así
   la siguiente pasada la completa y el panel no la da por terminada.
3. **Resolver una revisión purga las secciones en error** de la caché de esa
   obra (`purgar_secciones_en_error`), incluso sobre entradas heredadas marcadas
   `.completa`. Las cachés viejas sanas siguen siendo válidas tal cual.
4. **Los textos de las notas SEACE tienen fuente única** en
   `orquestador/descargas_seace.py`. No volver a escribirlos a mano en
   `etapas_reales`.
5. `descargar_cui` va por la misma caché y reporta las secciones extra.

Gate: **837 passed, 25 skipped** (base 826), sin red, `cui.py` intacto → no
aplica golden. Sin push, sin despliegue, issue #81 **abierta** (la cierra el
dueño al comprobar). Comprobación manual:
`docs/pruebas/bloque-r-comprobacion-manual.md`.

## Nota (2026-08-04, Claude) — planes F5 y T-005 en el backlog

El plan operativo del saldo técnico (S/2,600) quedó documentado en tres
niveles: **`tasks/backlog.md`** con las tareas estructuradas
`T-TAREA-SEACE-F5` (candado de identidad CUI↔proceso, S/800, con fixtures
obligatorios de la corrida Vitarte) y `T-TAREA-CRUCES-FECHAS` (2 reglas +
hoja «Cronología de expedientes», S/1,200, depende de F5) — ahí está el
detalle de desarrollo; **`docs/nuevos_modulos/plan-desarrollo-extras.html`
§4b** con la versión para el cliente (día a día + cobros); y el **dashboard
projects-list** (tickets T-010/T-011) con partidas y rangos internos de
negociación. Ninguna arranca sin cerrar la cotización con Manuel.

## Nota (2026-08-04, Agente) — Veredicto consolidado #80 y brechas de seguimiento

Veredicto verificado de primera mano: el cierre de la **#80** es legítimo y cumple
la especificación D1–D5 en lo esencial. Gate consolidado: **748 passed, 25 skipped**
(+5 pruebas de caché de obra). D1, D3 y D5 limpios con agrupación por `obra_id` real.
D2 comparte helper de materialización y filtra por año. D4 conserva marcas `.ok` e
integridad con el Panel.

Brechas identificadas (candidatas registradas para issue de seguimiento de resiliencia):
1. **Resiliencia de Caché**: Evitar congelar marcas `.completa` en `cache_obras/` ante errores transitorios de sección; purgar entrada de `cache_obras/` al resolver/re-evaluar revisiones.
2. ~~Layout ZIP por Obra~~ **RESUELTO por el correctivo #80**: el ZIP conserva el árbol completo por experiencia; `DOCUMENTOS_COMPARTIDOS/` quedó eliminado y NO debe reintroducirse (la dedup vive en la descarga, `cache_obras/`).
3. **Texto del Índice**: Precisar nota a *"ninguno corresponde al periodo del certificado"* cuando existan informes fuera de rango.
4. **Limpieza de `.part`**: Recolección de carpetas `.part` huérfanas en `cache_obras/` tras interrupción/kill duro.
5. **Caché en `descargar_cui`**: Reutilizar `cache_obras/` en descargas directas por CUI.

## Nota (2026-08-04, Codex) — #80 resuelta con caché InfoObras por job

Implementadas D1–D5: `cache_obras/{obra_id}` descarga el corpus completo una
vez, exige `.completa`, conserva estado serializado y materializa cada P/E por
hardlink/copia atómica. Los informes se filtran localmente con la semántica
histórica inclusiva por año; aprobaciones y documentos MEF invariantes se bajan
una vez usando los requisitos agrupados de la obra. Las marcas `.ok` por
experiencia permanecen compatibles con jobs históricos y la barra del panel.

La entrega conserva el árbol completo; el índice compara SHA únicamente dentro
de la misma `obra_id`. Replay offline Vitarte generado en Downloads como
`InfoObras_essalud-vitarte_cons-hospitalario_CORREGIDO_V2.zip`: 971,718,423
bytes, 1,205 PDF, 29 manifiestos, cero almacén central y `testzip` limpio. Gate:
**748 passed, 25 skipped**. El resolver no cambió; la golden no es aplicable y
su corpus sigue ausente. El ZIP centralizado de 405 MB queda solo como referencia.

## Nota (2026-08-04, Codex) — auditoría EsSalud corregida (#32, #72–#79)

Se documentaron y corrigieron las observaciones del análisis de 31 experiencias:
ALT04 reconcilia reinscripciones con histórico HABIDO; toda obra sin cruce deja
el veredicto provisional; las 14 hojas P muestran conclusión; Factor A usa el
exceso efectivo y retira el puntaje si el baremo no está estructurado; Base de
Datos recibe CUI resuelto/procedencia y rotula colegiatura pendiente; se sanean
textos, duplicados, regresiones, montos/fechas discordantes y descargas; la ficha
de obra se deduplica entre certificados; los días se imponen inclusivos en todo
el libro; y un recorte J/K ya no se embebe como Factor A.

Entregable replay offline, sin sobrescribir el original:
`Downloads/Analisis_essalud-vitarte_cons-hospitalario_CORREGIDO.xlsx`. Auditoría:
31 filas, 29 CUI, 14/14 conclusiones, 6 reinscripciones reconciliadas, 10 punteros
de obra repetida y 14 recortes Factor A incorrectos rechazados. Gate: **742
passed, 25 skipped** y **54/54** scripts Node. El único cambio del resolver es
abstención pura (`revision` persiste `sin_verificar`); golden v4 sigue ausente y
no se promovió ninguna coincidencia.

## Nota (2026-08-03, Codex) — compatibilidad de auditoría cerrada

Antes del push se corrigieron cuatro regresiones puntuales: jobs heredados sin
confiabilidad ya no aparecen en rojo; una experiencia procesada sin documentos
cuenta como terminada y los jobs viejos usan las marcas `.ok`; SUNAT ambiguo
muestra candidatos en el Panel; y el ZIP por CUI excluye `.part`. No cambió el
resolver CUI, por lo que no aplica golden. Gate: **738 passed, 25 skipped**,
`compileall` y diff limpios; Panel con TypeScript y build productivo aprobados.
No hubo push ni despliegue.

## Nota (2026-08-03, Codex) — confiabilidad y descargas ya son auditables

La auditoría Excel/ZIP/panel quedó implementada en `demo`: confiabilidad global
y críticos persisten y aparecen en Excel/panel; el recuento de documentos nace
del disco después de descargar; carpetas sin documentos reciben
`SIN_DOCUMENTOS.txt`; el índice declara fallos y secciones incompletas. Panel:
tarjeta SUNAT completa, RENIPRESS como etapa 9, progreso corregido,
`en_revision` visible y mensajes técnicos saneados. Excel: saneo de
`⟦Claude:`, puntaje ausente visible y violeta extendido a hitos/Parte 5.

Resolver CUI intacto: no aplica golden. No hubo despliegue.
Gate: **736 passed, 25 skipped** + 5 focales posteriores; Panel con TypeScript
y build productivo aprobados.

## Nota (2026-08-02, Codex) — #54, #57 y #66 cerradas; diseño #70 abierto

En `demo`, `7593dea` cierra los tres defectos restantes del bloque: los
veredictos sin razón ahora bloquean tanto en la skill como en el backend
(#54); la fila TOTAL declarada es autoridad exclusiva del backend y el Excel
muestra por separado paralizaciones, traslapes y total efectivo (#57); y el
CUI literal incrustado en el párrafo del servicio se conserva y se rotula como
«citado y verificado» cuando coincide (#66). Gate: **731 passed, 25 skipped**
en backend, **54/54** en scripts de la skill, `compileall` y `diff --check`.
No cambió el resolver CUI, por lo que no aplicó golden. No hubo despliegue.

La clasificación expediente/obra de #50 no se redujo a un booleano. Quedó
documentada en la nueva #70 como un diseño pendiente por concurso y por
experiencia, con vocabulario, precedencias, contradicciones, contrato y gates.
#50 queda bloqueada por ese diseño; #49 continúa pausada por ADR-S007.

## Nota (2026-08-02, Codex) — fixes pre-deploy completos

Sobre `demo` quedaron implementadas #68 (rango TDR y detección de folio
repetido), #64 (clamp desde inicio real de obra), #42 (revisión asíncrona
consultable + polling/recuperación en el Panel) y #65 (procedencia estructurada
de supuestos con color violeta). El contrato espejo sube a v1.3.0 de forma
aditiva. Gate: **727 passed, 25 skipped**; contrato Pydantic/Zod aprobado sobre
9 espejos históricos; build productivo del Panel aprobado; compilación y diff
limpios. No cambió `backend/resolucion/cui.py`, por lo que no aplicó golden.
No hubo despliegue.

## Nota (2026-08-02, Codex) — tren A–D completo en `demo`

El tag `demo-pre-D-cache-seace` apunta a `3156d26`. D quedó integrado como
`345c601`: caché compartida en `datos/referencia/seace`, clave por `fileCode`
(SHA-256 si falta), validación por magia PDF/ZIP/RAR, publicación y copias
atómicas, reutilización entre experiencias y jobs y limpieza de temporales.
La ejecución continúa secuencial: no entraron pool, manifiestos v2, ZIP
parcial, routers/comandos ni métricas del runtime nuevo. Prueba clave: dos
experiencias y un segundo job comparten una sola descarga y tres entregables
idénticos. Validación: **34 focales; 721 passed, 25 skipped** en suite completa,
`compileall` y `diff --check`. Se estabilizó además el test concurrente de B
para que el lector de prueba no monopolice NTFS (`5cc0070`, cinco repeticiones
verdes). El resolver no cambió; no aplicó golden.

Los cuatro rescates están ya en `demo`. `refactor` sigue congelada en
`65d41af`. No hubo push ni despliegue y no hay servicios de Pivote corriendo
en el servidor del cliente. Siguiente trabajo: inventario de capacidades del
backend y luego preparación del despliegue desde esta `demo`.

## Nota (2026-08-02, Codex) — rescate C integrado en `demo`

El tag local `demo-pre-C-ingesta` apunta a `90a3e1e`. El rescate C quedó en
`bb263c1`: `POST /analizar` lee y valida todos los insumos antes de crear el
job, un ZIP roto produce 422 explícito y cada certificado aceptado debe
comenzar con `%PDF-`. Se conservaron límites, conteo de entradas, control de
ZIP bomb y path traversal. No entraron staging, hashes, validación estructural
XLSX ni lista cerrada de nombres. El contrato sigue siendo `201 + job_id`, con
`BackgroundTasks` y layout actual. Validación: **22 pruebas API; 717 passed,
25 skipped** en suite completa, `compileall` y `diff --check`. El resolver no
cambió; no aplicó golden. C avanzó por fast-forward a `demo`. No hubo push ni
despliegue. Siguiente: tag de retorno y `rescue/D-cache-seace`.

## Nota (2026-08-02, Codex) — rescates A y B validados

ADR-S007 fijó `demo` como línea de producto y congeló `refactor` en `65d41af`.
El tag local `demo-pre-rescates` apunta a `5503082`. En `rescue/A-seace`, el
fix WAF `ed9795c` se aplicó como `d4d3612` y las pruebas dirigidas quedaron en
`6e37605`: User-Agent, Referer exclusivo de `prodN`, timeout, formatos,
limpieza de `.part` y bloqueo automático de red externa en pytest. A quedó
integrado por fast-forward en `demo` como `586f430`; el tag local
`demo-pre-B-atomicos` marca ese punto. Sonda pública CUI 2279396: 5 procesos;
Bases Integradas RAR descargadas, 1,561,634 bytes, magia válida y cero
parciales.

En `rescue/B-atomicos`, `c67e290` incorpora reintento acotado solo ante
`PermissionError` y lo aplica únicamente a los JSON del repositorio. No toca
ZIP ni otros artefactos. Cubre dos bloqueos y éxito, agotamiento, integridad
del archivo anterior, limpieza del temporal y lectura concurrente. Validación
B: **9 focales pasaron, 4 skips de PostgreSQL; 713 passed, 25 skipped** en la
suite completa, `compileall` y `diff --check`. B quedó integrado por
fast-forward en `demo` como `3beb94b`. No hubo push ni despliegue. Siguiente
paso: abrir `rescue/C-ingesta` desde un tag de retorno propio.

## Nota (2026-07-29, Codex) — ReniPress integrado al orquestador

El cliente/API de `rafram96/renipress-product` se integró a `demo`.
`EtapaRenipressReal` corre como rama 3c junto a InfoObras y SUNAT, solo para
proyectos de salud, y persiste el contrato bajo `renipress` por experiencia.
Una caída queda como `ERROR_PARCIAL`; no se confunde con una búsqueda vacía.
Es evidencia auxiliar para salud pública y privada: no cambia veredictos ni
crea revisiones. Matching automático pendiente hasta contar con corpus
auditado. Validación: **90 focalizadas; 704 passed, 25 skipped** en suite.
Detalle: [`2026-07-29_codex.md`](2026-07-29_codex.md).

## Nota (2026-07-29, Codex) — #69: CUI citado validado contra función MEF

Sobre `feat/seace-abierto`, el Paso 0 ahora consulta la ficha enriquecida del
ETL aunque InfoObras encuentre el CUI exacto. Si certificado y ficha declaran
rubros positivos incompatibles, se abstiene y manda a revisión. Validación real:
CUI 2105743 (Hospital Abancay II) → función MEF `ENERGÍA` → revisión. Suite:
**687 passed, 25 skipped**. PostgreSQL local `pg-pivote-issue69` queda encendido
en `127.0.0.1:54329`, volumen `pivote_issue69_pgdata`, carga
`20260729T200354Z-790dc78d`.

La promoción solo-MEF de Bocanegra NO se implementó: relajaría el candado F7
(revisión→resuelto) y está prohibida sin golden v4. La parte de abstención del
error real sí queda resuelta; mantener #69 abierta o dividirla antes de cerrar.

Continuación: un CUI descartado ya no termina Paso 0. Se conserva como alerta y
el resolver continúa por nombre/RUC/ubicación/MEF. Aunque la alternativa pase
las compuertas, el resultado final queda en revisión con los candidatos y
`cui_citado_descartado`; el Excel no recibe el CUI falso ni un reemplazo sin
confirmación. Suite posterior: **688 passed, 25 skipped**.

## Nota (2026-07-29, Codex) — T-004 F2 lista para PR

F2 quedó cableada localmente en `feat/seace-abierto`: selección por tipo en la
etapa InfoObras, descarga diferida SEACE aun sin `obra_id`, marcas separadas,
ZIP y bloque Excel. Suite: **677 passed, 24 skipped**. Validación viva local
con CUI 2279396: contrato PDF correcto; Bases Integradas publicadas como RAR
pero el host devolvió HTTP 403, degradado honestamente a nota de error.
Detalle: [`2026-07-29_codex.md`](2026-07-29_codex.md).

⛔ No se hizo ni se debe inferir deploy/redeploy: Rafael lo realizará
manualmente. F3 y F5 continúan pendientes.

## Nota (2026-07-29, Codex) — ETL MEF replanificado desde datos reales

Rama hija `plan/etl-mef-v2`. Se ejecutó EDA streaming sobre los tres CSV del
corte 26-jul (620,985 filas, 640.7 MB, unión de 95 columnas) y se reescribió
`docs/backend/modulo_etl_mef.md` desde cero; la épica #12 queda tratada como
brainstorm, no especificación. `ADR-009` ahora decide convivencia: índice RAM
vigente para el resolver + schema PostgreSQL `mef` para raw/canonical, cargas
versionadas y trazabilidad. El cron será Programador de tareas de Windows que
invoca un contenedor one-shot. Antes de implementar: EDA reproducible +
importación PG desechable para medir capacidad y cerrar DDL. No se tocaron
issues de GitHub ni código del producto.

### Continuación — decisión PostgreSQL e implementación

El usuario confirmó que el uso inmediato es enriquecer el resolver y corrigió
que el destino **debe ser PostgreSQL**. ADR-009 final: RAM queda para nombres;
schema PG `mef` para ficha exacta por `(load_id, CUI/SNIP)`. Implementados ETL
versionado, aliases, retry, COPY, recarga sin reinicio, health y tarea Windows.
Corrida real aislada en PG16: 620,985 filas/620,984 identidades en 117.5 s,
tabla+índices 719.3 MB; lookup 6–9 ms tras abrir pool. Diferencial: 100 fichas
exactas + 20 rankings, cero diferencias legacy. Suite: 685 passed, 25 skipped
e integración PG real aprobada. Implementación cerrada en `a404aa9`; queda
integrarla por fast-forward en `feat/seace-abierto`.

## Nota (2026-07-29, Codex) — arquitectura visual v3

Actualizado `docs/nuevos_modulos/arquitectura-sistema.html`: ahora reconstruye
el Excel horizontal `para RAFAEL-V2.xlsx` como flujo público-primero, muestra
SUNAT en ambas ramas y RENIPRESS para todo salud como evidencia auxiliar (nunca
INCUMPLE automático). Añade estado real por componente, arquitectura completa y
separa la base MEF mínima existente del ETL PostgreSQL futuro.

## Nota (2026-07-29, tarde) — T-004 F1 construida + manual de operación

Rama `feat/seace-abierto` (`70c78e8`). El módulo `scraping/seace_abierto.py` ya
selecciona el proceso correcto por tipo (requisito N°1) y descarga bases y
contrato — **usable a mano desde hoy** con `docs/uso-manual-seace-abierto.md`.
El cableado F2 tiene guía paso a paso en el ANEXO de
`docs/plan-integracion-bases-contrato.md`. Detalle en
`context/current_state.md` («T-004 en construcción»).

## Nota (2026-07-29) — reunión con el cliente: T-004 es LA prioridad

Detalle en `context/current_state.md` (bloque «Reunión 29-jul»). En una línea:
el cliente está bajando bases y contratos **a mano** y no revisará más Excels
hasta ver precisión — **construir T-004 primero** (diseño v2 listo en
`docs/plan-integracion-bases-contrato.md`, con la segmentación por tipo de
proceso como requisito N°1 y los documentos al ZIP antes que el candado).
Pedido nuevo chico: #65 (marcar supuestos con color). RENIPRESS despriorizado.

## Cierre del 2026-07-28 — Correcciones de Identidad en Lircay (#58, #59, #60, #61)

Auditada la corrida de Lircay (job `371fa5a1e704`), se aplicaron 4 fixes en `fix/identidad-lircay`:
1. **#60 (`excel_final.py`):** Se separó el rótulo del Excel entre "CUI del certificado" y "No consignado en el certificado — el sistema identificó el CUI X" para no confundir la inferencia del backend con un dato del documento.
2. **#58 (`cui.py::resolver_con_dedup`):** La herencia por folio ahora exige coincidencia de emisor (score de empresa ≥ 70) para evitar que folios corridos por la skill hereden obras ajenas (rechaza Arcadia≠Picota).
3. **#59 (`cui.py::_paso_codigo_citado`):** Se acotó la exención del CUI exacto para que caigan a `revision` los códigos citados cuya obra contradiga simultáneamente nombre, departamento y rubro (caso Navarro, P9-E3).
4. **#61 (`cui.py`):** Se añadió veto de fase para que registros de InfoObras de "ELABORACIÓN DE EXPEDIENTE TÉCNICO" no respalden experiencias de ejecución/supervisión vía `ruc_match` (caso Santa Anita, P2-E3).

Resultados: 627 tests pasados, 0 regresiones. Los 3 casos de Lircay (2:4, 9:3, 2:3) pasan ordenadamente a `revision`.

## Cierre del 2026-07-27 — FALSO CUMPLE corregido

Auditar 3 análisis reales (156 experiencias) destapó **5 profesionales en verde con
el tiempo efectivo bajo el mínimo**. Cerrado en #51 / PR #56 (`cf9804b` en `demo`),
619 tests. Lo que hay que saber: **la conciliación ya existía y estaba inhabilitada
por un regex** que solo leía «años» cuando las bases dicen «meses» (0 de 44). Ver
`context/current_state.md` y las lecciones nuevas en `memory/common_mistakes.md`.

Queda abierto de esa auditoría: #57 (la columna TOTAL la calcula el LLM y no es
confiable) y 3 defectos sin dueño — oferta económica incompleta, experiencia del
postor no computable y jerga técnica en el entregable. Inventario completo en el
comentario de auditoría de #51.

## Handoff previo (2026-07-27) — gobierno y saneamiento

Detalle completo en [`2026-07-27_claude.md`](2026-07-27_claude.md). Sesión sin
código de producto; un commit (`27c8cde`). Lo que hay que saber antes de tocar nada:

1. **La skill instalada ahora es un junction a `Pivote/skill/`**, no una copia.
   Llevaba 13 días corriendo una versión del 14-jul **sin el escudo de integridad**
   (podía subir corridas incompletas). ⛔ **Nunca borrar ese enlace con `rm -rf`**
   — se lleva el destino. Ver `conventions/coding.md`.
2. **El repo es PÚBLICO.** Antes de commitear un documento, revisar si trae precios,
   cuentas por cobrar o la IP del servidor. `docs/comercial/` está gitignored por eso.
3. **Antes de proponer un diseño, buscar en `decisions/`.** Hoy se abrió una issue
   re-derivando ADR-010, que ya estaba decidido.
4. **T-008 ya no promete Postgres/Hot-Cold/pg_trgm** en el material comercial —
   no existe en el código. El épico ETL #12-#25 es trabajo pendiente, no hecho.
5. ⚠ **`ai-cli` no se puede usar en este nivel**: `counters.json` está en 0 con
   ADR-013 existiendo → `ai-cli new` colisiona. Y `validate` da 67 errores
   preexistentes (frontmatter faltante en los 13 ADR y en 3 índices de `tasks/`).
   El nivel `InfoObras/.ai` valida limpio.

## Nota (2026-07-26) — fixtures preparados para probar el backend nuevo

Detalle completo en [`2026-07-26_claude.md`](2026-07-26_claude.md). En una línea:
`Pronis_Sonitor/`, `Soritor2/` y `Consorcio-Lircay/` quedaron preparadas con
`_prep/MAPA.md`; **no había propuestas repetidas** (sí bases triplicadas,
≈273 MB); mapa de carpetas en `fixtures/ing manuel/_CONCURSOS.md`. Tres cosas
que importan para cualquier corrida:

1. En **Soritor** el factor **C. Sostenibilidad Social está eliminado**
   (tachado) — no puntúa.
2. En **Lircay** las bases dicen "sin tachas" y **sí tienen tachado en 16
   páginas** (equipamiento estratégico y funciones BIM) → usar
   `_prep/bases_texto.txt`.
3. En **Lircay falta la oferta económica** de los 2 postores → sin límite
   inferior.

Herramientas en `src/tools/`: `detectar_tachado_pdf.py`, `trocear_pdf.py`,
`render_paginas.py`.

## Nota de mantenimiento (2026-07-23) — el checklist de deploy RECAYÓ una vez

La auditoría de migración de la base `.ai` (dos niveles) encontró que
`context/roadmap.md` y `context/current_state.md` volvían a resumir el
checklist de deploy — el mismo patrón que ADR-S002 ya había corregido — y
los resúmenes eran peligrosos: omitían el merge del Panel y la regla de
orden de ADR-007 (plugin SOLO después del backend nuevo). Fase 1 de la
corrección ejecutada: ambos quedaron reducidos a puntero a
`InfoObras/.ai/tasks/active.md` (fuente única; verificado que ahí la regla
de orden está literal y el paso del Panel existe). Si ves el checklist
copiado en cualquier otro archivo, es una regresión: bórralo y deja puntero.

Más tarde el mismo día: **merge fast-forward `sonda/refactor-cui` → `demo`**
(`c31f71a`, solo local — push pendiente de confirmación del desarrollador;
la sonda no recibe más commits) y **Fase 2 de la corrección cerrada** sobre
`demo` (commits `c7045a7…`): coexistencia overview↔topology declarada, lista
T-00x consolidada en `vision.md` (raíz), tareas reubicadas por nivel,
ADR-S004 en la raíz, conteo de la golden con fuente única en
`architecture/backend.md`.

## Nota (2026-07-25) — ADR-011 arrancó, y un bug que apareció de paso

`EtapaResolucionCui.correr` (`etapas_reales.py`) acumulaba observaciones
`MULTI_OBRA` / `PROBABLE` / `PRIVADA` y **no las pasaba a `_res`**: se perdían
en el return, así que nunca llegaban al job ni al panel (solo quedaban, a
medias, en el enriquecimiento). Corregido en PR-1 del Issue #26. Si ves una
etapa que arma una lista `obs` y no la devuelve, es el mismo patrón.

## Nota (2026-07-26) — PRs 33/34/35 revisadas, corregidas y mergeadas a demo

Orquestación completa: #33 (pestañas/nombres) la mergeó el desarrollador;
#34 (SUNAT histórico) se mergeó tras corregir el hallazgo H2 del review
(`d59f900`: «habido durante la obra» exigía solo que un tramo TOCARA el
periodo → verde con días sin dato; ahora pide cobertura completa y degrada a
«No verificable» con los huecos listados); #35 (ADR-011 multi-obra) mergeó
limpia; #36 arregló el choque de integración 33×35 (tests con nombre de
pestaña viejo). Suite en demo: **333 passed**. H1 del review (fixture
`hacer_motor` sin `extras_sunat` → pytest puede tocar la red) quedó SIN
corregir por decisión del desarrollador. Pendientes que dejaron los merges:
**un solo rebuild del plugin** (33/34/35 tocaron skill/schemas — ADR-007:
viaja con el backend), ~~regenerar `golden_cui_baseline.json`~~ (HECHO 26-jul,
ver nota abajo)
(el actual es pre-refactor y da −10 falsos), y los issues del panel
(sub-obras panel#1 + render SUNAT).

25-jul: **issue #30 — el emisor del certificado en SUNAT** (rama
`rafram96/issue-30-mostrar-representante-legal`). Sondeada y cableada la
consulta "Información Histórica" (`getinfHis`, sin captcha) además de los
representantes legales (`getRepLeg`, ya existía sin usar). El bloque emisor del
Excel ahora responde **¿estaba HABIDO al emitir el certificado y durante la
obra?** con la pregunta en el título del campo, lista los representantes
(informativo — ADR-008 descartó ALT-12), y suma un cuadro histórico contiguo
(R:U) que corrió el de representante de obra a W:Z. Falta el render en el
panel (repo `Panel-InfoObras`): el JSON ya viaja con `representantes`,
`historico` y `habido`.
## Nota (2026-07-26) — issue #32, el factor de evaluación en cada hoja P

Rama `rafram96/issue-32-embeber-el-factor-2` (`17b1e04`), sobre demo ya con
33/34/35 dentro. Lo que un agente nuevo necesita para retomarlo:

- **Falta lo único que no se puede hacer offline**: correr un job real y MIRAR
  el recorte. No basta `regenerar_excel_final`: hay que re-correr
  `extraer_certificados.js` con `bases.pdf` y volver a subir el ZIP, porque los
  `certs/` en disco no tienen el `P{n}_FACTOR.pdf`. No re-scrapea nada.
- **El riesgo vivo es el número de página**, no el código: lo elige un LLM
  (`agent-bases`), y un recorte de la página equivocada se ve legítimo. El
  script valida el rango y avisa por stdout; la corrección real es mirarlo.
- **No agrava el pendiente de rebuild del plugin**: el cambio es compatible en
  ambos sentidos (un `P{n}_FACTOR.pdf` en un backend viejo se ignora; un
  backend nuevo sin el archivo genera la hoja como antes). Viaja con el rebuild
  único que ya deben 33/34/35.
- **Pendiente de cliente**: confirmar si el TDR y el Anexo 16 se quedan al
  INICIO de la hoja (hoy) o bajan junto al factor. Son dos líneas en
  `excel_final.py`.

## Nota (2026-07-26) — baseline de la golden REGENERADO, y la caché ya sirve

El baseline vivía desde el 20-jul (PRE-refactor T-008) y comparar contra él daba
−10 correctos que parecían regresión y eran la deuda de no regenerarlo. Además
`--solo-cache` había dejado de funcionar: la caché es de ANTES de que el resolver
fusionara candidatos MEF, así que le faltaban **642 de 1957 claves** (461 `cod:`,
181 `nom:`) y abortaba en el primer hueco.

Corrida en vivo autorizada por el desarrollador (26-jul, sobre `demo` = `b7d4c4a`,
post-merge de #48): **339 s, 1.2 s/caso, cero `portal_caido`**. La caché quedó
completa (7.9 MB) y **`--solo-cache` vuelve a correr offline** — verificado.

Baseline nuevo (es el vigente): correcto **230** · incorrecto **10** · revisión 34
· privada 3. Contra el viejo: incorrecto 16→10, y la matriz de transiciones da
**cero `correcto → incorrecto`** (el criterio duro de la Regla de oro). Los 8
`correcto → revisión` son el costo de abstención que ADR-005 ya había aceptado.
El viejo se conservó como `golden_cui_baseline.prerefactor.json`.

⚠ Un solo caso empeoró de verdad (`revisión → incorrecto`): CUI **2195439**
(I.E. N° 0022 Jorge Ríos) — y es **uno de los dos casos de "verdad auditada
dudosa"** que ya estaban en el backlog (Tocache vs Loreto). Antes de tratarlo como
regresión hay que resolver cuál es la verdad.

## Nota (2026-07-26) — la golden ANCHA es el baseline, y lo que revela

La golden armaba cada caso con solo `proyecto` + `cui` (fechas en None), así que
**toda regla que lea `ubicacion`, `entidad_contratante` o `ruc_emisor` era INERTE
en ella**: los vetos de ubigeo, ADR-013 entero, `ruc_match`, `ent_match` y la
clasificación de privadas nunca se ejercitaban. Se comprobó cuando ADR-013 dio
matriz perfectamente diagonal — probó cero regresión y no validó nada.

Ensanchada (`golden_cui.py` hace join contra el espejo de origen por
`job` + `prof:exp`): **277/277 casos enriquecidos, 0 degradados**. El baseline
ancho ya está promovido (autorizado 26-jul); los anteriores quedan como
`golden_cui_baseline.estrecha.json` y `.prerefactor.json`.

⚠ **Lo que revela, y hay que mirarlo**: con los datos completos el resolver
saca **14 mal-resueltos, no 10**, y aparece **1 `correcto → incorrecto`** más 3
`revisión → incorrecto`, varios **vía RUC**. No es regresión del código: es que
la golden estrecha nunca lo midió. La hipótesis a investigar es que la exención
«`ruc_match` exime de todo veto» sea demasiado fuerte — el RUC del emisor casa
con una obra donde esa empresa participó, pero no con la del certificado.

## Nota (2026-07-26) — #47: los certificados son escaneos

De los **729 recortes** del corpus, **solo 2 traen capa de texto**; los otros 727
son escaneos puros. La verificación folio↔emisor está implementada y cableada en
VALIDACIÓN, pero solo puede pronunciarse sobre el 0.3%: el caso que motivó la
issue (`95af90f1578e` prof 1 exp 1, folio 358 en vez de 359) es un escaneo y el
módulo se abstiene. Decisión del desarrollador: **la abstención "No verificable"
es el comportamiento correcto**; adivinar sobre 727 escaneos sería ruido en masa.
Detectar el corrimiento de folio en general exige verificar ANTES del recorte
(lado skill, donde está el PDF completo) o meter OCR.

## ¿Qué se estaba haciendo?

Semana 20-22 jul: **refactor completo del resolver de CUI** (rama
`sonda/refactor-cui`, 13 commits) — base local MEF, público-primero, camino
expedientes/obra, candados de abstención — validado con una auditoría golden de
277 casos (errores silenciosos 16→10, cero regresiones) y corridas reales.
Además: optimización de la skill (Paso 4.5), rescate del análisis San Isidro, y
actualización del paquete comercial de extras (T-003…T-008).

## ¿Qué falta? (en orden recomendado)

1. **Deploy como paquete** (cross-repo: backend + panel + plugin + server) —
   el checklist canónico vive en **`InfoObras/.ai/tasks/active.md`** (nivel
   sistema); aquí no se copia. Regla clave: NO entregar el plugin sin el
   backend nuevo (ADR-007).
2. Pulido camino A (filtro de secciones de obra en descargas/Excel).
3. Reunión de cotización (materiales: `docs/nuevos_modulos/*.html` v3).
4. Resto: `tasks/backlog.md`.

## Archivos clave

- Resolver: `backend/resolucion/cui.py` (+ `base_mef.py`, `texto.py`).
- Orquestación: `backend/orquestador/etapas_reales.py` (caller del resolver,
  camino A/B, clamps) y `motor.py`.
- Validación: `backend/scripts/golden_cui.py` + baselines en
  `backend/datos_pivote/golden_cui_*.json` (gitignored pero presentes local).
- Skill: `skill/SKILL.md` (Paso 4.5) y `skill/prompts/agent-propuesta-profesional.md`.
- Jobs de referencia local: `b4f385c31811` (San Isidro camino A, entregado),
  `c9c769976750` (replay BNP con `revision_manual.md`).

## Nota (2026-07-26) — #28 paso 1: el dato que estaba y nadie leía

Antes de agregar columnas a la base MEF, revisar si el campo ya está cargado.
`estado_dataset` viajaba en `base_mef.py` desde F3, se exponía en la ficha del
candidato y **ningún consumidor lo leía**: 229k de 494k filas son DESACTIVADAS
y competían de igual a igual con las vivas. Usarlo rompió el empate de Sullana
de 4 a 2 y liberó el 23% del presupuesto de consultas al portal, sin regenerar
el artefacto (PR #39). El alcance original de la #28 arrancaba por regenerar la
base; el orden correcto era al revés.

**Regla que salió de acá:** las señales de la base MEF son DESEMPATE, jamás
filtro. 15 de 191 verdades auditadas viven en filas DESACTIVADA (un CUI
reformulado queda desactivado y el certificado cita al viejo). Y el guard exige
el dato en AMBOS lados: un CUI ausente de la base es DESCONOCIDO, no vivo —
resolver apoyándose en la ausencia de información es adivinar.

**Trampas del dataset de 68 campos, medidas (para el paso 2):**
- `DES_TIPOLOGIA` está VACÍA en los dos CUIs de referencia (2483109, 2502652);
  0% en desactivadas, 32.6% global. No sirve como veto.
- `TIPO_INVERSION` no es binario "PROYECTO vs IOARR": son 8 valores y las obras
  ARCC del caso HV son `INTERVENCIONES IRI`. Un veto por tipo mata al correcto.
- Las DESACTIVADAS no traen `PRIMER/ULTIMO_DEVENGADO` (solo el acumulado).
- `golden_cui.py:190` arma la experiencia con `fecha_inicial: None` → cualquier
  regla de ventana temporal es INERTE en el golden. Para medirla hay que
  enriquecer el corpus con las fechas del cert (join `job` + `prof:exp` contra
  los `espejo.json`).

## Riesgos vivos

- Server en producción corre el código VIEJO hasta el deploy.
- Los baselines/caches de la golden viven solo en esta laptop (datos_pivote
  gitignored) — no borrarlos; sin ellos la re-validación exige corrida en vivo
  (~1.5 h contra InfoObras).
- Límite de gasto mensual de la cuenta Claude alcanzado (21-jul): subagentes
  pueden morir a mitad; preferir trabajo directo o esperar el ciclo.
- 2 verdades de auditoría dudosas (ver `tasks/backlog.md`).

## Regla de oro antes de tocar el resolver

> ⚠ **NOTA (2026-07-28) — EL CORPUS DE LA GOLDEN SE PERDIÓ IRREMEDIABLEMENTE**
> (confirmado por el desarrollador): `auditoria_cui_v3.xlsx` (~277 verdades
> humanas), `_golden_cui_cache.json` y `golden_cui_baseline.json` no existen
> en ninguna máquina. **El ciclo de abajo NO se puede ejecutar** hasta
> reconstruir el corpus (plan v4: exportar las revisiones resueltas en el
> panel del server —cada CUI pegado por el evaluador es una verdad humana—
> + capturar los reclamos de auditoría del ing. como filas de verdad; luego
> regenerar caché y baseline). MIENTRAS TANTO: solo se aceptan cambios del
> resolver de **ABSTENCIÓN PURA** (resuelto→revisión, nunca al revés) con
> regresiones unitarias dirigidas + replay de jobs reales del server con
> `scripts/resubir_job.py` (antes/después). Aflojar vetos o recalibrar
> umbrales queda PROHIBIDO hasta que la golden v4 exista — es exactamente
> lo que ADR-005 no permite hacer sin instrumento.

Cualquier cambio se valida así, en este orden (ciclo HISTÓRICO, hoy sin
instrumento — ver nota):
`pytest backend/tests -q` (offline) → `golden_cui.py --con-base --solo-cache`
→ comparar contra `golden_cui_baseline.json`. Criterio: mal-resueltos nunca
suben, cero correcto→incorrecto. Nunca relajar compuertas para "ganar" casos
(ADR-005).

## 2026-09-05 — Medición de las vías NUMERO/CONTRATO/RESOLUCION sobre una corrida real
- Job resubido (`scripts/resubir_job.py`): pendientes **21 → 11** (49 experiencias, 12 profesionales; profesionales con pendientes 9 → 8; ningún CUI resuelto cambió).
- Fixes que salieron de la medición: `mef.contratos_de_expediente` (todos los contratos ET, no el más barato; «consultoría de obra para la elaboración del expediente» ES contrato de expediente), `EtapaInfoObrasReal._resoluciones_08a` (hasta 2 documentos de aprobación por candidato).
- Los 11 restantes: sin candidato o con contrato/resolución que nombra a otro consultor → no resolubles con fuentes oficiales; el Excel muestra la evidencia.
- Suite: 1097 passed, 25 skipped. Pre-pase aplicable offline a un job ya corrido (ver handoff raíz `.ai/handoffs/2026-09-05_claude.md`).
- **Vía MEF** (mismo día, commits `9b9389c` y `f64e357`): 7 de 8 «no detectables» estaban en la base MEF con nombre exacto; el resolver los perdía en `_fusionar_mef` por exigir obra en InfoObras. Ahora la ficha compite (`_solo_ficha`, solo expedientes) y resuelve con candados propios; la etapa verifica solo contra el MEF (`_procesar_sin_obra`) y, sin documentos MEF, marca `sin_documentos_mef` en vez de `sin_verificar`. Corrida real: pendientes **21 → 7**, profesionales por confirmar 9 → 6. Suite 1102 passed. Ideas abiertas: 2ª pasada del buscador MEF por establecimiento para los casos donde la ficha correcta no queda arriba (I.E. 14038, Hospital Chulucanas).
- **Correcciones del Excel (tarde 2026-09-05, commits `6fdfcb9`…`e5bb1c2`)**: veto por etapa en el resolver; plausibilidad de la fecha de resolución (`fecha_descartada`/`fecha_motivo`); bloque MEF con el contrato del emisor (`elegido_por`, `contrato_emisor`); multi-obra 0/N a revisión; cruces con contrato MEF y textos honestos; `entregables/certeza.py` + Parte 5 de expedientes (Identificación, Alerta, fila MEF, totales por certeza, DÍAS EFECTIVOS = reconciliar). Suite 1198. Tag de retorno: `checkpoint-2026-09-05-pre-correcciones-excel`. Pendiente: Panel con la misma certeza; corrida real completa.
- **API de certeza para el Panel** (`ef54b38`, `447ecfa`): `/espejo` y `/resumen` exponen `identificacion`, `alertas`, `fuente_mef`, `certeza` y `tipo_evaluacion` (solo expedientes); paridad con la Parte 5 del Excel probada. La vía RESOLUCION persiste la lectura confirmante. Panel actualizado en `d91375d`. Pendiente: réplica para ejecución de obra.
## 2026-09-11 — extracción focal Pucallpa P1 EXPEDIENTES

RAW generado para Marcos Díaz Espinoza: `backend/datos_pivote/prueba-rutas-luna-20260911/pucallpa_expediente/_prof/`.
Incluye `profesional_01.json` y `auditoria_extraccion.json`; 8 periodos extraídos
de páginas físicas 306–311, con imágenes y vecinos ±2 revisados. Validación JSON
OK. `ai-cli validate` queda bloqueado por frontmatter histórico ya existente en
tasks/decisions.
## 2026-09-12 — guardas de encargo SEACE

Implementadas en `2026-09-12_candado_encargo.md`: promoción con adjudicatario
favorable obligatorio, abstención por varios contratos con IDs distintos,
resumen ampliado para investigación, rótulo honesto y gates de fechas sin
rescate entidad+objeto. Focal: 96 pruebas pasadas. La pluralidad se persiste como
`contratos_multiples` derivada de IDs distintos y los gates exigen adjudicatario
fuerte favorable. Consumidores SUNAT/Gantt ajustados: suite relacionada 104 passed.
