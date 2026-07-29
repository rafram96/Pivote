# RENIPRESS — contrato de integración

## Alcance del primer corte

El cliente RENIPRESS consulta el buscador público de SUSALUD por nombre, razón
social, código único o RUC. Es una fuente auxiliar de existencia para
establecimientos de salud; este corte no decide por sí solo si una experiencia
profesional cumple.

Código reusable:

- `backend/scraping/renipress.py`
- `GET /api/pivote/renipress`
- `tools/renipress.py` (diagnóstico manual)

## Endpoint

```http
GET /api/pivote/renipress?q=00008215&solo_activos=true&limite=50
```

Parámetros:

- `q`: entre 2 y 120 caracteres.
- `solo_activos`: `true` por defecto.
- `limite`: entre 1 y 500; predeterminado 50.

Estados del cuerpo:

- `encontrado`: la fuente respondió y devolvió una o más filas.
- `sin_resultados`: la fuente respondió correctamente, sin filas.
- `portal_no_disponible`: no fue posible obtener una respuesta confiable.

Los dos primeros usan HTTP 200. `portal_no_disponible` usa HTTP 503. Esta
distinción es parte del contrato: una caída jamás prueba que el
establecimiento no exista.

`ambiguo=false` significa que existe exactamente una coincidencia exacta para
el término consultado. Una búsqueda textual por substring normalmente será
ambigua y requiere política adicional antes de conectarse al motor.

## Configuración

Todas las variables son opcionales:

| Variable | Predeterminado | Uso |
|---|---:|---|
| `PIVOTE_RENIPRESS_URL` | portal público SUSALUD | Base URL, útil para pruebas o proxy |
| `PIVOTE_RENIPRESS_REINTENTOS` | `3` | Intentos por consulta |
| `PIVOTE_RENIPRESS_TIMEOUT` | `40` | Timeout HTTP en segundos |

## Validación

Pruebas offline:

```powershell
python -m pytest backend/tests/test_renipress.py backend/tests/test_api.py -q
```

Prueba viva explícita:

```powershell
python tools/renipress.py 00008215 --json
```

La prueba viva depende de SUSALUD y no forma parte de la suite offline.
