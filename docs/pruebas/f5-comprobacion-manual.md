# F5 — comprobar el candado SEACE con tus propios ojos

> Candado de identidad **certificado ↔ proceso SEACE** (T-004 F5).
> Todo lo de abajo se corre desde la raíz del repo (`Pivote/`), con
> `venv/Scripts/python`. Ninguno de estos comandos escribe en un job real.

## Qué hace el candado, en una frase

Elegir el proceso por **CUI + tipo** no prueba que sea el del certificado. El
candado cruza cuatro señales antes de presentar las Bases/Contrato como
verificados, y **nunca bloquea la descarga**: los PDF siguen yendo al ZIP como
sustento; lo que cambia es el rótulo de confianza del Excel y del índice.

| Veredicto | Cuándo | Qué dice el entregable |
|---|---|---|
| `confirmado` | ≥2 señales fuertes a favor y **cero** en contra | «Identificado y verificado contra el certificado» |
| `por_confirmar` | evidencia insuficiente (incluye datos faltantes) | «Por confirmar — no se pudo verificar contra el certificado» |
| `contradice` | ≥1 señal fuerte **en contra** | «Por confirmar — los datos del proceso NO coinciden con el certificado» + alerta |

Las señales:

| Señal | Fuerza | Puede contradecir |
|---|---|---|
| **Entidad** convocante del proceso vs entidad contratante del certificado | fuerte | sí |
| **Emisor** del certificado entre los adjudicatarios del proceso (igualdad de RUC) | fuerte | **no** — solo suma |
| **Objeto** del proceso vs tipo de la experiencia | fuerte | sí |
| **Fechas** (días completos, tolerancia 15 días) | fuerte | sí |
| **Monto** | débil | **no** — ni veta ni promueve sola |

---

## Antes de empezar (una sola vez)

Los tres primeros casos consultan los datos abiertos y **guardan una copia
local**, así que la primera corrida de cada CUI necesita internet y las
siguientes ya no. La bandera es `--vivo`.

---

## Caso A — el positivo real: Pedro Sánchez Meza → **VERIFICADO**

Constancia de INDECONSULT por la supervisión del E.S. Pedro Sánchez Meza
(Chupaca, Junín), CUI 2337618. Es la experiencia 8:2 del job Vitarte.

```
venv/Scripts/python backend/scripts/probar_candado_seace.py caso ^
    --cui 2337618 --vivo ^
    --entidad "GOBIERNO REGIONAL DE JUNIN" ^
    --emisor "INSTITUTO DE CONSULTORIA S.A." --ruc-emisor 20263373058 ^
    --inicio 2021-10-01 --fin 2023-10-11
```

*(en Git Bash, cambia `^` por `\`)*

**Qué debes ver para dar el OK:**

- Lista los 6 procesos del CUI, clasificados: 2 de supervisión, 3 de ejecución,
  1 de expediente.
- Elige `AS-SM-28-2021-GRJ-CS-1`.
- `VEREDICTO: VERIFICADO` con **3 señales a favor y 0 en contra**:
  - `[+] Empresa que emitió el certificado` — RUC 20263373058 **es el
    adjudicatario** del proceso.
  - `[+] Objeto del proceso` — supervisión vs supervisión.
  - `[+] Fechas` — el periodo del certificado (01/10/2021–11/10/2023) cae dentro
    de la vigencia del proceso (25/09/2021–12/03/2024), 741 días en común.
  - `[ ] Entidad que contrató` — **abstención**, y es correcto: «GOBIERNO
    REGIONAL DE JUNIN» vs «GOBIERNO REGIONAL DE JUNIN SEDE CENTRAL» da 80/100,
    que cae en la zona gris (60–84). Casi seguro es la misma entidad, pero 80 no
    alcanza el umbral de coincidencia fuerte, así que la señal **no decide**.
    Lo que confirma el caso es la igualdad de RUC, no un parecido de texto.

> Si esa abstención te parece demasiado dura, ese es el único umbral que
> conviene discutir. Está en `UMBRAL_ENTIDAD_A_FAVOR` (85) y es el mismo que ya
> usan SUNAT y el resolver de CUI — se dejó igual a propósito, para no tener dos
> definiciones distintas de «es la misma empresa» en el sistema.

---

## Caso B — el negativo real: Hospital del Altiplano → **no hay qué verificar**

```
venv/Scripts/python backend/scripts/probar_candado_seace.py caso ^
    --cui 2300016 --vivo ^
    --entidad "SEGURO SOCIAL DE SALUD - ESSALUD" ^
    --inicio 2022-03-01 --fin 2024-06-30
```

**Qué debes ver:**

- **14 procesos**, y los 14 clasificados como `otro`.
- `NO HAY PROCESO QUE VERIFICAR` — «el CUI no tiene proceso de supervision en
  datos abiertos».

**Hallazgo de la investigación previa (2026-08-05, consulta en vivo a
CONOSCE/OCDS):** los 14 procesos publicados bajo el CUI 2300016 son
**adquisiciones de equipamiento biomédico** de EsSalud CEABE (angiógrafos,
ventiladores, esterilización, lámparas quirúrgicas…), todos con
`mainProcurementCategory: goods`. **No existe** un proceso de supervisión, ni de
ejecución, ni de expediente bajo ese CUI, con ninguna nomenclatura. Se revisó
además si la API permitía buscar por texto o por entidad para encontrarlo con
otro nombre: solo acepta `projectID`, y devuelve exactamente esos 14.

**Conclusión: no es un fallo del selector.** El selector hace lo correcto al
negarse a cruzar de tipo — no hay nada que promover. La obra y su supervisión no
están indexadas bajo ese CUI en los datos abiertos. Las 6 experiencias del job
Vitarte que apuntan a este CUI quedan legítimamente sin documentos SEACE, con el
motivo dicho en el Excel. **No hay nada que corregir.**

---

## Caso C — inventado: entidad de otra región → **NO COINCIDE**

Mismo proceso del caso A, pero diciendo que el certificado lo emitió una obra de
Maynas (Loreto) con otro emisor.

```
venv/Scripts/python backend/scripts/probar_candado_seace.py caso ^
    --cui 2337618 ^
    --entidad "MUNICIPALIDAD PROVINCIAL DE MAYNAS" ^
    --emisor "CONSTRUCTORA AMAZONICA S.A.C." --ruc-emisor 20512345678 ^
    --inicio 2021-10-01 --fin 2023-10-11
```

*(sin `--vivo`: ya hay copia local del caso A)*

**Qué debes ver:**

- `VEREDICTO: NO COINCIDE`.
- `[-] Entidad que contrató` → «son entidades distintas (38/100)».
- Y lo importante: **aunque haya 2 señales a favor** (objeto y fechas
  coinciden), la contradicción manda. Promover exige señales; una sola señal
  fuerte en contra degrada.
- El emisor desconocido aparece como `[ ]`, no como `[-]`: una constancia puede
  emitirla legítimamente un consorciado con RUC propio, así que su ausencia
  **no** se cuenta como contradicción.

---

## Caso D — replay del job Vitarte, sin red

Recorre las 45 experiencias del job real `7e9306a321ac` (Concurso Público
N° 02-2025-ESSALUD/GCL-1) y dice en qué estado del candado queda cada una.

```
venv/Scripts/python backend/scripts/probar_candado_seace.py replay 7e9306a321ac --detalle
```

*(la primera vez, agregar `--vivo` para bajar los procesos de sus 3 CUI)*

**Resultado esperado (corrido el 2026-08-05):**

```
Experiencias con proceso SEACE elegido: 10
  VERIFICADO    (confirmado)   : 9
  POR CONFIRMAR (insuficiente) : 0
  NO COINCIDE   (contradice)   : 1

Experiencias SIN proceso que verificar (no llegan al candado):
   13  el CUI no publica un proceso del tipo de la experiencia
    6  el CUI no figura en datos abiertos (cobertura 2018+)
```

**La única contradicción es 11:3** y merece una mirada: el certificado declara
un periodo del **02/04/2025 al 31/12/2025**, y el contrato del proceso de
supervisión terminó el **12/03/2024**. Es la misma experiencia que la etapa
anterior ya había marcado como dudosa («2 procesos de supervisión sin solape que
desempate; se eligió el más reciente — VERIFICAR contra el certificado»). El
candado la convierte en un aviso explícito en vez de un rótulo de verificado.

---

## Dos defectos reales que aparecieron construyendo esto

Ambos ya corregidos, y por eso vale la pena que los veas:

1. **La ventana del proceso se tomaba de `contracts[0]`.** El orden que devuelve
   la fuente es arbitrario, y un proceso suele traer más de un contrato (el
   original y su liquidación). En el CUI 2343407 (Challhuahuacho, PRONIS)
   `contracts[0]` era un registro de **dos días de 2024** y el contrato de
   verdad era el segundo, **18/04/2018 – 01/05/2020**. Con el primero, las
   experiencias 1:1 y 1:2 salían «NO COINCIDE» siendo legítimas. Ahora la
   ventana abarca **todos** los contratos y la firma es la **más temprana**.
   Eso también arregla la «Fecha de firma» que el Excel venía mostrando.

2. **Los 3 `*_ERROR.txt` de Bases Integradas del job Vitarte no eran del host.**
   La descarga leía la clave `format` (inglés, la de la fuente) sobre el bloque
   ya guardado, que la escribe como `formato`. Resultado: la extensión caía
   siempre a `.pdf`, el archivo bajaba bien y la validación por firma lo
   rechazaba por no empezar con `%PDF`. Verificado el 2026-08-05: con la
   extensión correcta, el ZIP de Challhuahuacho baja en **428,781 bytes** y el
   RAR de La Libertad en **1,515,008 bytes**. Ya corregido; se resuelve solo al
   volver a correr las descargas de ese job.

---

## Comprobaciones automatizadas

```
cd backend && ../venv/Scripts/python -m pytest tests/test_candado_seace.py -q
```

32 pruebas offline: promoción, degradación por metadata incompleta,
contradicción por entidad/objeto/fechas, zona gris, monto que ni veta ni
promueve, los 3 rótulos en el Excel y en el índice del ZIP, y la compatibilidad
de un job anterior a F5.

Suite completa del backend: **789 passed, 25 skipped** (línea base antes de F5:
757 / 25 — las 32 nuevas suman, ninguna regresión).

---

## Lo que queda fuera de esta entrega

La **corrida integral en el servidor del cliente** (snapshot previo, corrida con
una propuesta real y comparación del espejo antes/después, donde solo pueden
cambiar los campos `seace.*`). No hay despliegue en esta entrega.
