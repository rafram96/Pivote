---
timestamp: "2026-09-12"
agent: Claude Opus (desempate de falsos negativos)
rama: resolver/desempate-falsos-negativos (desde demo 080064e)
---

# Desempate del resolver: los falsos negativos de la auditoría de identificación

## Qué se hizo

Dos commits en `resolver/desempate-falsos-negativos`:

| commit | qué |
|---|---|
| `973792b` | `fix(replay)`: el snapshot dejaba de lado casi todos los candidatos + prueba de aceptación contra la auditoría |
| `1bbeead` | `fix(resolucion)`: desempatar con la evidencia del certificado |

**Suite completa: 1901 pasan, 33 omitidas** (antes 1883/33; +18 pruebas nuevas).
Sin push, sin cambiar de rama, sin tocar el checkout principal salvo LEER
`backend/datos_pivote/`. Sin regenerar entregables.

## Lo primero y más importante: el instrumento estaba roto

El replay (`scripts/replay_enriquecimiento.py`) es el sustituto de la golden y
medía un universo falso. El enriquecimiento **solo persiste el `obra_id` de la
obra ELEGIDA**, no el de los candidatos, y el resolver usa ese campo como CLAVE de
`vistos` (`_recolectar_candidatos`): con todos los candidatos en `None`
**sobrevivía UNO por experiencia** —el primero— donde la corrida real tuvo tres o
cuatro. Un replay sin rivales no dispara guards de empate: por eso «pasaban» casos
que en producción se abstenían.

Consecuencia práctica: **todas las cifras de replay anteriores a este commit están
medidas sobre un universo recortado**. No son comparables con las de acá.

Otras dos correcciones de fidelidad en el mismo commit:

- **una sola pasada** de `resolver_con_dedup` con todas las experiencias del job,
  como en producción (`etapas_reales` arma una lista plana). Agrupar por
  profesional apagaba la herencia, que cruza profesionales;
- modo **`fidelidad_mef`** (automático cuando se pasa la base del MEF): los
  candidatos que en la corrida original trajo la FUSIÓN se sirven por CÓDIGO y no
  por nombre. Servirlos por nombre los disfraza de obra que InfoObras devolvió y
  desactiva el candado de ADR-005 §1 — el replay salía más fácil que la realidad.

Con el instrumento arreglado, la reconstrucción del job auditado reproduce **7 de
los 9 falsos negativos** (1:5, 2:2, 3:1, 12:3, 14:3, 15:1, 16:1). Los otros dos
(1:3 y 13:2) siguen saliendo bien en la reconstrucción aunque en producción
fallaron: su snapshot no conserva los rivales ni las fechas de obra que la corrida
real tuvo. **No hay forma offline de reproducir bit a bit una corrida contra el
portal en vivo** (`buscar` y `por_codigo` no se graban); el candado de esos dos se
puso con pruebas sintéticas.

## Los 9 casos, uno por uno

Reconstrucción del job auditado con la base local del MEF; «antes» y «después» son
con el MISMO instrumento (el arreglado).

| clave | esperado | antes | después | qué lo arregló |
|---|---|---|---|---|
| 1:3 | RESUELTO · A | RESUELTO · A | RESUELTO · A | ya salía bien en la reconstrucción (ver abajo) |
| 1:5 | RESUELTO · B | PENDIENTE | **RESUELTO · B** | nombre literal único desempata el guard |
| 2:2 | RESUELTO · C | PENDIENTE | **RESUELTO · C** | herencia por mismo proyecto (desde 1:2) |
| 3:1 | RESUELTO · D | RESUELTO · **E** | RESUELTO · **E** | ⚠ no arreglado — artefacto del instrumento, ver abajo |
| 12:3 | RESUELTO · F | PENDIENTE | PENDIENTE | ⚠ no arreglado — requiere decisión sobre ADR-005 §1 |
| 13:2 | RESUELTO · G | RESUELTO · G | RESUELTO · G | `fase_de`: SALDO antes de PRINCIPAL (probado sintéticamente) |
| 14:3 | RESUELTO · H | PENDIENTE | **RESUELTO · H** | nombre literal único desempata el guard de ubicación |
| 15:1 | RESUELTO · C | PENDIENTE | **RESUELTO · C** | herencia por mismo proyecto (desde 1:2) |
| 16:1 | RESUELTO · I | PENDIENTE | PENDIENTE | ⚠ no arreglado — requiere decisión sobre ADR-005 §1 |

(Los CUI reales están solo en el archivo privado de aceptación; acá van como
letras a propósito — el repo es público.)

Además, **14:2** (que no estaba en la lista de los 9) pasó de PENDIENTE a RESUELTO
con el CUI que la auditoría confirma.

**Total sobre las 62 experiencias del job: coincidencias con la auditoría de 51 a
56.** Las 4 diferencias que quedan: 3:1 y 12:3 y 16:1 (arriba) más 12:4 y 13:3,
que no son de los 9 y cuya resolución en producción vino de una fuente que el
replay no tiene (vía CONTRATO / entidad reconocida como pública), y 9:1 que es
multi-obra y queda fuera del replay por diseño.

## Las tres que NO se arreglaron, y por qué

### 16:1 y 12:3 — hace falta una decisión tuya sobre ADR-005 §1

En los dos (y también en 15:1 y 2:2, que se salvaron por otra vía), el candidato
que el auditor da por correcto llegó por la FUSIÓN (`origen = 'mef'`) y **su
provincia/distrito oficial COINCIDE con la que declara el certificado**, pero el
candado de ADR-005 §1 (`_mef_sin_corroborar`) solo mira el trío
`ruc_match | num_match | ent_match` y lo demota. Un homónimo más débil ocupa su
lugar como `best` y dispara el guard de ubicación: de ahí sale el motivo
«homónimo apartado por estar en otra ubicación» que el auditor marcó como falso.

**El cambio de una línea que los resuelve** es usar `_corroborado` en vez del trío
—la lista que ADR-013 ya definió, con `geo_match` dentro—. Lo probé: resuelve los
cuatro. **Y rompe** `test_chinchinga_fusion_rescata_pero_no_resuelve_sin_corroborar`
(`tests/test_resolucion_fusion.py`), que es **exactamente el mismo patrón**
(InfoObras solo trae basura por nombre, el MEF aporta el nombre oficial y la
ubicación calza) y que el golden respaldaba. O sea: no es un desempate, es bajarle
la sensibilidad al candado, y el encargo lo prohibía explícitamente. Lo dejé sin
tocar, con el razonamiento escrito en el propio `_compuertas` apuntando a este
handoff.

**Lo que hay que decidir**: si la coincidencia POSITIVA de provincia/distrito
cuenta como corroboración dura para el candado MEF. Evidencia a favor: 4 falsos
negativos reales de alta confianza en una sola propuesta, y ADR-013 ya la trata
como señal dura para su propio candado. Evidencia en contra: un caso del golden
(Chinchinga) que quedaría resuelto por nombre + ubicación sin ninguna
confirmación de InfoObras. Si decides que sí, hay que **reescribir el caso
Chinchinga** (no borrarlo: cambiarlo a «resuelve y así se documenta por qué»).

### 3:1 — el instrumento resuelve con otro CUI, y ya lo hacía antes

La reconstrucción resuelve 3:1 con un CUI distinto al auditado, **antes y después
de mis cambios, igual** (aparece en la línea base con el instrumento arreglado).
No es una regresión mía. Es un artefacto: el certificado tiene dos candidatos del
MISMO establecimiento (una reformulación del otro), en producción quedaron a 2.4
puntos y el guard de empate los mandó a revisión; la reconstrucción los separa por
5.6 puntos porque recompone el score con el nombre de InfoObras que se persistió y
no con el que la corrida real puntuó. Con los puntajes de producción el guard sigue
disparando y 3:1 seguiría PENDIENTE también después de mis cambios.

Y **PENDIENTE es lo correcto acá**: el auditor le puso `confianza: media` y su
separador es la numeración del código SNIP antiguo (cronología), no algo que esté
escrito en el certificado. Hay una prueba sintética que fija esa abstención
(`test_dos_candidatos_con_el_mismo_nombre_literal_siguen_en_revision`).

### 1:3 — abstención correcta

Dos CUIs del Banco de Inversiones con el MISMO nombre (uno con la cola de distrito
añadida), misma provincia, mismo distrito. El auditor los separa por cronología
(«un CUI muy posterior no podía existir cuando se contrató el expediente en 2008»)
y también le pone `confianza: media`. No implementé esa señal: ver abajo.

## Lo que decidí NO hacer (y por qué), donde el encargo dejaba margen

1. **La causa 2 del encargo, «fechas del certificado como desempate», quedó a
   medias**: implementé la parte de la fase SALDO (13:2) porque era un bug de orden
   de patrones, pero **no** un desempate por fechas de contrato/resolución del MEF.
   Razón: **no hay fuente offline de esas fechas**. La base local del MEF
   (`inversiones.csv.gz`) trae 10 columnas —`cui, snip, nombre, estado_dataset,
   situacion, ubigeo, dpto, prov, dist, entidad`— y ninguna es una fecha; las
   fechas de contrato y de resolución vienen de PostgreSQL (ficha enriquecida) o de
   la lectura de resoluciones que hace `etapas_reales` DESPUÉS de resolver. Y el
   argumento cronológico que el auditor usa en 1:3 y 3:1 no es una fecha: es la
   NUMERACIÓN del CUI como proxy del año. Convertir eso en una señal exigiría
   calibrar CUI→año, no se puede medir offline, y equivocarse produce
   mal-resueltos silenciosos. **Recomendación**: si quieres esta señal, el camino
   es exponer la fecha de registro/viabilidad del MEF en la ficha (ya está en
   PostgreSQL) y vetar al candidato cuya inversión no podía existir al inicio
   declarado. Es una tarea con su propia medición.

2. **El encargo pedía leer `departamento`/`provincia`/`distrito` del certificado.
   Esos campos no existen en el espejo**: `schemas/espejo.py::ExperienciaProf` solo
   tiene `ubicacion` (línea 315). Lo que hice fue leer MEJOR ese campo (el rótulo
   sin «de») y el pool de términos de ubicación. Si quieres campos separados, es un
   cambio de contrato (skill + zod + Pydantic), no del resolver.

3. **No toqué `_senal_dura` con `geo_match`**, que era la vía obvia para 14:3:
   ADR-013 lo dejó fuera a propósito porque DELTA=4 está calibrado contra la
   golden. Usé el nombre literal, que es una señal nueva y separada, y la metí
   como condición aparte del trío (no OR-eada con él) justo para no mover lo
   calibrado. En 1:5 los dos candidatos comparten `ent_match` —el gobierno regional
   que ejecuta ambos proyectos, señal vacía justo ahí— y solo el nombre literal los
   separa.

4. **Conservé el trabajo parcial del agente anterior** (la extracción de
   `resolver_snapshot` y `tests/test_aceptacion_auditoria.py`): la extracción está
   bien pensada y la prueba de aceptación tiene el diseño correcto (vocabulario
   cerrado, datos privados por entorno, skip sin archivo). Le agregué el modo de
   fidelidad y arreglé el bug de la clave.

## Cifras del replay sobre los 23 jobs locales (1107 experiencias)

Mismo instrumento antes y después, `base=None` (el modo documentado del CLI):

| | antes | después |
|---|---|---|
| sin cambio respecto al histórico | 889 | 892 |
| revisión → resuelto | 106 | **112** |
| resuelto → revisión | 48 | **39** |
| revisión → NO APLICA (privada) | 23 | 23 |
| NO APLICA → revisión | 34 | 34 |
| **RESUELTO → RESUELTO con CUI distinto** | **6** | **6 — los mismos 6** |

Los 6 que cambian de CUI respecto al histórico son **idénticos antes y después**:
no los introduce este cambio, los introduce la reconstrucción (el snapshot no tiene
las fechas de obra ni el universo completo del portal). Claves, para que las mires:
`104b00e538b3 2:7`, `41a442cdcd81 3:1`, `41a442cdcd81 8:3`, `41a442cdcd81 8:5`,
`8a4b468ac700 14:1`, `e7c0fff6afb1 14:1`.

Las 6 que el cambio mueve de revisión a resuelto (para que las revises):
`0838c4ba1fe0 1:4`, `104b00e538b3 8:6`, `36a39eacfd48 1:5`, `3f04f6e73550 1:5`,
`41a442cdcd81 1:9`, `41a442cdcd81 7:9`. Las tres de `1:4/1:5` son el mismo
certificado (el hospital de la sierra norte) repetido en tres propuestas.

Las 9 que el cambio devuelve a coincidir con el histórico (antes el replay las
degradaba a revisión y ahora resuelven como en producción): `15ee32f32c26 6:4`,
`41a442cdcd81 6:4`, `7409d2c628d2 4:3`, `7ff70fd37a81 4:3`, `886c5663f937 4:3`,
`8a4b468ac700 16:2`, `a61c7c44e976 4:3`, `e7c0fff6afb1 16:2`, `e7c0fff6afb1 4:2`.

## Cómo correr la aceptación (datos privados, fuera del repo)

```
cd backend
PIVOTE_ACEPTACION_JSON=C:/Users/Holbi/InfoObras/analisis/auditoria-identificacion-tacna-20260912/esperado_identificacion_tacna.json \
PIVOTE_DATA_DIR=C:/Users/Holbi/Documents/Freelance/proyectos/InfoObras/Pivote/backend/datos_pivote \
python -m pytest tests/test_aceptacion_auditoria.py -q
```

Hoy falla en 4 (3:1, 12:4, 13:3, 16:1) + 9:1 sin resultado (multi-obra). Sin el
archivo se SALTA, así que la suite del repo queda verde.

## Notas de vigencia para los ADR (no los edité, como pedías)

- **ADR-005 §1** (candado MEF): la auditoría aporta 4 casos reales donde el candado
  demota al candidato correcto teniendo la ubicación a favor. La decisión de sumar
  `geo_match` a la corroboración dura está pendiente y tiene un costo conocido
  (el caso Chinchinga del golden). Ver arriba.
- **ADR-005 §2** (guard de empate ≤4 pts sin señal dura): sigue vigente y con
  DELTA=4 sin tocar. Se le agregó una señal separadora nueva —nombre literal único
  del certificado— que es lo que el propio ADR pide («sin señal dura separadora →
  revisión»), no un cambio de umbral. Convendría anotarlo en el ADR.
- **ADR-013**: su lista de señales duras (`_corroborado`, con `geo_match`) sigue
  como estaba; lo que cambió es que `_ubigeo_coincide` ahora ve coincidencias que
  el rótulo ausente le ocultaba, así que el candado de nombre genérico se abre en
  algunos casos más. Medido en el replay: entra en las 6 altas y en ninguna baja.
- **ADR-011** (multi-obra): sin cambios. `9:1` del job auditado es multi-obra y el
  replay la salta por diseño; si se quiere cubrir hace falta replayar `resolver_obras`.

## Siguiente paso sugerido

1. Decidir lo de ADR-005 §1 (arriba). Si es «sí», son ~3 líneas más el rewrite del
   caso Chinchinga, y suben 16:1 y 12:3.
2. Mirar las 6 experiencias que pasaron a resuelto en el replay.
3. Si quieres el desempate por fechas del MEF, abrir tarea aparte (necesita la
   fecha en la ficha; hoy no existe offline).
