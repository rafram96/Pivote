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

Misma información, estructurada y autovalidante (Pydantic). Incluye la evaluación
de Claude **y** un bloque `_backend` con todo en `null` — el **contrato explícito**
de lo que el servidor debe llenar.

```jsonc
{
  "_meta": { "analisis_id": "...", "concurso": "...", "postor": "...",
             "version_contrato": "1.0.0", "generado_por": "claude-code" },
  "postor": {
    "formularios": [ /* anexos 1-6: presenta/no, folio */ ],
    "oferta_economica": { "monto": ..., "limite_inferior": ..., "cumple": ... },
    "experiencia_postor": [ /* contrato, monto, %, le_corresponde, acredita */ ]
  },
  "profesionales": [ { "n_prof", "cargo", "nombre", "profesion", "colegiatura",
                       "fecha_colegiatura", "profesion_valida", "certificaciones",
                       "folios" } ],
  "experiencias": [ {
     "n_correlativo", "n_prof",
     "proyecto",            // ⭐ VERBATIM y completo (sin abreviar ni meter metadata) — ver agent-propuesta §A-B
     "cui",                 // ⭐ CUI/SNIP citado en el cert (solo dígitos) → cruce determinístico; null si no aparece
     "emisor": { "nombre", "ruc": null },  // ruc del emisor (11 díg.) si está literal → cruce + ALT12
     "firmante": { "nombre", "cargo_declarado" },
     "cargo_emisor_valido_claude": { "cumple", "detalle": "ASUMIDO" },
     "fecha_inicio", "fecha_fin", "dias", "meses", "anios", "folio",
     "anterior_a_colegiatura", "cargo_ocupado", "cargo_bases_valido",
     "cert_antes_de_culminar", "incluye_covid", "tipo_obra_valido",
     "nivel_categoria",
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
  "resumen_evaluacion": { /* factores A, B, C, E, J → puntaje */ },
  "observaciones_claude": [ /* severidad + referencia */ ]
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
