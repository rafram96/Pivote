# Comprobación del camino A (expedientes) — 2026-08-06

> Camino A = experiencias de la familia expediente: **elaboración del ET**,
> **estudio de preinversión/perfil/factibilidad** y **supervisión de la
> elaboración del ET**. Comprobado offline con el código real del backend
> (`es_expediente_exp` → `tipo_esperado` → `seleccionar_proceso`), sin red.
> Suite de referencia: 18 tests de expedientes en verde (`pytest -k "exped or
> preinversion"`), 967/25 la suite completa.

## Resultado del enrutado (calculado, no supuesto)

| Caso | `es_expediente_exp` | Busca proceso | Resultado |
|---|---|---|---|
| Elaboración del ET (proceso de consultoría ET en el CUI) | True | `expediente` | ✔ **seleccionado** — candado F5 + Regla A/B operan |
| Elaboración del ET (CUI sin procesos 2018+) | True | `expediente` | `sin_procesos` — abstención honesta |
| **Estudio de preinversión** (el CUI solo tiene proceso de preinversión) | True | `expediente` | ⚠ **sin_tipo** — «procesos vistos: preinversion» |
| **Supervisión de la elaboración del ET** (el CUI tiene el proceso de supervisión) | True | `expediente` | ⚠ **sin_tipo** — «procesos vistos: supervision» |

## Lo que funciona

1. **Clasificación de experiencias**: las 3 variantes clasifican como expediente,
   incluso cuando la palabra clave vive en `objeto`/`cargo_ocupado` y no en
   `proyecto` (caso San Isidro). Modo `PIVOTE_FORZAR_EXPEDIENTES=1` disponible
   para concursos 100% de expedientes.
2. **Enriquecimiento**: verificación MEF 08-A (contratista/contrato/resolución
   con veredictos ✔/✗), aprobación del proyecto de InfoObras como respaldo, sin
   clamp por valorizaciones de la construcción posterior.
3. **Regla B con gate anti-circularidad**: con contratista MEF en
   `discrepancia`, la regla de fechas SE ABSTIENE (no dispara contra el
   profesional) — exige `verificado_en_mef` + contratista `ok`
   (`reglas/cruces_fechas.py:253-265`). Verificado en el demo.

## Los 2 huecos (registrados en la issue #70)

`tipo_esperado()` (`scraping/seace_abierto.py:441`) devuelve siempre
`expediente` para toda la familia — nunca `preinversion` ni `supervision`.
Como `seleccionar_proceso` jamás cruza de tipo (requisito del cliente, 29-jul),
las variantes **estudio de preinversión** y **supervisión del ET** caen en
`sin_tipo`:

- La abstención es honesta (nunca un falso match ni un falso incumplimiento),
- pero esas experiencias quedan **sin candado F5, sin Regla A y sin
  Bases/Contrato en el ZIP**.

El fix probable —que `tipo_esperado` distinga las sub-variantes— toca el
requisito «no cruzar de tipo» y se decide dentro del diseño de la #70, no como
parche.

## Cómo reproducir

Los generadores de los dos Excel de demostración (datos 100% sintéticos, 3
profesionales / 4 CUIs cada uno) viven en el scratchpad de la sesión del
2026-08-06 (`generar_excel_demo.py` camino B, `generar_excel_camino_a.py`
camino A). El sondeo del enrutado se reproduce en 10 líneas:

```python
from resolucion.cui import es_expediente_exp
from scraping.seace_abierto import tipo_esperado, seleccionar_proceso

exp = {"proyecto": "ESTUDIO DE PREINVERSIÓN A NIVEL DE PERFIL: ...", "cargo_ocupado": "Formulador"}
tipo = tipo_esperado(es_expediente_exp(exp), exp["proyecto"])   # → "expediente"
procesos = [{"ocid": "x", "tender": {"title": "ELABORACION DEL ESTUDIO DE PREINVERSION ..."}}]
seleccionar_proceso(procesos, tipo)["motivo"]
# → "el CUI no tiene proceso de expediente en datos abiertos (procesos vistos: preinversion)"
```

## Feedback de presentación registrado (Rafael, 6-ago)

El bloque de cronología/cruces **en las hojas por profesional** es complicado
de leer; evaluar un **formato vertical**. Tarea registrada en
`.ai/tasks/backlog.md` (T-TAREA-CRONOLOGIA-VERTICAL). La hoja global
«Cronología de expedientes» no recibió la misma observación.
