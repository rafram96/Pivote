---
timestamp: "2026-09-13"
agent: "Claude Opus (ADR-015)"
session_status: "complete"
rama: "resolver/adr-015 (desde demo 27e52bf)"
---

# ADR-015 implementado: orden con la vía MEF, variantes del establecimiento y la rama de privadas al final

## Qué se hizo

Cuatro commits en `resolver/adr-015`, uno por cambio de la sección Decisión de
ADR-015, cada uno con sus pruebas sintéticas versionadas (CUI y nombres
inventados: el repo es público).

| commit | qué |
|---|---|
| `fdb3577` | `fix(resolucion)`: la vía MEF se evalúa ANTES del candado §1 en expedientes (ADR-015 §2) |
| `ba9052e` | `fix(resolucion)`: candado de variantes del mismo establecimiento |
| `973b1cf` | `fix(resolucion)`: la rama de privadas va al final de verdad (precisa ADR-004) |
| `7467276` | `test(aceptacion)`: resuelto por etapa cuenta como resuelto (ADR-015 §4) |

**Suite completa: 1917 pasan, 33 omitidas** (antes 1901/33; +16 pruebas nuevas
en 4 archivos). **Aceptación privada: las dos pruebas pasan** con
`PIVOTE_ACEPTACION_JSON` puesta, y se saltan sin ella. Sin push, sin cambiar de
rama, sin `git stash`, sin tocar el checkout principal salvo LEER
`backend/datos_pivote/`. No se tocó skill, Panel ni entregables.

## Los cinco casos de la aceptación

| clave | esperado | antes | después | qué lo arregló |
|---|---|---|---|---|
| 3:1 | PENDIENTE | RESUELTO (principal) | **PENDIENTE** | candado de variantes: el otro CUI es el plan de contingencia del mismo establecimiento |
| 12:3 | RESUELTO | PENDIENTE | **RESUELTO** | orden con la vía MEF (ficha 99,2; rivales a más de 8 puntos) |
| 12:4 | RESUELTO | PENDIENTE (posible privada) | **RESUELTO** | tercera puerta a PROBABLE por nombre literal + entidad de la ficha MEF |
| 13:3 | RESUELTO | PENDIENTE | **RESUELTO** | aceptación: `resuelto_por_etapa` se comprueba contra lo persistido (vía CONTRATO) |
| 16:1 | RESUELTO | PENDIENTE | **RESUELTO** | orden con la vía MEF (ficha 100; la rival 95,9 está vetada por provincia) |

Además **9:1** (multi-obra, fuera del replay por diseño de ADR-011) dejó de
contarse como «sin resultado»: se compara contra lo persistido y coincide con el
PENDIENTE que dictaminó el auditor.

## Cambio 1 · Orden con la vía MEF (ADR-015 §2)

El candado de ADR-005 §1 se escribió para OBRAS. En un EXPEDIENTE, que InfoObras
no devuelva el proyecto por NOMBRE es lo normal (la fusión lo trae por CÓDIGO,
con `origen == "mef"` y sin `solo_ficha`). Con el orden viejo se demotaba al
candidato correcto, un homónimo más débil ocupaba su lugar y la vía MEF
terminaba evaluando a un SUSTITUTO.

Ahora, en camino A, `ranked[0]` de origen `mef` pasa PRIMERO por los candados
propios de la vía MEF (nombre oficial ≥ 95, cobertura ≥ 80 %, sin contradicción
de ubicación, sin rubro ajeno, sin ficha rival). Si los supera, resuelve por vía
MEF **conservando el `obra_id` real de InfoObras** cuando existe (antes se
anulaba siempre, porque la vía solo recibía fichas sintetizadas); si no, se
demota exactamente como antes.

- **No se relajó el candado**: sumar `geo_match` al trío —la salida que el
  handoff del 12-sep dejó sobre la mesa— sí habría bajado su sensibilidad y roto
  el caso Chinchinga. Lo que cambió es el ORDEN. `test_chinchinga_fusion_rescata_
  pero_no_resuelve_sin_corroborar` sigue verde sin tocarse.
- El comentario largo «PENDIENTE DE DECISIÓN» de `_compuertas` se reemplazó por
  la nota de qué se decidió y por qué.

## Cambio 2 · Variantes del mismo establecimiento

Candado nuevo (`_rival_variante`) que se abstiene cuando dos CUIs distintos son
el MISMO establecimiento inscrito dos veces y uno es variante del otro: plan de
contingencia, saldo, reformulación, actualización, componente, etapa, o la
CONTRATACIÓN del expediente técnico de otra inversión (registro que se llama
como el contrato y cita el código de la inversión madre).

**Independiente del puntaje a propósito**: en producción los dos registros del
3:1 quedaron a 2,4 puntos (el guard de empate los frenó) y en la reconstrucción
offline a 5,6 (resolvía el principal). Mismo certificado, dos veredictos según
el ruido del score; la ambigüedad es del documento.

Corre ANTES del guard de empate porque su motivo NOMBRA a los dos candidatos y
dice cuál es la variante, donde el del guard era genérico («varios proyectos
homónimos sin señal que los distinga»).

**Decisión tomada donde había margen — la condición del nombre literal.** El
ADR pide «comparten los tokens del establecimiento y la misma ubicación». Con
solo eso, medido sobre el replay, el candado alcanzaba **6 casos más que NO son
variantes**: un parque y un mercado en la misma comunidad nativa, un atractivo
turístico «I ETAPA» en la misma provincia que un hospital, el saldo de obra de
OTRO centro de salud de la misma provincia, y una ampliación antigua del mismo
centro de salud. El topónimo compartido basta para que los tokens coincidan. Se
exige además que **AMBOS candidatos lleven el nombre del certificado LITERAL**
(`nombre_literal`, contención palabra por palabra) — que es lo que distingue
«dos códigos del MISMO proyecto» de «dos proyectos distintos del mismo pueblo».
Con esa condición el replay mueve exactamente las 3 apariciones del certificado
auditado y nada más.

## Cambio 3 · La rama de privadas al final de verdad (precisa ADR-004)

Dos causas independientes por las que la rama pisaba a candidatos identificados:

1. Un nombre oficial de puro genérico + geografía («HOSPITAL REGIONAL EN LA
   PROVINCIA DE …») no tiene NINGÚN token propio: con `toks` vacío ni la
   compuerta de tokens ni el mínimo `n_hit ≥ 1` de la vía PROBABLE pueden
   cumplirse **nunca**, así que la experiencia caía hasta la rama de privadas
   aunque un solo CUI llevara su nombre palabra por palabra y la ubicación
   coincidiera. Se abre una **tercera puerta a PROBABLE**: nombre literal ÚNICO
   + corroboración dura (la lista de ADR-013) + el mismo mínimo de puntaje.
   Ningún umbral se mueve.
2. El fuzzy contra el catálogo no reconocía a «GOBIERNO REGIONAL
   LIMA-PROVINCIAS» (89,5). Ahora la `entidad` de la ficha MEF del candidato
   ganador también cuenta para dar por pública a la contratante, comparando con
   el guion normalizado como separador de palabras (sin eso el token queda
   pegado y el fuzzy cae a 87,2; con eso, la contratante contiene a la entidad
   de la ficha y da 100). **El umbral 90 del catálogo NO baja y el catálogo no
   se toca**: se compara contra la ficha del propio candidato, que es evidencia
   de identidad, no de vocabulario. El mismo helper
   (`_entidad_publica_contratante`) gobierna el candado de entidad de la vía
   PROBABLE y la rama b de privadas.

Y la rama b no corre cuando hay candidato fiable (ganador del desempate
literal): decir «posible obra privada» de una obra cuyo proyecto está
identificado es un motivo falso y además tapa al candidato en la cola.

## Cambio 4 · Aceptación: resuelto por etapa cuenta como resuelto

`tests/test_aceptacion_auditoria.py` ahora lee el resultado PERSISTIDO del job
en dos casos, documentados en el encabezado del módulo:

- la experiencia que la auditoría marca `resuelto_por_etapa` (vías CONTRATO /
  RESOLUCION / MEF: consultan el MEF **en vivo**, no hay forma offline de
  reproducirlas). Si el job la registra por otra vía, la prueba falla;
- la clave que el replay no cubre (multi-obra, ADR-011): antes contaba como
  «sin resultado» y ahora se compara contra lo que el job produjo de verdad.

En ambos casos la referencia es el archivo del job, que es un HECHO de la
corrida real, no una expectativa relajada.

`test_ninguna_resuelta_cambia_de_cui` deja escrito por qué solo cuenta las
experiencias cuyo esperado es RESUELTO **con CUI**: una que el auditor dejó en
PENDIENTE no tiene CUI de referencia, así que resolverla es un desacuerdo de
abstención —lo mide la otra prueba— y nunca un «cambio de CUI».

La traducción de vocabularios se cubre aparte y sin datos privados
(`tests/test_aceptacion_vocabulario.py`), porque la aceptación se salta entera
cuando la auditoría no está.

## Replay sobre `datos_pivote/` (23 jobs, 1107 experiencias)

**El modo documentado del CLI (`base=None`) es CIEGO a estos tres cambios** y su
salida es idéntica byte a byte antes y después (1107 · sin cambio 892 · cambios
215): sin la base del MEF no hay candidatos con `origen == 'mef'`, ni
`geo_match`, ni fichas con entidad — las tres señales que gobiernan lo que se
tocó. La medición real es **con la base local del MEF**, que es la que tuvo la
corrida original y la que usa la aceptación:

| respecto al histórico persistido | antes | después |
|---|---|---|
| sin cambio | 933 | 920 |
| revisión → resuelto | 72 | **87** |
| resuelto → revisión | 27 | **25** |
| revisión → NO APLICA (privada) | 32 | 32 |
| NO APLICA → revisión | 39 | 39 |
| **RESUELTO → RESUELTO con CUI distinto** | **3 — los mismos 3** | **3 — los mismos 3** |

Los 3 que difieren del histórico son idénticos antes y después (artefacto del
snapshot, no de este cambio): `0838c4ba1fe0 3:3`, `0838c4ba1fe0 4:2`,
`104b00e538b3 3:4`.

**Cero experiencias resueltas cambian de CUI** por este cambio (criterio de
ADR-015 §3).

### Las 20 que pasan de revisión a resuelto

Las 18 por vía MEF (cambio 1) y las 2 por PROBABLE (cambio 3). Se revisaron una
por una: en todas el nombre oficial del Banco de Inversiones coincide con el del
certificado casi palabra por palabra y la ubicación calza.

| clave | vía |
|---|---|
| `0838c4ba1fe0 12:3` · `36a39eacfd48 12:3` · `3f04f6e73550 12:3` | MEF |
| `0838c4ba1fe0 16:1` · `36a39eacfd48 16:1` · `3f04f6e73550 16:1` | MEF |
| `104b00e538b3 4:13` · `6:4` · `7:11` · `8:7` · `11:8` (mismo certificado) | MEF |
| `104b00e538b3 11:1` | MEF |
| `41a442cdcd81 4:7` · `41a442cdcd81 5:15` | MEF |
| `7ff70fd37a81 5:1` · `7ff70fd37a81 6:1` (mismo certificado) | MEF |
| `7ff70fd37a81 7:3` · `7ff70fd37a81 10:3` | MEF |
| `36a39eacfd48 12:4` · `3f04f6e73550 12:4` | PROBABLE |

(Los grupos repetidos son el MISMO certificado presentado en varias propuestas.)

### Las 3 que pasan de resuelto a revisión

Las tres son **el mismo certificado** (el caso 3:1 de la auditoría) en tres
propuestas distintas: `0838c4ba1fe0 3:1`, `36a39eacfd48 3:1`, `3f04f6e73550 3:1`.
El auditor las dictaminó PENDIENTE el 13-sep: dos registros del mismo
establecimiento (el principal y el plan de contingencia contratado sobre él) y
el certificado no separa ninguno. Es una variante real; el candado hace lo que
debe. **Ninguna otra experiencia del corpus pasa a revisión.**

## Notas de vigencia para ADR-015 (no lo edité, como pedía el encargo)

1. **El punto 2 habla solo de `origen == "mef"`, y hay un caso real que no
   cubre.** El 12:4 de la auditoría resolvió en producción por vía MEF con una
   ficha `solo_ficha`; en la reconstrucción offline el mismo candidato llega con
   `origen == "ambos"` (el snapshot lo sirve además por nombre) y por tanto NO
   entra por la puerta del punto 2. Se resolvió por otro camino —la tercera
   puerta a PROBABLE del punto 6—, que da el mismo CUI. Si se quiere que la vía
   MEF cubra también a los `ambos`, hace falta decidirlo y medirlo aparte: es
   una puerta bastante más ancha (casi todo candidato corroborado por el MEF es
   `ambos`) y no la abrí por mi cuenta.
2. **El punto 6 dice «la comparación de entidad pública mira también la entidad
   de la ficha MEF del candidato».** Lo implementé exigiendo además que la
   contratante se PAREZCA a esa entidad (mismo umbral 90, con el guion
   normalizado). Leído al pie de la letra, bastaría con que la entidad de la
   ficha sea pública; me pareció demasiado (una clínica privada mal emparejada
   con un proyecto público se daría por pública sin que nada relacione a las dos
   entidades). Conviene anotar la condición en el ADR.
3. **El candado del punto sobre variantes exige, además de lo que dice el ADR,
   que ambos candidatos lleven el nombre del certificado LITERAL.** Sin esa
   condición produce 6 falsos positivos medidos sobre el corpus (arriba). Vale
   la pena escribirlo en el ADR: es la diferencia entre «mismo establecimiento»
   y «mismo topónimo».
4. **El punto 3 nombra al replay «sin red» como instrumento obligatorio, pero el
   modo documentado del CLI (`base=None`) no ve los cambios que dependen del
   MEF.** Para que el instrumento mida lo que el ADR pide, el replay de
   regresión debe correrse CON la base local del MEF. Hoy eso exige una opción
   que el CLI no tiene (lo medí con un script aparte). Vale una tarea: agregarle
   `--mef` a `scripts/replay_enriquecimiento.py`.

## Cómo correr la aceptación (datos privados, fuera del repo)

```
cd backend
PIVOTE_ACEPTACION_JSON=C:/Users/Holbi/InfoObras/analisis/auditoria-identificacion-tacna-20260912/esperado_identificacion_tacna.json \
PIVOTE_DATA_DIR=C:/Users/Holbi/Documents/Freelance/proyectos/InfoObras/Pivote/backend/datos_pivote \
python -m pytest tests/test_aceptacion_auditoria.py -q
```

## Siguiente paso sugerido

1. Mirar las 20 que pasan de revisión a resuelto (tabla arriba) contra sus
   certificados, si quieres una segunda opinión sobre el cambio 1.
2. Decidir las cuatro notas de vigencia de arriba y precisar ADR-015.
3. `--mef` en el CLI del replay, para que la regresión del ADR se pueda correr
   con un comando.
