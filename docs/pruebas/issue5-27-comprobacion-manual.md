# Issues #27 y #5 — comprobar con tus propios ojos

> **#27** — buscar un CUI en la base local del MEF por HTTP y por consola.
> **#5** — las tres tools del MCP (`buscar_cui`, `descargar_documentos_cui`,
> `consultar_descarga_cui`) y la descarga por CUI como trabajo asíncrono.
>
> Todo se corre desde la raíz del repo (`Pivote/`). Los pasos **(a)** y **(b)**
> no tocan internet: leen la base local del MEF que ya está en
> `backend/datos_pivote/referencia/mef/`. El paso **(c)** sí sale a InfoObras
> —es su razón de existir— y por eso conviene correrlo en el server.

## Lo que ya existía y lo que se construyó

| | Antes de esta tanda | Ahora |
|---|---|---|
| Base MEF (579.481 CUIs) | Sólo la usaba el resolver de CUI por dentro. Nadie más podía preguntarle nada. | `GET /api/pivote/mef/buscar` + `python -m scripts.buscar_mef`, sobre **un** núcleo compartido (`resolucion/busqueda_mef.py`). |
| Descarga por CUI | **Ya era un trabajo asíncrono** con estado en disco (`POST` 201 + `descarga_id`, `GET` estado, `GET` zip): eso no había que inventarlo. Lo que faltaba: mientras corría no decía nada — `estado: en_progreso` y a esperar. | Cada tramo se persiste apenas empieza (`paso`), y el error dice el motivo en castellano. |
| Tools del MCP | Cuatro: `probar_conexion`, `listar_concursos`, `subir_analisis`, `consultar_estado`. **`buscar_cui` y `consultar_descarga_cui` NO existían** (ni como stub). | Tres tools nuevas, que contestan en castellano de evaluador (`textos.js`), no en JSON. |

---

## (a) El buscador de CUIs — #27

### Por consola

```
cd backend
../venv/Scripts/python -m scripts.buscar_mef "hospital abancay" --limite 3
```

**Lo que debes ver** (base del 2026-07-26; los nombres son literales del MEF,
con sus erratas incluidas — «GUILLEREMO», «ESTERILIZACIN»):

```
Búsqueda: "hospital abancay"   (base del MEF actualizada hace 10 día(s))
==============================================================================
 1. CUI 2029145  ·  coincidencia 100%
    CONSTRUCCION DE INFRAESTRUCTURA DEL SERVICIO DE EMERGENCIA DEL HOSPITAL
    GUILLERMO DIAZ DE LA VEGA DE ABANCAY
    - TODOS -, ABANCAY, APURIMAC  ·  MINISTERIO DE SALUD  ·  VIABLE
 2. CUI 2039502  ·  coincidencia 100%
    EQUIPAMIENTO DE LA UNIDAD DE CUIDADOS INTENSIVOS DEL SERVICIO DE
    NEONATOLOGIA DEL  HOSPITAL GUILLERMO DIAZ DE LA VEGA DE ABANCAY
    - TODOS -, - TODOS -, APURIMAC  ·  GOBIERNO REGIONAL APURIMAC  ·  VIABLE
 3. CUI 2042064  ·  coincidencia 100%
    MEJORAMIENTO INTEGRAL DE LA CAPACIDAD DE RESPUESTA DE LOS SERVICIOS
    GENERALES ... DEL HOSPITAL GUILLEREMO DIAZ DE LA VEGA DE ABANCAY
    - TODOS -, ABANCAY, APURIMAC  ·  GOBIERNO REGIONAL APURIMAC  ·  VIABLE
==============================================================================
3 resultado(s) por nombre  ·  ~90000 ms en responder (la primera consulta de
cada corrida incluye la carga del índice).
```

> El CLI tarda ~1,5 min **cada vez**: carga el índice de medio millón de filas
> en un proceso que después muere. El endpoint lo paga **una sola vez** por
> arranque del backend. Es la diferencia esperada, no un problema del CLI.

Otras formas que vale la pena probar:

```
../venv/Scripts/python -m scripts.buscar_mef 2029145            # por código exacto
../venv/Scripts/python -m scripts.buscar_mef "hospital" --dpto apurimac --limite 5
../venv/Scripts/python -m scripts.buscar_mef "puesto de salud"  # texto genérico
```

El último no devuelve una lista vacía muda: dice **por qué** («todas sus
palabras aparecen en decenas de miles de inversiones») y qué hacer.

### Por HTTP

Levanta el backend (una sola vez; queda caliente):

```
cd backend
PIVOTE_ETAPAS=esqueleto ../venv/Scripts/python -m uvicorn api.app:app --port 8001
```

```
curl -s "http://127.0.0.1:8001/api/pivote/mef/buscar?q=hospital+abancay&dpto=apurimac&limite=2"
```

**Lo que debes ver** (recortado):

```json
{"q":"hospital abancay","filtros":{"dpto":"apurimac"},"limite":2,
 "coincidencia":"nombre","base_mef_no_disponible":false,"aviso":null,
 "edad_dias":10,"ms":249.2,"total":2,
 "resultados":[{"cui":"2029145","snip":"17387",
   "nombre":"CONSTRUCCION DE INFRAESTRUCTURA DEL SERVICIO DE EMERGENCIA DEL
             HOSPITAL GUILLERMO DIAZ DE LA VEGA DE ABANCAY",
   "dpto":"APURIMAC","prov":"ABANCAY","dist":"- TODOS -","ubigeo":"030100",
   "ubicacion":"- TODOS -, ABANCAY, APURIMAC","entidad":"MINISTERIO DE SALUD",
   "estado":"CERRADA","situacion":"VIABLE","score":100.0}, …]}
```

Los cuatro controles que valen por todos:

1. **`ms`**: la **primera** consulta del backend recién arrancado sale en
   ~66.000 ms (incluye la carga del índice) y **todas las siguientes** en 250 ms
   con nombre amplio, 12 ms por código. La issue prometía <200 ms; se cumple
   para códigos y consultas acotadas, no para un nombre genérico que une decenas
   de miles de candidatos, y ahora el número está en la respuesta para que no
   haya que creerle a nadie.
2. **Un código gana**: `?q=2029145` responde `"coincidencia":"codigo"` y una
   sola ficha.
3. **Los filtros no mienten**: `?q=2029145&dpto=lima` responde `total: 0`. Ese
   CUI no está en Lima; devolverlo igual sería el error.
4. **Lo inválido es 400, la base ausente NO**: `?q=h` → `400 {"detail":"q debe
   tener entre 2 y 200 caracteres"}`; en cambio, un equipo **sin** la base
   instalada responde `200` con `base_mef_no_disponible: true` y un aviso —
   nunca un 500 ni un traceback.

---

## (b) Las tools del MCP desde Claude Code — #5

### Configurar el puente

1. Backend arriba (el mismo comando de arriba, puerto 8001).
2. `cd mcp-server && npm install` (una sola vez).
3. En la configuración del MCP de Claude Code, el servidor
   `infoobras-onprem-bridge` apuntando a este repo con
   `SERVER_URL=http://127.0.0.1:8001` (ver `mcp-server/cowork-config-ejemplo.json`;
   ojo: **127.0.0.1**, no `localhost`).
4. Reinicia Claude Code y comprueba con la tool `probar_conexion`.

### `buscar_cui`

Pídeselo en castellano: **«búscame el CUI del hospital de Abancay»**.

**Lo que debes ver en el chat** (verificado contra el backend local):

```
Encontré 3 inversión(es) para «hospital abancay»:

1. CUI 2029145  (parecido 100%)
   CONSTRUCCION DE INFRAESTRUCTURA DEL SERVICIO DE EMERGENCIA DEL HOSPITAL
   GUILLERMO DIAZ DE LA VEGA DE ABANCAY
   - TODOS -, ABANCAY, APURIMAC  ·  MINISTERIO DE SALUD  ·  VIABLE
2. …

Si alguna es la obra que buscas, pide sus documentos con
descargar_documentos_cui y su CUI.
```

Con un código exacto (**«confírmame qué obra es el CUI 2029145»**) cambia el
encabezado y **desaparece el «parecido»** — sobre un código no hay parecido que
discutir:

```
El código 2029145 corresponde a esta inversión:

1. CUI 2029145
   CONSTRUCCION DE INFRAESTRUCTURA DEL SERVICIO DE EMERGENCIA DEL HOSPITAL …
   - TODOS -, ABANCAY, APURIMAC  ·  MINISTERIO DE SALUD  ·  VIABLE

Para bajar sus documentos: descargar_documentos_cui con ese CUI.
```

### `descargar_documentos_cui` y `consultar_descarga_cui`

**«bájame los documentos del CUI 2029145»**:

```
Empecé a bajar los documentos de la obra del CUI 2029145 desde InfoObras.

Número de seguimiento: 9f3c1a77b204
Ahora mismo: En cola: esperando turno para consultar InfoObras.

Puede tardar varios minutos (una obra grande trae cientos de archivos).
Consulta cómo va con consultar_descarga_cui y ese número.
```

La respuesta llega **al instante**: el trabajo sigue en el servidor. Después,
**«cómo va la descarga 9f3c1a77b204»**:

```
Descarga 9f3c1a77b204 · CUI 2029145
HOSPITAL …  ·  obra 111

En curso. Descargando los informes de control de la Contraloría.

Vuelve a consultar en un momento con el mismo número de seguimiento.
```

y al terminar:

```
Descarga 9f3c1a77b204 · CUI 2029145
HOSPITAL …  ·  obra 111

Listo: 42 documento(s) descargados, 1 que la fuente no entregó.

Los archivos NO se pueden mandar por el chat. Descarga el ZIP desde:
http://127.0.0.1:8001/api/pivote/descargar-cui/9f3c1a77b204/zip
```

**El control que vale por todos**: en ningún momento el chat intenta traerte los
PDFs. El modelo es la tubería, no el camión: lo que viaja es la **dirección** del
ZIP. (Y si pides un número de seguimiento que no existe: «No encuentro esa
descarga. Revisa el número de seguimiento que te di al iniciarla.»)

---

## (c) El flujo completo, sin Claude de por medio

Con el backend arriba, tres comandos. **Este paso sí toca InfoObras**, así que
córrelo en el server; el CUI de ejemplo es real.

```bash
# 1 · buscar
curl -s "http://127.0.0.1:8001/api/pivote/mef/buscar?q=hospital+abancay&limite=3"

# 2 · pedir los documentos de uno de los CUIs → responde AL INSTANTE
curl -s -X POST http://127.0.0.1:8001/api/pivote/descargar-cui \
     -H "Content-Type: application/json" \
     -d '{"cui":"2029145","fecha_inicio":"2019-01-01","fecha_fin":"2021-12-31"}'
# {"descarga_id":"9f3c1a77b204","estado":"en_progreso",
#  "paso":"En cola: esperando turno para consultar InfoObras."}

# 3 · seguir el avance (repetir cada 10-20 s)
curl -s http://127.0.0.1:8001/api/pivote/descargar-cui/9f3c1a77b204
# {"estado":"en_progreso","paso":"Descargando los informes de control de la
#   Contraloría.","descargados":0,"listo":false,"actualizado_en":"…"}
# …
# {"estado":"listas","paso":"Listo: 42 documento(s) en el ZIP.","listo":true,
#  "obra_id":111,"descargados":42,"fallidos":1,"secciones":{…},"avisos":[…]}

# 4 · bajar el ZIP (202 mientras prepara; 200 + application/zip cuando está)
curl -s -o obra.zip -D - http://127.0.0.1:8001/api/pivote/descargar-cui/9f3c1a77b204/zip
```

Qué mirar:

- El **paso 2 vuelve en milisegundos** aunque la obra pese cientos de MB. Ésa es
  la lección del `ECONNRESET`: nunca un request que dura minutos.
- El **`paso` cambia** entre consultas (`En cola` → `Buscando la obra` →
  `Descargando las valorizaciones…` → `informes de control` → `datos de cierre`
  → `Ordenando los documentos` → `Armando el ZIP` → `Listo: N documento(s)`).
  Está en **disco**: si reinicias el backend a mitad, el estado sigue ahí.
- Con un CUI inexistente (`{"cui":"9999999"}`) el estado queda en `error` con
  `paso: "Ese CUI no corresponde a ninguna obra publicada en InfoObras."`, y el
  `/zip` devuelve **409**, no un ZIP vacío.

---

## Las pruebas automáticas que respaldan esto

```
cd backend && ../venv/Scripts/python -m pytest -q      # 949 passed, 25 skipped
cd mcp-server && npm test                              # 22 tests, 0 fail
```

Ninguna toca la red: la base MEF de los tests es un fixture de 24 filas y las
descargas de InfoObras van monkeypatcheadas.
