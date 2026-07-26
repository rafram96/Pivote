# Contrato de salida de la skill

La skill emite **dos artefactos** por análisis. Fuente autoritativa:
`docs/contrato/contrato_refactor.md` §3.

## 1 · Excel "Formato de Evaluación" — hoja `CLAUDE` (new_format)

La skill produce la hoja **`CLAUDE`** (formato vigente). El bloque Parte 3+4
**se repite por cada profesional** (N profesionales). Referencia:
`fixtures/new_format/02. Formato de evaluacion COMPLETADO.xlsx`.

| Parte | Contenido |
|---|---|
| 1. Formularios del postor | Anexos (ANEXO·DOCUMENTO·¿presenta?/¿corresponde?·folio) + oferta vs **límite inferior** (= 90% de la cuantía; regla del 2.º decimal) y superior |
| 2. Experiencia del postor | Certificados: monto S/, % por objeto, le corresponde, ¿acredita (consorciado)?, ¿20 años?, ¿tipo solicitado? |
| 3. Info general — `PROFESIONAL n DE N` | Nombre, título, ¿profesión ok?, colegiatura+fecha, certificaciones (incl. PMP), **experiencia total declarada** |
| 4. Experiencia — `CARGO — Nombre` | Contexto de bases (cargos/tipo exp/tipo obra válidos) + tabla por experiencia (emisor, ¿válido emitir?, fechas, DÍAS/MESES/AÑOS, ¿ant. colegiatura?, ¿antes culminar?, ¿COVID 16/03–30/06/2020?, ¿tipo obra?, **¿traslape? → rojo**) + TOTAL + **cross-checks (NOTA 1)** + **Notas** |
| 5. Resumen | Factores (A, B, C, G, J…) con puntaje o **"NO APLICA"** + PUNTAJE TÉCNICO TOTAL |

> **Reglas de dominio portadas del flujo manual** (las "NOTAS" del evaluador):
> límite inferior 90%; cross-check anti-omisión por profesional (NOTA 1, hasta 4×);
> 1 fila por periodo; orden por fecha-fin asc; traslapes en rojo; COVID como rango;
> los ISO se mapean **por nombre** (14001 → Sostenibilidad Ambiental, 37001 →
> Integridad, 9001 → Gestión de Calidad) a la **letra que use el formato**; en
> **consorcio** el ISO puntúa solo si **todos** acreditan; PMP solo PMI/sello/2
> años (no PDU); factores ausentes del Cuadro Resumen → "NO APLICA".

> **Hojas por profesional** (desglose certificado/efectiva → **días efectivos**,
> Paso 5): NO las produce la skill. Las agrega el **backend** vía scraping de
> InfoObras (paralizaciones). Aquí Claude pone los **días brutos**.

Generación (cliente): `node scripts/generar_excel.js` (exceljs) — construcción
dinámica: un bloque por profesional, filas variables, estilos del ingeniero +
resaltado Claude(amarillo)/backend(naranja). Validado round-trip con Trujillo.
El gemelo en Python (`backend/scripts/generar_excel.py`) lo usa el **servidor**
para **regenerar** el Excel final enriquecido (no parchea el del cliente).

## 2 · JSON espejo (fuente de verdad de máquina)

Misma información, estructurada y autovalidante. **Contrato v1.2.0** — el schema
ejecutable es `schemas/espejo.js` (zod, este lado) y `backend/schemas/espejo.py`
(Pydantic, lado servidor); `tools/test_contrato.py` garantiza la paridad. Incluye
la evaluación de Claude **y** un bloque `_backend` con todo en `null` — el
**contrato explícito** de lo que el servidor debe llenar.

Forma **plana**: las experiencias viven DENTRO de cada profesional (no a nivel
raíz), y los datos del emisor/firmante son campos planos (no objetos anidados).

```jsonc
{
  "_meta": { "analisis_id": "...",
             "slug": "huachocolpa",   // nombre CORTO del concurso → nombre de los archivos
             "concurso": "...", "postor": "...",
             "version_contrato": "1.2.0", "generado_por": "claude-code" },
  "postor": {
    "detalle": "...",
    "formularios": [ { "anexo", "documento", "observacion", "folio" } ],
    "oferta_economica": { "cuantia", "limite_inferior", "propuesta", "detalle" },
    "experiencia_postor": [ { "n", "cliente", "contrato", "proyecto",
                              "tipo_acreditacion", "monto", "pct_objeto",
                              "le_corresponde",
                              "acredita",     // consorciado que acredita (texto) o monto
                              "folio", "ultimos_20_anios", "tipo_solicitado",
                              "observaciones" } ],
    "experiencia_postor_total": { "acredita": ... },
    "postor_cumple": "SÍ CUMPLE — razón literal …",
    "consorciados": [ { "nombre", "ruc", "pct" } ]   // de la Promesa de Consorcio (NOTA 14)
  },
  "profesionales": [ {
     "n_prof", "cargo",                    // cargo = etiqueta LITERAL de la propuesta (sin "(cargo bases N°…)")
     "cargo_bases_num", "cargo_bases_nombre", // correspondencia con el Cuadro de Personal de las bases (atómica, la pone agent-evaluador)
     "nombre", "folio_nombre",
     "titulo", "folio_titulo", "profesion_valida",
     "colegiatura", "fecha_colegiatura", "folio_colegiatura",
     "certificaciones",                    // texto (incl. hechos PMP para Factor B)
     "experiencia_total_declarada",        // lo autodeclarado en el Anexo 16 (NOTA 1/5)
     "requisitos": { "cargos_validos", "tipo_experiencia", "tipo_obra" },
     "experiencias": [ {
        "n",
        "entidad_emisora",     // empresa/entidad que emite el certificado
        "ruc_emisor",          // ⭐ RUC (11 díg.) si está literal → cruce + ALT12; null si no
        "proyecto",            // ⭐ VERBATIM y completo (sin abreviar ni meter metadata)
        "cui",                 // ⭐ CUI/SNIP citado en el cert (solo dígitos) → cruce determinístico
        "tipo_documento",
        "nombre_emisor",       // persona que firma
        "cargo_emisor",        // cargo del firmante
        "cargo_valido_emitir", // juicio Claude, sufijo "(ASUMIDO)" — el backend confirma vía SUNAT
        "fecha_inicial", "fecha_final", "fecha_emision",
                               // ISO "YYYY-MM-DD" · parcial "YYYY-MM (anotación)" · "POR VERIFICAR…" (NOTA 12)
        "folio", "dias", "meses", "anios",
        "anterior_colegiatura", "cargo_ocupado", "cargo_bases_valido",
        "funciones_similares", "cert_antes_culminar",
        "incluye_covid",       // ventana 16/03/2020–30/06/2020 (NOTA 10)
        "tipo_obra_valido",
        "traslape",            // "SÍ" en AMBOS periodos que se superponen (NOTA 9)
        "nivel_categoria",     // "II-1", "II-2", "Centro de Salud"… si el cert lo cita
        "area_construida_m2", "monto_contrato_soles",
        "entidad_contratante", // dueño de la obra (≠ emisor) → score CUI
        "ubicacion",           // dpto/prov/distrito → score CUI
        "observaciones",
        "_backend": {                          // ⚠ Claude deja TODO en null
           "fecha_creacion_emisor": null,      // SUNAT ALT04
           "alerta_antiguedad_emisor": null,   // ALT04
           "firmante_facultado_sunat": null,   // ALT12 (getRepLeg)
           "vinculacion_postor_emisor": null,  // conflicto intragrupo (nuevo)
           "codigo_ciu": null, "codigo_infoobras": null,  // InfoObras
           "paralizaciones": null,             // InfoObras (Paso 5)
           "alerta_experiencia_antigua": null  // recálculo cutoff 25 años
        }
     } ],
     "total": { "dias", "meses", "anios" },
     "cross_checks": [ { "label": "Cross-check vs cuadro resumen del Anexo 16:",
                         "valor": { "extraidas", "declaradas", "cuadra", "intentos" } } ],
     "notas": [ "…" ],
     "cumple", "anios_adicionales"
  } ],
  "resumen_evaluacion": {
    "factores": [ { "factor", "criterio", "folio", "detalle",
                    "aplica",            // false ⇔ puntaje "NO APLICA"
                    "puntaje" } ],       // número · null · "NO APLICA…"
    "puntaje_total", "nota"
  },
  "observaciones_claude": [ { "severidad", "tipo", "mensaje", "referencia" } ]
}
```

## Reparto Claude ↔ backend (resumen)

| Claude (esta skill) | Backend on-prem |
|---|---|
| Extrae todo de los PDFs | Verifica RUC/representante (SUNAT) → ALT04, ALT12 |
| Evalúa cumplimiento + razones literales | Recalcula DÍAS efectivos descontando paralizaciones (InfoObras, Paso 5) |
| DÍAS/MESES/AÑOS **brutos** | Detecta vinculación postor↔emisor (conflicto) |
| Marca firmante como "ASUMIDO" | Recalcula cutoff de años (25, no 20) |
| Llena el Excel + JSON espejo | **Regenera** el Excel final enriquecido + persiste |
