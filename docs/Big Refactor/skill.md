# Big Refactor de la skill

> Estado: propuesta técnica elaborada el 29-jul-2026 sobre `demo`, considerando
> las responsabilidades actuales de `skill/` y las capacidades ya implementadas
> en el backend. Este documento no autoriza una reescritura completa ni cambios
> simultáneos de prompts, contrato y backend.

## Resumen ejecutivo

La skill debe concentrar el uso de tokens en las tareas que realmente necesitan
un modelo:

- leer documentos escaneados;
- extraer hechos fieles al certificado;
- interpretar requisitos de las bases;
- resolver equivalencias semánticas;
- explicar veredictos con sustento literal.

El backend ya puede asumir buena parte del trabajo que hoy repite
`agent-evaluador`: cálculos de fechas, COVID, totales, traslapes, cumplimiento
temporal, validaciones de integridad, núcleo del cargo y verificaciones oficiales.

El refactor recomendado es incremental:

1. Dejar de pedirle al LLM cálculos que el backend ya produce.
2. Reducir el contexto que recibe `agent-evaluador`.
3. Reparar evaluaciones por profesional, no repitiendo el análisis completo.
4. Compactar los prompts que se multiplican por cada profesional.
5. Separar evaluación semántica profesional y evaluación global.
6. Evaluar después si el Excel preliminar sigue siendo necesario.

El objetivo no es reducir tokens sacrificando cobertura. Es reservarlos para la
lectura e interpretación que no puede hacerse de forma determinística.

## Estado actual

La topología vigente es:

```text
agent-bases ───────────────┐
                           ├─► agent-evaluador ─► consolidador
agent-propuesta-mapa ──────┤
          │                │
          └─► N agentes profesionales
```

Las propuestas pueden contener miles de folios. El mapa acota la lectura y cada
agente profesional profundiza únicamente en su bundle. Esta división debe
conservarse: evita mezclar profesionales y permite paralelizar.

El problema está en la etapa posterior. `agent-evaluador` vuelve a recibir las
salidas completas de todos los profesionales y vuelve a calcular información que
el backend recalcula al recibir el espejo.

El costo fijo también creció:

| Archivo | Tamaño aproximado |
|---|---:|
| `skill/SKILL.md` | 5.175 tokens |
| `prompts/agent-propuesta-profesional.md` | 4.774 tokens |
| `prompts/agent-evaluador.md` | 3.986 tokens |
| `prompts/agent-propuesta-mapa.md` | 2.713 tokens |
| `prompts/agent-bases.md` | 1.640 tokens |

La cifra es una estimación por caracteres, no una medición de facturación. Su
utilidad es comparativa: el prompt profesional se paga una vez por cada
profesional. Con 14 profesionales representa alrededor de 67.000 tokens de
instrucción antes de leer sus folios.

## Capacidades nuevas del backend que cambian la frontera

### Recálculo determinístico de Parte 4

`backend/validacion/recalculo.py`, cableado en la etapa VALIDACIÓN, ya deriva:

- días;
- meses;
- años;
- anterioridad a colegiatura;
- intersección con la ventana COVID;
- totales cuando son computables.

`EtapaReglasReal` calcula además:

- paralizaciones;
- traslapes;
- días efectivos;
- años efectivos;
- cumplimiento temporal contra el mínimo exigido.

### Escudo de integridad

`backend/validacion/integridad.py` detecta:

- profesionales sin evaluar;
- veredictos vacíos;
- corrimientos entre profesionales;
- experiencias sin juicio;
- numeraciones ajenas;
- especialidades que parecen pertenecer a otro profesional;
- oferta económica incompleta;
- experiencia del postor sin montos.

El escudo no reemplaza la evaluación semántica. Comprueba que la evaluación
entregada corresponde a los profesionales y experiencias correctos.

### Candado de núcleo del cargo

`backend/validacion/cargo_nucleo.py` ya puede contrastar:

- alternativas de cargos válidos como OR;
- términos del núcleo de cada alternativa como AND;
- cargo literal del certificado;
- funciones textuales como segunda puerta;
- ausencia de evidencia mediante abstención.

### Fuentes oficiales y enriquecimiento

El backend también tiene a su cargo:

- resolución pública-primero del CUI;
- ficha MEF enriquecida en PostgreSQL;
- validación de rubro, ubicación e identidad;
- InfoObras;
- SUNAT e histórico;
- SEACE y documentos de expediente;
- Excel final enriquecido.

La skill no debe reproducir estas verificaciones por navegador ni intentar
resolver códigos ausentes.

## Principios no negociables

- Un falso `CUMPLE` es peor que una revisión adicional.
- El backend on-prem nunca llama APIs cloud de IA.
- La skill transcribe hechos; no inventa datos oficiales.
- El certificado manda sobre el cuadro autodeclarado.
- Ningún ahorro puede omitir profesionales o experiencias.
- Los folios deben verificarse antes del recorte cuando el PDF completo está
  disponible.
- Los cambios de topología se validan sobre propuestas reales representativas.
- No mezclar reducción de tokens con cambios en criterios de negocio.
- Cada fase debe poder compararse contra la salida anterior.

## Diseño objetivo

```text
BASES
  └─► requisitos estructurados

PROPUESTA
  └─► mapa + bundles + postor
         ├─► profesional 1: hechos + juicio semántico acotado
         ├─► profesional 2: hechos + juicio semántico acotado
         └─► profesional N: hechos + juicio semántico acotado

EVALUADOR GLOBAL REDUCIDO
  └─► postor + oferta + factores + resumen

CONSOLIDADOR
  └─► espejo factual y semántico mínimo

BACKEND
  └─► integridad + cálculos + fuentes oficiales + Excel final
```

## Fase 0 — Medición antes de cambiar

Antes de optimizar se necesita una línea base por corrida:

- tokens de entrada y salida de cada tipo de agente;
- páginas o folios leídos;
- cantidad de profesionales;
- cantidad de experiencias;
- reintentos;
- tiempo de ejecución;
- completitud del consolidador;
- observaciones del escudo de integridad;
- diferencias contra el Excel final.

Corpus mínimo:

- propuesta con capa de texto;
- propuesta escaneada;
- concurso con pocos profesionales;
- concurso con 10 o más profesionales;
- certificado multiobra;
- expediente técnico;
- propuesta con factores ISO;
- propuesta con experiencia del postor extensa.

Sin esta medición no se debe atribuir un ahorro a una modificación concreta.

## Fase 1 — Eliminar aritmética del evaluador

### Cambio

Dejar de pedir a `agent-evaluador`:

- `dias`;
- `meses`;
- `anios`;
- `anterior_colegiatura`;
- `incluye_covid`;
- `traslape`;
- totales temporales.

El extractor profesional entrega únicamente las fechas literales. El backend
calcula los campos derivados.

### Campos que permanecen en el evaluador

- `cargo_bases_valido`;
- `tipo_obra_valido`;
- `profesion_valida`;
- `cumple`, con razón literal;
- factores facultativos;
- juicio semántico de la experiencia del postor.

### Requisito previo

El contrato y el consolidador deben aceptar esos campos derivados en `null` sin
considerar incompleta la evaluación. El escudo de integridad ya distingue campos
que solo puede producir el evaluador de campos que el backend sabe rellenar.

### Validación

- Comparar espejos y Excels de al menos tres corridas.
- Los campos backend deben coincidir con los vigentes o ser más conservadores.
- Ningún profesional puede perder su veredicto semántico.
- Las observaciones de integridad no deben aumentar.

### Ahorro esperado

Medio-alto, proporcional al número de experiencias, con riesgo bajo.

## Fase 2 — Proyección compacta para `agent-evaluador`

### Problema

El evaluador recibe bases, mapa y todos los JSON profesionales completos. Muchos
campos no participan en sus decisiones.

### Cambio

Agregar un script determinístico que genere `entrada_evaluador.json`.

Por profesional:

- número y cargo ofertado;
- título o profesión;
- requisito aplicable;
- mínimo exigido.

Por experiencia:

- `n`;
- cargo ocupado;
- funciones textuales;
- proyecto;
- tipo, nivel, área o monto cuando las bases los usen;
- fechas literales;
- observaciones críticas;
- referencia al folio.

Excluir:

- `_backend`;
- datos de transporte;
- páginas de recorte que no participen en el juicio;
- RUC y CUI destinados a fuentes oficiales;
- campos temporales derivados;
- estructuras duplicadas del mapa;
- explicaciones internas del consolidador.

### Regla

La proyección no resume ni reescribe los hechos relevantes. Solo elimina campos
que el evaluador no consulta.

### Validación

Ejecutar el evaluador antiguo y el evaluador con proyección sobre las mismas
salidas de extracción. Comparar:

- veredictos;
- cargo y tipo de obra;
- profesión;
- factores;
- razones literales;
- observaciones críticas.

### Ahorro esperado

Alto en propuestas con muchos profesionales, con riesgo bajo si la proyección
está cubierta por pruebas.

## Fase 3 — Reintento localizado

### Problema

Si el consolidador detecta un profesional faltante o una experiencia sin juicio,
el flujo puede volver a ejecutar todo `agent-evaluador`.

### Cambio

Crear un modo de reparación que reciba:

- requisito del cargo;
- datos de un solo profesional;
- experiencias afectadas;
- error literal del consolidador;
- evaluación previa, si existe.

La salida se fusiona por:

- `n_prof`;
- `n` de experiencia.

No se permite pareo por posición.

### Casos

- profesional sin `cumple`;
- una experiencia sin `cargo_bases_valido`;
- `n` inexistente;
- veredicto que habla de otra especialidad;
- último profesional omitido;
- corrección de un factor global, sin repetir profesionales.

### Validación

- Pruebas del parche determinístico.
- El resultado reparado debe volver a pasar el consolidador completo.
- No se sobrescriben evaluaciones sanas.

### Ahorro esperado

Muy alto en corridas con fallos, porque evita repetir el contexto global.

## Fase 4 — Compactar prompts multiplicativos

### Objetivo principal

Reducir `agent-propuesta-profesional.md`, porque se carga una vez por
profesional.

### Estrategia

Separar:

1. Núcleo obligatorio corto.
2. Contrato de salida compacto.
3. Reglas condicionales por escenario.

Reglas condicionales:

- certificado multiobra;
- gestión de portafolio;
- funciones textuales;
- fecha parcial o ilegible;
- folio distinto de página física;
- duplicado posible.

El orquestador solo adjunta un módulo cuando el mapa detecta ese escenario.

### Trabajo que debe hacer el código

- `_meta`;
- `n_prof`;
- numeración contigua;
- defaults;
- normalización de fechas;
- normalización SÍ/NO;
- aliases conocidos;
- estructura `_backend`;
- validación de tipos.

Estas tareas ya son competencia natural del consolidador y del schema. No deben
explicarse extensamente a cada agente.

### Trabajo que permanece en el prompt

- leer el certificado, no la autodeclaración;
- una fila por periodo;
- transcripción literal;
- no inventar CUI/RUC;
- funciones solo si están escritas;
- páginas físicas correctas;
- cross-check antiomisión;
- abstención ante ilegibilidad.

### Ahorro esperado

Alto y multiplicativo, con riesgo bajo si los prompts compactos se evalúan
contra el corpus.

## Fase 5 — Evaluación semántica distribuida

### Cambio

Cada agente profesional recibe el requisito correspondiente a su cargo y
devuelve dos bloques:

- `hechos`;
- `evaluacion_semantica`.

La evaluación semántica incluye:

- profesión compatible;
- cargo literal o equivalente;
- funciones acreditadas;
- tipo de obra;
- restricciones cualitativas;
- veredicto provisional y razón.

El evaluador global deja de recibir todas las experiencias. Solo procesa:

- experiencia del postor;
- oferta;
- factores;
- coherencia global;
- resumen.

### Ventaja

- Evita el fan-in completo.
- Reduce corrimientos.
- Un fallo afecta a un profesional.
- Los reintentos son pequeños.

### Riesgo

El extractor y evaluador quedan en el mismo agente. Puede contaminar hechos con
juicio o aplicar criterios distintos entre profesionales.

### Mitigación

- Salida separada en `hechos` y `evaluacion_semantica`.
- Requisito exacto del cargo, no todas las bases.
- Checklist común y pequeño.
- Candado de integridad posterior.
- Casos golden por especialidad.

### Ahorro esperado

Muy alto, pero debe implementarse después de las fases conservadoras.

## Fase 6 — Experiencia del postor y oferta económica

`skill/scripts/montos_postor.js` ya rescata de manera determinística montos
contractuales desde los folios acotados.

### Mover a código

- normalización de montos;
- porcentaje atribuible;
- monto que le corresponde;
- suma total;
- comparación contra cuantía mínima;
- cálculo del límite inferior;
- comparación de oferta contra el límite;
- suma de puntajes numéricos.

### Mantener en el LLM

- si el objeto contractual corresponde al tipo solicitado;
- qué consorciado acredita;
- interpretación de excepciones;
- ambigüedad entre monto de obra y monto de consultoría;
- razón literal.

### Regla de abstención

Si existen varios montos contractuales plausibles o solo montos de la obra
supervisada, el script no elige. Entrega candidatos para revisión.

### Ahorro esperado

Medio-alto y mejora simultánea de confiabilidad.

## Fase 7 — Simplificar instrucciones de fuentes oficiales

Las instrucciones para los agentes pueden reducirse a:

> Transcribe literalmente CUI, SNIP, RUC, proyecto, entidad y ubicación cuando
> estén visibles. No busques, resuelvas ni verifiques fuentes oficiales. Lo no
> impreso queda en `null`.

No es necesario explicar repetidamente:

- ranking del resolver;
- base MEF;
- consultas InfoObras;
- estrategia SEACE;
- validaciones SUNAT;
- caminos internos del backend.

Sí se deben conservar como hechos:

- CUI/SNIP citado;
- proyecto verbatim;
- prefijo de expediente técnico;
- entidad contratante;
- ubicación;
- RUC literal;
- subobras y códigos múltiples.

### Ahorro esperado

Bajo-medio, pero prácticamente sin riesgo.

## Fase 8 — Folios y OCR

Esta responsabilidad no debe trasladarse al backend.

El corpus actual contiene certificados mayoritariamente escaneados. Después del
recorte, el backend no dispone de suficiente contexto para detectar de forma
general que se recortó el folio vecino.

La skill debe conservar:

- folio impreso;
- página física;
- `paginas_pdf`;
- emisor visible;
- relación entre certificado y experiencia;
- detección de corrimientos antes de recortar;
- relectura focalizada ante datos críticos.

### Optimización permitida

- Centralizar la explicación “folio no siempre es página”.
- Reusar un índice OCR local.
- Pasar a cada agente únicamente sus páginas.
- Renderizar de nuevo solo páginas críticas.
- No adjuntar texto OCR de folios fuera del bundle.

## Fase 9 — Excel preliminar

El backend ya regenera el Excel autoritativo con:

- cálculos determinísticos;
- abstenciones;
- discrepancias;
- CUI/MEF/InfoObras;
- SUNAT;
- SEACE;
- documentos;
- trazabilidad Claude/backend.

Debe evaluarse un contrato futuro:

```text
skill → espejo + certificados
backend → único Excel final
```

### Condición

No eliminar el Excel preliminar mientras:

- el endpoint lo exija;
- exista un flujo offline que dependa de él;
- el backend pueda estar apagado y el usuario necesite un entregable;
- no se haya migrado panel, MCP y plugin como paquete.

El ahorro directo de tokens es menor que en las fases anteriores. La ganancia
principal es reducir complejidad y evitar dos generadores con responsabilidades
solapadas.

## Qué no debe migrar al backend

Mientras se mantenga la prohibición de IA cloud, deben permanecer en la skill:

- OCR visual y lectura de escaneos;
- detección de profesionales y bundles;
- extracción literal de certificados;
- interpretación de tachados en PDF;
- equivalencias semánticas de cargos;
- clasificación cualitativa de tipo de obra;
- interpretación de funciones;
- factores facultativos narrativos;
- selección de evidencia acreditante;
- razones literales con folios.

## Priorización

| Prioridad | Cambio | Ahorro | Riesgo |
|---|---|---:|---:|
| P0 | Medir tokens por agente y corrida | habilitador | bajo |
| P0 | Quitar aritmética de Parte 4 del evaluador | alto | bajo |
| P0 | Proyección compacta para el evaluador | alto | bajo |
| P1 | Reintento localizado por profesional | muy alto en fallos | bajo-medio |
| P1 | Compactar prompt profesional | alto × N | bajo |
| P1 | Automatizar cálculos del postor y oferta | medio-alto | bajo-medio |
| P2 | Evaluación semántica distribuida | muy alto | medio |
| P2 | Simplificar instrucciones de fuentes | bajo-medio | bajo |
| P3 | Eliminar Excel preliminar | bajo en tokens | medio |

## Criterios de aceptación globales

Una fase solo se considera exitosa si:

- reduce tokens medidos, no solo el tamaño aparente del prompt;
- no omite profesionales;
- no omite experiencias;
- no aumenta falsos `CUMPLE`;
- conserva razones literales y folios;
- pasa schema y consolidador;
- no genera nuevos hallazgos críticos de integridad;
- mantiene o mejora los resultados del backend;
- permite abstención explícita;
- puede revertirse sin migración destructiva.

## Secuencia recomendada de implementación

```text
medición
  ↓
eliminar cálculos duplicados
  ↓
proyección compacta
  ↓
reintentos localizados
  ↓
compactación de prompts
  ↓
cálculos postor/oferta
  ↓
evaluación distribuida
  ↓
revisión del Excel preliminar
```

Las cuatro primeras fases ofrecen la mejor relación ahorro/riesgo. La evaluación
distribuida debe abordarse cuando ya exista telemetría suficiente para comparar
calidad, costo y fallos contra el evaluador monolítico.
