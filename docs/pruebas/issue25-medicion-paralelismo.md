# Issue #25 — medición previa de la paralelización de N profesionales

> **Veredicto: NO-GO.** La paralelización que la issue propone —resolver N
> profesionales en paralelo contra la base local— puede ahorrar como máximo
> **entre 1,9 y 5,8 segundos** de un análisis que hoy dura **entre 3 y 21
> minutos**. Es el **0,4 %–1,7 %** del tiempo total. El 97,9 % del tiempo de esa
> etapa es espera del portal InfoObras, y paralelizar el portal está prohibido
> por regla del proyecto (y desaconsejado por la evidencia que hay más abajo).
>
> Medición hecha el **2026-08-05**, sin red, sobre los **7 concursos reales** de
> `datos_pivote/` (333 experiencias, 97 profesionales). Reproducible con
> `venv/Scripts/python backend/scripts/medir_paralelismo.py`.

La issue #25 lo exigía así: *«esto NO se implementa a ciegas»*, y su criterio de
aceptación contempla explícitamente cerrar sin implementar dejando la medición
como evidencia. Eso es lo que ocurrió.

---

## 1 · Qué tramo se paralelizaría, exactamente

| Pieza | Archivo | Qué itera |
|---|---|---|
| Bucle de resolución | `backend/orquestador/etapas_reales.py::EtapaResolucionCuiReal.correr` | una vuelta por experiencia (`ctx.items_experiencia()`), luego `resolver_con_dedup(pendientes, consulta, base=base)` |
| Herencia por folio | `backend/resolucion/cui.py::resolver_con_dedup` (línea ~2037) | `for exp, clave in experiencias: r = resolver(...)`, acumulando `por_folio` |
| Búsqueda difusa local | `backend/resolucion/base_mef.py::buscar_candidatos` | **lo que la issue nombra**: índice invertido + `rapidfuzz` sobre la base MEF |
| Fuentes por experiencia | `EtapaInfoObrasReal.correr`, `EtapaSunatReal`, `EtapaRenipressReal` | una vuelta por experiencia, con caché por obra y 2ª pasada por flakiness |

La issue acota el alcance ella misma: **«la paralelización va SOLO contra la base
local, JAMÁS contra portales en vivo»**. Es decir, de todo lo anterior, lo único
elegible es `buscar_candidatos()`.

---

## 2 · Lo que se midió, y con qué

Todo offline. Tres fuentes de números, ninguna simulada:

1. **Wall-clock real** — cada job persiste `metrica.duracion_ms` por etapa en su
   `job.json`. Son corridas de verdad, en el servidor, contra los portales
   vivos, entre el 27-jul y el 04-ago-2026. No hay banco de pruebas que sea
   mejor evidencia que esto.
2. **CPU local de la resolución** — el bucle de producción (`resolver_con_dedup`,
   sin re-implementar) contra el snapshot del portal reconstruido desde el
   enriquecimiento persistido: el harness de `scripts/replay_enriquecimiento.py`.
   Cero red.
3. **Base MEF real** — `buscar_candidatos()` contra la base instalada en esta
   máquina (620.985 filas, 579.481 CUIs), con los **333 nombres de obra reales**
   del corpus.

**Límite honesto del corpus.** La issue pedía ≥ 1.042 experiencias. Ese corpus
no existe: se perdió con el banco de verdades v3 (ver `.ai/handoffs/current.md`,
nota del 2026-07-28). Lo disponible son las 333 experiencias de los 7 concursos
reales, que sí incluyen el caso e2e que la issue exigía (**17 profesionales ×
67 experiencias**, job `371fa5a1e704`) y tres concursos completos más de ese
tamaño. Para medir percentiles de latencia, 333 consultas reales alcanzan de
sobra; para calibrar el `_STOP` del índice no alcanzarían, pero eso no es lo que
se decide aquí.

---

## 3 · M1 · Línea base real (segundos, portales vivos)

| job | prof | exp | validación | **resolución** | infoobras | sunat | excel | **TOTAL** |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `ff44d2833590` | 10 | 35 | 1,5 | 94,0 | 26,2 | 38,1 | 26,7 | **186,5** |
| `7e9306a321ac` | 14 | 31 | 0,5 | 111,2 | 87,0 | 47,1 | 28,2 | **306,5** |
| `ae368cb5dafa` | 5 | 22 | 1,1 | 178,5 | 127,0 | 79,2 | 31,0 | **416,8** |
| `15ee32f32c26` | 17 | 54 | 0,7 | 161,6 | 209,1 | 129,9 | 29,0 | **530,3** |
| `8a4b468ac700` | 17 | 62 | 0,1 | 372,8 | 365,7 | 160,4 | 7,3 | **906,4** |
| `371fa5a1e704` | 17 | 67 | 1,0 | 263,6 | 506,2 | 352,0 | 14,9 | **1.137,8** |
| `e7c0fff6afb1` | 17 | 62 | 1,9 | 455,7 | 485,0 | 231,6 | 112,9 | **1.287,0** |

Un concurso completo son **3 a 21 minutos**. Las tres etapas que hablan con
portales (resolución + InfoObras + SUNAT) son el **94 %–98 %** del total; todo lo
demás (ingesta, validación, reglas, Excel, persistencia) cabe en segundos.

---

## 4 · M2 · CPU local de la resolución: 0,6 ms por experiencia

Replay offline, 3 repeticiones, se toma el mínimo:

| job | exps replayadas | CPU local | ms/experiencia |
|---|---:|---:|---:|
| `15ee32f32c26` | 53 | 0,03 s | 0,63 |
| `371fa5a1e704` | 64 | 0,04 s | 0,62 |
| `7e9306a321ac` | 31 | 0,02 s | 0,64 |
| `8a4b468ac700` | 51 | 0,03 s | 0,62 |
| `ae368cb5dafa` | 21 | 0,02 s | 0,75 |
| `e7c0fff6afb1` | 51 | 0,03 s | 0,65 |
| `ff44d2833590` | 35 | 0,02 s | 0,57 |

El bucle de resolución entero —herencia por folio incluida— cuesta **cuatro
centésimas de segundo** en el concurso más grande. Ahí no hay nada que ganar.

---

## 5 · M3 · La base MEF, que es lo que la issue propone paralelizar

333 consultas reales contra la base real:

| Métrica | Valor |
|---|---|
| p50 | **81,7 ms** |
| p95 | **203,8 ms** |
| máximo | **351,9 ms** |
| media | 91,0 ms |
| suma de las 333 | **30,3 s** |
| carga perezosa del índice | **13,8 s** (una vez por proceso) |
| RAM del índice | **448,6 MB** |
| consultas con candidatos | 333 / 333 |

Dos correcciones a lo que decía el ADR-002 y el encabezado de `busqueda_mef.py`,
ambas a favor: la consulta típica cuesta **82 ms, no 200 ms**, y la carga del
índice es de **~14 s, no de 60-90 s** (medido en caliente de caché de disco; en
frío puede ser mayor, pero se paga una vez por proceso y la absorbe el primer
análisis del día).

**Coste por concurso** (cota superior: se asume 1 consulta por experiencia, y en
realidad las resueltas por código o heredadas por folio no consultan por nombre):

| job | exps | MEF ≤ | % del job |
|---|---:|---:|---:|
| `ae368cb5dafa` | 22 | 1,9 s | 0,46 % |
| `7e9306a321ac` | 31 | 2,8 s | 0,91 % |
| `ff44d2833590` | 35 | 3,2 s | **1,72 %** |
| `8a4b468ac700` | 62 | 4,6 s | 0,51 % |
| `e7c0fff6afb1` | 62 | 4,6 s | 0,36 % |
| `15ee32f32c26` | 54 | 4,8 s | 0,90 % |
| `371fa5a1e704` | 67 | 5,8 s | 0,51 % |

El criterio de aceptación de la issue («si la secuencial ya cumple < 3 s por
concurso, se cierra sin implementar») se cumple en 3 de 7 concursos al pie de la
letra, y en los 7 por su espíritu: donde no baja de 3 s, sigue siendo **medio
punto porcentual** del tiempo que el usuario espera.

---

## 6 · M4 · De dónde sale el tiempo, y cuál es el techo

| job | etapa resolución | local (CPU + MEF) | espera de portal | % portal |
|---|---:|---:|---:|---:|
| `15ee32f32c26` | 161,6 s | 4,9 s | 156,7 s | 97,0 % |
| `371fa5a1e704` | 263,6 s | 5,9 s | 257,7 s | 97,8 % |
| `7e9306a321ac` | 111,2 s | 2,8 s | 108,4 s | 97,4 % |
| `8a4b468ac700` | 372,8 s | 4,7 s | 368,1 s | 98,7 % |
| `ae368cb5dafa` | 178,5 s | 1,9 s | 176,6 s | 98,9 % |
| `e7c0fff6afb1` | 455,7 s | 4,7 s | 451,0 s | 99,0 % |
| `ff44d2833590` | 94,0 s | 3,2 s | 90,8 s | 96,6 % |

**Promedio: 97,9 % de la etapa es esperar a InfoObras.**

Amdahl, con la fracción paralelizable *permitida* (la local, 2,1 % de la etapa):

- aceleración máxima **de la etapa**, con infinitos trabajadores: **×1,02**;
- aceleración máxima **del job completo**: **×1,004 – ×1,017**;
- en el concurso más grande: **4,4 s** ahorrados de **19 minutos**, con 4
  trabajadores.

Para dimensionarlo al revés: si la etapa de resolución entera desapareciera —no
paralelizada, *gratis*— el job mejoraría entre **×1,30 y ×2,02**. Ese es el techo
absoluto e inalcanzable de trabajar sobre esta etapa; la paralelización de la
parte local captura menos del 2 % de él.

---

## 7 · Riesgos: qué comparte estado hoy

Inventario del código actual. No es una lista de «cosas a cuidar»: son cinco
cosas que hoy **están rotas para el paralelismo**, y arreglarlas es el verdadero
costo de la fase 2.

**1 · `BaseMef` se serializa a sí misma — esto solo ya anula la propuesta.**
`buscar_candidatos()` y `existe_cui()` ejecutan **todo su cuerpo** dentro de
`with self._lock:` (un `RLock` de instancia, `base_mef.py`). Un `ThreadPoolExecutor`
contra la base local daría **exactamente ×1**: los hilos harían cola en el lock.
Antes de ganar un solo milisegundo habría que estrechar ese lock a la sección que
de verdad muta estado (la carga perezosa), y eso es un cambio en el módulo que
sostiene el resolver, con el golden de por medio.

**2 · La herencia por folio es secuencial por definición, y es una regla de
negocio.** `resolver_con_dedup` acumula `por_folio` mientras itera: el «2.º
periodo del mismo certificado» hereda el CUI del hermano ya resuelto (#58). El
resultado depende del **orden**. La issue exige «resultados idénticos, mismo
orden» como criterio de aceptación — con este bucle, paralelizar y conservar la
herencia obliga a re-secuenciar o a una segunda pasada, es decir, a rehacer el
candado, no a envolverlo en un pool.

**3 · `ConsultaInfoObras` no es concurrente.** Una instancia por etapa, con
`self._cache` y `self._rango_cache` como dicts sin lock y un `requests.Session`
compartido (`requests` documenta que `Session` no es thread-safe). Y hay un
efecto peor que la carrera: **desbandada de caché**. N hilos que arrancan a la
vez fallan el mismo `key`, y los N salen al portal — la deduplicación se
evapora justo cuando la concurrencia es máxima. Lo mismo aplica al `cache` por
obra de `EtapaInfoObrasReal` y a `cache_seace`.

**4 · Las estadísticas de descarga son `threading.local`.**
`entregables/zip_infoobras.py::_dl_local`, con el comentario explícito de que
`reset_descargas_stats()` al inicio y `descargas_stats()` al cierre son seguros
**porque corren en el mismo hilo**. Si las descargas pasan a un pool, los
contadores de reintentos y fallidos vuelven cero **en silencio** — y son
precisamente la métrica con la que se sostiene el punto 5 de esta sección. Un
fallo silencioso nuevo, en el proyecto que acaba de cerrar #24 por eso mismo.

**5 · La traza pierde jerarquía.** `observabilidad/traza.py` escribe con lock (no
se corrompe), pero la pila de spans vive en un `ContextVar` que **no se propaga**
a hilos nuevos: los spans de los trabajadores saldrían a nivel raíz, mezclados.
Y `ctx.reportar(etapa, i, n, …)` —el «Verificando la obra i de n» que el usuario
ve— asume orden secuencial.

---

## 8 · Riesgo del portal: la evidencia dice que ya está al límite

InfoObras es flaky en secuencial, y los reintentos medidos no son ruido: escalan
con la carga que ya le estamos poniendo.

| job | descargas | reintentos | tasa | volumen | throughput |
|---|---:|---:|---:|---:|---:|
| `ae368cb5dafa` | 123 | 3 | 2,4 % | 0,4 GB | 2,8 MB/s |
| `ff44d2833590` | 239 | 2 | 0,8 % | 0,3 GB | 12,1 MB/s |
| `7e9306a321ac` | 1.205 | 2 | 0,2 % | 1,1 GB | 12,2 MB/s |
| `15ee32f32c26` | 2.605 | 53 | 2,0 % | 7,8 GB | 37,2 MB/s |
| `8a4b468ac700` | 2.480 | 234 | **9,4 %** | 13,9 GB | 38,0 MB/s |
| `e7c0fff6afb1` | 2.489 | 237 | **9,5 %** | 14,0 GB | 29,0 MB/s |
| `371fa5a1e704` | 3.292 | 244 | **7,4 %** | 15,4 GB | 30,5 MB/s |

Dos lecturas, las dos incómodas para la paralelización:

- **La tasa de fallo se multiplica por cinco** cuando el job pasa de ~1.200 a
  ~2.500 descargas. Secuencialmente ya se está tocando el techo del portal.
- **El throughput se aplana en 29–38 MB/s** en los tres jobs pesados. Cuando el
  cuello es ancho de banda sostenido y no latencia ociosa, abrir N conexiones no
  reparte mejor: reparte lo mismo en más trozos, con más handshakes y más
  probabilidad de que el portal corte (`IncompleteRead`, que es exactamente el
  fallo que el bloque R vino a contener).

No se midió un rate-limit explícito: hacerlo exige tocar el portal en vivo, y
esta medición es offline por mandato. Lo que sí está medido es que el portal se
degrada con la carga secuencial actual.

---

## 9 · Cuánto queda realmente sobre la mesa

El ahorro grande **ya se cobró** en #80: la caché por obra eliminó la
re-descarga entre profesionales que comparten obra, que era el gasto redundante
de verdad. Lo que queda es esto:

| | Segundos | % del job más grande |
|---|---:|---:|
| CPU del bucle de resolución | 0,04 | 0,004 % |
| Consultas a la base MEF (cota alta) | 5,8 | 0,51 % |
| **Total paralelizable por regla** | **5,8** | **0,51 %** |
| Espera de portales (prohibido paralelizar) | ~1.120 | ~98 % |

Contra eso, la fase 2 costaría: estrechar el lock de `BaseMef` (módulo del
resolver, con golden), rehacer o duplicar el paso de herencia por folio, hacer
concurrente `ConsultaInfoObras` sin perder su caché, migrar las estadísticas de
descarga fuera de `threading.local`, y arreglar traza y progreso. Días de trabajo
sobre las piezas más delicadas del backend, para ahorrar **cuatro segundos y
medio**.

---

## 10 · Veredicto

**NO-GO.** Cerrar #25 sin implementar, con esta medición como evidencia — que es
uno de los dos desenlaces que la propia issue declara válidos («resultado válido
y barato, no un fracaso»).

**Qué habría que ver para reabrirlo** (condiciones, no plazos):

1. que la etapa de resolución pase a costar **> 30 s de CPU local** por concurso
   —lo que implicaría ~50× más consultas locales que hoy—, por ejemplo si el
   resolver empezara a puntuar varias variantes de nombre por experiencia; o
2. que la base MEF crezca al punto de que el p95 de `buscar_candidatos` supere
   **~1 s**; o
3. que se levante la regla de no paralelizar portales, cosa que la evidencia de
   la sección 8 desaconseja por su cuenta.

**Si alguna vez se hace, con estos límites**: pool máximo **4**, solo sobre
`buscar_candidatos` (nunca sobre red), la herencia por folio **fuera** del tramo
paralelo, y la verificación de identidad de resultados contra la versión
secuencial sobre el corpus completo antes de mergear.

**Dónde sí está el tiempo, si se quiere atacar de verdad**: en las descargas de
InfoObras (26–506 s por job, 15 GB en el peor caso) y en SUNAT (38–352 s). No en
la búsqueda local. Cualquier trabajo de rendimiento futuro debería empezar por
ahí — con la salvedad de que ahí la palanca **no** es la concurrencia, sino bajar
menos: filtrar documentos por periodo, deduplicar por obra (ya hecho en #80) y
no traer lo que el evaluador no va a abrir.

---

## Cómo reproducir

```
cd backend
../venv/Scripts/python scripts/medir_paralelismo.py            # las cuatro medidas
../venv/Scripts/python scripts/medir_paralelismo.py --sin-mef  # sin cargar el índice
../venv/Scripts/python scripts/medir_paralelismo.py --json     # números crudos
```

No toca la red ni PostgreSQL, no escribe en ningún job, y no importa nada de
producción salvo para medirlo. Requiere la base MEF instalada en
`datos_pivote/referencia/mef` para la medida M3; sin ella, `--sin-mef` da las
otras tres.
