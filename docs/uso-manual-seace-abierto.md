# Manual — bajar Bases Integradas y Contratos A MANO con `seace_abierto`

> **Para quién**: Rafael, operando manualmente mientras el cableado al pipeline
> (F2) no existe. Con esto se produce HOY lo que Manuel pidió en la reunión del
> 29-jul: los PDFs correctos, por experiencia, en carpetas listas para el ZIP.
>
> **Qué hay detrás**: `backend/scraping/seace_abierto.py` (F1, commit `70c78e8`,
> rama `feat/seace-abierto`) · diseño completo en
> `docs/plan-integracion-bases-contrato.md` · 18 tests en
> `backend/tests/test_seace_abierto.py`.

## 0 · Requisitos

- Repo en la rama `feat/seace-abierto` (o donde ya esté mergeada la F1).
- El venv del repo: `venv/Scripts/python.exe` (tiene `requests` y `openpyxl`).
- **IP de Perú** (los hosts del Estado geobloquean desde fuera).
- Los snippets se corren **desde la raíz del repo** (`Pivote/`).

## 1 · Preparar la caché CONOSCE (una sola vez)

Baja los Excel anuales de contratos (2018–2026) a
`backend/datos_pivote/referencia/conosce/`. Después de esto, las consultas de
contratos son 100% offline.

```bash
venv/Scripts/python.exe -c "import sys; sys.path.insert(0,'backend'); from scraping.seace_abierto import CacheConosce; print(CacheConosce().actualizar(datasets=('contratos',)))"
```

Lectura del resultado:

| Campo | Significa |
|---|---|
| `descargados` | años que bajaron ahora |
| `vigentes` | ya estaban en disco (no se piden de nuevo) |
| `fallidos` | el host no los dio — **reintentar más tarde, NO es fatal** |

⚠ `conosce.osce.gob.pe` es **intermitente** (el 27-jul estuvo caído ~1h con
`bi.seace.gob.pe` funcionando). Si todo sale en `fallidos`, no es tu red ni el
código: reintentar en unas horas. Los años ya descargados nunca se pierden.
La API OCDS (paso 2) es OTRO host y suele estar arriba aunque CONOSCE no.

## 2 · La receta por certificado (el flujo completo)

Para cada experiencia a la que quieras bajarle bases + contrato necesitas 3
datos del certificado/análisis:

1. **CUI** de la obra (del Excel del análisis, columna CÓDIGO CUI/SNIP).
2. **Tipo** de la experiencia: `expediente` | `supervision` | `ejecucion`.
3. **Periodo** declarado (fecha inicial y final) — opcional, ayuda a desempatar.

Guarda esto como `descargar_uno.py` en la raíz (o pega en una consola python):

```python
import sys; sys.path.insert(0, "backend")
from datetime import date
from pathlib import Path
from scraping.seace_abierto import (
    procesos_por_cui, seleccionar_proceso, clasificar_proceso,
    doc_bases_integradas, doc_contrato_firmado, descargar_pdf,
    codigo_convocatoria, CacheConosce,
)

# ── EDITAR ESTOS 4 VALORES ──────────────────────────────────────────────
CUI     = "2279396"
TIPO    = "supervision"            # expediente | supervision | ejecucion
PERIODO = (date(2023, 1, 24), date(2023, 11, 30))   # o None
DESTINO = Path("descargas_seace") / f"CUI_{CUI}_{TIPO}"
# ────────────────────────────────────────────────────────────────────────

procs = procesos_por_cui(CUI)
if procs is None:
    raise SystemExit("La API OCDS no respondió — reintentar (no significa que no exista)")
if not procs:
    raise SystemExit(f"El CUI {CUI} no tiene procesos en datos abiertos "
                     "(probable pre-2018) — anotar 'No disponible', NO es un error")

print(f"{len(procs)} proceso(s) del CUI:")
for p in procs:
    t, saldo = clasificar_proceso(p)
    print(f"  [{t}{' +saldo' if saldo else ''}] {p.get('ocid')}")

r = seleccionar_proceso(procs, TIPO, periodo=PERIODO)
print("\nMOTIVO:", r["motivo"])
if r["elegido"] is None:
    raise SystemExit("Sin proceso de ese tipo → 'No disponible en datos abiertos'. "
                     "JAMÁS usar el de otro tipo (regla del cliente).")
if r.get("ambiguo"):
    print("⚠ AMBIGUO: varios procesos del tipo sin fechas para desempatar."
          " VERIFICAR contra el certificado antes de entregar.")

comp = r["elegido"]
DESTINO.mkdir(parents=True, exist_ok=True)
for etiqueta, doc in (("SEACE_01_BASES_INTEGRADAS", doc_bases_integradas(comp)),
                      ("SEACE_02_CONTRATO_FIRMADO", doc_contrato_firmado(comp))):
    if doc is None:
        (DESTINO / f"{etiqueta}_NO_DISPONIBLE.txt").write_text(
            "Este documento no está publicado en los datos abiertos de este proceso.",
            encoding="utf-8")
        print(f"  {etiqueta}: no publicado (queda la nota)")
        continue
    ok = descargar_pdf(doc["url"], DESTINO / f"{etiqueta}.pdf")
    print(f"  {etiqueta}: {'OK' if ok else 'FALLÓ (reintentar luego)'}")

# fechas del contrato para los cruces (T-005) — vía CONOSCE offline si cruza
cod = codigo_convocatoria(comp)
for c in CacheConosce().contrato(cod):
    print("  contrato CONOSCE:", c.get("num_contrato"),
          "| firmado:", c.get("fecha_suscripcion"),
          "| vigencia:", c.get("vigencia_ini"), "→", c.get("vigencia_fin"))
```

```bash
venv/Scripts/python.exe descargar_uno.py
```

### Cómo elegir el TIPO (la regla del cliente, 29-jul)

> «Si estamos en expediente, buscamos solo expediente. Si estamos en
> supervisión de obra, de supervisión o de ejecución.»

| La experiencia del certificado es de… | TIPO |
|---|---|
| Elaboración de expediente técnico / estudio definitivo | `expediente` |
| Supervisión (de obra o del expediente) | `supervision` |
| Residente / ejecución / construcción | `ejecucion` |

**Nunca** entregar las bases de un tipo cuando la experiencia es de otro:
mejor una nota de «No disponible» que el documento equivocado.

## 3 · Qué significa cada resultado (tabla de decisiones)

| El módulo dice | Qué es | Qué haces |
|---|---|---|
| `procesos_por_cui → None` | la API no respondió (portal) | reintentar más tarde; NO anotar «no existe» |
| `procesos_por_cui → []` | el CUI no está en datos abiertos | anotar «No disponible (probable pre-2018)» — es un dato honesto, no un fallo |
| `elegido = None` | hay procesos, pero ninguno del tipo buscado | «El proceso de {tipo} no está en datos abiertos»; el motivo lista qué SÍ había |
| `ambiguo = True` | varios procesos del tipo, sin fechas que desempaten | se eligió el más reciente — **abrir el PDF y verificar** contra el certificado antes de entregar |
| `doc_bases_integradas → None` | el proceso existe pero no publicó las Integradas | nota «no publicado»; NO sustituir por las Administrativas (son la versión previa) |
| `descargar_pdf → False` | la descarga falló o no era un PDF | reintentar; si persiste, anotar y seguir |

## 4 · Armar la entrega para Manuel

Su estructura es carpetas por proyecto (como él lo hace a mano). Con las
descargas de la receta:

```
<Proyecto o Profesional>/
  <Experiencia N>/
    SEACE_01_BASES_INTEGRADAS.pdf
    SEACE_02_CONTRATO_FIRMADO.pdf     (o las notas _NO_DISPONIBLE.txt)
```

- Los nombres `SEACE_01_…`/`SEACE_02_…` son los del diseño (§7 del plan) — al
  cablear F2 el pipeline generará exactamente los mismos, así el entregable
  manual y el automático son indistinguibles.
- **Si `ambiguo=True`, revisar el PDF antes de incluirlo** (nombre de la obra
  y entidad en la carátula de las bases vs el certificado).

## 5 · Problemas conocidos y sus salidas

| Síntoma | Causa | Salida |
|---|---|---|
| Todo CONOSCE en `fallidos` | host intermitente (visto 27-jul: TCP muerto ~1h) | reintentar en horas; el resto del flujo (OCDS) funciona igual |
| `records` responde lento/timeout | portal OCDS cargado | el módulo ya reintenta 3× con backoff; si devuelve None, esperar |
| CUI real pero `[]` | proceso pre-2018 (seacev3 arranca 2018) | «No disponible» honesto; el buscador SEACE con captcha queda como plan B manual |
| `codigo_convocatoria` con guiones (ej. `2022-41-52`) | el sufijo del ocid no siempre es numérico (visto en vivo) | el cruce CONOSCE puede no encontrar ese código; las fechas salen igual del propio OCDS (`dateSigned`) |
| Descarga no es `%PDF` | Alfresco devolvió HTML de error | `descargar_pdf` ya lo detecta y devuelve False; reintentar |
| Corres fuera de Perú | geobloqueo de oece/conosce | solo desde IP Perú (el server del cliente lo es) |

## 6 · Verificación rápida de que todo sigue vivo

```bash
venv/Scripts/python.exe -m pytest backend/tests/test_seace_abierto.py -q
```

18 tests offline (no tocan red). Si pasan, el módulo está íntegro.

## 7 · Dónde está cada cosa

| Qué | Dónde |
|---|---|
| Módulo | `backend/scraping/seace_abierto.py` |
| Tests | `backend/tests/test_seace_abierto.py` |
| Diseño completo (incl. F2/F3 pendientes) | `docs/plan-integracion-bases-contrato.md` |
| Caché de datasets | `backend/datos_pivote/referencia/conosce/` (gitignored) |
| Sondas originales (histórico) | `tools/fuentes_estado/{conosce,ocds}.py` |
| Requisitos del cliente (fuente) | transcripción reunión 29-jul · `.ai/context/current_state.md` |

Caso real de referencia (probado en vivo el 29-jul): CUI **2279396** (Hospital
de Pichanaki) → 5 procesos (2 supervisiones, ejecución+saldo, expediente+saldo,
expediente); la selección de `supervision` eligió el proceso 2022 con Bases
Integradas y contrato firmado descargables.
