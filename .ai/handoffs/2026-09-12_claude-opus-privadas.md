---
timestamp: "2026-09-12"
agent: "Claude Opus"
session_status: "clean"
---

# Clientes privados reconocidos y la constancia sola en el Excel

Rama `mejoras/privadas-constancia`, desde `f17c00d` de `demo`. Dos cambios
acotados y un commit cada uno:

- `8f720a0` `fix(resolucion)` — léxico de privadas ampliado.
- `fa5c45f` `feat(entregables)` — solo la constancia en el Excel; el PDF
  completo al ZIP.

Sin red, sin push, sin reinicio del backend, sin tocar la skill ni el Panel, y
sin sobrescribir ningún entregable del cliente. Suite completa en verde (ver
abajo).

## 1 · Léxico de proyectos privados (`resolucion/cui.py`)

El léxico solo cubría colegios e institutos particulares, así que las clínicas
privadas caían en la cola de revisión como obra pública sin identificar y a una
el resolver le buscó CUI en el MEF. Regla del cliente: «los de privada déjalos
tal cual» (clasificar PRIVADA / NO APLICA, sin buscarles CUI).

`_es_experiencia_privada` ahora decide en tres capas con un **veto público por
delante**, y sigue leyendo solo `proyecto` + `entidad_contratante` + `objeto`
(el emisor queda fuera: el contratista privado es lo normal en obra pública):

0. **veto**: entidad o establecimiento público inequívoco nombrado (EsSalud,
   MINSA/ministerio, gobierno regional o local, municipalidad, PRONIS/PRONIED,
   universidad o instituto nacional, hospital regional/nacional/militar,
   DIRESA/GERESA/red de salud, centro o puesto de salud, asociación público
   privada, obra por impuestos) → NO es privada, pase lo que pase.
1. **léxico explícito**: el educativo de siempre + «proyecto/obra/edificio
   privado» (nunca «propiedad privada» ni «inversión privada»).
2. **establecimiento de salud privado**: «clínica» y «policlínico» como núcleo
   del nombre, borrando antes los usos adjetivales («ingeniería clínica»,
   «historia clínica», «patología clínica»).
3. **contratante persona natural** («SR./SRA./DON/DOÑA» + nombre).

**El orden de ADR-004 NO se movió**: la clasificación de privada sigue
ocurriendo al final, en `_clasificar_privada`, cuando la resolución pública ya
se agotó.

### Dos decisiones donde el encargo dejaba margen

- **«centro médico / oftalmológico» no entra como señal suelta.** Medido sobre
  1174 experiencias de espejos locales, añadirlo marcaba privadas 12 obras con
  nombre canónico de inversión pública («CONSTRUCCIÓN Y MEJORAMIENTO DEL CENTRO
  MÉDICO …, DISTRITO DE …, PROVINCIA DE …»). Esos nombres llegan igual por la
  capa 1 cuando el certificado declara el proyecto como privado, o acompañando a
  «clínica».
- **La forma societaria del contratante (S.A./S.A.C./E.I.R.L./S.R.L.) no
  clasifica privada**: es señal de `posible_privada` (revisión) en la rama b de
  `_clasificar_privada`, que hasta ahora era inerte sin base MEF. Ese campo
  llega mal llenado con el contratista o el consorcio de la obra pública
  demasiado seguido para decidir un NO APLICA con él.

Riesgo residual anotado en el código: EsSalud llama «policlínico» a varios de
sus locales; el veto los salva cuando el texto la nombra, y si no, el evaluador
lo ve rotulado PRIVADA en el Excel.

### Medición (sin red, solo lectura)

Script nuevo y versionado: `scripts/comparar_lexico_privadas.py <datos_pivote>`
(`--detalle` para ver los textos; no versiona datos ni imprime nada del cliente
sin esa bandera). Sobre los 24 jobs locales, 1174 experiencias:

| | |
|---|---|
| pasan a privada | **29** |
| dejan de ser privada | **0** |
| hoy resueltas con CUI que pasan a privada | **0** |

Replay offline (`scripts/replay_enriquecimiento.py --todos`) antes/después del
cambio: **26 diferencias nuevas y todas del mismo tipo**, `revisión → NO APLICA
(PRIVADA)`; ninguna `resuelto → privada`, ninguna privada que deje de serlo,
ningún CUI que cambie de valor. (29 frente a 26 porque el replay se salta las
experiencias sin enriquecimiento guardado.)

Sub-obras de edificios multifamiliares: el léxico **no** las toca, ni antes ni
después. Hallazgo colateral: en el job donde aparecen ya venían con `via:
PRIVADA` en el enriquecimiento, pero eso proviene de una **corrección manual**
(`correcciones/preparacion-…/enriquecimiento_CORREGIDO.json`, 6-ago), no del
resolver: su texto de decisión no existe en el código ni en el historial. Es
decir, hoy el resolver tampoco las clasificaría privadas por sí solo. No se
cambió nada ahí; queda como pendiente si el cliente lo pide.

### Pruebas

Seis casos nuevos en `tests/test_resolucion_cui.py` con nombres inventados: los
seis patrones positivos, los negativos públicos (EsSalud, universidad nacional,
gobierno regional, APP, «clínica» adjetivo, emisor privado S.A.C. certificando
obra pública, municipalidad), la persona natural y la forma societaria. **Ninguna
prueba existente pinzaba el comportamiento viejo**: no se editó ni se relajó
ningún test previo.

## 2 · Solo la constancia en el Excel; el PDF completo al ZIP

En el job de Tacna una experiencia trae una resolución gerencial de diez páginas
pegada detrás de la constancia, y esa sola experiencia se comía más de 800 filas
de la hoja del profesional.

- **Excel** (`entregables/excel_final.py`): `embeber_cert` acepta `max_pag` y la
  constancia de la experiencia se llama con **1**. Si el PDF tiene más páginas,
  debajo de la imagen queda **una sola fila**: «Documento de N páginas; el PDF
  completo está en el ZIP (carpeta de la experiencia)». TDR, Anexo 16 y Factor
  siguen con el límite de siempre. `_render_cert_pages` conserva firma y default
  de 12; el total de páginas se cuenta solo cuando el render pudo truncarse
  (nuevo helper `paginas_pdf`).
- **ZIP** (`entregables/zip_infoobras.py`): los `certs/` **no entraban** al ZIP
  (comprobado por grep y por lectura de la función). Ahora
  `construir_zip_infoobras` acepta `certificados` y escribe el PDF íntegro como
  `CONSTANCIA_P{n}_E{m}.pdf` en la carpeta de la experiencia. El índice (txt, md
  y json) lo lista como «Constancia presentada en la propuesta (N páginas)», la
  cabecera explica que es un adjunto del postor y el manifiesto de la carpeta lo
  separa en un bloque propio, «ADJUNTO DE LA PROPUESTA (no descargado de una
  fuente oficial)». **No cuenta como documento descargado**: no suma a los
  conteos y una experiencia sin descargas sigue diciendo SIN DOCUMENTOS. El
  parámetro es opcional: sin él el ZIP es byte-equivalente al de antes. Los dos
  puntos de armado del ZIP en `api/app.py` ya pasan `mapear_certificados`.
  `scripts/redescargar_documentos.py` NO se tocó: usa el layout plano legado,
  donde `mapear_certificados` no aplica.

### Medición sobre el job de Tacna (regenerado sin red, a scratch)

Se regeneró a `datos_pivote/3f04f6e73550/_constancia/` con `regenerar_excel_final`
(revisiones de `job.json`, `certificados=mapear_certificados(...)`); **no se
sobrescribió `final.xlsx` ni `infoobras.zip`**. El ZIP de comprobación (1,33 GB)
se borró después de contar; los dos `.xlsx` quedan en la carpeta scratch.

| | antes | después |
|---|---|---|
| hoja P1 · filas | 1653 | **830** |
| hoja P1 · imágenes | 21 | **10** |
| 17 hojas de profesional · filas | 14 415 | **12 926** |
| 17 hojas de profesional · imágenes | 169 | **149** |
| libro | 27,7 MB | 24,5 MB |

11 de las 62 constancias tienen más de una página (P1_E5 es la de 11) → 11 filas
de aviso, ni una más. El ZIP contiene **62 constancias** (22,1 MB) y el índice
las rotula 62 veces.

### Pruebas

`tests/test_constancia_una_pagina.py`, 6 casos con PDFs sintéticos hechos con
fitz: tres páginas → una imagen y una fila de aviso sin «Página 2/3»; una página
→ sin aviso; la hoja es más corta que con el adjunto completo; el ZIP lleva el
PDF íntegro bajo la carpeta P/E con su rótulo en índice y manifiesto; sin
`certificados` nada cambia; y la constancia no levanta el SIN DOCUMENTOS.

## Gate

`python -m pytest tests -q -p no:cacheprovider` con
`NODE_PATH=…/skill/node_modules` (necesario para `test_espejo_servicio_contrato`,
que necesita `zod` y el worktree no tiene `skill/node_modules`): **1883 passed,
31 skipped**, exit 0, sin fallos. 1914 pruebas recogidas; **+12 nuevas** (6 del
léxico de privadas y 6 de la constancia), todas ejecutadas, ninguna omitida.
Las 31 omitidas son las del árbol base.

## Lo que NO se hizo

- No se regeneraron los entregables del cliente ni se reinició el backend.
- No se creó ADR ni IDs nuevos; `ai-cli validate` conserva sus errores
  históricos de metadatos, intactos.
- No se tocó el resolver más allá de la clasificación de privadas: scoring,
  vías, cruces y cálculo quedan igual.
- El caso de los multifamiliares (ver arriba) queda identificado y sin cambiar.
