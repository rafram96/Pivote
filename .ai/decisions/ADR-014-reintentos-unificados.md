# ADR-014 · Un solo mecanismo de reintentos y una sola semántica de fallo en scraping

- Fecha: 2026-08-05 · Estado: **aprobado, implementado** (T-REFACTOR-001)
- Aprobó: Rafael, 2026-08-05 — *«Concuerdo con el T-REFACTOR-001»*

## Contexto

El sondeo A03 encontró que «el portal no respondió» se dice en **tres dialectos
distintos**, uno por fuente, y que cada llamador tiene que conocer el dialecto de
la suya:

| Fuente | Cómo dice «no respondió» | Backoff |
|---|---|---|
| `resolucion/cui.py::_Infra._query` | excepción `PortalNoResponde` | lineal `1.5·(i+1)` |
| `scraping/infoobras.py` (3 bucles) | relanza la última excepción, salvo `_buscar_por_cui` que devuelve `[]` | lineal `1.5·(i+1)` |
| `scraping/mef.py` (2 bucles) | `None` / `False` | exponencial `1.5·2ⁱ` |
| `scraping/sunat.py` | `None` | exponencial `0.5·2ⁱ` + jitter 0.3 |
| `scraping/seace_abierto.py` (2 bucles) | `None` / `False` | lineal `1.5·(i+1)` |
| `scraping/renipress.py` | `ResultadoRENIPRESS(estado="portal_no_disponible")` | lineal `1.5·i` |
| `entregables/zip_infoobras.py` (5 bucles) | relanza · `False` · `[]` · `{0,0}` | exponencial `1.0·2ⁱ` + jitter 0.5 |

Inventario completo: **15 bucles de reintento artesanales** en 7 módulos, con 4
fórmulas de backoff, 3 formas de jitter (ninguno / `uniform(0,.3)` /
`uniform(0,.5)`) y 6 valores de retorno para el mismo evento.

El costo no es estético. **«Vacío ≠ caído» ya se pagó una vez**: en el caso 6:1
una microcaída del portal agotaba los tres intentos en milisegundos, el resolver
leía el `[]` resultante como «no hay obra» y degradaba al fragmento genérico
(`recurring_patterns.md`). El fix vive hoy en `cui.py` —`PortalNoResponde`— pero
es **local a ese archivo**: nada impide que la próxima fuente repita el error,
porque el mecanismo no lo evita, lo evita la memoria del que escribió ese bucle.

Dos conflaciones «vacío = caído» siguen vivas hoy en el código (ver §Pendientes).

## Decisión

### 1 · Helper único `con_reintentos()` en `scraping/errores_red.py`

Un solo bucle en todo el backend. La operación de red se pasa como función sin
argumentos; el helper aporta política, clasificación y logging.

```python
res = con_reintentos(_pedir, politica=_POLITICA, etiqueta="MEF GET …",
                     excepciones=(requests.RequestException, RespuestaTransitoria))
```

- **`Politica(intentos, base, modo, jitter, tope)`** — `modo` es `LINEAL`
  (`base·(i+1)`) o `EXPONENCIAL` (`base·2ⁱ`); `jitter` suma `jitter·azar()`
  (equivalente exacto a los `random.uniform(0, j)` que había). Congela las 4
  fórmulas que existían en **una** con parámetros; ninguna fuente cambió su
  temporización.
- **Clasificación única**: reutiliza `clasificar()`/`corto()`, que ya vivían en
  este módulo. Todo intento fallido se loguea **siempre** con `corto()` — antes
  tres módulos escupían la excepción cruda y uno no logueaba nada.
- **`dormir` y `azar` inyectables** (resueltos en tiempo de llamada, no como
  default de firma) → la política es testeable sin dormir y sin red, y los
  `monkeypatch.setattr(mod.time, "sleep", …)` que ya existen siguen funcionando.
- **`al_reintentar(intento, error)`**: gancho para los contadores por hilo de
  `zip_infoobras` (`descargas_stats()["reintentos"]`), que tenían que quedar
  dentro del bucle.

### 2 · Semántica de retorno ÚNICA: `Resultado` (valor-resultado)

```python
@dataclass(frozen=True)
class Resultado:
    respondio: bool          # ¿la fuente contestó?  ← la pregunta
    valor: Any               # el dato (puede venir vacío: eso ES un dato)
    error: BaseException | None
    intentos: int
```

- **`respondio=True`** → la fuente contestó. `valor` puede ser `[]`, `None`,
  `False`: **eso es un dato** («no hay»), y el llamador puede concluir.
- **`respondio=False`** → la fuente no contestó tras agotar los intentos. Es una
  **incógnita**: reintentar más tarde o abstenerse. Nunca «no hay».

La distinción se hace **imposible de confundir por construcción**, no por
disciplina: `Resultado.__bool__` **lanza `TypeError`**. `if res:` — el error
exacto del caso 6:1 escrito en una línea— deja de compilar mentalmente y falla
ruidosamente con un mensaje que explica la diferencia. Es la única forma de que
un agente nuevo no repita el error sin haber leído este ADR.

Tres primitivas más, todas en `errores_red.py`:

- **`reintentar(valor_final)`** — la operación contestó pero la respuesta parece
  un hipo del portal (200 con lista vacía). Se reintenta; si se agotan los
  intentos el resultado es **RESPONDIÓ** con `valor_final`, porque contestar
  vacío tres veces seguidas sí es un dato. Es exactamente el contrato que
  `_buscar_por_cui` implementaba a mano con su bandera `hubo_respuesta`.
- **`RespuestaTransitoria`** (subclase de `OSError`) — la fuente contestó algo
  que no es respuesta (5xx, cuerpo vacío, transferencia cortada). Cuenta como
  caída.
- **`permanente()`** — context manager que marca lo de adentro como
  no-reintentable (un 4xx). El helper relanza la excepción original de inmediato,
  con su tipo intacto.

**Cualquier valor devuelto por la operación es una respuesta definitiva.** Solo
las excepciones y `reintentar()` provocan otro intento. Esa regla es la que
elimina el dialecto: no hay «`None` significa caído en mef pero no-existe en
sunat».

### 3 · La migración unifica el MECANISMO, no los contratos públicos

Cada función migrada **traduce el `Resultado` a lo que ya devolvía**:
`mef._get` sigue devolviendo `Response | None`, `_buscar_por_cui` sigue
devolviendo `[]` o relanzando, `zip_infoobras._get_inventario` sigue relanzando.
`PortalNoResponde` sigue existiendo y saliendo de `cui.py` hacia sus llamadores.
Ningún test existente se tocó — y ese fue el criterio: si un test hubiera pedido
cambio, era señal de que la semántica se movió.

## Alternativa descartada

**Excepciones tipadas en todas las fuentes** (mover `PortalNoResponde` a
`errores_red.py` y hacer que las 7 fuentes lo lancen, eliminando los `None`/`[]`).
Es la opción más limpia sobre el papel y se descartó por tres razones medidas:

1. **Cambia el contrato público de 15 sitios a la vez.** `mef._get` devuelve
   `None` a cuatro llamadores; `sunat._request_with_retry`, a nueve. Convertirlos
   a `try/except` es exactamente el «cambio de comportamiento observable» que
   esta tarea prohíbe, y sin golden vigente (el corpus se perdió, ver handoff) no
   hay instrumento para probar que nada se movió.
2. **No sirve para las fuentes que no fallan del todo.** SUNAT y RENIPRESS
   necesitan devolver evidencia parcial junto al fallo; una excepción obliga a
   colgarle atributos al error, que es un valor-resultado disfrazado.
3. **Un `except` olvidado es silencioso hacia arriba** (la excepción sube y mata
   el job), mientras que un `Resultado` mal leído ahora **explota en el acto**
   por el `__bool__`. Para el error concreto que queremos evitar —confundir vacío
   con caído— el valor-resultado tiene mejor modo de falla.

El valor-resultado también permitió migrar **sin introducir un tercer dialecto**:
no se creó ninguna excepción pública nueva de «no respondió».

## Alcance de la migración

**Migrados — 13 bucles, 6 módulos** (mecanismo unificado, contrato externo intacto):

- `scraping/infoobras.py`: `_crear_session`, `_buscar_por_cui`,
  `_extraer_datos_ejecucion`.
- `scraping/mef.py`: `_get`, `descargar_pdf`.
- `scraping/sunat.py`: `_request_with_retry`.
- `scraping/seace_abierto.py`: `_get`, `descargar_archivo`.
- `scraping/renipress.py`: `ClienteRENIPRESS.buscar`.
- `entregables/zip_infoobras.py`: `_descargar_a_carpeta`, `_get_inventario`,
  `_descargar_url`, `obtener_informes_control`, `descargar_datos_cierre`.

Los contadores por hilo del ZIP (`_dl_local`, `descargas_stats`) **sí se
integraron**, vía el gancho `al_reintentar`: quedaron dentro del helper sin
perder su semántica propia (alimentan el índice del entregable).

### Pendientes conscientes — NO migrados, y por qué

1. **`resolucion/cui.py::_Infra._query`** — queda fuera. Su bucle es
   mecánicamente migrable, pero el archivo es el núcleo de decisión, **no aplica
   golden** (el corpus v4 no existe) y su `logger.warning(… %r)` con la excepción
   cruda es la única traza forense de la clase de fallo del caso 6:1;
   reemplazarla por `corto()` perdería el tipo exacto. `PortalNoResponde` sigue
   viviendo en `cui.py` y **no** se hizo subclase de nada en `errores_red.py`:
   eso obligaría a tocar el archivo para ganar cero llamadores. Reingresa cuando
   la golden exista.
2. **`infoobras.py::fetch_by_cui`, reintento del `codigoObra` faltante** (~línea
   1228, `time.sleep(2.0)` + una repetición de la búsqueda). No es un reintento
   de red: la fuente **sí** respondió y el dato vino incompleto. Meterlo al helper
   disfrazaría de caída lo que es un defecto del payload.
3. **`obtener_informes_control` y `descargar_datos_cierre` conflacionan vacío y
   caído**: devuelven `[]` y `{encontrados: 0}` tanto si no hay informes como si
   el portal nunca respondió. La migración lo dejó **igual a propósito** (cambiar
   el retorno cambia lo que ve el índice del ZIP y el Panel), pero ahora la
   conflación está localizada en dos líneas —`return res.valor_o([])`— con el
   `Resultado` a la vista. Corregirlo es una tarea de producto, no de refactor.
4. **Fuera de `scraping/`, sin tocar**: `infraestructura/archivos_atomicos.py`
   (reintento ante `PermissionError` de NTFS — disco, no red),
   `scripts/actualizar_base_mef.py` y `scripts/golden_cui.py` (herramientas de
   línea de comandos; el segundo reintenta el **caso completo**, no una request),
   y la segunda pasada de `orquestador/etapas_reales.py` (reintento de
   orquestación sobre experiencias, minutos después — otra escala).

### Un cambio de comportamiento, declarado

`mef._get` y `seace_abierto._get` hacían `kw.pop("timeout", …)` **dentro** del
bucle: a partir del segundo intento el `timeout` del llamador se perdía y
volvía al valor por defecto. Al migrar, el `pop` ocurre una sola vez y el
timeout pedido rige en todos los intentos. Es la corrección de un defecto
latente; ningún llamador vivo pasa `timeout` a esas dos funciones, así que no
mueve nada observable hoy.

## Consecuencias

- **Un agente nuevo no puede repetir el 6:1 sin saltarse un `TypeError`.** El
  candado dejó de ser una nota en un comentario.
- Cambiar la temporización de una fuente es cambiar una `Politica`, no reescribir
  un bucle.
- Nuevo costo: la operación de red se escribe como closure. A cambio, el manejo
  de errores deja de repetirse 15 veces.
- Los tests de política (intentos, backoff llamado, jitter acotado, vacío ≠
  caído) corren **sin red y sin dormir** — antes eso solo era cierto para
  RENIPRESS, que ya inyectaba `dormir`.

## Verificación

`pytest backend/tests -q` — línea base **870 passed, 25 skipped**; tras la
tarea **902 passed, 25 skipped** (+32 tests nuevos en
`test_errores_red_reintentos.py` y `test_reintentos_por_fuente.py`; **cero tests
existentes modificados** — ese fue el criterio de que la semántica no se movió).
Sin red en pytest (`conftest.bloquear_red_externa`) y sin dormir: las nuevas
pruebas inyectan `dormir`. `cui.py` **intacto** → no aplica golden.
