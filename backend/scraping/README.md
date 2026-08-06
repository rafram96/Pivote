# `backend/scraping/` — las fuentes públicas que verifican lo declarado

Código de **producción** del pivote. Aquí vive todo lo que sale a internet: el
backend contrasta contra fuentes oficiales lo que la skill extrajo de la
propuesta. Nada de esto llama a APIs de IA (regla on-prem, ver
`.ai/architecture/backend.md`).

> Este archivo llegó a ser una copia del README de `src/referencia/` — decía
> «no editar», daba rutas de `Alpamayo-InfoObras` y anunciaba ALT-12 como una
> regla viva. Nada de eso aplica: esta carpeta es código propio y editable, y
> **ADR-008 descartó ALT-12** (firmante ≠ representante legal) por falsos
> positivos sistemáticos.

## Módulos

| Módulo | Fuente | Qué resuelve |
|---|---|---|
| `infoobras.py` | InfoObras (Contraloría) | Ficha de la obra por CUI, datos de ejecución (avances, paralizaciones, supervisor/residente/contratista) y descarga de documentos. Es el **decisor** de identidad de obra. |
| `sunat.py` | e-consultaruc | Ficha del RUC emisor: inscripción (ALT04), condición HABIDO, representantes legales e información histórica (`getRepLeg` / `getinfHis`). |
| `mef.py` | Banco de Inversiones (SSI) | Verificación de **expedientes técnicos** (T-003): Formato 08-A, contratos SEACE del CUI y PDFs de sustento. |
| `seace_abierto.py` | CONOSCE + OCDS del OECE | Bases Integradas y contrato firmado por CUI, con la segmentación por tipo de proceso (T-004). |
| `renipress.py` | RENIPRESS (SUSALUD) | Existencia de establecimientos de salud. Evidencia **auxiliar**: no cambia veredictos. |
| `errores_red.py` | — | Clasifica excepciones en `red` / `portal` / `otro` para que los logs no escupan la excepción cruda. Puro, sin red. |
| `nombres_empresa.py` | — | Prelimpiado compartido de nombres de entidad (fuera el paréntesis con los miembros del consorcio, fuera la cola «RUC …»). Lo consumen el cruce SUNAT, el candado SEACE y la verificación de expedientes del MEF. Puro, sin red y sin dependencias. |

`__init__.py` está vacío a propósito: cada consumidor importa el módulo que
necesita (`from scraping import sunat`), y los tests parchean sobre esa fachada.

## Patrón de la carpeta

- **Parseo puro ↔ fetch**: las funciones que interpretan HTML/JSON no tocan la
  red y se prueban offline con fixtures; solo los `fetch_*` salen a internet.
  `pytest backend/tests` **bloquea la red externa** (fixture de `conftest.py`),
  así que un test que la intente falla en vez de quedar flaky.
- **Vacío ≠ caído**: una búsqueda válida sin resultados y un portal que no
  respondió son cosas distintas, y ningún consumidor debe confundirlas. Cada
  módulo tiene su dialecto para decirlo (excepción / `[]` / `None`); unificarlos
  es deuda registrada (T-REFACTOR-001), no un bug.
- **Reintentos** propios por portal, con la razón acortada por `errores_red`.
- **Cachés** en `PIVOTE_DATA_DIR/referencia/` (CONOSCE, procesos SEACE) para no
  depender en vivo de hosts intermitentes.

## Qué NO vive aquí

- La **resolución de CUI por nombre** es de `resolucion/cui.py` (base MEF,
  público-primero, vetos y candados de abstención — ADR-002…005). En
  `infoobras.py` no debe reconstruirse un resolver por nombre.
- Los **veredictos**: scraping devuelve evidencia; quien juzga es
  `reglas/` + `validacion/`.
