# Preparación de PDFs para una corrida de licitación

> Runbook del paso **previo** a correr `analizar-licitacion-osce`: dejar los
> insumos (bases + propuesta) en PDF limpio y legible. NO es la corrida en sí —
> es solo "preparar los PDFs".
>
> Escrito a partir del caso `fixtures/ing manuel/expedientes/first_try`
> (Concurso Público para Consultoría de Obra / expediente técnico, jul-2026).
> Se corre en el Windows de Holbi (poppler MiKTeX + Word instalados; sin
> Tesseract). Ver también [`arquitectura.md`](arquitectura.md) y las memorias
> `bases-integradas-tachado-limpiar`, `entorno-render-pdf-escaneado`,
> `propuestas-grandes-y-verificar-mapa`.

---

## Por qué hay que "preparar" (y no basta con soltar los archivos)

Tres fricciones recurrentes con los insumos que manda el cliente:

1. **Las bases llegan como `.docx` con TACHADO.** En las "Bases Integradas
   Definitivas" de OSCE, el texto tachado (`w:strike`) son **requisitos que se
   ELIMINARON** en la integración (cambios de plazo, meses de experiencia,
   especialidad). En PDF el tachado es solo una línea dibujada → el OCR/visión
   NO lo distingue y lee lo eliminado como vigente, en silencio. **Solo el DOCX
   permite quitarlo de forma determinística.** → Hay que limpiar el DOCX y
   exportarlo a PDF; **nunca** usar un PDF crudo de las bases para requisitos.

2. **La propuesta suele venir escaneada y partida en varios PDFs.** Sin capa de
   texto, y a veces alguna parte pesa cientos de MB. El `Read` **falla con PDFs
   > 100 MB** ("exceeds maximum allowed size"). → Mantener sub-PDFs por parte,
   cada uno < 100 MB; **no fusionar** (el merge se pasaría del límite).

3. **En esta laptop el `Read` no rasteriza PDFs** (falta poppler en el PATH del
   harness) y **no hay Tesseract**. → Para leer PDFs escaneados en la corrida
   hay que **pre-renderizar a PNG** con `pdftoppm` (Camino B: visión nativa de
   Claude sobre las imágenes).

---

## Insumos típicos y cómo clasificarlos

| Tipo | Qué es | Trae texto | Acción de preparación |
|---|---|---|---|
| **Bases** | `BASES INTEGRADAS DEFINITIVAS*.docx` | (DOCX) | Limpiar tachado → PDF |
| **Propuesta técnica-económica** | `OFERTA TEC_ECON PARTE 1..N.pdf` | No (escaneada) | Verificar < 100 MB c/u; pre-render a PNG para la corrida |
| **Oferta económica** | `OFERTA ECONOMICA*.pdf` | No (escaneada) | Igual que la propuesta |
| **Apoyo** | `PRONUNCIAMIENTO*.pdf`, `ESTRUCTURA DE COSTOS.pdf` | Sí (born-digital) | Ninguna; referencia |

---

## Procedimiento

### Paso 1 — Inventario: detectar escaneado vs. con texto

Cuenta páginas y mide cuánto texto real trae cada PDF (si `pdftotext` devuelve
casi nada en las primeras páginas → escaneado → habrá que renderizar).

```bash
cd "<carpeta_del_concurso>"
for f in *.pdf; do
  chars=$(pdftotext -f 1 -l 5 "$f" - 2>/dev/null | tr -d '[:space:]' | wc -c)
  pages=$(pdfinfo "$f" 2>/dev/null | grep -i '^Pages' | awk '{print $2}')
  printf '%-55s pags=%-5s chars(p1-5)=%s\n' "$f" "${pages:-?}" "$chars"
done
```

Regla de dedo: `chars(p1-5)` de unas pocas decenas = **escaneado**; de miles =
**con capa de texto**.

### Paso 2 — Bases: limpiar el tachado del DOCX → PDF

El script quita los runs `w:strike`/`w:dstrike` (document.xml + headers/footers)
con `lxml` — round-trip por `zipfile`, preserva namespaces, tablas y layout — y
convierte a PDF con **Word COM** (`ExportAsFixedFormat(..., 17)`, fidelidad
total). En Cowork/Linux cae a `soffice` headless.

```bash
cd "C:/Users/Holbi/Documents/Freelance/proyectos/InfoObras/Pivote"
venv/Scripts/python.exe skill/scripts/limpiar_bases_docx.py \
  "<carpeta>/BASES INTEGRADAS DEFINITIVAS (1).docx" \
  "<carpeta>/bases_limpio.pdf"
# stderr: "tachados removidos: N"   ·   stdout (última línea): ruta del PDF limpio
```

> ⚠ **Ese `bases_limpio.pdf` es el `bases.pdf` de la corrida.** No usar el DOCX
> ni un PDF crudo de las bases: el tachado ya está removido de forma
> determinística. La misma técnica está ruteada en `agent-bases` **Paso 0**
> (`.docx` = script determinístico; `.pdf` = leer por visión y excluir el
> tachado a ojo).

### Paso 3 — Verificar el PDF limpio de bases

Un número alto de tachados removidos es normal (son *runs*, no palabras: una
frase tachada son muchos runs). Aun así conviene confirmar que los requisitos
clave quedaron **coherentes, no truncados**.

```bash
pdfinfo bases_limpio.pdf | grep -iE '^(Pages|Page size)'
pdftotext bases_limpio.pdf - | grep -niE "experiencia|meses|personal clave|especialista" | head
```

Checklist de coherencia: el objeto del contrato, el **plazo**, los **meses de
experiencia** por cargo y el roster de **personal clave** (sección B.1) se leen
completos y con sentido.

### Paso 4 — Propuesta: confirmar tamaños, no fusionar

Cada parte debe quedar **< 100 MB**. Si alguna se pasa, trocearla por propósito
con PyMuPDF (front/anexos, pc = personal clave, exp = experiencias) pasando a
los subagentes **páginas locales con su offset**. Aquí las 5 partes ya venían
< 100 MB → se dejan tal cual, como sub-PDFs. **No fusionar** (el total superaría
el límite del `Read`).

### Paso 5 — Pre-render a PNG (para la CORRIDA, no para "solo los PDFs")

Como el `Read` no rasteriza en esta laptop, antes de lanzar los subagentes hay
que convertir a imágenes lo escaneado (y, por la misma limitación de poppler,
también conviene renderizar la bases born-digital si se va a leer con `Read`):

```bash
RAST="C:/Users/Holbi/AppData/Local/Programs/MiKTeX/miktex/bin/x64/pdftoppm"
"$RAST" -png -r 120 "parte1.pdf" "img_prop/p1_"   # → p1_-001.png … (relleno 3 díg.)
```

- **Folio ↔ página:** en la propuesta **folio = página (1:1)**. En las bases el
  offset depende del documento (el impreso puede ir corrido respecto a la página
  física) → **verificar caso a caso**, no asumir un offset fijo.
- Se pasa a cada subagente la **carpeta de PNG por rangos de página**, no el PDF.

---

## Resultado del caso `first_try` (referencia)

Corrida del 2026-07-14. Concurso Público para **Consultoría de Obra**
(elaboración de expediente técnico).

**Bases** — único insumo que no era PDF:
- `bases_limpio.pdf` — **206 págs, A4, con capa de texto**, generado del DOCX
  quitando **738 runs tachados**. ✅ Requisitos verificados coherentes:
  experiencia **18 meses** (jefe/estructuras) y **12 meses** (otros cargos) "en
  el cargo… en expedientes"; personal clave completo (Arquitectura, Equipamiento
  y Mobiliario, Estructuras, Instalaciones Sanitarias, Costos y Presupuestos…);
  sección B.1 presente.

**Propuesta** — ya en PDF, escaneada (sin capa de texto):

| Archivo | Págs | < 100 MB |
|---|---|---|
| `1.+OFERTA+TEC_ECON_PARTE_1_OK.pdf` | 40 | ✅ 25 MB |
| `1.1+…PARTE_2_OK.pdf` | 59 | ✅ 50 MB |
| `1.2+…PARTE_3_OK.pdf` | 140 | ✅ 77 MB |
| `1.3+…PARTE_4.pdf` | 9 | ✅ 9 MB |
| `1.4+…PARTE_5_ok.pdf` | 93 | ✅ 62 MB |
| **Total técnico-económica** | **341** | |
| `2.+OFERTA+ECONOMICA_…pdf` | 3 | ✅ 2 MB (escaneada) |

**Apoyo** (born-digital, con texto): `PRONUNCIAMIENTO…pdf` (95 págs) +
`ESTRUCTURA DE COSTOS.pdf` (1 pág).

**Pendiente para la corrida:** pre-render a PNG de las 341 págs de propuesta
(Paso 5) — no se hizo porque el pedido fue "solo preparar los PDFs".

---

## Gotchas

- El PDF de Word sale **born-digital con texto** → el `pdftotext` de arriba lo
  lee bien (los `�` en la terminal son solo encoding de la consola, el PDF está
  OK).
- Cuidado con substrings: una frase legítima puede contener texto que también
  aparece tachado (ej. "SALDO DE OBRA" como objeto del contrato vs. la
  especialidad tachada). El script filtra por la **máscara `w:strike` run a
  run**, no por substring — por eso es confiable.
- `pdftoppm` de MiKTeX imprime un warning de "MiKTeX requires Windows 10" pero
  **renderiza bien**.
- Requisitos del script: `lxml` (en el venv) + Microsoft Word (Windows) o
  `soffice` (Linux/Cowork).
