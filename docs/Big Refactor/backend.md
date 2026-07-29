# Big Refactor del backend

> Estado: propuesta técnica reconstruida el 29-jul-2026 a partir del análisis
> realizado sobre `demo`. Este documento no autoriza una reescritura masiva.
> Antes de implementar cada hallazgo se debe reproducir el comportamiento sobre
> el commit vigente y agregar una prueba que falle por la causa descrita.

## Resumen ejecutivo

El backend no carece de arquitectura. La división existente por `api/`,
`orquestador/`, `resolucion/`, `scraping/`, `validacion/` y `entregables/`
expresa capas útiles y debe conservarse.

El problema es el crecimiento por acumulación dentro de algunos archivos. Varias
piezas que comenzaron como módulos terminaron conteniendo subsistemas completos:

| Archivo | Responsabilidades acumuladas |
|---|---|
| `backend/resolucion/cui.py` | búsqueda, fusión MEF, ranking, vetos, compuertas, deduplicación y decisión |
| `backend/scraping/infoobras.py` | transporte HTTP, reintentos, parsing y reglas del portal |
| `backend/entregables/excel_final.py` | composición del libro, reglas de presentación, estilos e imágenes |
| `backend/orquestador/etapas_reales.py` | múltiples casos de uso e integraciones externas |
| `backend/api/app.py` | bootstrap, configuración, rutas, concurrencia, archivos y coordinación |

El refactor recomendado es incremental:

1. Proteger primero los fallos silenciosos con pruebas.
2. Extraer casos de uso sin cambiar contratos.
3. Separar infraestructura de lógica de negocio.
4. Mantener adaptadores de compatibilidad durante cada migración.
5. Medir comportamiento antes y después.

Una reescritura completa aumentaría el riesgo de perder reglas de abstención,
compatibilidad con jobs históricos y detalles operativos que hoy solo están
expresados en código y pruebas.

## Principios no negociables

- Un falso `CUMPLE` es peor que una revisión adicional.
- El backend on-prem nunca llama APIs cloud de IA.
- Los archivos siguen siendo la fuente operativa de los binarios.
- Los datos del cliente nunca entran al repositorio.
- Los cambios del resolver requieren pruebas dirigidas y golden cuando exista el
  instrumento correspondiente.
- Cada extracción debe conservar el contrato público del módulo original hasta
  que todos sus consumidores hayan migrado.
- No mezclar refactor estructural con recalibración de reglas de negocio.

## Riesgos funcionales prioritarios

Los siguientes puntos proceden del análisis original. Deben tratarse como
hipótesis verificables, no como licencia para modificar código sin reproducción.

### P0 — Descarga de Excel potencialmente degradada

**Zona:** `backend/api/app.py`.

Si `final.xlsx` no existe, la ruta de descarga puede regenerarlo directamente
desde el espejo y los certificados sin reconstruir todo el enriquecimiento del
pipeline. El archivo resultante puede parecer válido aunque no incorpore
resoluciones, paralizaciones, conciliación temporal o revisiones.

**Riesgo:** entregar un Excel formalmente correcto pero semánticamente incompleto.

**Dirección recomendada:**

- Responder `409 Entregable todavía no disponible` si la etapa Excel no terminó.
- Convertir la regeneración en un caso de uso explícito.
- Exigir que ese caso de uso cargue el contexto enriquecido completo.
- Registrar en el job la versión y procedencia del entregable.

**Prueba requerida:** un job sin `final.xlsx`, pero con cálculos enriquecidos,
jamás debe producir por la ruta de descarga un libro que use valores brutos.

### P0 — Descargas parciales marcadas como completas

**Zonas:** `backend/orquestador/etapas_reales.py` y `backend/api/app.py`.

Algunas descargas complementarias pueden absorber errores y aun así terminar con
un marcador `.ok`. Después, el ZIP puede publicarse con
`descargas_estado = "listas"` aunque falten documentos esperados.

**Riesgo:** “listas” termina significando “el flujo principal no lanzó una
excepción”, no “el conjunto esperado fue evaluado completamente”.

**Dirección recomendada:** reemplazar el marcador binario por un manifiesto:

```json
{
  "obra": "CUI o clave",
  "documentos": [
    {"tipo": "contrato", "estado": "descargado"},
    {"tipo": "bases", "estado": "no_disponible", "detalle": "HTTP 403"},
    {"tipo": "cierre", "estado": "no_aplica"}
  ]
}
```

Estados mínimos:

- `descargado`
- `no_aplica`
- `no_disponible`
- `error`

El estado global solo debe ser `listas` cuando no existan errores pendientes y
cada documento esperado tenga una clasificación explícita.

### P0 — Revisión humana consumida antes de completar la reejecución

**Zona:** `backend/orquestador/motor.py`.

La decisión humana puede marcar el ítem como resuelto antes de terminar las
etapas que recalculan el job. Si una etapa posterior falla, la revisión queda
consumida aunque el nuevo resultado no haya sido publicado correctamente.

**Riesgo:** pérdida lógica de una decisión humana y job inconsistente.

**Dirección recomendada:**

1. Guardar la propuesta humana con estado `pendiente_aplicacion`.
2. Reejecutar sobre una copia o versión nueva del contexto.
3. Publicar resultado, checkpoint e ítem resuelto en una sola transición lógica.
4. Si falla, conservar la revisión pendiente y registrar el error del intento.

PostgreSQL puede ofrecer una transacción para sus registros, pero los archivos
también necesitan publicación atómica mediante temporales y `os.replace`.

### P1 — ZIP de certificados inválido aceptado silenciosamente

**Zona:** `backend/api/app.py`.

Un `BadZipFile` no debe transformarse en una colección vacía de certificados.

**Dirección recomendada:**

- Responder `422` con un mensaje explícito.
- Validar que un ZIP no vacío contenga al menos un PDF aceptable.
- No crear ni programar el job hasta validar todos los insumos.

### P1 — Jobs huérfanos durante una subida fallida

**Zona:** ingesta en `backend/api/app.py`.

Si el job se crea antes de terminar la lectura y validación de Excel,
certificados y demás entradas, un fallo intermedio puede dejar un job en
`RECIBIDO` sin pipeline programado.

**Dirección recomendada:**

1. Recibir en un directorio temporal acotado.
2. Validar tamaño, formato, ZIP y archivos mínimos.
3. Construir el descriptor inicial.
4. Publicar atómicamente el directorio del job.
5. Recién entonces persistir y programar el pipeline.

### P1 — Identificadores inestables de alertas

**Zona:** proyección de alertas en `backend/api/app.py`.

IDs como `al-0`, `al-1` dependen del orden de la lista. Una reejecución que
inserte o reordene alertas puede asociar una decisión anterior con otro problema.

**Dirección recomendada:** usar una identidad estable derivada de:

```text
codigo + referencia + origen + huella_del_mensaje_normalizado
```

Si una alerta tiene ciclo de vida propio, persistir un UUID desde su creación.
La huella debe ser un mecanismo de identidad, no una autorización automática
para migrar decisiones entre mensajes semánticamente distintos.

### P1 — Borrado concurrente con trabajos activos

**Zona:** rutas de eliminación y coordinación del pipeline.

Un endpoint puede borrar archivos mientras un hilo continúa procesando o
descargando. El trabajador puede recrear artefactos después del borrado o guardar
una versión tardía del job.

**Dirección recomendada:**

- Responder `409` al intentar borrar un job activo; o
- implementar cancelación cooperativa;
- usar un coordinador único por job para pipeline, revisión, descargas y borrado;
- verificar la versión del job antes de publicar resultados.

### P1 — Locks válidos solamente dentro de un proceso

**Zona:** locks y semáforos globales de `backend/api/app.py`.

Los locks en memoria protegen un único proceso. Con dos workers de Uvicorn o dos
instancias dejan de coordinar read-modify-write, regeneración, revisión,
descargas y borrado.

**Mitigación inmediata:** documentar y comprobar al arrancar que producción usa
un solo worker mientras exista esta implementación.

**Dirección posterior:** locks de archivo, advisory locks de PostgreSQL o una
cola con ownership y versión por job. La elección depende de si se mantendrá una
sola instancia on-prem o se permitirá escalar horizontalmente.

### P2 — Un JSON corrupto puede inutilizar listados completos

**Zona:** `backend/orquestador/repositorio.py`.

Una comprensión que carga y valida todos los jobs puede abortar el listado por
un único archivo corrupto.

**Dirección recomendada:**

- Aislar errores por archivo.
- Registrar la ruta y la excepción.
- Exponer el elemento como `corrupto` cuando se pueda identificar.
- Permitir listar y recuperar los demás jobs.
- Añadir una herramienta de diagnóstico/reparación, nunca reparación silenciosa.

### P2 — Configuración inválida cae al valor por defecto

**Zona:** helpers de entorno como `_int_env` en `backend/api/app.py`.

Ocultar un valor mal escrito cambia el comportamiento operativo sin señal
visible.

**Dirección recomendada:**

- Modelo tipado de configuración al iniciar.
- Error fatal para valores definidos pero inválidos.
- Defaults solamente cuando la variable está ausente.
- Endpoint de salud que exponga valores operativos no sensibles.

## Arquitectura objetivo

La estructura propuesta conserva las capas existentes y crea límites internos.

```text
backend/
  api/
    app.py
    dependencies.py
    responses.py
    routers/
      concursos.py
      jobs.py
      revisiones.py
      entregables.py
      salud.py

  aplicacion/
    analizar_propuesta.py
    resolver_revision.py
    gestionar_descargas.py
    regenerar_entregable.py
    eliminar_analisis.py
    recuperar_jobs.py

  dominio/
    jobs/
      estados.py
      transiciones.py
    resolucion/
      modelos.py
      decisiones.py

  infraestructura/
    archivos/
      repositorio.py
      almacenamiento_insumos.py
      escritura_atomica.py
    postgres/
      repositorio.py
    concurrencia/
      coordinador_jobs.py

  orquestador/
    motor.py
    contexto.py
    etapas/
      ingesta.py
      validacion.py
      infoobras.py
      resolucion_cui.py
      sunat.py
      reglas.py
      descargas.py
      entregables.py
```

### Responsabilidad de `api/app.py`

Debe limitarse a:

- construir la aplicación;
- instalar lifespan;
- registrar routers;
- ensamblar dependencias.

No debe contener reglas de negocio, lectura detallada de ZIP, coordinación de
threads ni regeneración de entregables.

### Casos de uso en `aplicacion/`

Representan acciones completas solicitadas por la API:

- iniciar análisis;
- aplicar revisión;
- administrar descargas;
- regenerar un entregable;
- eliminar un análisis;
- recuperar trabajos tras reinicio.

Un caso de uso puede coordinar dominio e infraestructura, pero no debe depender
de FastAPI.

### Infraestructura

Implementa detalles sustituibles:

- archivos y publicación atómica;
- persistencia PostgreSQL;
- locking;
- clientes externos;
- reloj e identificadores.

Las interfaces deben extraerse desde los consumidores reales, evitando crear
repositorios genéricos anticipadamente.

## Descomposición del resolver de CUI

`cui.py` contiene reglas muy sensibles y no debe dividirse mediante un movimiento
masivo. La separación sugerida es por fases estables:

```text
resolucion/cui/
  __init__.py          # fachada compatible: resolver, resolver_obras
  texto.py             # normalización y tokens
  rubro.py             # clasificación y contradicciones positivas
  ubicacion.py         # departamento, provincia, distrito
  candidatos.py        # recolección InfoObras + MEF
  scoring.py           # señales y ranking
  compuertas.py        # abstención, vetos y decisión final
  citado.py            # Paso 0 y recuperación tras CUI descartado
  multiobra.py         # sub-obras y deduplicación
  modelos.py           # tipos internos
```

Orden recomendado:

1. Extraer helpers puros con pruebas existentes intactas.
2. Mantener una fachada `resolucion.cui` compatible.
3. Extraer Paso 0 y sus pruebas.
4. Extraer ranking sin cambiar pesos.
5. Extraer compuertas sin cambiar el orden de evaluación.
6. Ejecutar suite y golden en cada paso.

Nunca mezclar en el mismo commit “mover código” y “cambiar umbrales”.

## Descomposición de InfoObras

Objetivo:

```text
scraping/infoobras/
  cliente.py           # sesión HTTP, retry, timeout, rate limiting
  endpoints.py         # construcción de requests
  parsing.py           # respuestas remotas → modelos internos
  modelos.py
  servicio.py          # buscar, por_codigo, documentos
```

Beneficios:

- probar parsing con fixtures sin red;
- probar retry sin reglas de negocio;
- distinguir “sin resultado” de “portal no respondió”;
- reutilizar el cliente en búsquedas y descargas;
- centralizar métricas y trazas.

## Descomposición de `etapas_reales.py`

Cada etapa ya es una unidad conceptual. Primero se deben mover clases completas
sin alterar sus firmas:

```text
orquestador/etapas/
  ingesta.py
  validacion.py
  infoobras.py
  resolucion_cui.py
  sunat.py
  reglas.py
  descargas.py
  excel.py
```

`etapas_reales.py` puede mantenerse temporalmente como módulo de reexportación
para no romper imports, tests ni scripts.

Después de la extracción se podrá observar qué lógica es realmente compartida y
llevarla a servicios. No crear una clase base compleja antes de medir esa
duplicación.

## Descomposición de `excel_final.py`

Objetivo:

```text
entregables/excel/
  generador.py
  estructura.py
  estilos.py
  imagenes.py
  hojas/
    resumen.py
    postor.py
    profesional.py
    alertas.py
```

Separar:

- qué datos se muestran;
- cómo se componen las hojas;
- cómo se estilizan;
- cómo se insertan imágenes o recortes.

Las reglas de cumplimiento y cálculo no deben vivir en estilos ni celdas.

## Modelo de consistencia de jobs

El refactor debe formalizar una máquina de estados. Ejemplo inicial:

```text
RECIBIENDO
  → RECIBIDO
  → PROCESANDO
  → REVISION_REQUERIDA
  → REPROCESANDO
  → COMPLETADO

cualquier estado operativo → ERROR
COMPLETADO / ERROR          → ELIMINANDO → ELIMINADO
```

Cada transición debe definir:

- precondiciones;
- versión esperada;
- artefactos que publica;
- si es reintentable;
- estado tras una interrupción;
- quién posee el job durante la operación.

No basta con agregar más locks: primero hay que definir qué transición se
protege.

## Observabilidad requerida

Antes de mover piezas se necesitan señales que permitan comparar:

- duración por etapa;
- número y tipo de documentos esperados/obtenidos;
- reintentos por portal;
- versión del job antes y después de una revisión;
- origen de cada Excel;
- cantidad de candidatos y motivo de abstención del resolver;
- fallos de parsing aislados;
- carga activa del ETL MEF.

Los logs deben usar IDs de job/obra estables y nunca incluir documentos o datos
sensibles completos.

## Plan de ejecución

### Fase 0 — Instrumentación y reproducción

- Revalidar cada riesgo P0/P1 sobre `demo`.
- Crear una prueba fallida por riesgo confirmado.
- Registrar comportamiento actual y contrato esperado.
- No mover archivos todavía.

### Fase 1 — Correcciones de seguridad

Orden sugerido:

1. Rechazar ZIP inválido.
2. Evitar jobs huérfanos en ingesta.
3. Prohibir Excel degradado.
4. Transacción lógica de revisión humana.
5. Manifiesto de descargas.
6. Protección frente a borrado concurrente.

Cada corrección debe ser pequeña y desplegable independientemente.

### Fase 2 — Composición de la API

- Introducir configuración tipada.
- Extraer routers sin cambiar URLs.
- Extraer dependencias y casos de uso.
- Mantener `app.py` como raíz de composición.

### Fase 3 — Etapas del orquestador

- Mover una etapa por commit.
- Mantener reexportaciones temporales.
- Eliminar imports circulares antes de introducir nuevas abstracciones.

### Fase 4 — Resolver

- Solo con corpus/golden disponible.
- Primero movimientos mecánicos.
- Después, en commits separados, cambios funcionales.
- Comparar matriz de transiciones, no únicamente cantidad total de aciertos.

### Fase 5 — Integraciones y entregables

- Separar InfoObras.
- Separar Excel.
- Formalizar manifiesto documental.
- Integrar SEACE/UNOPS/RENIPRESS detrás de interfaces de evidencia, sin convertir
  ausencia de datos en una conclusión negativa.

## Estrategia de commits

Ejemplos:

```text
test(api): reproduce excel degradado cuando falta entregable
fix(api): rechaza descarga hasta completar etapa excel

refactor(api): extrae router de entregables sin cambiar contrato
refactor(orquestador): mueve etapa sunat a modulo propio

test(resolver): congela comportamiento del paso citado
refactor(resolver): extrae paso cero sin cambiar decisiones
```

Cada commit de refactor debe cumplir:

- diff revisable;
- sin recalibración oculta;
- suite verde;
- compatibilidad temporal documentada;
- posibilidad razonable de revertirlo de forma aislada.

## Criterios de finalización

El Big Refactor no termina porque los archivos sean más pequeños. Termina cuando:

- las rutas HTTP solo traducen transporte;
- los casos de uso coordinan operaciones completas;
- dominio e infraestructura no dependen de FastAPI;
- las transiciones de jobs son explícitas;
- ninguna descarga parcial se presenta como completa;
- una revisión humana no puede consumirse a medias;
- un archivo corrupto no inutiliza los demás;
- el resolver conserva o mejora sus garantías de abstención;
- los entregables registran la procedencia de sus datos;
- cada integración externa distingue ausencia, no aplicación y fallo.

## Pendientes de revalidación

Debido a que la sesión original fue cerrada accidentalmente antes de preservar su
transcripción completa, antes de convertir este documento en épica se debe:

- actualizar números de línea;
- confirmar el flujo exacto de regeneración de Excel;
- confirmar dónde se escribe cada marcador `.ok`;
- reproducir el consumo anticipado de revisión;
- verificar el tratamiento vigente de `BadZipFile`;
- medir el comportamiento con más de un worker;
- revisar si commits posteriores ya corrigieron alguno de estos puntos.

La fuente de verdad final será el código y las pruebas de `demo`, no este
documento.
