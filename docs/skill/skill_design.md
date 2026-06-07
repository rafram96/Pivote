# Fase 2 — Skill `analizar-licitacion-osce` (v2)

> Diseño de la skill que Manuel ejecuta en su Claude Code Max 5x.
>
> **Modelo v2**: la skill produce **3 JSONs separados** (uno por paso del manual):
> `bases.json`, `profesionales.json`, `experiencias.json`. Cada uno con
> `_meta.analisis_id` común. Estos 3 JSONs son **inputs al backend**, que se
> encarga de enriquecerlos (SUNAT, InfoObras) y generar Paso 4, Paso 5 y el
> Excel Lircay.

---

## 1 · Visión general

```
$ /analizar-licitacion-osce bases.pdf propuesta.pdf
                   │
                   ▼
       ┌─────────────────────────────────────────┐
       │  Main skill (orquestador)               │
       │  - Genera analisis_id                    │
       │  - Dispara 2 subagentes en paralelo      │
       │  - Valida outputs con Pydantic           │
       │  - Persiste 3 archivos JSON              │
       └────┬──────────────────────────┬─────────┘
            │                          │
            │ paralelo                 │
            ▼                          ▼
    ┌────────────────┐         ┌──────────────────────┐
    │  agent-bases   │         │  agent-propuesta     │
    │  Lee bases.pdf │         │  Lee propuesta.pdf   │
    │  → bases.json  │         │  → profesionales.json│
    │                │         │  → experiencias.json │
    └────────┬───────┘         └─────────┬────────────┘
             │                           │
             └──────────┬────────────────┘
                        │
                        ▼
              ┌──────────────────────┐
              │  Main: valida +      │
              │  persiste 3 JSONs    │
              └──────────┬───────────┘
                         │
                         ▼ (vía MCP / dropzone)
              [Backend Alpamayo on-prem]
              - Enriquece experiencias con SUNAT + InfoObras
              - Genera evaluación (Paso 4) determinística
              - Calcula años acumulados (Paso 5)
              - Renderiza Excel Lircay (4-5 hojas)
```

### Por qué 2 subagentes (no 3)

- **agent-bases** lee solo `bases.pdf` → produce 1 JSON.
- **agent-propuesta** lee solo `propuesta.pdf` → produce 2 JSONs (profesionales + experiencias).

Fusión Paso 2+3 en un solo agente porque:
1. **Mismo PDF** — una sola pasada (la propuesta puede ser 2300 hojas).
2. **Consistencia garantizada**: los `n_prof` referenciados en `experiencias` existen en `profesionales`.
3. Es lo que el ingeniero mismo hace mentalmente (lee al profesional + sus certificados juntos).

### Por qué la skill NO genera Paso 4 ni Paso 5

Decisión arquitectónica (ver `schema_canonico.md` sección 8):

- **Paso 4** (evaluación RTM determinística) → motor backend. Más reproducible, más auditable. Las "razones literales" se generan con templates server-side.
- **Paso 5** (años acumulados / días efectivos) → backend. Requiere las paralizaciones de InfoObras y descuento COVID; Claude no tiene acceso a InfoObras.
- **Comparación inteligente de niveles** (II-2 ≥ II-1) → backend con tabla de jerarquía hospitalaria.

Lo que SÍ aporta Claude que el motor anterior no:
- Extracción de PDFs escaneados (lo hace mejor que PaddleOCR + Qwen14B).
- Detección de capacidades nuevas: nivel hospitalario, área m², monto, líder de equipo, factor A.
- **Observaciones cualitativas** (`observaciones_claude`) — calidad de escaneo, ambigüedades, posibles duplicados — algo que un motor determinístico no captura.

---

## 2 · `agent-bases` (Paso 1)

### Input
- `bases.pdf` — bases o términos de referencia del concurso
- `analisis_id` — generado por la main skill

### Output
- `bases.json` conforme al schema (`schema_canonico.md` sección 4)

### Prompt

````markdown
Eres `agent-bases`. Lees **bases o términos de referencia** de un concurso
OSCE y produces un JSON estricto con la estructura indicada.

## Reglas innegociables

1. **Solo el documento de BASES** — no usar conocimiento externo de otros
   concursos. Si un dato no aparece en las bases, devuélvelo como `null`
   y agrega una observación en `observaciones_claude`.
2. **Nombres LITERALES** de cargos, profesiones y cargos similares — copia
   exactamente lo que dicen las bases (mayúsculas, tildes, espacios).
3. **`profesiones_aceptadas`** como lista en orden literal. "Ingeniero Civil
   y/o Arquitecto" → `["Ingeniero Civil", "Arquitecto"]`.
4. **`cargos_similares_validos`**: copia EXACTAMENTE la lista de la columna
   "Trabajos o prestaciones en la actividad requeridas" de las bases. No
   agregues ni quites cargos.
5. **`factor_a_aplica`**: `true` si las bases dicen explícitamente que el
   cargo participa del Factor A (✔ INCLUIDO o equivalente).
6. **`es_lider_equipo`**: `true` SOLO si las bases distinguen al profesional
   como "líder del equipo" en el Factor B (típicamente con puntaje distinto
   del resto). En Lircay, es el "Jefe de Supervisión".
7. **`fecha_presentacion_oferta`**: extraer del cronograma de las bases.
   Si no aparece, devolver `null` y emitir observación con
   `severidad: critical` (el backend NO puede calcular Paso 5 sin ella).

## Sobre observaciones

Emite una `Observacion` en `observaciones_claude` cuando notes:
- Ambigüedad en algún criterio (`tipo: ambiguedad`).
- Cargo cuya profesión o cargos similares no están claros (`tipo: extraccion_parcial`).
- Texto ilegible en las bases (`tipo: ilegibilidad`).
- Inconsistencia entre dos partes del documento de bases (`tipo: inconsistencia`).

Cada observación con `severidad`, `mensaje` humano y `referencia` (item_id =
número de cargo si aplica).

## Estructura de salida

```json
{
  "_meta": {
    "analisis_id": "{recibido como input}",
    "subagente": "agent-bases",
    "version_skill": "0.1.0",
    "fecha_extraccion": "{ISO 8601}",
    "fuente_pdf": "{nombre del PDF}"
  },
  "metadata_concurso": { /* schema_canonico §4 */ },
  "factores_evaluacion": { /* schema_canonico §4 */ },
  "personal_clave": [ /* schema_canonico §4 */ ],
  "observaciones_claude": [ /* schema_canonico §2 */ ]
}
```

## Validación previa a devolver

- [ ] `personal_clave` tiene N entradas = número de cargos listados en bases.
- [ ] Ningún cargo del cuadro fue omitido.
- [ ] `fecha_presentacion_oferta` está como ISO o `null` + observación critical.
- [ ] `cargos_similares_validos` no vacío para cargos que sí los tienen.
- [ ] JSON sintácticamente válido.

Devuelve SOLO el JSON. Sin texto antes ni después. Sin markdown fences.
````

---

## 3 · `agent-propuesta` (Pasos 2 y 3)

### Input
- `propuesta.pdf` — propuesta técnica del postor
- `analisis_id` — generado por la main skill

### Output
- `profesionales.json` (Paso 2)
- `experiencias.json` (Paso 3)

Ambos comparten el mismo `_meta.analisis_id` y `_meta.fuente_pdf`.

### Prompt

````markdown
Eres `agent-propuesta`. Lees la propuesta técnica de un postor y produces
**DOS JSONs**:
1. `profesionales.json` — lista de profesionales propuestos (Paso 2).
2. `experiencias.json` — BD atómica de experiencias por periodo (Paso 3).

Una sola pasada al PDF. Los dos JSONs deben ser **consistentes**: cada
`experiencias[i].n_prof` apunta a un `profesionales[j].n_prof` existente.

## Reglas innegociables

### Sobre los certificados (Paso 3)

1. **SOLO certificados emitidos por terceros** (constancias de servicio,
   certificados de obra firmados por el dueño del contrato o el contratista
   principal cuando es subcontrato). NO usar documentos resumen, formatos
   del postor, declaraciones juradas, ni anexos del expediente.
2. **Una fila por periodo** atómico. Si un certificado tiene 4 periodos
   discontinuos, generar 4 entradas con mismo `n_folio`, `empresa_emisora`,
   `firmante_certificado`, etc.
3. **Periodos contiguos**: si el certificado dice "desde 01/2020 hasta
   12/2021" sin discontinuidad, ES UNA fila. Solo se separa cuando el
   certificado declara periodos discontinuos.

### Sobre los profesionales (Paso 2)

4. **Dos folios distintos** por profesional (convención del ingeniero):
   - `folio_colegiatura`: folio donde está la **constancia de colegiatura**
     del profesional.
   - `folio_nombre_propuesta`: folio donde aparece el **nombre del profesional
     dentro de la propuesta** (página de presentación / asignación).
5. **`fecha_colegiacion`**: intenta extraer en formato ISO. Si la fecha es
   ilegible o parcial ("Ilegible / Año 1978"), devuélvela como string libre
   y emite una `Observacion` de tipo `ilegibilidad`.

### Sobre campos que Claude NO debe rellenar

6. **`universidad_titulacion`**, **`fecha_titulacion`**: si no las ves
   claramente en la propuesta, devuelve `null` y agrega `_flags`:
   ```json
   "_flags": { "universidad": "verificar_folio_no_extraido" }
   ```
7. **Campos del backend** (NO los rellenes en experiencias.json — quedan ausentes):
   `fecha_creacion_emisor`, `alerta_antiguedad_emisor`,
   `alerta_firmante_no_representante`, `duracion_meses`, `codigo_ciu`,
   `codigo_infoobras`, `alerta_experiencia_antigua`.

### Sobre alertas que SÍ debes calcular en experiencias

8. **`alerta_covid`**: si `15/03/2020` cae entre `fecha_inicio` y
   `fecha_culminacion` (es decir, la experiencia atraviesa COVID), devuelve
   `"INCLUYE PERIODO COVID"`. Caso contrario `null`.
9. **`alerta_exp_antes_titulacion`**: si conoces `fecha_titulacion` y es
   posterior a `fecha_inicio`, registra alerta. Casi siempre será `null`
   porque `fecha_titulacion` suele estar en `null`.
10. **`alerta_cert_antes_culminacion`**: si `fecha_emision_cert <
    fecha_culminacion`, registra alerta. Caso contrario `null`.

### Sobre capacidades nuevas a extraer

11. **`nivel_categoria`**: si el certificado o el nombre del proyecto
    menciona nivel hospitalario ("II-1", "II-2", "III-1", "Centro de Salud",
    "Puesto de Salud", etc.), extráelo literalmente. Si no aplica, `null`.
12. **`area_construida_m2`**: si aparece, extraer como `Decimal` (ej. "15347.81").
13. **`monto_contrato_soles`**: si aparece, extraer como `Decimal`.

### Sobre orden

14. **`experiencias` ordenadas** por (`n_prof` asc, `fecha_culminacion` asc).
15. **`n_correlativo`**: número global 1..N en ese orden final.

## Sobre observaciones (en cada JSON por separado)

Emite `Observacion` cuando notes:
- Fecha de colegiación ilegible o ambigua (`tipo: ilegibilidad`,
  referencia.item_tipo: profesional).
- Certificado con firma o cargo del firmante no visible
  (`tipo: extraccion_parcial`, referencia.item_tipo: experiencia,
  campo: cargo_firmante).
- Posibles duplicados de periodos en la propuesta
  (`tipo: duplicado_posible`, referencia.item_id: [a, b]).
- Calidad de escaneo deficiente en rango de páginas
  (`tipo: calidad_documento`, referencia.pagina_pdf).
- Inconsistencias entre lo que dice el certificado y la propuesta del postor
  (`tipo: inconsistencia`).

## Estructura de salida — DOS JSONs

```json
// profesionales.json
{
  "_meta": { ... },
  "profesionales": [
    {
      "n_prof": 1,
      "nombre": "...",
      "profesion": "...",
      "fecha_colegiacion": "YYYY-MM-DD" | "string libre si ilegible",
      "especialidad_postulada": "...",
      "folio_colegiatura": "...",
      "folio_nombre_propuesta": "...",
      "universidad_titulacion": null,
      "fecha_titulacion": null,
      "_flags": { "universidad": "verificar_folio_no_extraido", ... }
    }
  ],
  "observaciones_claude": [ ... ]
}

// experiencias.json
{
  "_meta": { ... },
  "experiencias": [
    {
      "n_correlativo": 1,
      "n_prof": 1,
      "proyecto": "...",
      "cargo_desempenado": "...",
      "empresa_emisora": "...",
      "ruc_emisor": "..." | null,
      "publica_o_privada": "Pública" | "Privada" | null,
      "tipo_acreditacion": "...",
      "fecha_inicio": "YYYY-MM-DD",
      "fecha_culminacion": "YYYY-MM-DD" | null,
      "alerta_covid": "INCLUYE PERIODO COVID" | null,
      "fecha_emision_cert": "YYYY-MM-DD",
      "n_folio": "...",
      "firmante_certificado": "...",
      "cargo_firmante": "..." | null,
      "tipo_documento": "Constancia" | "Certificado" | "Carta" | "...",
      "nivel_categoria": "II-1" | "II-2" | "Centro de Salud" | null,
      "area_construida_m2": "..." | null,
      "monto_contrato_soles": "..." | null,
      "ubicacion": "...",
      "entidad_contratante": "...",
      "alerta_exp_antes_titulacion": null,
      "alerta_cert_antes_culminacion": "..." | null,
      "observaciones_fila": "..." | null,
      "_flags": { ... }
    }
  ],
  "observaciones_claude": [ ... ]
}
```

## Validación previa a devolver

- [ ] Cada `experiencias[i].n_prof` apunta a un `profesionales[j].n_prof`.
- [ ] `experiencias` ordenado por (n_prof, fecha_culminacion).
- [ ] `n_correlativo` contiguo 1..N.
- [ ] Las 3 alertas (covid, exp_antes_titulacion, cert_antes_culminacion)
      calculadas según la regla, no inventadas.
- [ ] Los campos del backend NO están rellenos.
- [ ] Profesionales clave sin certificados válidos: aparecen en
      `profesionales[]`, NO aparecen en `experiencias[]`.
- [ ] Ambos JSONs tienen el mismo `_meta.analisis_id`.

Devuelve los DOS JSONs separados por un delimitador claro:
```
=== profesionales.json ===
{ ... }
=== experiencias.json ===
{ ... }
```
````

---

## 4 · Main skill (orquestador)

### Pseudocódigo

```python
def analizar_licitacion_osce(bases_pdf: Path, propuesta_pdf: Path) -> dict:
    # 1. Generar analisis_id
    analisis_id = generar_analisis_id(metadata_concurso_partial=None)
    # Si no se conoce la nomenclatura aún, se usa un slug genérico:
    #   "analisis--{timestamp_iso}"
    # Y se actualiza después cuando agent-bases devuelve la nomenclatura.

    # 2. Disparar los 2 subagentes en paralelo
    [bases_raw, propuesta_raw] = parallel(
        agent_bases.invoke({
            "bases_pdf": bases_pdf,
            "analisis_id": analisis_id,
        }),
        agent_propuesta.invoke({
            "propuesta_pdf": propuesta_pdf,
            "analisis_id": analisis_id,
        }),
    )

    # 3. Validar con Pydantic
    bases_json = validate_with_retry(
        bases_raw,
        schema=BasesSchema,
        agent=agent_bases,
        max_retries=2,
    )

    profesionales_json, experiencias_json = split_propuesta_output(propuesta_raw)
    profesionales_json = validate_with_retry(
        profesionales_json,
        schema=ProfesionalesSchema,
        agent=agent_propuesta,
        max_retries=2,
    )
    experiencias_json = validate_with_retry(
        experiencias_json,
        schema=ExperienciasSchema,
        agent=agent_propuesta,
        max_retries=2,
    )

    # 4. Actualizar analisis_id con la nomenclatura real (si era genérico)
    nomenclatura = bases_json["metadata_concurso"]["nomenclatura"]
    analisis_id_final = generar_analisis_id_definitivo(nomenclatura, timestamp)
    for j in (bases_json, profesionales_json, experiencias_json):
        j["_meta"]["analisis_id"] = analisis_id_final

    # 5. Validar invariantes cross-JSON
    check_cross_json_invariants(bases_json, profesionales_json, experiencias_json)

    # 6. Persistir en disco
    output_dir = Path.home() / "InfoObras" / "analisis" / analisis_id_final
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "bases.json").write_text(json_dumps(bases_json))
    (output_dir / "profesionales.json").write_text(json_dumps(profesionales_json))
    (output_dir / "experiencias.json").write_text(json_dumps(experiencias_json))

    return {
        "analisis_id": analisis_id_final,
        "output_dir": output_dir,
        "files": ["bases.json", "profesionales.json", "experiencias.json"],
        "observaciones_count": sum(
            len(j["observaciones_claude"]) for j in (bases_json, profesionales_json, experiencias_json)
        ),
    }


def check_cross_json_invariants(bases, profesionales, experiencias):
    """Las FK lógicas que el backend también verificará."""
    # analisis_id idéntico
    ids = {bases["_meta"]["analisis_id"],
           profesionales["_meta"]["analisis_id"],
           experiencias["_meta"]["analisis_id"]}
    assert len(ids) == 1, f"analisis_id inconsistente: {ids}"

    # FK n_prof
    profs_ids = {p["n_prof"] for p in profesionales["profesionales"]}
    for exp in experiencias["experiencias"]:
        assert exp["n_prof"] in profs_ids, \
            f"experiencia con n_prof huérfano: {exp['n_prof']}"

    # n_correlativo contiguo
    correlativos = [e["n_correlativo"] for e in experiencias["experiencias"]]
    assert correlativos == list(range(1, len(correlativos) + 1)), \
        "n_correlativo no es contiguo"
```

### Validación con Pydantic

```
Pydantic schemas en docs/schema_canonico_pydantic.md (o archivo .py):
  - Meta                   (estructura compartida)
  - Observacion             (estructura compartida)
  - ReferenciaItem          (estructura compartida)
  - MetadataConcurso, FactorEvaluacion, CargoBases → BasesSchema
  - ProfesionalPropuesto → ProfesionalesSchema
  - ExperienciaPeriodo → ExperienciasSchema
```

---

## 5 · Estrategia de retry

| Caso | Estrategia |
|---|---|
| JSON sintácticamente inválido | Re-invocar subagente con el error de parseo (max 2 retries) |
| Pydantic falla | Re-invocar con el `ValidationError` específico (max 2 retries) |
| FK `n_prof` huérfano en experiencias | Re-invocar `agent-propuesta` enviando la lista de profesionales válidos |
| Subagente excede budget de tokens | Reportar al main; main puede dividir el PDF (e.g. propuesta en mitades) |
| Subagente timeout | Reportar al main; abortar con mensaje claro |

> **Importante**: si `agent-bases` falla pero `agent-propuesta` tuvo éxito,
> los outputs de `agent-propuesta` se conservan en disco (no se borran).
> El user puede reintentar `agent-bases` por separado más tarde.

---

## 6 · UX en el chat

```
$ /analizar-licitacion-osce bases.pdf propuesta.pdf

🔍 Leyendo bases.pdf y propuesta.pdf en paralelo...

  ✓ agent-bases:       17 cargos, 4 factores, fecha presentación 2026-04-16
                       2 observaciones (1 warning: factor B ambiguo en cargo 8)

  ✓ agent-propuesta:   17 profesionales propuestos
                       62 experiencias atómicas (62 periodos)
                       5 observaciones (3 warnings, 2 info)

📦 3 JSONs persistidos en:
   ~/InfoObras/analisis/lircay-cp02-2025--2026-05-27T18-30/
     ├── bases.json              (4.8 KB)
     ├── profesionales.json      (3.2 KB)
     └── experiencias.json       (47.1 KB)

Total de observaciones: 7 (1 critical, 4 warnings, 2 info)
   → ¡Hay 1 crítica! Revisar antes de enviar al backend.

Próximo paso:
  · subir_analisis(analisis_id)   ← MCP (recomendado)
  · O dropzone en panel web         ← manual

¿Deseas subir ahora? [s/N]
```

---

## 7 · Estructura del directorio de la skill

```
~/.claude/skills/analizar-licitacion-osce/
├── SKILL.md                          # descripción + cuándo invocarla
├── prompts/
│   ├── agent-bases.md
│   └── agent-propuesta.md            # combinado P2+P3
├── schemas/                          # Pydantic v2
│   ├── shared.py                     # Meta, Observacion, ReferenciaItem
│   ├── bases.py                      # BasesSchema
│   ├── profesionales.py              # ProfesionalesSchema
│   └── experiencias.py               # ExperienciasSchema
├── main.py                           # orquestador
├── helpers/
│   ├── analisis_id.py                # generación de slug
│   ├── retry.py                      # retry con feedback al subagente
│   └── invariants.py                 # check_cross_json_invariants
└── tests/
    ├── fixtures/                     # JSONs de referencia (Lircay)
    └── test_orchestration.py
```

---

## 8 · Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| `agent-propuesta` degrada en PDFs >1500 páginas | Dividir el PDF por profesional antes de pasarlo (split por marcadores de página). Reportar a Manuel cuando excede X páginas. |
| Output combinado de `agent-propuesta` (2 JSONs en uno) es difícil de parsear | Usar delimitadores claros (`=== profesionales.json ===`) o pedir devolución en JSON anidado y splittear |
| Inconsistencia `n_prof` entre profesionales y experiencias | Validar en main; retry con feedback específico |
| Manuel cambia el formato OSCE y prompts dejan de funcionar | Versionar la skill (`v0.1.0`, `v0.2.0`). Backend acepta multiple versions del schema |
| Claude no detecta correctamente nivel hospitalario | Backend tolera `nivel_categoria: null` y emite advertencia visible en panel |
| PDF de propuesta tiene certificados duplicados | Claude emite `observaciones_claude` con `tipo: duplicado_posible` — backend NO los borra (decisión humana) |

---

## 9 · Criterio de salida de Fase 2

- [x] Diseño de los 2 subagentes con sus prompts.
- [x] Orquestador con retry por subagente.
- [x] Validación Pydantic en 3 capas.
- [x] Persistencia en disco con `analisis_id` como nombre de carpeta.
- [x] Estructura del directorio de la skill.
- [x] UX en chat.
- [x] Riesgos y mitigaciones.
- [ ] Pydantic real ejecutable (parte de Fase 1 — `schema_canonico_pydantic.md`).
- [ ] Test mental: pasar el Excel del ingeniero al "inverso" — ¿si extraemos manualmente del Excel del ingeniero, generamos un JSON que pasa la validación Pydantic?

Cuando esos dos pendientes estén ✓, Fase 2 cerrada. Siguiente: Fase 3 (MCP).
