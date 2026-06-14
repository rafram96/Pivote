# Archivos de la skill `propuestas` de Manuel

Procedencia: **capturas de pantalla parciales** que Manuel compartió el
2026-06-11 (estaba ocupado; no envió los archivos como tal). Transcritas
fielmente aquí. Cierran el **gate G2** (las 15 NOTAS) que el plan venía
esperando — aunque incompletas.

| Archivo | Estado de la captura |
|---|---|
| `reglas.md` | **Parcial** — Parámetros + NOTAS 1-11. Faltan 12-15. |
| `estructura_formato.md` | **Completo** (la captura se ve entera). |
| `build_eval_xlsx.py.parcial.txt` | **Parcial** — ~40 líneas (estilos + `pdate`). |
| `ocr_proposal.py.parcial.txt` | **Parcial** — ~40 líneas (docstring + `ensure_spa`). |

Pendiente pedir a Manuel: NOTAS 12-15 completas y los 2 `.py` enteros.

---

## Reconciliación con nuestra reconstrucción (`docs/backend/validador.md`)

Lo que confirmó, corrigió o agregó respecto a lo que habíamos reconstruido:

### ✅ CONFIRMADO (nuestra reconstrucción era correcta)

- **Ventana COVID = 16/03/2020 – 30/06/2020.** Cierra la duda "15 vs 16/03"
  que arrastraba `contrato_refactor.md`. **16/03 es el correcto** → corregir
  cualquier "15/03" residual en docs.
- **Cutoff de antigüedad del personal clave = 25 años desde la colegiatura.**
  Nuestro ALT03 usa 25 ✓. (Y aclara: el del **postor** son **20 años** desde
  conformidad/pago — distinto; no confundir.)
- **Numeración de NOTAS resuelta** (teníamos ⚠ en 6/8 y 10/11):
  - N6 = una fila por periodo · N7 = orden por fecha de fin · **N8 = no omitir
    ninguna experiencia, cada periodo en su fila** (es refuerzo de atomicidad,
    no "sub-periodos de experiencia efectiva" como supusimos).
  - N10 = ventana COVID · N11 = advertencia/incumplimiento/validación que no
    cumpla → rojo. **Nuestro split 10/11 era correcto.**
- N1 (conteo vs Anexo 16, hasta 4×), N2 (cargo estricto), N3 (ISOs ≥4
  búsquedas), N4 (PMP solo PMI), N5 (certificado manda), N9 (traslape rojo):
  todos coinciden con lo que implementamos.

### ➕ AGREGA / PRECISA (vale incorporar)

- **Límite inferior — regla más rica de lo que teníamos:** 90% de la cuantía +
  regla del 2.º decimal, y **la oferta menor al límite ⇒ DESCALIFICACIÓN**.
  Otros métodos: rango 95%-110% o fija 100% (verificar en Bases). → ampliar
  el chequeo económico del validador/evaluador.
- **Semántica de color del Excel de Manuel:** dentro de la hoja usa
  **rojo `FFC7CE`** = incumple/traslape/COVID y **verde `C6EFCE`** = por
  verificar/duda. Es DISTINTO de nuestro código de origen (amarillo=Claude,
  naranja=backend). Pueden coexistir: el suyo es semántica de contenido, el
  nuestro es procedencia del dato. **Decidir con Manuel si el Excel final
  combina ambas o adopta solo la suya.**
- **Paleta de profesionales** (hoja Base de Datos) — colores exactos de Manuel:
  `["DDEBF7","FCE4D6","E2EFDA","FFF2CC","FBE5D6","E4DFEC","D9E1F2","EAD1DC"]`.
  La nuestra (`excel_final.py`) es la misma idea con orden distinto →
  alinear al orden de Manuel es trivial y deja el Excel idéntico al suyo.

### 🔧 Acciones derivadas

1. Subir `docs/backend/validador.md` de "borrador" a confirmado en N1-N11;
   corregir la numeración 6/8 y marcar 10/11 como confirmadas.
2. Unificar "15/03" → "16/03/2020" donde quede.
3. Alinear `_PALETA_PROF` de `excel_final.py` al orden de Manuel.
4. Evaluar agregar la semántica rojo/verde de contenido al Excel final.
5. Pedir NOTAS 12-15 y los `.py` completos (el `ocr_proposal.py` es el que la
   skill del pivote debe reusar para el Paso 0 — ver [[manuel-ya-tiene-skill-propuestas]]).
