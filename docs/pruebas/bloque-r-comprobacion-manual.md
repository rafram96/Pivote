# Bloque R — comprobar la resiliencia de las descargas con tus propios ojos

> Issue **#81** (R1, R3, R4, R5). Todo lo de abajo se corre desde la raíz del
> repo (`Pivote/`), con `venv/Scripts/python`. **Ningún comando escribe en un
> job real** y **ninguno toca la red**: los cuatro modos leen lo que ya está en
> disco o simulan la descarga.

## Qué cambió, en una frase cada uno

| | Antes | Ahora |
|---|---|---|
| **R1** | Una sección caída (portal InfoObras inestable) se guardaba con `{"error": true}` y la caché igual se marcaba **completa**: ese hueco se propagaba a todas las experiencias de la obra y no había forma de reintentarlo. | La caché se publica **PARCIAL**. El siguiente pedido de esa obra re-descarga **solo** lo fallido, conserva lo sano por enlace duro y, si sale bien, promueve la entrada a completa. Resolver una revisión fuerza ese reintento. |
| **R3** | «sin documentos publicados (0 disponibles)» aunque la obra sí publicara informes de control fuera del periodo. Notas SEACE telegráficas. | El índice distingue *no hay* de *los hay, pero de otros años*. Las notas SEACE son frases de evaluador, conservando la diferencia entre «se puede reintentar» y «no existe publicado». |
| **R4** | Un kill duro dejaba carpetas `.{obra}.{uuid}.part` que nadie recogía. | Se recolectan al empezar la descarga del job. |
| **R5** | La descarga por un solo CUI bajaba directo y su reporte decía «0 fallidos» aunque se cayeran secciones enteras. | Va por la misma caché y **reporta descargados/fallidos incluyendo** informes, cierre y aprobación. |

---

## (a) Los textos nuevos de las notas SEACE, sobre el job real de Vitarte

```
venv/Scripts/python backend/scripts/probar_cache_descargas.py notas 7e9306a321ac
```

Lee las 41 notas que el job `7e9306a321ac` (EsSalud Vitarte) tiene en disco y
muestra, por caso, **qué dice hoy cada nota y qué dirá la próxima corrida**.

**Qué debes ver (números exactos, 2026-08-05):**

```
Job 7e9306a321ac · notas SEACE en disco: 41

■ estado «sin_tipo» · nota NO_DISPONIBLE · 26 archivo(s) en 13 experiencia(s)
  ANTES : el CUI no tiene proceso de supervision en datos abiertos (procesos vistos: otro)
  AHORA : El SEACE solo publica procesos de otro tipo para esta obra (por ejemplo
          ejecución o equipamiento); el proceso que certifica esta experiencia no
          figura en los datos abiertos.

■ estado «sin_procesos» · nota NO_DISPONIBLE · 12 archivo(s) en 6 experiencia(s)
  ANTES : el CUI no figura en los datos abiertos disponibles (cobertura 2018+)
  AHORA : Los datos abiertos del SEACE cubren contrataciones desde 2018; esta
          contratación es anterior, por eso sus documentos no están publicados ahí.

■ estado «seleccionado» · nota ERROR · 3 archivo(s) en 3 experiencia(s)  (P1/E1, P1/E2, P13/E1)
  ANTES : La descarga falló o la fuente no devolvió un PDF/ZIP/RAR válido. Reintentar más tarde.
  AHORA : No se pudo descargar este documento en esta corrida: la fuente oficial
          falló temporalmente. El proceso sí lo publica; se puede reintentar.
```

**Los dos controles que valen por todos:**

1. La **distinción se conserva**: las tres notas de `P1/E1`, `P1/E2` y `P13/E1`
   siguen siendo `_ERROR` («se puede reintentar»); las otras 38 siguen siendo
   `_NO_DISPONIBLE` («no existe publicado»). El texto cambió, el significado no.
2. Ninguna nota nombra un estado interno (`sin_tipo`, `fuente_no_disponible`)
   ni deja el apunte técnico del selector.

Para **abrir los archivos** tal como los verá el evaluador:

```
venv/Scripts/python backend/scripts/probar_cache_descargas.py notas 7e9306a321ac ^
    --salida %USERPROFILE%\Downloads\notas_vitarte.zip
```

*(en Git Bash, cambia `^` por `\` y usa `~/Downloads/…`)*

Ese ZIP trae **solo las 41 notas regeneradas** (ningún PDF: pesa nada y abre al
instante), cada una en la carpeta `P{n}_E{m}` de su experiencia. El ZIP grande
del job no se toca.

> ⚠ Los archivos que están hoy dentro de `datos_pivote/7e9306a321ac/descargas/`
> conservan el texto viejo: se escribieron en la corrida original. El texto
> nuevo lo escribe la próxima descarga — por eso la comprobación se hace con el
> ANTES/AHORA de arriba y no regenerando el ZIP entero.

---

## (b) «Los informes son de otros años» — el caso real P1/E2 de Vitarte

```
venv/Scripts/python backend/scripts/probar_cache_descargas.py informes 7e9306a321ac
```

Recorre el job y lista las experiencias donde la obra **sí publica** informes de
control pero **ninguno** cae en el periodo del certificado.

**Qué debes ver:** `10` experiencias, encabezadas por el caso que motivó la
issue:

```
■ P1/E2 · obra 74266 · 3 informe(s) publicado(s) por la obra, 0 en el periodo
  ANTES : SECCIÓN Informes de control: sin documentos publicados (0 disponibles)
  AHORA : SECCIÓN Informes de control: los informes de control publicados no
          corresponden al periodo de este certificado (3 publicados, todos de otros años)
```

Fíjate en `P8/E2`, `P8/E3`, `P9/E2` y `P11/E1`: con **un solo** informe el texto
se dice en singular — *«(1 publicado, de otro año)»*.

**Y el índice de verdad**, generado por el mismo código que arma el entregable:

```
venv/Scripts/python backend/scripts/probar_cache_descargas.py informes 7e9306a321ac ^
    --zip P1_E1,P1_E2 --salida %USERPROFILE%\Downloads\indice_muestra.zip
```

Empaqueta **solo esas dos experiencias** (el job completo pesa ~1 GB) e imprime
su `indice.txt`. Tiene que verse:

```
[P01 / E1]  GERENTE DE CONTRATO · Supervisión de la Obra: …: 62 documento(s) + 1 nota(s)
  ADVERTENCIA: SEACE_01_BASES_INTEGRADAS: la fuente devolvió un error.
[P01 / E2]  GERENTE DE CONTRATO · Supervisión de la Obra: …: 59 documento(s) · 59 compartido(s) …
  SECCIÓN Informes de control: los informes de control publicados no corresponden
                               al periodo de este certificado (3 publicados, todos de otros años)
```

**E1 y E2 son la misma obra (74266)**: E1 se lleva los 3 informes porque su
periodo los cubre y E2 no, y ahora el índice lo dice en vez de sugerir que la
obra no tiene informes. La **ausencia real conserva su texto**: una sección sin
nada publicado sigue diciendo «sin documentos publicados (0 disponibles)».

> El recuento de «publicados» de este modo se reconstruye de lo que hay en
> disco, porque el job es anterior a la issue. Las corridas nuevas guardan el
> inventario en el manifiesto y el índice sale así directamente.

---

## (c) El reintento selectivo, simulado offline

```
venv/Scripts/python backend/scripts/probar_cache_descargas.py reintento
```

Tres pasadas sobre una caché de mentira en una carpeta temporal (se borra sola):

```
PASADA 1 — el portal se cae en «Informes de control»
  secciones caídas      : Informes de control
  marca publicada       : .parcial
  corpus sano en disco  : ['Datos de cierre', 'Valorizaciones']
  → el error NO se congela: la entrada queda reintentable.

PASADA 2 — el portal responde
  se pidió a la fuente   : ['Informes de control']      ← SOLO la fallida
  secciones caídas       : (ninguna)
  marca publicada        : .completa
  valorización de la 1ª pasada intacta: True            ← lo sano no se re-descarga
  informe descargado ahora           : True

PASADA 3 — caché ya completa: no se vuelve a la fuente
  cache_hit: True   ·   consultas totales a la fuente: 2 (1 completa + 1 selectiva)
```

**Las tres cosas que hay que leer ahí:**

1. `marca publicada: .parcial` en la pasada 1 — el error **no** queda congelado
   como corpus definitivo.
2. `se pidió a la fuente: ['Informes de control']` — el reintento no repite las
   secciones sanas ni tira el corpus.
3. `consultas totales: 2` — una obra con una caída cuesta **una** consulta extra,
   no una descarga completa.

**En el pipeline real**, además: la experiencia cuyo corpus quedó parcial **no**
recibe su marca `.ok`, así que la siguiente pasada (otra experiencia de la misma
obra, una revisión resuelta o una reanudación tras reinicio) la vuelve a
materializar ya completa. Mientras siga incompleta, la barra del panel la cuenta
como pendiente: es la verdad, no un defecto.

**Y desde el panel**: al resolver una revisión, el backend purga las secciones en
error de la caché de esa obra — incluso si la entrada venía marcada `.completa`
por un job corrido con el backend anterior, que es justamente el caso que un
evaluador no podía desatascar. Una caché sana **no** se purga: la revisión la
reutiliza sin volver al portal.

---

## (d) La carpeta `.part` huérfana

```
venv/Scripts/python backend/scripts/probar_cache_descargas.py part
```

```
Carpeta huérfana plantada: .74266.0a1b2c3d….part
  contenido: ['a medias.pdf']
Recolectadas en la corrida siguiente: 1
  ¿sigue existiendo?      : False
  caché válida intacta    : True (+ True su documento)
Segunda pasada (nada que recoger): 0
```

Lo importante es la **tercera línea**: la entrada válida `74266` y su documento
quedan intactos. Solo se recogen los hijos directos de `cache_obras/` con forma
de temporal nuestro (`.{obra}.{uuid}.part`), nunca una entrada publicada.

---

## La comprobación automática

```
venv/Scripts/python -m pytest tests/test_descargas_infoobras.py -q     # desde backend/
venv/Scripts/python -m pytest tests -q                                 # suite completa
```

**837 passed, 25 skipped** (línea base antes de la issue: 826). Sin red. Las 11
pruebas nuevas cubren: la caché parcial y su reintento selectivo, que un
reintento fallido **no** destruya el corpus ya publicado, la purga que dispara
una revisión (incluida la marca heredada `.completa`), el recorrido completo por
`descargar_documentos_job` con el índice del ZIP en los dos momentos, la
recolección de `.part` dentro y fuera del job, los tres textos SEACE, el texto de
los informes fuera de periodo en los **tres** formatos del índice (txt/md/json) y
el reporte por secciones de la descarga por CUI.
