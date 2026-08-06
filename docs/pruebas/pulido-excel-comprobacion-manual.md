# Pulido del Excel — comprobarlo con tus propios ojos

> Cuatro correcciones sobre el **entregable**, más un candado en dos scripts de
> operación. Todo se corre desde la raíz del repo (`Pivote/`) con
> `venv/Scripts/python`. **Ningún comando escribe en un job real** y ninguno
> toca la red.

## Qué se arregló, en una frase cada una

| | Se veía así | Ahora |
|---|---|---|
| **1** | Un factor sin puntaje dejaba la celda **en blanco** y la NOTA de abajo seguía diciendo «80/100 (A=40…)» sobre una tabla que sumaba 40 | La celda dice **POR CONFIRMAR** en amarillo claro y la NOTA se **arma con lo que la tabla muestra** |
| **2** | La CONCLUSIÓN del profesional citaba **1267 días** y la PARTE 5 de arriba mostraba **1269** | La conclusión **antepone la cifra verificada** y explica de dónde sale la otra |
| **3** | El entregable decía «backend», «candado:», «espejo» | Palabras de evaluador; ningún término de taller sobrevive |
| **4** | El **mismo** amarillo marcaba «lo declara el certificado» y «esto está por verificar», con una leyenda que solo prometía lo primero | «Por verificar» pasa a **amarillo claro** y la leyenda declara los colores que la hoja usa de verdad |

## Regenerar tu Excel

Es el mismo comando de siempre; el job original **no se toca**.

```
venv/Scripts/python backend/scripts/probar_candado_seace.py cruces 7e9306a321ac ^
    --excel "%USERPROFILE%\Downloads\Vitarte_pulido.xlsx"
```

Tarda un par de minutos (rearma las 17 hojas con las imágenes de los
certificados). Al terminar imprime cuántas hojas quedaron.

---

## Check 1 · PARTE 5 de la hoja CLAUDE

Abre la hoja **CLAUDE** y baja del todo, a `PARTE 5: RESUMEN DE LA EVALUACIÓN`.

- La fila del **Factor A** ya no tiene la casilla de PUNTAJE vacía: dice
  **POR CONFIRMAR**, con el mismo amarillo claro que el resto de lo pendiente.
- Debajo de `PUNTAJE TÉCNICO TOTAL 40`, la **NOTA** ahora dice exactamente lo
  que la tabla muestra:

  > Puntaje técnico total 40 = C 10 + G 10 + J 20. Por confirmar: A — su tramo
  > no se pudo determinar con el cuadro de las bases, así que no suma. No
  > aplican (eliminados de las bases): B, D.

  Súmalo a mano: 10 + 10 + 20 = 40. **Cuadra con la tabla de arriba.**
- El texto viejo (el del «80/100») **sigue estando**, una fila más abajo, bajo
  el rótulo *«Observaciones de la evaluación (redactadas antes del recálculo del
  puntaje)»*. Se conserva porque trae observaciones útiles (el alcance del ISO
  9001, la admisibilidad), y el rótulo explica por qué sus cifras no coinciden.

## Check 2 · la cifra de días, en las dos superficies

Abre la hoja **P1. Contr** y baja a la `PARTE 5 — EXPERIENCIA DEL PROFESIONAL`.

- `TOTAL, DÍAS (suma por experiencia)` → **1269** (657 + 612).
- Dos filas más abajo, `CONCLUSIÓN DEL TIEMPO EFECTIVO` ahora **empieza** con:

  > **1269 días verificados (3.48 años).** CUMPLE — acredita 1267 días (3.47
  > años) frente a 2 años exigidos… · La cifra de 1267 días que cita esta
  > conclusión cuenta un día menos por periodo; el cómputo del proyecto incluye
  > el día de inicio y el de fin, y da 1269.

  La frase del evaluador **se conserva palabra por palabra** (es lo que audita
  el Comité); lo que se agrega es la cifra que manda y el porqué de la otra.
  La celda **sigue en verde**: el color se toma del veredicto original.
- Lo mismo en la hoja **CLAUDE**, fila `¿EL PROFESIONAL CUMPLE?` del
  PROFESIONAL 1, justo debajo de `TOTAL EFECTIVO VERIFICADO`.

**Ojo con lo que NO cambia, a propósito:** en las hojas **P6, P7, P8, P9 y P11**
la conclusión sigue igual. Ahí la diferencia entre lo declarado y lo efectivo
**no** es el conteo de bordes (son recortes del Paso 5 por falta de
valorizaciones), y el Excel ya la explica en sus propias filas. Llamarla «conteo
de días» sería mentir, así que el sistema se abstiene.

## Check 3 · Ctrl+F de las palabras de taller

Con el libro abierto, `Ctrl+F` → **Buscar todo** → marca *Libro* en el
desplegable «Dentro de», para que busque en las 17 hojas.

| Buscar | Resultado esperado |
|---|---|
| `backend` | **0 resultados** (antes: 15 — la fila «TOTAL EFECTIVO (backend)» × 14 + una celda de la PARTE 3) |
| `candado` | **0 resultados** |
| `espejo` | **0 resultados** |

La fila del total ahora se llama **TOTAL EFECTIVO VERIFICADO**, y donde antes
decía «Verificar folio/título (backend/evaluador)» dice «(equipo evaluador)».

## Check 4 · los dos amarillos y la leyenda

En cualquier hoja **P**, mira la fila 4 (`LEYENDA:`). Ahora dice:

> violeta = supuesto o inferido · amarillo = dato del certificado / valorización
> dentro del periodo · **amarillo claro = por verificar** · **verde = verificado
> correcto** · cyan = efectivo verificado · naranja = periodo excluido · rojo =
> alerta o contradicción

Los dos resaltados son los que faltaban. Para ver que además es verdad:

- **P2. Jefe Superv**, celda **M183** — el aviso `🟡 ALT04 — probable
  reinscripción`: pasó de amarillo fuerte a **amarillo claro**.
- **P2. Jefe Superv**, celda **F220** — `No se encontró un proceso del tipo
  correspondiente a la experiencia` (candado SEACE sin confirmar): **amarillo
  claro**.
- **P2. Jefe Superv**, celdas **B1080 / B1082 / …** — los motivos del bloque
  `CRUCE DE FECHAS…`: **amarillo claro**.
- En contraste, el encabezado `CERT. N°1`, la fila `Periodo certificado` y las
  fechas de la fila `Certificado` siguen en **amarillo fuerte** — eso sí es
  «dato del certificado», que es lo que la leyenda promete.

**Lo que se dejó igual a propósito** (decisión explícita, va a mantenimiento):
la leyenda de la hoja *Base de Datos* y los tres rojos del libro.

---

## Check 5 · el candado de los scripts de operación

Dos utilidades (`avance_descargas.py` y `redescargar_documentos.py`) siguen
escritas contra el formato de datos **anterior** — cuando los archivos de un job
vivían sueltos en la raíz en vez de en su propia carpeta. Sobre un job de hoy
trabajarían en un sitio que ni el Excel ni el Panel miran, y nada lo delataría.

Pruébalo:

```
venv/Scripts/python backend/scripts/avance_descargas.py 7e9306a321ac
```

Tiene que **detenerse antes de tocar nada**, con esto:

```
El job 7e9306a321ac está guardado en el formato vigente (una carpeta por job) y
este script usa un formato de datos anterior.
Correrlo aquí puede dejar el Excel y el Panel sin ver lo redescargado: escribiría
los archivos en un sitio que el sistema ya no lee.
Si sabes lo que haces, repite el comando con --forzar.
```

`--forzar` lo deja pasar (para rescatar un job histórico que sí quedó en el
formato viejo). Mismo comportamiento en
`python -m scripts.redescargar_documentos <job> [--forzar]`, y el aviso también
está al abrir el archivo, en las primeras líneas.

---

## Cómo se comprobó que no se rompió nada más

Se regeneró el Excel de Vitarte **antes** (con `4157814`) y **después**, y se
compararon las 17 hojas celda por celda (valor + color): **105 diferencias**, y
todas caen en los cuatro arreglos —

| Nº | Qué | Dónde |
|---|---|---|
| 14 | `TOTAL EFECTIVO (backend)` → `TOTAL EFECTIVO VERIFICADO` | CLAUDE, una por profesional |
| 14 + 8 | conclusión con la cifra verificada al frente | CLAUDE + hojas P1–P5, P10, P12, P14 |
| 1 | `titulo=null` / `(backend/evaluador)` saneados | CLAUDE!D161 |
| 3 | puntaje `POR CONFIRMAR` + NOTA nueva + observaciones rotuladas | CLAUDE!E317, B324, A325/B325 |
| 14 | leyenda con los dos swatches que faltaban | fila 4 de cada hoja P |
| 50 | amarillo fuerte → amarillo claro en lo «por verificar» | hojas P |

Suite completa del backend: **865 passed, 25 skipped** (línea base 837/25;
+19 del pulido y +9 del candado). Sin red, resolver de CUI intacto, Panel y
skill sin tocar.
