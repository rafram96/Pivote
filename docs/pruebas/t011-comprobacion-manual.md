# T-011 — comprobar los cruces de fechas con tus propios ojos

> Cruces **contrato / expediente ↔ certificado** + hoja «Cronología de
> expedientes». Todo lo de abajo se corre desde la raíz del repo (`Pivote/`),
> con `venv/Scripts/python`. **Ningún comando escribe en un job real** y
> ninguno toca la red (salvo que agregues `--vivo`).

## Las dos reglas, en una frase cada una

| | Pregunta | Cuándo aplica |
|---|---|---|
| **A** | ¿El profesional empezó **después** de que se firmara el contrato del proceso? | Toda experiencia con proceso publicado |
| **B** | ¿El profesional terminó **antes** de que se aprobara el expediente? | Solo experiencias de expediente técnico |

Las dos responden `SÍ` (verde), `NO` (rojo, a revisar) o `POR VERIFICAR`
(amarillo). **`POR VERIFICAR` no es un incumplimiento**: es el sistema
absteniéndose porque la fuente no existe o no se pudo confirmar que corresponda
a este certificado. Nunca sale una alerta por falta de datos.

## Las tolerancias, y por qué son esas

| Regla | Tolerancia | Porqué |
|---|---|---|
| A | **15 días** | Es la misma vara que ya usa el candado F5: el desfase habitual entre firmar el contrato y arrancar el servicio (entrega de terreno, orden de inicio), que las constancias suelen redondear. Una sola vara para la misma comparación: si algún día se cambia, cambia en los dos sitios a la vez. |
| B | **30 días** | Vara propia porque mide otra cosa: el cierre administrativo. Entre la resolución que aprueba el expediente y la conformidad/liquidación pasan días o semanas, y una constancia legítima puede llegar hasta ese cierre. Seguir «elaborando» meses después de aprobado es lo que la regla existe para señalar. |

**La aritmética es día-exacta, jamás por mes.** Un inicio declarado el 05/01
contra una firma del 30/01 «coincide» si solo se comparan meses — y son 25 días
que ninguna fuente respalda. El Caso 1 de abajo es exactamente ese.

## El candado que impide señalar el concurso equivocado

Antes de comparar fechas, cada regla exige que la **identidad** de su fuente
esté confirmada **por señales que no sean la fecha misma**:

- **Regla A**: el proceso tiene que estar sostenido por ≥2 señales fuertes
  ajenas a la fecha (entidad convocante, RUC del adjudicatario, objeto) y por
  ninguna en contra que no sea la fecha. Lo que se verifica no puede elegir su
  propia identidad.
- **Regla B**: el MEF tiene que confirmar que quien emitió la constancia es el
  proyectista del expediente. Si no, se estaría midiendo contra la aprobación
  del expediente de otra empresa.

Sin eso, la regla **se abstiene**: ni dispara ni valida.

---

## Caso 1 — la Regla A dispara: el borde «mismo mes, días incompatibles»

Sin red, sin job. El profesional declara empezar el 05/01 y el contrato se firmó
el 30/01.

```
venv/Scripts/python backend/scripts/probar_candado_seace.py cruce-caso ^
    --inicio 2021-01-05 --fin 2021-12-31 --firma 2021-01-30 ^
    --entidad "GOBIERNO REGIONAL DE JUNIN" ^
    --entidad-proceso "GOBIERNO REGIONAL DE JUNIN SEDE CENTRAL" ^
    --emisor "INSTITUTO DE CONSULTORIA S.A." --ruc-emisor 20263373058
```

*(en Git Bash, cambia `^` por `\`)*

**Qué debes ver para dar el OK:**

- `Identidad del proceso (candado F5): CONTRADICE — 2 señal(es) a favor, 1 en
  contra`. Las 2 a favor son la entidad y el adjudicatario; la que contradice es
  la fecha — que es justamente lo que la regla va a nombrar.
- `¿EMPEZÓ DESPUÉS DE FIRMADO EL CONTRATO? → NO`
- `Diferencia día-exacta: 25 día(s)`
- El texto dice literalmente las dos fechas (`05/01/2021`, `30/01/2021`), los 25
  días y la tolerancia de 15.
- La Regla B avisa que no aplica (no es un expediente).

**Prueba del día exacto**: cambia `--inicio` a `2021-01-15` (15 días de
diferencia) → la respuesta pasa a `SÍ`. Con `2021-01-14` (16 días) vuelve a
`NO`. El corte está en el día, no en el mes.

---

## Caso 2 — la Regla A se abstiene: identidad insuficiente

Mismo desfase flagrante, pero sin RUC de emisor ni entidad contratante: solo
queda una señal a favor, que no basta.

```
venv/Scripts/python backend/scripts/probar_candado_seace.py cruce-caso ^
    --inicio 2021-01-05 --fin 2021-12-31 --firma 2021-01-30 ^
    --entidad-proceso "GOBIERNO REGIONAL DE JUNIN SEDE CENTRAL"
```

**Qué debes ver:** `→ POR VERIFICAR`, con el motivo *«solo 1 de 2 señales
independientes de la fecha confirman que el proceso sea el del certificado;
cruzar fechas contra un proceso sin confirmar puede señalar el concurso
equivocado»*. **Ninguna alerta.** Es el gate anti-circularidad funcionando: es
preferible callar a acusar contra el concurso equivocado.

---

## Caso 3 — la Regla B dispara: siguió «elaborando» un expediente ya aprobado

```
venv/Scripts/python backend/scripts/probar_candado_seace.py cruce-caso ^
    --tipo expediente ^
    --inicio 2023-01-10 --fin 2024-03-31 --firma 2023-01-05 ^
    --entidad "GOBIERNO REGIONAL DE HUANUCO" ^
    --emisor "INSTITUTO DE CONSULTORIA S.A." --ruc-emisor 20263373058 ^
    --aprobacion-et 2023-08-14
```

**Qué debes ver:**

- Regla A → `SÍ` (`-5 días`: el contrato ya existía cuando empezó).
- Regla B → `NO`, `Diferencia día-exacta: 230 día(s)`, y el texto nombra el
  31/03/2024 declarado contra el 14/08/2023 de la aprobación, más la tolerancia
  de 30 días y **de dónde sale la fecha** de aprobación.

---

## Caso 4 — la Regla B se abstiene: el MEF no confirma al proyectista

El mismo caso, pero simulando que el MEF no confirma que el emisor sea quien
elaboró el expediente:

```
venv/Scripts/python backend/scripts/probar_candado_seace.py cruce-caso ^
    --tipo expediente ^
    --inicio 2023-01-10 --fin 2024-03-31 --firma 2023-01-05 ^
    --entidad "GOBIERNO REGIONAL DE HUANUCO" ^
    --emisor "INSTITUTO DE CONSULTORIA S.A." --ruc-emisor 20263373058 ^
    --aprobacion-et 2023-08-14 --mef-no-coincide
```

**Qué debes ver:** Regla B → `POR VERIFICAR`, motivo *«el MEF no confirma que
quien emitió la constancia sea el proyectista del expediente; comparar contra
esa aprobación sería comparar con otro encargo»*. Los 230 días desaparecen: sin
identidad no hay veredicto.

---

## Caso 5 — el replay del job real (Vitarte, `7e9306a321ac`)

Recorre las 31 experiencias del análisis de EsSalud Vitarte y aplica las dos
reglas. **Offline** (usa la copia local de los procesos que dejó F5) y **no
modifica el job**.

```
venv/Scripts/python backend/scripts/probar_candado_seace.py cruces 7e9306a321ac
```

**Qué debes ver (números exactos, 2026-08-05):**

```
Experiencias del análisis: 31

REGLA A · inicio declarado vs firma del contrato
  Se pronunció sobre        : 31 experiencia(s)
  CUADRA (la fecha calza)   : 9
  NO CUADRA (a revisar)     : 0
  POR VERIFICAR (se abstuvo): 22
       21  no se identificó el proceso de contratación … (cobertura desde 2018)
        1  solo 1 de 2 señales independientes de la fecha confirman …

REGLA B · término declarado vs aprobación del expediente
  Se pronunció sobre        : 0 experiencia(s)
```

**Cómo leer esos números, sin adornos:**

- **9 cuadran**: las 9 experiencias cuyo proceso quedó confirmado por señales
  ajenas a la fecha. En las 9, el contrato existía antes del inicio declarado.
- **0 no cuadran**: en este análisis **no hay ninguna incoherencia de fechas**.
  Es un resultado, no un fallo de la herramienta — el Caso 1 demuestra que la
  regla sí dispara cuando hay con qué.
- **21 se abstienen por cobertura**: sus CUI no figuran en los datos abiertos
  del Estado (la cobertura empieza en 2018 y varias experiencias son de
  2012-2017). Ninguna alerta: sin fuente no hay juicio.
- **1 se abstiene por identidad**: hay proceso, pero no hay 2 señales ajenas a
  la fecha que confirmen que sea el del certificado.
- **Regla B en 0**: este job se corrió sin la verificación de expedientes del
  MEF (T-003), así que no hay ningún expediente verificado que cotejar. Los
  Casos 3 y 4 cubren esa regla a mano.

Con `--detalle` se listan las 31, una por una, con las dos fechas y el motivo.

---

## Caso 6 — la hoja «Cronología de expedientes» en el Excel del job Vitarte

El mismo comando regenera el entregable **en otra ruta** (el `final.xlsx` del
job no se toca):

```
venv/Scripts/python backend/scripts/probar_candado_seace.py cruces 7e9306a321ac ^
    --excel %USERPROFILE%\Downloads\Vitarte_con_cronologia.xlsx
```

*(en Git Bash: `--excel ~/Downloads/Vitarte_con_cronologia.xlsx`)*

Al final imprime:

```
  Hojas del libro: 17
  La hoja «Cronología de expedientes» SÍ está (es la última: Cronología de expedientes).
```

**Abre ese archivo y ve a la última pestaña, «Cronología de expedientes».**
Celda por celda, esto es lo que tiene que haber:

### Cabecera

| Celda | Contenido |
|---|---|
| `A1` | `CRONOLOGÍA DE EXPEDIENTES Y CONTRATOS` (banda azul oscuro) |
| `A2` | El párrafo que explica que `POR VERIFICAR` nunca cuenta en contra del postor |
| `A5` | La leyenda de colores (verde / rojo / amarillo / violeta) |

### Parte 1 — ficha por proyecto

| Celda | Contenido |
|---|---|
| `A7` | `1 · FICHA POR PROYECTO (3 de 10 con documentos publicados)` |
| `A9` | Nombre del proyecto + `CUI 2343407` + nº de experiencias (banda amarilla) |
| `A10` / `D10` | `Proceso de contratación` / `CP-SM-9-2017-PRONIS-1` |
| `A11` / `D11` | `Entidad que convocó` / `UNIDAD EJECUTORA 125 PROGRAMA NACIONAL DE INVERSIONES EN SALUD` |
| `A12` / `D12` | `Fecha de firma del contrato` / **`17/04/2018`** |
| `A13` / `D13` | `Vigencia del contrato` / `18/04/2018 a 25/04/2024` |
| `A14` / `D14` | `¿El proceso corresponde a este certificado?` / `Identificado y verificado contra el certificado` |
| `A15` / `D15` | `Modificaciones de plazo` / `InfoObras no registra modificaciones de plazo para este proyecto` |
| `A17`–`A23` | Lo mismo para el 2º proyecto: `AS-SM-28-2021-GRJ-CS-1`, GORE Junín, firma **`24/09/2021`**, vigencia `25/09/2021 a 12/03/2024` |
| `A25`–`A31` | Lo mismo para el 3º: `CP-SM-6-2022-GRJ-CS-1`, GORE Junín, firma **`18/10/2022`**, vigencia `19/10/2022 a 31/12/2023` |

> El `17/04/2018` de la primera ficha es el fix de F5 en acción: antes salía la
> fecha de una adenda de dos días de 2024, porque se leía el primer contrato de
> la lista en vez del más temprano.

### Parte 2 — tabla comparativa

| Celda | Contenido |
|---|---|
| `A34` | `2 · TABLA COMPARATIVA — periodo declarado frente a los hitos documentales` |
| Fila `35` | Los 11 encabezados, con autofiltro y celeste |
| `A36`–`K36` | `Florencio Yaco Aguilar` · exp `1` · CUI `2343407` · declarado `29/05/2018`–`15/03/2020` · firma `17/04/2018` · aprobación `—` · **`SÍ` en verde (col. I)** · `NO APLICA — no es un expediente técnico` (col. J, sin color) · la frase completa en `K36` |
| `A37`–`K37` | La 2ª experiencia del mismo profesional, también `SÍ` |
| `A38`–`K38` | `Lucar Antonio Cabanillas Toro` exp 1, CUI `2088779` (obra de 2012): firma `—` y **`POR VERIFICAR` en amarillo**, con el motivo de la cobertura desde 2018 en `K38` |
| … | 31 filas en total, una por experiencia |

**Los tres controles que valen por todos:**

1. Ninguna celda de la columna `I` o `J` está **en blanco**: o dice `SÍ`, o `NO`,
   o `POR VERIFICAR`, o `NO APLICA` — siempre con su explicación al lado.
2. Ninguna celda dice `por_confirmar`, `sin_dato`, `backend`, `agent-…` ni trae
   los corchetes `⟦ ⟧`: todo está en palabras de evaluador.
3. Las fechas de `E`, `F`, `G` y `H` se ven `29/05/2018`, **nunca**
   `2018-05-29 00:00:00`. Año de cuatro dígitos a propósito: aquí se compara
   contra documentos oficiales y el año es el dato que importa.

---

## Caso 6b — el bloque por profesional, dentro de cada hoja P

La hoja global es la vista de conjunto del Comité; el bloque de abajo es la
misma verdad **al lado del profesional que se está evaluando**, con una entrada
por experiencia. Los dos leen la misma función de presentación: si un texto o un
color cambia, cambia en los dos a la vez.

En el mismo archivo del Caso 6, abre la pestaña **`P1. Contr`** y baja hasta el
final de la hoja. Justo **debajo de `CONCLUSIÓN DEL TIEMPO EFECTIVO`** y encima
del recorte del factor, tiene que haber:

| Fila (aprox.) | Contenido |
|---|---|
| `A437` | Banda gris `CRUCE DE FECHAS CONTRA EL CONTRATO Y LA APROBACIÓN DEL EXPEDIENTE` |
| Fila `438` | Encabezados: `N°` · `Proceso de referencia` · `Inicio declarado` · `Firma del contrato` · `Término declarado` · `Aprobación del expediente` · `¿Empezó después de firmado el contrato?` · `¿Terminó antes de aprobarse el expediente?` |
| Fila `439` | Experiencia 1: `CP-SM-9-2017-PRONIS-1` · inicio `29/05/2018` (amarillo, es lo declarado) · firma `17/04/2018` · término `15/03/2020` · aprobación `—` · **`SÍ` en verde** · `NO APLICA — no es un expediente técnico` (sin color) |
| Fila `440` | La explicación completa, a todo lo ancho: *«El contrato del proceso se firmó el 17/04/2018 y el profesional declara haber iniciado el 29/05/2018, después de esa firma.»* |
| Filas `441`–`442` | Lo mismo para la experiencia 2 |

Y en **`P2. Jefe Superv`**, el mismo bloque con el caso contrario: las 5
experiencias de Lucar Antonio Cabanillas Toro salen en **`POR VERIFICAR`
amarillo**, con `Proceso de referencia` en `—` y la nota *«no se identificó el
proceso de contratación de esta experiencia en los datos abiertos del
Estado…»*. **Ninguna experiencia desaparece por no tener proceso publicado**:
aparece con su abstención escrita.

> Los números de fila son de la corrida del 2026-08-05 y se mueven con el
> contenido; lo que no se mueve es la posición relativa — el bloque va siempre
> entre la conclusión del tiempo efectivo y el recorte del factor.

**Lo que NO cambió en esas hojas**: todo lo que ya había queda intacto y en el
mismo sitio. Verificado regenerando Lircay con el código anterior (`70f39bf`) y
con el nuevo: `CLAUDE` y `Base de Datos` con **cero celdas modificadas**, las 17
hojas por profesional con **cero contenido preexistente perdido** — el bloque se
añade al final y el recorte del factor baja intacto.

---

## Caso 7 — un job VIEJO, sin nada que cruzar, no puede romperse

Lircay (`371fa5a1e704`) se corrió antes de que existieran los datos de SEACE:
ninguna de sus 51 obras tiene proceso publicado. Regenerar su Excel tiene que
funcionar igual y la hoja tiene que **decir por qué está vacía**.

```
venv/Scripts/python backend/scripts/probar_candado_seace.py cruces 371fa5a1e704 ^
    --excel %USERPROFILE%\Downloads\Lircay_con_cronologia.xlsx
```

**Qué debes ver en la consola:** `67 experiencia(s)`, `CUADRA 0`,
`NO CUADRA 0`, `POR VERIFICAR 67`, con una sola razón — la cobertura desde 2018.
Y `Hojas del libro: 20`, con la de cronología al final.

**Qué debes ver en la pestaña nueva:**

| Celda | Contenido |
|---|---|
| `A7` | `1 · FICHA POR PROYECTO (0 de 51 con documentos publicados)` |
| `A8` | `Sin procesos verificables: ninguno de los proyectos de esta propuesta tiene un proceso de contratación en los datos abiertos del Estado (la cobertura empieza en 2018) ni una aprobación de expediente publicada. No es un defecto de la propuesta ni del análisis: es lo que las fuentes publican.` (sobre fondo amarillo) |
| `A13` / fila `14` | El título de la tabla comparativa y sus encabezados |
| `A15` en adelante | Las 67 experiencias, todas en `POR VERIFICAR` |

Y en cada hoja P del mismo archivo, el bloque de cruces con todas las
experiencias de ese profesional en `POR VERIFICAR` y su nota. **Sin crash y sin
celdas mudas**: un job sin fuentes dice qué le falta.

**Nada de silencio**: la hoja existe, dice qué falta y por qué, y no insinúa que
la propuesta esté mal.

---

## La comprobación automática

```
venv/Scripts/python -m pytest tests/test_cruces_fechas.py -q        # desde backend/
venv/Scripts/python -m pytest tests -q                              # suite completa
```

37 pruebas nuevas, sin red. Cubren: los dos disparos, el borde «mismo mes»,
los bordes exactos de las dos tolerancias (15/16 y 30/31 días), las cuatro
formas de abstención, que la etapa no levante alerta cuando se abstiene, que la
hoja global aparezca con datos y sin ellos, que el bloque por profesional
aparezca con una entrada por experiencia —incluidas las abstenciones— y siempre
**debajo** de la PARTE 5, que las fechas lleven formato de fecha en las dos
vistas, que no haya jerga, y que las dos vistas lean **la misma** función de
presentación.
