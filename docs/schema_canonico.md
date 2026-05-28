# Fase 1 — Schema JSON canónico (v2)

> Contrato de datos entre Claude (máquina del cliente) y el backend on-prem.
>
> **Modelo v2**: la skill produce **3 JSONs separados** (uno por paso del manual)
> y el backend los consume para generar Pasos 4-5 + enriquecimiento + Excel
> Lircay. Anclado en:
> - El **Excel real del ingeniero** (`Alpamayo-InfoObras/variety/tools/excel_reader/10. Lircay  16.04.26.xlsx`)
> - El **manual del proceso** (`Alpamayo-InfoObras/docs/analisis/manual.md`)
> - Los **3 Excels que produjo Claude** sobre el caso Lircay CP-02-2025
> - Los **goldens previos** `rtm_huancavelica_literal.json` y `rtm_urcos_literal.json`

---

## 1 · Visión general

La skill `analizar-licitacion-osce` produce **3 archivos JSON** (uno por paso
de extracción según el manual):

```
analisis-{slug}--{timestamp}/
├── bases.json              (~5 KB)   ← Paso 1, output de agent-bases
├── profesionales.json      (~3 KB)   ← Paso 2, output de agent-propuesta
└── experiencias.json       (~50 KB)  ← Paso 3, output de agent-propuesta
```

> `agent-propuesta` lee el PDF de propuesta **una sola vez** y produce dos
> JSONs (profesionales + experiencias) para garantizar consistencia entre
> ellos (mismos `n_prof`).

Estos 3 JSONs son **inputs** al backend. El backend produce:
- Enriquecimiento de `experiencias.json` con SUNAT + InfoObras + duración + alertas
- `evaluacion.json` (Paso 4) — cruce determinístico de bases × experiencias
- `anos.json` (Paso 5) — agregación de años efectivos por profesional
- Excel Lircay final (4-5 hojas) con headers literales del ingeniero

---

## 2 · Mecanismos de metadata por JSON

Cada JSON tiene tres mecanismos complementarios encima del payload:

| Mecanismo | Granularidad | Para qué |
|---|---|---|
| `_meta` | Por JSON | Identificación (analisis_id, subagente, version, fecha, fuente PDF) |
| `_flags` | Por campo de item | Marcadores binarios atómicos. Ej: `{"universidad": "verificar_folio_no_extraido"}` |
| `observaciones_claude` | Por JSON, con referencia opcional a item | Observaciones cualitativas con severidad |

### `_meta`

```python
class Meta(BaseModel):
    analisis_id: str                # "lircay-cp02-2025--2026-05-27T18-30-00"
    subagente: Literal["agent-bases", "agent-propuesta"]
    version_skill: str              # "0.1.0"
    fecha_extraccion: datetime      # ISO 8601
    fuente_pdf: str                 # nombre del PDF original (sin ruta)
```

### `observaciones_claude`

```python
class Observacion(BaseModel):
    codigo: str                     # estable, machine-readable: "FECHA_COLEGIACION_ILEGIBLE"
    tipo: Literal[
        "ilegibilidad",             # texto/sello/firma no legible
        "ambiguedad",               # dato dudoso o con interpretación posible
        "duplicado_posible",        # entrada que parece repetida
        "inconsistencia",           # datos que se contradicen
        "calidad_documento",        # PDF rotado, escaneo malo, páginas faltantes
        "hallazgo_relevante",       # algo notable que debería revisarse
        "alerta_manual",            # requiere intervención humana sí o sí
        "extraccion_parcial",       # se extrajo pero con limitaciones
    ]
    severidad: Literal["info", "warning", "critical"]
    origen: Literal["claude", "backend"]
    mensaje: str                    # texto humano legible
    referencia: ReferenciaItem | None  # apunta al item afectado; null si es global

class ReferenciaItem(BaseModel):
    item_tipo: Literal["cargo", "profesional", "experiencia", "factor"] | None
    item_id: int | str | list | None    # n_prof, n_correlativo, o lista
    campo: str | None                   # nombre del campo afectado
    folio_pdf: str | None
    pagina_pdf: int | None
```

> **Diferencia entre `_flags` y `observaciones_claude`**:
> - `_flags` es **estructural** y atómico (no se pudo extraer un campo específico).
> - `observaciones_claude` es **narrativo** con severidad y referencia opcional —
>   contexto que un humano notaría pero el motor determinístico no captura.

---

## 3 · Identificador común (`analisis_id`)

```
analisis_id = "{nomenclatura_slug}--{timestamp_iso}"
            = "lircay-cp02-2025--2026-05-27T18-30-00"
```

- `nomenclatura_slug`: derivado de `metadata_concurso.nomenclatura`, lowercased y slugificado.
- `timestamp_iso`: ISO 8601 filesystem-friendly (sin `:`).

La skill lo genera **al iniciar** y se lo pasa a los 2 subagentes. Los 3 JSONs
comparten el mismo `analisis_id` en su `_meta`. El backend valida que los 3
JSONs recibidos coincidan en `analisis_id`.

---

## 4 · `bases.json` (Paso 1, output de `agent-bases`)

```json
{
  "_meta": { ... },
  "metadata_concurso": { ... },
  "factores_evaluacion": { ... },
  "personal_clave": [ ... ],
  "observaciones_claude": [ ... ]
}
```

### `metadata_concurso`

```python
class MetadataConcurso(BaseModel):
    nomenclatura: str               # "CP N° 02-2025/GOB.REG.HVCA/C"
    entidad: str                    # "Gobierno Regional de Huancavelica"
    objeto: str                     # "Supervisión Hospital II-1 Lircay"
    fuente_bases: str               # "Bases Integradas Definitivas (30.03.26)"
    especialidad: str               # "Edificaciones y Afines"
    subespecialidad: str | None     # "Establecimientos de Salud"
    fecha_presentacion_oferta: date # ISO; backend la necesita para Paso 5
```

> Si `fecha_presentacion_oferta` no aparece, Claude la deja `null` y emite
> una observación `severidad: critical` — el backend no puede calcular Paso 5
> sin ella.

### `factores_evaluacion`

```python
class FactorEvaluacion(BaseModel):
    codigo: str                     # "A", "B", "J", "G", etc.
    nombre: str                     # "Tiempo Adicional"
    max_pts: int                    # 45
    aplica_a: Literal[
        "profesional_individual",   # cada profesional acumula puntaje
        "grupo_profesionales",      # se evalúa al equipo globalmente
        "postor",                   # aplica a la empresa
    ]
    criterios: list[str]            # texto literal
    aplica_a_cargos: list[int]      # números de cargo (1-17) si es selectivo

class FactoresEvaluacion(BaseModel):
    factor_a: FactorEvaluacion
    factor_b: FactorEvaluacion
    factor_j: FactorEvaluacion | None
    factor_g: FactorEvaluacion | None
    otros: list[FactorEvaluacion]
```

### `personal_clave`

Una entrada por cargo requerido. Anclado en el Excel Paso 1 de Claude (17 cargos
para Lircay).

```python
class CargoBases(BaseModel):
    numero: int                          # 1..17, orden de las bases
    cargo: str                           # "GERENTE DE CONTRATO"
    profesiones_aceptadas: list[str]     # ["Ingeniero Civil", "Arquitecto"]

    anos_colegiado_min: int | None
    requiere_titulo_y_colegiatura: bool

    experiencia_minima_unidad: Literal["meses", "anos"]
    experiencia_minima_cantidad: int     # 24 meses, 36 meses, etc.
    cargos_similares_validos: list[str]  # lista literal de las bases

    tipo_experiencia_similar: str        # texto literal
    tipos_obra_validos: list[str]        # parseado

    # Factor A
    factor_a_aplica: bool                # ✔ INCLUIDO / ✘ NO incluido
    factor_a_detalle: str | None

    # Capacitación (Factor B)
    factor_b_aplica: bool
    es_lider_equipo: bool                # marca "(LÍDER)" en bases
    certificaciones_factor_b: list[str]
    factor_b_puntaje_individual: int

    # Otras (postor)
    certificaciones_postor: list[str]
```

---

## 5 · `profesionales.json` (Paso 2, output de `agent-propuesta`)

Lista limpia de profesionales propuestos. Anclado en la hoja `PROFESIONALES`
del Excel del ingeniero (18 filas × 7 cols).

```json
{
  "_meta": { ... },
  "profesionales": [ ... ],
  "observaciones_claude": [ ... ]
}
```

```python
class ProfesionalPropuesto(BaseModel):
    n_prof: int                          # 1..N, orden de la propuesta
    nombre: str                          # "MANUEL ECHANDIA MORENO" (uppercase preservada del PDF)
    profesion: str                       # "INGENIERO CIVIL"
    fecha_colegiacion: date | str | None # ISO; o string libre si es ilegible/parcial
    especialidad_postulada: str          # "GERENTE DE CONTRATO"

    # ⭐ Convención del ingeniero: 2 folios distintos
    folio_colegiatura: str               # "1691" — folio del certificado de colegiatura
    folio_nombre_propuesta: str          # "1690" — folio donde aparece el nombre en la propuesta

    # Estos campos los deja Claude null si no se ven claros en el PDF
    # → el backend NO los rellena tampoco
    universidad_titulacion: str | None
    fecha_titulacion: date | None

    _flags: dict[str, str]               # ej: {"universidad": "verificar_folio_no_extraido"}
```

> **Sobre `fecha_colegiacion`**: el ingeniero acepta valores no normalizados
> (`"30 de abril de 1995"`, `"Ilegible / Año 1978"`, datetime). Internamente
> intentamos parsear a ISO `YYYY-MM-DD`; si no se puede, lo dejamos como string
> y emitimos una observación de tipo `ilegibilidad` o `extraccion_parcial`.

---

## 6 · `experiencias.json` (Paso 3, output de `agent-propuesta`)

BD atómica de experiencias. **El JSON más grande y crítico.** Anclado en la
hoja `BD roberto` del ingeniero (63 filas × 27 cols).

```json
{
  "_meta": { ... },
  "experiencias": [ ... ],
  "observaciones_claude": [ ... ]
}
```

```python
class ExperienciaPeriodo(BaseModel):
    n_correlativo: int                   # 1..N, orden global atómico
    n_prof: int                          # FK a profesionales.json

    # ── Datos del proyecto ──────────────────────────────────────────────────
    proyecto: str                        # nombre completo
    cargo_desempenado: str               # "Gerente de Supervisión"

    # ── Emisor del certificado ──────────────────────────────────────────────
    empresa_emisora: str                 # "INSTITUTO DE CONSULTORIA S.A."
    ruc_emisor: str | None               # "20263373058" / null

    # ── Clasificación ───────────────────────────────────────────────────────
    publica_o_privada: Literal["Pública", "Privada"] | None
    tipo_acreditacion: str               # "Emitido por el Contratista", "Dueño del contrato", etc.

    # ── Fechas ──────────────────────────────────────────────────────────────
    fecha_inicio: date
    fecha_culminacion: date | None       # null si la obra no terminó
    # alerta_covid la calcula Claude (regla: 15/03/2020 cae entre inicio y fin)
    alerta_covid: str | None             # "INCLUYE PERIODO COVID" o null

    # ── Certificado ─────────────────────────────────────────────────────────
    fecha_emision_cert: date
    n_folio: str                         # "1791" (str para preservar leading zeros)
    firmante_certificado: str            # "Danitza Z. Echandia Moreno"
    cargo_firmante: str | None           # "Representante Legal"
    tipo_documento: str                  # "Constancia", "Carta", "Certificado", etc.

    # ⭐ Capacidades nuevas (extrae Claude, no el motor backend)
    nivel_categoria: str | None          # "II-1", "II-2", "Centro de Salud", null
    area_construida_m2: Decimal | None
    monto_contrato_soles: Decimal | None
    ubicacion: str                       # "Cerro Colorado – Arequipa – Arequipa"
    entidad_contratante: str             # "ESSALUD / Gobierno Regional Arequipa"

    # ── Alertas que SÍ calcula Claude ───────────────────────────────────────
    alerta_exp_antes_titulacion: str | None
    alerta_cert_antes_culminacion: str | None
    observaciones_fila: str | None       # campo libre Col 28 del prompt

    # ⚠ CAMPOS QUE CLAUDE DEJA null — BACKEND LOS RELLENA:
    #   - fecha_creacion_emisor (SUNAT)
    #   - alerta_antiguedad_emisor (ALT04)
    #   - alerta_firmante_no_representante (ALT12)
    #   - duracion_meses (calculable; backend la genera consistentemente)
    #   - codigo_ciu (InfoObras)
    #   - codigo_infoobras (InfoObras)
    #   - alerta_experiencia_antigua (cutoff 25 años desde fecha_presentacion_oferta)

    _flags: dict[str, str]
```

> **Nota sobre cols 12-13 vacías del manual**: en el JSON canónico NO existen
> placeholder vacíos — ese era artefacto del Excel. El JSON tiene solo los
> campos con semántica.

---

## 7 · Relaciones entre los 3 JSONs

```
bases.json                  profesionales.json           experiencias.json
─────────                   ─────────────                ─────────────
_meta.analisis_id ◄────────────► _meta.analisis_id ◄──────► _meta.analisis_id
                                 (mismo en los 3)

personal_clave[].cargo  ◄──┐                             ┌──► n_prof
                           │                             │
                           └──── (cruce conceptual ──────┘
                                  para evaluación —
                                  lo hace backend)
                                                            
                            profesionales[].n_prof ◄──FK── experiencias[].n_prof
```

**FK lógicas que el backend valida al recibir los 3 JSONs**:
- Todos los `experiencias[].n_prof` existen en `profesionales[].n_prof`.
- Todos los `experiencias[].cargo_postulado` (derivado del cargo del profesional)
  matchean con algún `personal_clave[].cargo`.
- Los 3 `_meta.analisis_id` son idénticos.

---

## 8 · Contrato de responsabilidades (Claude vs Backend)

### Skill (Claude) — extracción pura

| JSON | Genera |
|---|---|
| `bases.json` | metadata_concurso, factores_evaluacion, personal_clave[] |
| `profesionales.json` | profesionales[] con `folio_colegiatura` + `folio_nombre_propuesta` |
| `experiencias.json` | experiencias[] (sin SUNAT, sin InfoObras, sin duración, sin alerta_>20años) |
| Todos | `_meta` + `observaciones_claude[]` |

### Backend (Alpamayo on-prem) — procesamiento + enriquecimiento

| Tarea | Origen del dato |
|---|---|
| `fecha_creacion_emisor` por RUC | Scraping SUNAT (`src/scraping/sunat.py`) |
| `alerta_antiguedad_emisor` (ALT04) | Cálculo sobre datos SUNAT |
| `alerta_firmante_no_representante` (ALT12) | Comparación firmante vs representantes SUNAT |
| `codigo_ciu`, `codigo_infoobras` | Scraping InfoObras (`src/scraping/infoobras.py`) |
| `paralizaciones` | InfoObras (no aparece en el JSON Claude) |
| `duracion_meses` | Cálculo (fecha_culminacion - fecha_inicio) |
| `alerta_experiencia_antigua` | Cutoff **25 años** desde `fecha_presentacion_oferta` |
| Paso 4: Evaluación RTM (motor determinístico) | Cruce `bases.json` × `experiencias.json` enriquecido |
| Paso 5: Años acumulados / días efectivos | Agregación por profesional + descuento paralizaciones + COVID |
| Excel Lircay (4-5 hojas) | Render final con headers literales del ingeniero |

---

## 9 · Mapeo Excel del ingeniero → JSON canónico

### Hoja `PROFESIONALES` (18 × 7) → `profesionales.json`

| Col del ingeniero | Campo JSON |
|---|---|
| Col 1: Nombre del Profesional | `nombre` |
| Col 2: Profesión | `profesion` |
| Col 3: Fecha de colegiación | `fecha_colegiacion` (ISO interno) |
| Col 4: Especialidad a la que postulan | `especialidad_postulada` |
| Col 5: Folio de la colegiatura | `folio_colegiatura` |
| Col 6: Folio del nombre del profesional | `folio_nombre_propuesta` |

### Hoja `BD roberto` (63 × 27) → `experiencias.json`

| Col del ingeniero | Campo JSON | Quién llena |
|---|---|---|
| Col 1: Nombre del Profesional | (derivado vía n_prof → profesionales) | Claude (referencia) |
| Col 2: DNI / Colegiatura | (derivado del profesional) | Claude |
| Col 3: Nombre del proyecto | `proyecto` | Claude |
| Col 4: Cargo en el proyecto | `cargo_desempenado` | Claude |
| Col 5: Consorcio o empresa emisora | `empresa_emisora` | Claude |
| Col 6: RUC emisor | `ruc_emisor` | Claude |
| Col 7: Pública o Privada | `publica_o_privada` | Claude |
| Col 8: Tipo de acreditación | `tipo_acreditacion` | Claude |
| Col 9: Fecha de inicio | `fecha_inicio` | Claude |
| Col 10: Fecha de fin | `fecha_culminacion` | Claude |
| Col 11: Alerta COVID | `alerta_covid` | Claude |
| Col 12, 13: (vacías) | — | (no existen en JSON) |
| Col 14: Duración | `duracion_meses` | **Backend** |
| Col 15: Fecha de emisión | `fecha_emision_cert` | Claude |
| Col 16: ALERTA emisión | `alerta_cert_antes_culminacion` | Claude |
| Col 17: Folio | `n_folio` | Claude |
| Col 18: Firma el certificado | `firmante_certificado` | Claude |
| Col 19: Cargo del firmante | `cargo_firmante` | Claude |
| Col 20: ALERTA no representante | `alerta_firmante_no_representante` | **Backend** (SUNAT) |
| Col 21: Fecha creación (SUNAT) | `fecha_creacion_emisor` | **Backend** (SUNAT) |
| Col 22: ALERTA creación | `alerta_antiguedad_emisor` | **Backend** (SUNAT) |
| Col 23: ALERTA > 20 años | `alerta_experiencia_antigua` (con cutoff 25) | **Backend** |
| Col 24: Documento presentado | `tipo_documento` | Claude |
| Col 25: Código CIU / CUI | `codigo_ciu` | **Backend** (InfoObras) |
| Col 26: Código infoobras | `codigo_infoobras` | **Backend** (InfoObras) |
| Col 27: Fecha creación y ALERTA | (redundante con Col 21+22) | **Backend** |

### Hoja `ANAISIS BD` (63 × 25) → output del **backend**

Esta hoja **NO es output de Claude**. El backend la genera cruzando
`bases.json` × `experiencias.json` enriquecido.

---

## 10 · Decisiones de formato (interno vs render Excel)

### Capa interna (JSON)

- ISO `YYYY-MM-DD` para fechas. Strings libres para fechas no parseables, con observación.
- `null` para datos no extraídos; `_flags` cuando hay marcador binario.
- `Decimal` para montos / áreas (no float, evita problemas de precisión).
- Razones siempre presentes (auditoría).
- `c10 ≡ c7` (typo del prompt) NO se duplica en el JSON.

### Capa render (Excel Lircay)

- Headers **literales del ingeniero** (`Col 1: Nombre del Profesional`, etc.).
- Cardinalidad de columnas idéntica al Excel del ingeniero.
- `"No disponible"` (string) cuando el backend no obtuvo el dato (en lugar de celda vacía).
- Fechas: formato `dd.mm.yyyy` o como el ingeniero las muestra (a definir con Manuel).
- Razones literales solo cuando NO cumple; cuando cumple, mostrar solo `SI` / `CUMPLE`.
- DNI / Colegiatura **renderizados juntos** en Col 2 (aunque internamente sean campos separados).
- `c10 ≡ c7` **se duplica** en el Excel (porque así está en el del ingeniero).

---

## 11 · Discrepancias conocidas

| Discrepancia | Solución |
|---|---|
| Excel Paso 4 c10 ≡ c7 (typo de Manuel) | JSON tiene UN campo `cargos_validos_bases`. Render Excel duplica la columna por consistencia con el ingeniero. |
| Manual.md dice 22 cols Paso 4 vs ingeniero usa 25 | El render del Excel usa 25 (formato real del ingeniero). |
| Manual.md dice 27 cols Paso 3, ingeniero usa 27 | Coincide. Cols 12-13 vacías en ambos. |
| Claude (49) vs ingeniero (62) experiencias | Documentos distintos. Verificar atomicidad de periodos en el prompt de `agent-propuesta`. |
| Excel ingeniero Col 11 BD: header dice "Alerta COVID" pero valor es numérico | El JSON respeta el header (alerta COVID textual). La duración tiene su columna (Col 14). |
| Excel ingeniero: CIU = código InfoObras (mismo valor) | Backend distingue ambos (son campos diferentes según el manual). Si coinciden, los pone iguales; si no, pone distintos. |
| Claude pone "Verificar folio" en universidad / fecha_titulación | JSON los pone `null` + `_flags[...] = "verificar_folio_no_extraido"`. |
| Cutoff 20 años del ingeniero vs 25 del CLAUDE.md de Alpamayo | Backend recalcula con 25. El ingeniero no se entera de la diferencia (en el render se muestra el cálculo nuevo). |

---

## 12 · Ejemplo abreviado (los 3 JSONs)

### `bases.json`

```json
{
  "_meta": {
    "analisis_id": "lircay-cp02-2025--2026-05-27T18-30-00",
    "subagente": "agent-bases",
    "version_skill": "0.1.0",
    "fecha_extraccion": "2026-05-27T18:30:00",
    "fuente_pdf": "bases-integradas-30.03.26.pdf"
  },
  "metadata_concurso": {
    "nomenclatura": "CP N° 02-2025/GOB.REG.HVCA/C",
    "entidad": "Gobierno Regional de Huancavelica",
    "objeto": "Supervisión Hospital II-1 Lircay",
    "fuente_bases": "Bases Integradas Definitivas (30.03.26)",
    "especialidad": "Edificaciones y Afines",
    "subespecialidad": "Establecimientos de Salud",
    "fecha_presentacion_oferta": "2026-04-16"
  },
  "factores_evaluacion": {
    "factor_a": {
      "codigo": "A",
      "nombre": "Tiempo Adicional",
      "max_pts": 45,
      "aplica_a": "grupo_profesionales",
      "criterios": ["..."],
      "aplica_a_cargos": [1, 2, 4, 5, 6, 7, 11, 12, 14, 15, 16, 17]
    }
  },
  "personal_clave": [
    {
      "numero": 1,
      "cargo": "GERENTE DE CONTRATO",
      "profesiones_aceptadas": ["Ingeniero Civil", "Arquitecto"],
      "anos_colegiado_min": null,
      "requiere_titulo_y_colegiatura": true,
      "experiencia_minima_unidad": "meses",
      "experiencia_minima_cantidad": 24,
      "cargos_similares_validos": ["Gerente de Obra", "Gerente de Proyecto"],
      "tipos_obra_validos": ["Establecimientos de Salud"],
      "factor_a_aplica": true,
      "factor_b_aplica": true,
      "es_lider_equipo": false,
      "certificaciones_factor_b": ["PMP (PMI)", "PMI-CP™ (PMI)"],
      "factor_b_puntaje_individual": 2,
      "certificaciones_postor": ["ISO 9001:2015", "ISO 37001:2016"]
    }
  ],
  "observaciones_claude": []
}
```

### `profesionales.json`

```json
{
  "_meta": {
    "analisis_id": "lircay-cp02-2025--2026-05-27T18-30-00",
    "subagente": "agent-propuesta",
    "version_skill": "0.1.0",
    "fecha_extraccion": "2026-05-27T18:31:00",
    "fuente_pdf": "propuesta-tecnica-postor.pdf"
  },
  "profesionales": [
    {
      "n_prof": 1,
      "nombre": "MANUEL ECHANDIA MORENO",
      "profesion": "INGENIERO CIVIL",
      "fecha_colegiacion": "2022-04-19",
      "especialidad_postulada": "GERENTE DE CONTRATO",
      "folio_colegiatura": "1691",
      "folio_nombre_propuesta": "1690",
      "universidad_titulacion": null,
      "fecha_titulacion": null,
      "_flags": {
        "universidad": "verificar_folio_no_extraido",
        "fecha_titulacion": "verificar_folio_no_extraido"
      }
    }
  ],
  "observaciones_claude": [
    {
      "codigo": "FECHA_COLEGIACION_ILEGIBLE",
      "tipo": "ilegibilidad",
      "severidad": "warning",
      "origen": "claude",
      "mensaje": "La fecha de colegiación de CESAR GUILLERMO URTEAGA ARAUJO aparece como 'Ilegible / Año 1978' en la constancia. Solo se preservó el año estimado en formato libre.",
      "referencia": {
        "item_tipo": "profesional",
        "item_id": 5,
        "campo": "fecha_colegiacion",
        "folio_pdf": "1707",
        "pagina_pdf": null
      }
    }
  ]
}
```

### `experiencias.json`

```json
{
  "_meta": {
    "analisis_id": "lircay-cp02-2025--2026-05-27T18-30-00",
    "subagente": "agent-propuesta",
    "version_skill": "0.1.0",
    "fecha_extraccion": "2026-05-27T18:31:00",
    "fuente_pdf": "propuesta-tecnica-postor.pdf"
  },
  "experiencias": [
    {
      "n_correlativo": 1,
      "n_prof": 1,
      "proyecto": "SUPERVISION DE OBRA 'CONSTRUCCION DEL SALDO DE OBRA DEL HOSPITAL II-1 DE SAN IGNACIO'",
      "cargo_desempenado": "Gerente de Supervisión",
      "empresa_emisora": "INSTITUTO DE CONSULTORIA S.A.",
      "ruc_emisor": "20263373058",
      "publica_o_privada": "Pública",
      "tipo_acreditacion": "Emitido por el Contratista",
      "fecha_inicio": "2022-04-20",
      "fecha_culminacion": "2024-05-11",
      "alerta_covid": null,
      "fecha_emision_cert": "2024-09-07",
      "n_folio": "1791",
      "firmante_certificado": "Danitza Z. Echandia Moreno",
      "cargo_firmante": "Representante Legal",
      "tipo_documento": "Constancia",
      "nivel_categoria": "II-1",
      "area_construida_m2": null,
      "monto_contrato_soles": null,
      "ubicacion": "San Ignacio",
      "entidad_contratante": "Gobierno Regional",
      "alerta_exp_antes_titulacion": null,
      "alerta_cert_antes_culminacion": null,
      "observaciones_fila": null,
      "_flags": {}
    }
  ],
  "observaciones_claude": [
    {
      "codigo": "POSIBLE_DUPLICADO_PERIODO",
      "tipo": "duplicado_posible",
      "severidad": "info",
      "origen": "claude",
      "mensaje": "Las experiencias 4 y 5 tienen el mismo proyecto, mismo emisor y folio (001818) con periodos contiguos. Podrían ser un periodo único partido por la propuesta. Se conservaron como entidades separadas; verificar.",
      "referencia": {
        "item_tipo": "experiencia",
        "item_id": [4, 5],
        "campo": null,
        "folio_pdf": "001818",
        "pagina_pdf": null
      }
    },
    {
      "codigo": "FIRMANTE_SIN_CARGO_VISIBLE",
      "tipo": "extraccion_parcial",
      "severidad": "warning",
      "origen": "claude",
      "mensaje": "El certificado del folio 001500 está firmado pero el cargo del firmante no es legible (línea cortada en el escaneo). Backend no podrá validar ALT12 contra SUNAT para esta fila.",
      "referencia": {
        "item_tipo": "experiencia",
        "item_id": 7,
        "campo": "cargo_firmante",
        "folio_pdf": "001500",
        "pagina_pdf": null
      }
    }
  ]
}
```

---

## 13 · Criterio de salida de Fase 1

- [x] Schema documentado en `docs/schema_canonico.md` (este archivo, v2 — 3 JSONs).
- [ ] Schema en Pydantic en código en `docs/schema_canonico_pydantic.md` (próximo paso).
- [ ] Tres ejemplos JSON sintéticos en `docs/examples/`:
  - `lircay_bases.json` — Paso 1 lleno
  - `lircay_profesionales.json` — Paso 2 con observaciones de ilegibilidad
  - `lircay_experiencias.json` — Paso 3 con campos `null` para backend
- [x] Discrepancias documentadas (sección 11).
- [x] Mapeo Excel ingeniero → JSON canónico (sección 9).
- [x] Contrato Claude vs backend (sección 8).
- [x] Mecanismo `observaciones_claude` definido (sección 2).
- [ ] Schema validado contra Huancavelica + URCOS goldens.

Cuando estén ✓, Fase 1 cerrada. Siguiente: refactor de `docs/skill_design.md`
(skill con 2 subagentes que producen 3 JSONs).
