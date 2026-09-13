---
timestamp: "2026-09-12"
agent: "Claude Opus"
session_status: "clean"
---

# Hoja del profesional de vuelta al formato compacto

Rama `excel/limpieza-texto`, desde el checkpoint `a067eed` de `demo`. Solo
presentación de la hoja del profesional del Excel final: no se tocó la API, el
ZIP, el Panel, la skill, el cálculo ni los datos internos (`enriquecimiento`).

## Por qué

El cliente vio una entrega real (job de Tacna) y pidió literalmente «tiene
muchos campos que fueron agregados que hoy en día no sirven; hay mucho texto
basura». Es el error que ya está anotado en `memory/common_mistakes.md`
(«corregir datos ampliando el formato sin consultarlo»): las trazas de fuentes y
las advertencias genéricas se habían convertido en filas por experiencia.

## Qué se retiró o reescribió

Todo en `entregables/excel_final.py` (un solo archivo de código):

1. **Contraste de servicio** — las tres filas ya no existían en el generador; se
   comprueba con regresión en ambas rutas que no vuelven. El dato sigue en el
   análisis, la API y el ZIP, y la diferencia real sigue marcada en el campo del
   cargo.
2. **Estado de fuentes / documentos SEACE sin descarga** — sin residuo en el
   Excel por ninguna ruta; `estado_fuentes` sigue intacto para API y ZIP.
3. **«Documentos encontrados»** sin archivos dice «Sin documentos descargados»
   (antes remitía a un bloque que ya no existe). Con archivos, «N archivo(s)
   encontrado(s)», como el 5-sep.
4. **DOCUMENTOS DEL PROCESO (SEACE)**: «Adjuntos del contrato» vuelve a
   «Contrato firmado» y cuenta archivos («Sin enlace recuperado» si no hay);
   «Datos del proceso vs. certificado» vuelve a «Correspondencia con el
   certificado» con el rótulo corto del candado (Confirmado / Por confirmar /
   Contradice) y, solo si contradice, el motivo en la misma fila y en pocas
   palabras; se van la observación de fechas del bloque y el informe de
   identidad pendiente; «sin procesos» queda en «Sin procesos en SEACE para este
   CUI».
5. **«Observación de fechas» (col A, ruta expedientes)** se pinta solo cuando
   alguna de las dos comprobaciones tiene resultado concreto o una fecha con la
   que comparar; dos «POR VERIFICAR» sin fecha ya no ocupan una fila. Cuando se
   pinta, enuncia y explica **solo** la comprobación con dato: para eso
   `presentacion_cruces` expone además `motivo_a`/`motivo_b` (el `motivo`
   completo sigue igual para la cronología y el Gantt).
6. **Fila «Fuente: MEF-…»** eliminada: las etiquetas «(MEF)» ya dicen la fuente.
7. **Cabecera** «EXPEDIENTE TÉCNICO — verificación», sin el paréntesis.
8. **Emisor sin identificar en SUNAT** habla como un evaluador: «Sin coincidencia
   en SUNAT», «SUNAT no respondió; emisor por confirmar», «Emisor por confirmar;
   sin consulta a SUNAT registrada». La jerga por recurso sigue en
   `estado_fuentes` para API y ZIP.
9. **Leyenda de la PARTE 5** en una línea.
10. **Cuadro EMISOR (SUNAT)** conserva RUC, razón social, estado/condición,
    cruce, las dos preguntas de HABIDO, la tabla HISTÓRICO de condición y ALT04.
    Se retiran representantes legales, domicilio fiscal (y el anterior), objeto
    social, tipo de contribuyente, inicio de actividades y razón social
    anterior. ALT04 sigue calculándose con la fecha de inscripción, que nunca se
    pintaba.

No se tocaron imágenes de certificados ni la reserva de filas que ocupan.

## Cómo se comprobó

- **Antes/después sobre el job real de Tacna** (17 profesionales, 62
  experiencias), regenerado sin red desde `espejo.json` + `enriquecimiento.json`
  + `certs/` a una carpeta scratch privada; `final.xlsx` no se tocó. Informe en
  `backend/datos_pivote/3f04f6e73550/_limpieza/INFORME_LIMPIEZA.md` (privado).
  Cifras: **2173 → 1998 filas con contenido** en las 17 hojas (−175, −8%);
  1079 celdas de texto retiradas y 174 nuevas (reescrituras de los puntos 3, 4,
  7, 8 y 9). Las filas «Observación de fechas» bajan de 57 a 18, y las 18 que
  quedan tienen todas una fecha comparada.
- **Ninguna celda numérica ni de fecha cambió**: el multiconjunto de números y
  fechas de cada hoja es idéntico antes y después (días por hito, montos,
  fechas, totales de la PARTE 5, traslapes, años efectivos y conclusión).
- **Prueba sintética nueva por punto**, en las dos rutas:
  `backend/tests/test_limpieza_hoja_profesional.py` (77 casos, sin datos reales).
  Incluye una lista de textos retirados que no pueden volver por ninguna ruta.
- **Pruebas adaptadas** (fijaban los textos viejos): `test_pulido_excel.py`,
  `test_entregables.py`, `test_candado_seace.py`, `test_seace_f2.py`,
  `test_estado_fuentes_entregables.py`, `test_expedientes_sin_tarjetas_cruces.py`,
  `test_expedientes_coherencia.py`.
- **Suite completa**: 1871 pruebas pasan, 31 omitidas, **1 fallo ajeno**:
  `test_espejo_servicio_contrato.py::test_servicio_valido_pasa_pydantic_y_zod`
  no encuentra el módulo `zod` porque este árbol de trabajo no tiene
  `skill/node_modules` (no versionado). No se instaló nada: no es un fallo de
  este cambio y en el checkout principal ese test pasa.

## Lo que quedó fuera (a propósito)

- La hoja «Cronología de expedientes» conserva su rótulo largo del candado y su
  fila «Observación de fechas» (que ya solo se pinta con señales temporales
  reales): es la vista de conjunto del Comité, no la hoja del profesional.
- Se mantiene el label «Bases integradas» tal cual; el 5-sep lo escribía «Bases
  Integradas». Es solo la mayúscula y nadie la pidió.
- Ruta privada: la fila «Observación de fechas» sigue apareciendo porque «la
  fuente pública no aplica» sí es un resultado. Lo que ya no se repite es el
  «POR VERIFICAR — sin fuente pública localizada» sin fecha.
- Para un candado «por confirmar» el motivo ya no se pinta en la hoja del
  profesional. Sigue en la API y el ZIP.
- No se regeneró ningún entregable del cliente ni se reinició nada. Para que el
  cliente vea el formato nuevo hay que regenerar su Excel.
