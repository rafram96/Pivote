# Análisis de Estructura, Archivos Monolíticos y Plan de Modularización (Backend)

> **Fecha**: 2026-07-27 (inventario) · 2026-07-27 (plan de ejecución, v2)
> **Estado**: Issue `T-REFACTOR-004` en [.ai/tasks/backlog.md:708](file:///C:/Users/Holbi/Documents/Freelance/proyectos/InfoObras/Pivote/.ai/tasks/backlog.md) — `esperando_aprobacion`
> **Rama de trabajo**: `demo`

---

## 1. Resumen Ejecutivo

Un análisis de complejidad y tamaño de archivos en el backend reveló la presencia de **6 archivos monolíticos (*God Files*)** que concentran 8,636 líneas de código crítico, sobre un total de 28,262 líneas Python en `backend/`. Estos archivos violan el Principio de Responsabilidad Única (SRP) y dificultan el mantenimiento, la depuración y el trabajo colaborativo en paralelo.

**Lo que cambió en la v2 de este documento.** El inventario (§2) se mantiene íntegro: es exacto, verificado línea por línea contra el código. El plan de ejecución se reescribió por completo tras auditar el acoplamiento real, que arrojó tres hechos que la v1 no contemplaba:

1. **El tamaño del archivo no es el problema principal.** `cui.py` son 1,760 líneas repartidas en ~80 funciones de nivel superior (~22 líneas cada una): grande, pero legible y testeable. `excel_final.py` esconde algo cualitativamente distinto — **una sola función de 1,254 líneas con 23 closures anidados** que comparten estado mutable. Ordenar por bytes oculta esa diferencia.
2. **La fachada preserva los `import`, pero rompe los `monkeypatch`.** La suite parchea atributos de módulo en 8 sitios. Un `from .submodulo import f` en la fachada hace que parchear la fachada ya no afecte al llamador. En `test_descargar_cui.py` eso significa que la suite offline pasaría a **pegarle a la red de InfoObras**. Esta es la restricción que gobierna dónde cae cada corte (§3, R1).
3. **La superficie de acoplamiento son los privados, no la API pública.** Los tests importan ~15 símbolos `_privados`, y hasta [api/app.py:37](file:///C:/Users/Holbi/Documents/Freelance/proyectos/InfoObras/Pivote/backend/api/app.py) importa `_zip_carpeta` desde `entregables`.

En consecuencia el plan v2: **añade `api/app.py`** al alcance (estaba en la tabla como *Core* pero sin plan), **descompone de verdad** la *God Function* de Excel en lugar de mudarla de archivo, **saca `cui.py` del alcance** de esta issue, y **fija un protocolo de verificación** (§4) sin el cual un refactor de "no cambió nada" no es firmable.

---

## 2. Inventario de los Archivos Python Más Grandes

### Top 10 Archivos por Tamaño en Disco (Bytes) y Líneas

| Puesto | Archivo | Tamaño | Líneas | Categoría |
|:---:|---|:---:|:---:|---|
| **1** | [backend/resolucion/cui.py](file:///C:/Users/Holbi/Documents/Freelance/proyectos/InfoObras/Pivote/backend/resolucion/cui.py) | **96.1 KB** (96,137 B) | 1,760 | **Core (Resolución CUI)** |
| **2** | [backend/entregables/excel_final.py](file:///C:/Users/Holbi/Documents/Freelance/proyectos/InfoObras/Pivote/backend/entregables/excel_final.py) | **91.3 KB** (91,326 B) | 1,661 | **Core (Reportes Excel)** |
| **3** | [backend/orquestador/etapas_reales.py](file:///C:/Users/Holbi/Documents/Freelance/proyectos/InfoObras/Pivote/backend/orquestador/etapas_reales.py) | **79.1 KB** (79,065 B) | 1,366 | **Core (Pipeline de Etapas)** |
| **4** | [backend/scraping/infoobras.py](file:///C:/Users/Holbi/Documents/Freelance/proyectos/InfoObras/Pivote/backend/scraping/infoobras.py) | **78.2 KB** (78,206 B) | 1,841 | **Core (Scraper InfoObras)** |
| **5** | [backend/tests/test_etapas_reales.py](file:///C:/Users/Holbi/Documents/Freelance/proyectos/InfoObras/Pivote/backend/tests/test_etapas_reales.py) | **66.7 KB** (66,693 B) | 1,321 | *Pruebas de Integración* |
| **6** | [backend/tests/test_entregables.py](file:///C:/Users/Holbi/Documents/Freelance/proyectos/InfoObras/Pivote/backend/tests/test_entregables.py) | **62.1 KB** (62,146 B) | 1,193 | *Pruebas de Entregables* |
| **7** | [backend/tests/test_integridad.py](file:///C:/Users/Holbi/Documents/Freelance/proyectos/InfoObras/Pivote/backend/tests/test_integridad.py) | **50.4 KB** (50,399 B) | 991 | *Pruebas de Integridad* |
| **8** | [backend/validacion/integridad.py](file:///C:/Users/Holbi/Documents/Freelance/proyectos/InfoObras/Pivote/backend/validacion/integridad.py) | **47.6 KB** (47,556 B) | 958 | **Core (Auditoría Legal/Técnica)** |
| **9** | [backend/api/app.py](file:///C:/Users/Holbi/Documents/Freelance/proyectos/InfoObras/Pivote/backend/api/app.py) | **45.6 KB** (45,554 B) | 988 | **Core (API REST)** |
| **10** | [backend/scraping/sunat.py](file:///C:/Users/Holbi/Documents/Freelance/proyectos/InfoObras/Pivote/backend/scraping/sunat.py) | **43.7 KB** (43,669 B) | 1,136 | **Core (Scraper SUNAT)** |
| **11** | [backend/entregables/zip_infoobras.py](file:///C:/Users/Holbi/Documents/Freelance/proyectos/InfoObras/Pivote/backend/entregables/zip_infoobras.py) | **40.1 KB** (40,140 B) | 872 | **Core (Empaquetador ZIP)** |

> **Nota**: [infoobras.py](file:///C:/Users/Holbi/Documents/Freelance/proyectos/InfoObras/Pivote/backend/scraping/infoobras.py) es el más extenso en líneas de código (1,841 líneas), mientras que [cui.py](file:///C:/Users/Holbi/Documents/Freelance/proyectos/InfoObras/Pivote/backend/resolucion/cui.py) es el más pesado en disco (96.1 KB).

### 2.1. Densidad: dónde está la complejidad real

El tamaño en disco no ordena por dificultad. Esta tabla sí:

| Archivo | Líneas | Unidades de nivel superior | Media | Unidad mayor |
|---|---:|---:|---:|---|
| `cui.py` | 1,760 | ~80 funciones | ~22 | `_compuertas` (239) |
| `infoobras.py` | 1,841 | 14 dataclasses + ~45 funciones | ~31 | `fetch_by_cui` (182) |
| `sunat.py` | 1,136 | 4 dataclasses + ~25 funciones | ~38 | `consultar_ruc` (124) |
| `etapas_reales.py` | 1,366 | 6 clases + ~20 funciones | ~52 | `EtapaInfoObrasReal` (338) |
| `zip_infoobras.py` | 872 | ~25 funciones | ~35 | `construir_zip_infoobras` (68) |
| **`excel_final.py`** | **1,661** | **~12 funciones** | **~138** | **`construir_hoja_profesional` (1,254)** |

`excel_final.py` es el caso atípico por un orden de magnitud, y es el que más se gana con el refactor.

---

## 3. Reglas de Corte (invariantes del refactor)

Estas cinco reglas gobiernan **todos** los PRs. No son estilo: cada una nació de un acoplamiento verificado en el código.

### R1 — Regla del monkeypatch (la que decide los cortes)

> **La función parcheada por los tests y su llamador viven en el mismo módulo, o la dependencia se inyecta por parámetro.**

En Python, `f()` resuelve los nombres que usa en los *globals de su propio módulo*. Si `descargar_cui` se muda a `empaquetador.py` y la fachada hace `from .empaquetador import descargar_cui`, entonces `monkeypatch.setattr(zip_infoobras, "descargar_informes_control", ...)` deja de tener efecto sobre la función real. El test no falla: **pasa ejercitando el código de red**, en una suite diseñada para correr 100% offline.

Sitios afectados, verificados:

| Test | Parchea | Consumidor que debe quedar junto |
|---|---|---|
| [test_descargar_cui.py:44-49,86](file:///C:/Users/Holbi/Documents/Freelance/proyectos/InfoObras/Pivote/backend/tests/test_descargar_cui.py) | `descargar_documentos_obra_por_hito`, `descargar_informes_control`, `descargar_datos_cierre`, `descargar_aprobacion_expediente` sobre `zip_infoobras` | `descargar_cui` |
| [test_infoobras_parsing.py:524-531](file:///C:/Users/Holbi/Documents/Freelance/proyectos/InfoObras/Pivote/backend/tests/test_infoobras_parsing.py) | `_crear_session`, `_buscar_por_cui` sobre `scraping.infoobras` | `fetch_by_cui` |
| [test_api.py:166,187](file:///C:/Users/Holbi/Documents/Freelance/proyectos/InfoObras/Pivote/backend/tests/test_api.py) | `descargar_cui` sobre `api.app` | `_correr_y_descargar` |
| [test_golden_casos.py:167,180,200](file:///C:/Users/Holbi/Documents/Freelance/proyectos/InfoObras/Pivote/backend/tests/test_golden_casos.py) | `resolver` sobre `resolucion.cui` | `golden_cui.py` |
| [test_infoobras_parsing.py:479](file:///C:/Users/Holbi/Documents/Freelance/proyectos/InfoObras/Pivote/backend/tests/test_infoobras_parsing.py) | `infoobras.requests`, `infoobras.time` | los que hacen I/O |

**Patrón que resuelve los tres primeros casos sin tocar un solo test**: *el orquestador se queda en la fachada*. `descargar_cui`, `fetch_by_cui` y `_correr_y_descargar` son coordinadores delgados que llaman a piezas pesadas. Si el coordinador permanece en el módulo-fachada y los nombres parcheados son globals de ese módulo (`from .informes_control import descargar_informes_control` **a nivel de módulo, en la fachada**), el `setattr` sobre la fachada sigue funcionando exactamente igual que hoy. Lo que se muda es el cuerpo pesado, no el coordinador.

### R2 — La fachada re-exporta también los privados

Los tests y `app.py` importan ~15 símbolos privados. La fachada debe re-exportarlos todos, con `# noqa: F401` y un comentario que diga por qué. Lista verificada:

`_bonus_mef`, `_rucs_postor`, `_minimo_exigido`, `_cobertura_cert`, `_fuera_de_ventana`, `_motivo_cobertura`, `_provincia_desde_cola`, `_terminos_geo`, `_ubigeo_contra`, `_rubro_contradice`, `_zip_carpeta`, `_anio_informe`, `_items_descarga`, `_etiqueta_hito`, `_descargar_a_carpeta`, `_crear_session`, `_buscar_por_cui`, `_extraer_datos_ejecucion`, `_procesar_avances`.

Los cuatro últimos son consumidos por `cui.py` mediante imports diferidos ([cui.py:761,830,856](file:///C:/Users/Holbi/Documents/Freelance/proyectos/InfoObras/Pivote/backend/resolucion/cui.py)) y **no pueden dejar de resolverse desde `scraping.infoobras`**.

### R3 — Un PR = un archivo monolítico

`cui.py` ya carga 5 imports diferidos dentro de funciones apuntando a `scraping.infoobras` — un parche contra un ciclo preexistente. Partir dos monolitos acoplados en el mismo PR multiplica las rutas de import que pueden ciclar y vuelve imposible bisecar una regresión. Un archivo por PR, sin excepción.

### R4 — Cero cambios de comportamiento

Si durante el refactor aparece un bug, se **anota** en `backlog.md` y se arregla en un PR aparte. Un PR que refactoriza *y* corrige es un PR cuyo diff nadie puede revisar y cuya verificación (§4) deja de aplicar, porque el criterio es precisamente que la salida no cambie.

### R5 — Los tests se parten junto con el código

`test_entregables.py` (1,193), `test_etapas_reales.py` (1,321) y `test_integridad.py` (991) se dividen espejando la nueva estructura, **dentro del mismo PR** que parte el módulo de producción. No es trabajo opcional ni posterior: es aproximadamente la mitad del esfuerzo y está estimado como tal en §5.

---

## 4. Protocolo de Verificación (obligatorio, por PR)

El criterio de aceptación de este refactor es *"la salida no cambió"*. Eso exige poder demostrarlo, no afirmarlo.

### V0 — Arnés de comparación (se construye primero, PR 0)

**`tools/comparar_xlsx.py`** y **`tools/comparar_zip.py`**.

Una comparación byte a byte del `.xlsx` **no sirve**: openpyxl escribe `docProps/core.xml` con marcas de tiempo de creación/modificación, y el contenedor ZIP guarda `mtime` por entrada. Dos corridas idénticas producen bytes distintos. El arnés debe comparar de forma normalizada:

- **XLSX**: descomprimir ambos, ignorar `docProps/core.xml`, y comparar el resto de partes XML. Complementariamente, cargar ambos libros con openpyxl y diferenciar celda por celda: `value`, `number_format`, `fill.fgColor.rgb`, `font.bold/size/color`, celdas combinadas y anclas de imágenes embebidas. Salida: lista de celdas divergentes con hoja y coordenada.
- **ZIP**: comparar el listado de entradas y el CRC-32 de cada una, ignorando `mtime`.

Sin este arnés, PR 2 y PR 3 no son verificables — y son los dos que más superficie visible tocan.

### V1 — Suite offline verde

```bash
venv/Scripts/python.exe -m pytest backend/tests -q
```

Línea base: **590 funciones de test** (619 casos con parametrizaciones), verdes hoy en `demo`. Criterio: mismo número de tests pasados, **cero `skipped` nuevos** — un skip nuevo suele ser un import que dejó de resolver.

### V2 — Igualdad de entregables

La herramienta correcta es [tools/utils/regenerar_excel_final.py](file:///C:/Users/Holbi/Documents/Freelance/proyectos/InfoObras/Pivote/tools/utils/regenerar_excel_final.py): regenera el Excel **final del backend** desde el `espejo.json` + `enriquecimiento.json` de un job ya corrido, **sin re-correr scrapers** — es decir, ejercita `generar_excel_final` (la función bajo refactor) de forma determinista y offline.

> ⚠ **No usar `backend/scripts/generar_excel.py`**: ése produce el Excel de hoja única del lado de Claude (formato Trujillo), no el entregable de `excel_final.py`. Son artefactos distintos.

Jobs disponibles hoy en `backend/datos_pivote/` con espejo + enriquecimiento completos: `15ee32f32c26` (187 KB), `371fa5a1e704` (216 KB), `ff44d2833590` (111 KB). Se propone **`ff44d2833590`** como fixture de verificación por ser el liviano, con `371fa5a1e704` como segundo caso para PR 2.

```bash
# 1) línea base: en `demo`, ANTES de empezar (PR 0)
python tools/utils/regenerar_excel_final.py ff44d2833590 backend/datos_pivote /tmp/base.xlsx

# 2) tras el refactor, en la rama del PR
python tools/utils/regenerar_excel_final.py ff44d2833590 backend/datos_pivote /tmp/despues.xlsx

# 3) diff normalizado
python tools/comparar_xlsx.py /tmp/base.xlsx /tmp/despues.xlsx   # → 0 diferencias
```

> ⚠ **La línea base se genera en la máquina de desarrollo y no se versiona**: tanto `fixtures/` como los jobs de `datos_pivote/` están gitignored por contener datos reales del cliente. Por eso V2 se ejecuta como paso explícito del PR 0 y sus salidas se guardan fuera del repo (`/tmp/`, o el scratchpad de la sesión). En el PR se reporta el resultado del diff, nunca los archivos.

Aplica a PR 2 (Excel) y PR 3 (ZIP). Obligatorio, no opcional.

### V3 — Golden del resolver sin cambios

Aplica a todo PR que toque `resolucion/` o `scraping/infoobras.py`, por la regla de oro ya vigente en [.ai/handoffs/current.md](file:///C:/Users/Holbi/Documents/Freelance/proyectos/InfoObras/Pivote/.ai/handoffs/current.md):

```bash
python backend/scripts/golden_cui.py --con-base --solo-cache
```

Criterio: diff **exactamente cero** contra `golden_cui_baseline.json`. En un refactor no aplica el criterio suave de "los mal-resueltos no suben" — cualquier cambio en la golden significa que el refactor cambió comportamiento y el PR se rechaza.

### V4 — Sin ciclos de import nuevos

```bash
python -c "import api.app"        # arranque limpio desde backend/
python tools/ciclos_import.py     # detector propio (AST), se construye en PR 0
```

Criterio: el conteo de ciclos no sube respecto a la línea base medida en PR 0.

> `pydeps` queda descartado: exige Graphviz instalado y no está en el `requirements.txt` del backend. El detector propio es un walker AST de ~40 líneas sobre `backend/` (sin dependencias, offline, mismo estilo que el resto de `tools/`), que lista los ciclos `a → b → a` incluyendo los introducidos por imports diferidos si se les cambia el nivel.

---

## 5. Plan de Ejecución

Siete PRs secuenciales, ordenados por **valor ÷ riesgo**. El orden no es negociable: PR 0 habilita la verificación de todos los demás, y PR 1 es deliberadamente el más simple para estrenar el protocolo en terreno seguro.

### PR 0 — Arnés de verificación · ~0.5 d · riesgo nulo

Construir `tools/comparar_xlsx.py`, `tools/comparar_zip.py` y `tools/ciclos_import.py` (§4, V0 y V4). Medir y registrar las líneas base: número de tests, número de ciclos de import, y las salidas de referencia (Excel y ZIP) de los jobs `ff44d2833590` y `371fa5a1e704` — generadas localmente y guardadas fuera del repo. **No toca código de producción.**

---

### PR 1 — `api/app.py` (988 → ~250 + 5 routers) · ~0.5 d · riesgo bajo

No estaba en el plan v1 pese a figurar como *Core* en el inventario. Es el corte más limpio del backend: 22 endpoints planos, sin lógica de negocio que desenredar.

```
backend/api/
├── estado.py           # DATA_DIR, repo, motor, lock/mapa de descargas — los singletons compartidos
├── dependencias.py     # _dir_job, _job_o_404, _espejo_o_404, _int_env, _leer_limitado, _FiltroPolling
├── rutas_concursos.py  # 5 endpoints /concursos
├── rutas_jobs.py       # /analizar, /jobs/{id}, /espejo, /resumen, /revision, /alertas, /progreso, /descargas, DELETE
├── rutas_entregables.py# /excel, /zip
├── rutas_salud.py      # /salud, /profesionales
└── app.py              # fachada: FastAPI(), include_router ×4, startup,
                        # y el trío /descargar-cui + _correr_y_descargar
```

**Restricción de ciclos (nueva en v2.1)**: `app.py` importa los routers para el `include_router`; si un router importara `app.py` de vuelta (por `repo`, `motor` o `DATA_DIR`, que hoy son globals de módulo consumidos por casi todos los endpoints) habría **ciclo de import en el arranque**. Por eso los singletons se mudan a `estado.py`, que no importa nada de `api/` — los routers importan de `estado`, nunca de `app`.

**Restricción R1**: `_correr_y_descargar` ([:270](file:///C:/Users/Holbi/Documents/Freelance/proyectos/InfoObras/Pivote/backend/api/app.py)), el `from entregables import descargar_cui` **y los 3 endpoints `/descargar-cui` se quedan juntos en `app.py`**, porque `test_api.py:166,187` parchea `api.app.descargar_cui`. Moverlos a un router habría exigido que el router importara el coordinador desde `app.py` (ciclo, ver arriba) o mover también el símbolo parcheado (rompe los tests). Dejar el trío en la fachada es la única opción que cumple ambas restricciones sin tocar un test.

Verificación: V1 + V4.

---

### PR 2 — `entregables/excel_final.py` (1,661 → paquete) · ~2.5 d · riesgo medio, **valor máximo**

El PR más importante del refactor. La v1 proponía mudar `construir_hoja_profesional` entera a `hoja_profesional.py`, lo que habría dejado un archivo de **1,254 líneas** — todavía el 4.º más grande del backend. El trabajo real es desarmar la función.

**El problema concreto**: 23 closures anidados que comparten estado mutable — un cursor `top` que avanza monótonamente y un registro de obras ya pintadas que `_registrar_obra`/`_ya_pintada` mutan entre sí para evitar duplicar bloques.

**La costura**: introducir un `ContextoHoja` explícito (dataclass con `ws`, `top`, `registro_obras`, `paleta`, `fichas`, `certs`) y subir los renderizadores a nivel de módulo recibiéndolo como primer parámetro. Cada renderizador devuelve el nuevo `top`, tal como ya hacen hoy.

```
backend/entregables/excel/
├── __init__.py
├── contexto.py         # ContextoHoja + banda, fila, separador (~90)
├── estilos.py          # paletas, fills, fuentes, formatos (líneas 48-96) (~50)
├── formato.py          # _mayus_inicial, _motivo_accion, _fecha_iso, _ddmmaa, _mes_en_rango, _xl (~60)
├── recortes_pdf.py     # _render_cert_pages, _mapear_dir_certs, mapear_certificados (~55)
├── hoja_base.py        # _BD_HEAD/_BD_WIDTHS/_BD_VERDICTS, construir_hoja_base_datos (~65)
├── render_obra.py      # render_obra, render_multi_obra, render_ya_pintada,
│                       # render_subexperiencias + cluster de identidad de obra
│                       # (_canon, _clave_obra, _tipo_bloque, _huella_obra,
│                       #  _registrar_obra, _ya_pintada, _ficha_sub)        (~390)
├── render_sunat.py     # render_emisor (~165), render_historico (~76),
│                       # render_representante (~81)                         (~325)
├── render_cert.py      # embeber_cert, cert_marco (~177), _dias_exp         (~230)
├── render_revision.py  # render_revision, render_aviso_revision             (~80)
├── render_paso5.py     # _p5_head, _p5, _p5_tot                             (~105)
└── hoja_profesional.py # construir_hoja_profesional: solo el flujo          (~180)
```

`excel_final.py` queda como fachada (~130 líneas) con `generar_excel_final`, `regenerar_excel_final`, `desempaquetar_enriquecimiento`, `inyectar_veredicto_backend`, **más las re-exportaciones obligadas**: `construir_hoja_profesional` (importada por nombre en [test_entregables.py:349,371,399,462](file:///C:/Users/Holbi/Documents/Freelance/proyectos/InfoObras/Pivote/backend/tests/test_entregables.py) y [test_etapas_reales.py](file:///C:/Users/Holbi/Documents/Freelance/proyectos/InfoObras/Pivote/backend/tests/test_etapas_reales.py)), `construir_hoja_base_datos` y `mapear_certificados` (consumida por [entregables/\_\_init\_\_.py](file:///C:/Users/Holbi/Documents/Freelance/proyectos/InfoObras/Pivote/backend/entregables/__init__.py) y `etapas_reales.py`), además de las de R2.

**Por qué es el de menor riesgo pese al tamaño**: función pura, sin red, ~60 tests en `test_entregables.py` y salida verificable celda por celda con V2. Es el único de los seis donde se puede *demostrar* equivalencia, no argumentarla.

Se parte también `test_entregables.py` (1,193) espejando la estructura (R5).

Verificación: V1 + **V2 obligatorio** + V4.

---

### PR 3 — `entregables/zip_infoobras.py` (872 → paquete) · ~1 d · riesgo medio-alto

Cortes limpios, pero es donde R1 muerde con más fuerza: los cuatro descargadores están parcheados por `test_descargar_cui.py`.

```
backend/entregables/zip/
├── stats.py            # reset_descargas_stats, descargas_stats, _registrar_fallo, resumen_descargas (~45)
├── inventario.py       # _seccion, inventariar, _etiqueta_hito, inventariar_por_avance (~160)
├── descargas.py        # _descargar_a_carpeta, _get_inventario, descargar_documentos_obra[_por_hito] (~180)
├── informes_control.py # _parse_fecha_informe, _anio_informe, obtener/informes_relevantes, descargar (~145)
├── cierre.py           # _items_descarga, descargar_datos_cierre, descargar_aprobacion_expediente (~90)
└── empaquetador.py     # _ruta_segura, _wlong, _motivo_sin_docs, _cargo_corto, _corto,
                        # construir_zip_infoobras, _zip_carpeta (~150)
```

**`descargar_cui` NO se muda**: se queda en la fachada `zip_infoobras.py`, importando los cuatro descargadores a nivel de módulo. Así `monkeypatch.setattr(zip_infoobras, "descargar_informes_control", ...)` sigue funcionando sin tocar un solo test. Es el caso de manual de R1.

Verificación: V1 + **V2 (ZIP)** + V4.

---

### PR 4 — `scraping/sunat.py` (1,136 → paquete) · ~0.75 d · riesgo bajo

El más limpio de los scrapers: los bloques ya están contiguos en el archivo, el corte es casi mecánico.

```
backend/scraping/sunat/       # el módulo se convierte en paquete; __init__.py es la fachada
├── client.py     # _SUNATTlsAdapter, _crear_session_sunat, _request_with_retry, constantes de retry (líneas 44-176)
├── models.py     # EmpresaSUNAT, RepresentanteLegal, _FIELDS (177-234, 642-658)
├── nombres.py    # normalizar_nombre_empresa, score_match_empresa, _SUFIJOS_LEGALES_RE (235-302)
├── parsers.py    # _fake_captcha_token, _parse_fecha_sunat, _strip_tags, _parse_detalle,
│                 # _parse_lista, _detectar_encoding, diagnosticar_html_sunat, _parse_representantes (303-447)
├── consultas.py  # consultar_ruc, buscar_por_razon_social, consultar_representantes (448-790)
└── historico.py  # TramoCondicion, HistoricoSUNAT, _filas_tabla, _parse_historico,
                  # consultar_historico, condicion_en_fecha, condiciones_en_rango,
                  # _dias_sin_condicion, evaluar_habido (791-1094)
```

**Mecánica de la fachada (distinta a la de `entregables/`)**: aquí el nombre público ES el nombre del módulo (`scraping.sunat`), así que no puede coexistir un `sunat.py` con un paquete `sunat/` — la fachada es el **`__init__.py` del paquete**, que contiene `sondear` y re-exporta todo lo que `test_sunat_parsing.py` consume como atributo del módulo (`sunat._parse_detalle`, `_parse_lista`, `_parse_representantes`, `_parse_historico`, `_parse_fecha_sunat`, `TramoCondicion`, `condicion_en_fecha`, `evaluar_habido` — verificado). `from scraping import sunat` y `from scraping.sunat import X` siguen resolviendo idéntico. En `entregables/` el nombre público (`zip_infoobras`, `excel_final`) difiere del nombre del paquete nuevo, por eso allá la fachada puede ser un módulo hermano.

Verificación: V1 + V4.

---

### PR 5 — `scraping/infoobras.py` (1,841 → paquete) · ~1.5 d · riesgo alto

Las 14 dataclasses salen solas; el resto arrastra el ciclo con `cui.py`.

```
backend/scraping/infoobras/   # el módulo se convierte en paquete; __init__.py es la fachada
├── models.py       # 14 dataclasses: WorkInfo, SupervisorInfo, ResidenteInfo, AvanceMensual,
│                   # ContratistaInfo, ModificacionPlazoInfo, ... (64-241)
├── client.py       # HEADERS, _crear_session, _buscar_por_cui, _extraer_datos_*, _parse_js_vars (267-495)
├── parsers.py      # los 14 _procesar_*, _parsear_*_html, _to_float, _parse_fecha_* (242-266, 496-836)
├── inactividad.py  # _derivar_avance_actual, _extraer_periodos_suspension,
│                   # _huecos_de_valorizacion, periodos_inactividad (837-951)
├── seleccion.py    # _estado_obra, _ventana_obra, coincide_codigo, _cod_obra,
│                   # seleccionar_obra, elegir_obra_raw (952-1094)
├── expediente.py   # _url_a_item, parsear_aprobacion_expediente, _fetch_aprobacion_expediente (1095-1164)
└── verificacion.py # buscar_obras_por_nombre + scoring Jaccard (1347-final)
```

**Restricciones duras**:
- `fetch_by_cui` (1165-1346) **vive en el `__init__.py` del paquete** (misma mecánica que PR 4: el nombre público es el del módulo, la fachada es el `__init__`) — `test_infoobras_parsing.py:524-531` parchea `_crear_session` y `_buscar_por_cui` sobre el módulo, y como `fetch_by_cui` los resuelve en los globals del `__init__`, el patch sigue funcionando (R1).
- `BASE_MAPA`, `_crear_session`, `coincide_codigo`, `_extraer_datos_ejecucion`, `_procesar_avances` y `seleccionar_obra` deben seguir resolviéndose desde `scraping.infoobras` — son los imports diferidos de `cui.py` (R2).
- Los imports diferidos de `cui.py` **no se tocan en este PR**. Convertirlos a imports normales es trabajo del PR de `cui.py`, que está fuera de alcance (§6).

Verificación: V1 + **V3** + V4.

---

### PR 6 — `orquestador/etapas_reales.py` (1,366 → paquete) · ~1.5 d · riesgo alto

Va último porque es el archivo con más trabajo semántico encima: lo tocó el fix del Issue #51 hace tres días (commit `2677aad`) y tiene cuatro issues abiertas apuntando a su zona (#52, #53, #54, #57). **Gate explícito**: este PR no arranca mientras haya otro PR abierto que toque `etapas_reales.py` — si uno de esos issues entra en ejecución primero, PR 6 espera a que mergee.

La v1 proponía 6 archivos `etapa_*.py` por simetría nominal. Eso deja dos gordos y cuatro triviales (`EtapaInfoObrasReal` son 338 líneas; `EtapaValidacionReal`, 78) y **no asigna hogar a ~350 líneas que no son etapas**:

```
backend/orquestador/etapas/
├── comun.py          # _met, _res, _clave, _recorte, _fecha_iso, _fin_de_mes, _fx_de_obra (39-80, 152-185)
├── cobertura.py      # _COBERTURA_MIN, _cobertura_cert, _fuera_de_ventana, _motivo_cobertura (81-151)
│                     #   ⚠ zona del fix #51 — congelar durante el PR
├── validacion.py     # EtapaValidacionReal (186-263)
├── resolucion.py     # EtapaResolucionCuiReal (264-402)
├── infoobras.py      # EtapaInfoObrasReal (403-740)
├── descargas.py      # descargar_documentos_job (741-851) — ⚠ público, lo llama api/app.py:238
├── sunat.py          # _rucs_postor, _es_publica, _nombre_emisor_limpio, _elegir_match_exacto,
│                     # _evaluar_habido_emisor, EtapaSunatReal (852-1094)
├── reglas.py         # _RE_MINIMO, _DIAS_POR_UNIDAD, _minimo_exigido, EtapaReglasReal (1095-1303)
└── excel.py          # EtapaExcelReal (1304-1349)
```

`etapas_reales.py` queda como fachada con la función `etapas_reales()` (1350-1366) y las re-exportaciones de R2 — `test_etapas_reales.py` importa `_rucs_postor`, `_cobertura_cert`, `_fuera_de_ventana`, `_motivo_cobertura`, `_minimo_exigido`, `EtapaSunatReal`, `EtapaValidacionReal` e `EtapaInfoObrasReal` por nombre.

Se parte también `test_etapas_reales.py` (1,321) espejando la estructura (R5).

Verificación: V1 + V2 + **V3** + V4.

---

### Resumen de esfuerzo

| PR | Alcance | Días | Riesgo |
|---|---|---:|---|
| 0 | Arnés de verificación | 0.5 | nulo |
| 1 | `api/app.py` | 0.5 | bajo |
| 2 | `entregables/excel_final.py` + tests | 2.5 | medio |
| 3 | `entregables/zip_infoobras.py` | 1.0 | medio-alto |
| 4 | `scraping/sunat.py` | 0.75 | bajo |
| 5 | `scraping/infoobras.py` | 1.5 | alto |
| 6 | `orquestador/etapas_reales.py` + tests | 1.5 | alto |
| | **TOTAL** | **8.25 d** | |

Los PRs 0-4 (5.25 d) son autónomos y entregan la mayor parte del valor. Si hay que cortar por tiempo, se corta por ahí: PR 5 y 6 son los de peor relación valor/riesgo del lote aprobado.

---

## 6. Fuera de Alcance: `backend/resolucion/cui.py`

**`cui.py` sale de `T-REFACTOR-004`.** Es el archivo #1 del inventario, así que la exclusión requiere justificación explícita:

1. **Es el núcleo de decisión del producto.** Un error sutil aquí no rompe un test: produce un CUI mal resuelto que se ve correcto y llega al entregable del cliente.
2. **Está semánticamente en movimiento.** La compuerta de rubro entró hace días (rama `sonda/catch-cui`), y el problema de circularidad del selector de solape — el tier de solape en `cui.py:709-723` elige la obra usando el periodo *declarado*, con lo que puede lavar una mentira y hasta desplazar un `ruc_match` — sigue **abierto**. Refactorizar la estructura mientras cambia el significado es cómo se pierden semanas: cada regresión de la golden se vuelve ambigua entre "lo movió el refactor" y "lo movió el fix".
3. **Su densidad no lo exige.** ~80 funciones de ~22 líneas de media. Es un archivo grande, no un archivo enredado. El beneficio marginal de partirlo es el menor de los seis.
4. **La v1 subestimaba el reparto.** El grueso está en `_compuertas` (239 líneas), `_rankear` (149) y el bloque geográfico (~280). `cliente_infoobras.py`, en cambio, serían ~95 líneas: un módulo por una clase.

**Condición de reingreso** *(actualizada 2026-07-28 — el corpus de la golden v3 se perdió irremediablemente, ver `handoffs/current.md`)*: se abre `T-REFACTOR-005` cuando (a) la circularidad del solape esté resuelta o formalmente descartada, (b) **exista la golden v4** (corpus reconstruido con `exportar_verdades_panel.py` + caché + baseline regeneradas) y (c) esa baseline lleve dos semanas sin moverse. Sin instrumento de regresión, refactorizar el núcleo de decisión es volar a ciegas — la condición se ENDURECE, no se relaja.

---

## 7. Estructura Limpia del Core de Producción

Filtrando los artefactos de desarrollo (`tests/`, `datos_pivote/`, `exploracion/`, `observabilidad/` y `scripts/`), la arquitectura de tiempo de ejecución del backend queda definida así:

```text
backend/
├── .dockerignore
├── Dockerfile
├── config.py
├── requirements.txt
├── ic.html
├── api/                   # [1] Entrada HTTP / REST API (app.py)
│   ├── __init__.py
│   └── app.py
├── db/                    # [2] Definición de Esquema SQL Postgres
│   └── schema.sql
├── schemas/               # [3] Contratos Pydantic / Zod (pipeline, espejo, enriquecimiento)
│   ├── cargo.py
│   ├── enriquecimiento.py
│   ├── espejo.py
│   ├── nombres.py
│   └── pipeline.py
├── orquestador/           # [4] Motor del Pipeline y Persistencia
│   ├── __init__.py
│   ├── etapas.py
│   ├── etapas_reales.py
│   ├── motor.py
│   ├── progreso.py
│   ├── repositorio.py
│   └── repositorio_pg.py
├── scraping/              # [5] Conectores de Datos Externos (SUNAT, MEF, InfoObras)
│   ├── README.md
│   ├── __init__.py
│   ├── errores_red.py
│   ├── infoobras.py
│   ├── mef.py
│   └── sunat.py
├── resolucion/            # [6] Algoritmos de Coincidencia CUI y Desambiguación
│   ├── __init__.py
│   ├── base_mef.py
│   ├── cui.py
│   └── texto.py
├── validacion/            # [7] Auditoría Legal, Integridad de Folios e Inactividad
│   ├── __init__.py
│   ├── cargo_nucleo.py
│   ├── folios.py
│   ├── integridad.py
│   ├── notas.py
│   └── recalculo.py
├── reglas/                # [8] Lógica de Negocio y Cálculo Aritmético Auditables
│   ├── __init__.py
│   └── calculo.py
└── entregables/           # [9] Fábrica de Entregables (Excel estilizado y ZIPs)
    ├── __init__.py
    ├── excel_final.py
    └── zip_infoobras.py
```

---

## 8. Justificación de Carpetas Excluidas del Core

* **`backend/tests/`**: Suite de 590 funciones de prueba (619 casos) con pytest para verificación offline.
* **`backend/datos_pivote/`**: Cachés e inventarios JSON offline para correr la suite *Golden Set* de resolución CUI sin tocar la red.
* **`backend/exploracion/`**: Capturas HTML/JSON estáticas utilizadas durante la fase de ingeniería inversa de portales estatales.
* **`backend/observabilidad/`**: Motor de trazas de latencia (`traza.py`) y visor interactivo local (`visor_traza.html`).
* **`backend/scripts/`**: 18 comandos de CLI utilitarios para administradores (migraciones, parcheos manuales, backfills, demos).

> **Nota sobre §7**: el árbol refleja el estado **actual** (pre-refactor). Al cerrar cada PR de §5 se actualiza aquí la carpeta correspondiente, y al cerrar el último se sincroniza `.ai/architecture/backend.md`.
