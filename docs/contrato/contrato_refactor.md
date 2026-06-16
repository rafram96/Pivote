# Contrato de Refactor — InfoObras Claude-céntrico

> **Fecha**: 2026-05-30
> **Reemplaza a**: la arquitectura híbrida de 3 JSONs (`skill_design.md` v2,
> `schema_canonico.md` v2). Esos docs quedan como historia; este manda.
> **Qué es**: el contrato técnico del segundo pivote, donde Claude pasa de
> "extractor que alimenta al backend" a **motor central de extracción Y
> evaluación**, y el backend on-prem queda como **capa de verificación,
> enriquecimiento y persistencia**.

---

## 0 · Status del refactor (al 2026-05-30)

Leyenda: ✅ probado empíricamente · 📐 diseñado/decidido · 🔨 por construir ·
❌ descartado.

| Componente | Madurez | Evidencia / nota |
|---|---|---|
| SUNAT ALT04 (fecha creación emisor) | ✅ probado | `consultar_ruc` ya operaba |
| SUNAT ALT12 (firmante vs representante) | ✅ probado | `getRepLeg`, 4 RUCs reales incl. consorcios. Ya explorado desde 29-may (`_sunat_dump/`) |
| InfoObras por CUI (código) | ✅ probado | Florencia de Mora CUI 2258772 → obra OK |
| InfoObras por nombre | ⚠ funciona c/ ajuste | endpoint OK; extractor de keywords falla con nombre de *concurso* (~0.5 día) + bug CUI con 2 obras |
| Contrato Excel + JSON espejo | 📐 diseñado | §3 |
| Transporte dropzone (Camino B, MVP) | 📐 diseñado | §4 |
| Transporte MCP local (Camino A, fase 2) | 📐 diseñado | §4; verificar alcance LAN |
| Backend API HTTP desacoplada | 📐 decidido | sirve a dropzone + MCP |
| Skill `/analisis-propuesta` (3 subagentes: bases, propuesta, evaluador) | 🔨 por construir | Claude evalúa (agent-evaluador) → reemplaza el diseño viejo de 2 subagentes de `skill_design.md`. Subagentes = esenciales (propuestas grandes son lo normal, confirmado 2026-05-30) |
| Validador determinístico (15 notas) | 🔨 por construir | pieza central |
| Tabla equivalencias de cargos (ALT12) | ❌ descartado | firmante de constancia ≠ rep. legal SUNAT (funcionario de área) → falsos positivos; decisión cliente 2026-06-15 |
| Detección vinculación postor↔emisor | ✅ construido | RUC emisor ∈ RUCs del postor (formularios/consorciados) → alerta `VINCULACION`; determinístico, sin SUNAT |
| Excel final enriquecido | 🔨 por construir | servidor regenera |
| OCR local / Qwen14B / 3 JSONs / MCP remoto | ❌ descartado | §6 |

**Síntesis**: las dos verificaciones que eran el supuesto más riesgoso del
pivote (SUNAT firmantes, InfoObras obras) están **probadas**. Lo que queda es
**construcción** (validador + empaquetado + cableado), no investigación. El
riesgo técnico mayor ya se despejó.

**Estimación**: ~1 semana a 1½ (7-8 días). Desglose en §7.

---

## 1 · Por qué este segundo pivote

El cliente (Manuel) validó por su cuenta que Claude, con **un solo prompt + un
template Excel**, produce la evaluación completa de una propuesta OSCE —
incluyendo cosas que el plan original asignaba al backend (atomicidad de
periodos, cálculo de días/meses/años, evaluación de cumplimiento con razón
literal, factor A "años adicionales").

Evidencia: el Excel `02. Formato de evaluacion COMPLETADO - Consorcio Salud
Trujillo I.xlsx` (llenado por Claude solo) ya trae Paso 4 y parte del Paso 5
resueltos.

**Conclusión honesta**: el sistema determinístico que veníamos construyendo
**mejora poco** sobre lo que Claude ya hace solo. El motor local OCR+LLM se
vuelve redundante. Lo que Claude **NO** puede hacer (y sigue siendo nuestro
valor) son los **cruces contra fuentes oficiales** y la **verificación
determinística** de lo que Claude afirma.

> El prompt de Manuel (`100. Sintaxis Claude.docx`) tiene 15 notas acumuladas
> por iteración — son la prueba de que Claude **falla de formas conocidas**
> (omite experiencias, confunde postor/consorcio, salta ISOs, da por
> verificado lo que no verificó). El validador ataca exactamente eso.

---

## 2 · Arquitectura: dónde corre cada cosa

```
[ PC del ingeniero ]                  [ Servidor on-prem · red del cliente ]
  Claude Code (Max 5x)                  Backend InfoObras
  · lee bases.pdf + propuesta.pdf       · validador (openpyxl)
  · razona / evalúa                     · scrapers SUNAT + InfoObras
  · llena el Excel (formato Manuel)     · recálculos determinísticos
  · emite JSON espejo                   · PostgreSQL (histórico)
        │                               · regenera Excel final enriquecido
        │   Excel + JSON ── LAN ──►      · panel web
        ◄──── reporte / Excel final ──
```

**Regla de oro**: la PC hace lo no-determinístico (razonar sobre PDFs). El
servidor hace lo determinístico, lo que toca fuentes externas y lo que
persiste. **El validador NO corre en la PC del ingeniero — corre en el
servidor.**

### Por qué el validador va en el servidor (no en la PC)

| Razón | Detalle |
|---|---|
| Los scrapers ya viven ahí | SUNAT/InfoObras con TLS adapter + retry están en el backend Alpamayo. No se duplican en la PC. |
| Scraping sin exponer el server | El servidor hace requests **salientes** a SUNAT/InfoObras. No se abre ningún puerto entrante a internet. |
| Histórico + panel | PostgreSQL y el panel ya están en el servidor; el validador necesita persistir → ahí. |
| Un solo punto de mantenimiento | Se actualiza una vez. Si entra otra persona de Indeconsult a evaluar, no se instala nada en su máquina. |
| Cero setup en la PC del ingeniero | Su máquina solo necesita Claude Code. No le metemos Python. |

### Constraint on-prem — se preserva

El scraping de portales públicos del Estado (SUNAT, InfoObras) **no es** una
API cloud de IA. La regla "el backend nunca llama a cloud" se refiere a no
mandar datos del cliente a servicios de IA externos. Los cruces oficiales
siempre estuvieron permitidos (ya estaban en el diseño original). ✓

---

## 3 · Contrato de datos: **Excel + JSON espejo** ⭐

**Decisión central de este documento.** Claude emite **dos artefactos** por
cada análisis:

| Artefacto | Para quién | Rol |
|---|---|---|
| **Excel** (formato Manuel) | El humano | Lectura, revisión, entregable visual. Una sola hoja, 5 partes. |
| **JSON espejo** | La máquina (validador) | Transporte estructurado. Trivial de parsear, validar y cruzar. |

### Por qué los dos y no solo el Excel

- Parsear el Excel con openpyxl funciona (probado), pero es **frágil**: si
  Claude mueve una celda, agrega una fila o cambia un header, el parser se
  rompe.
- El JSON es **estable y autovalidante** (Pydantic). El servidor valida el
  JSON, hace los cruces, y **regenera el Excel final enriquecido** — no parchea
  el Excel de Claude, lo reconstruye con los datos verificados.
- El Excel de Claude queda como **fuente humana**; el JSON como **fuente de
  verdad de máquina**. Si discrepan, el servidor emite observación.

### El esquema canónico de Fase 1 NO se tira — revive aquí

El JSON espejo es la evolución del esquema canónico (`schema_canonico.md`).
Diferencias clave respecto a la versión original:

- **Antes**: 3 JSONs separados (bases, profesionales, experiencias), Claude
  solo extraía, backend evaluaba.
- **Ahora**: el JSON espejo **también incluye la evaluación** que hace Claude
  (Paso 4 + parte del Paso 5), porque ahora Claude evalúa. El backend
  **verifica y enriquece**, no re-evalúa desde cero.

### Estructura del JSON espejo (esqueleto)

```jsonc
{
  "_meta": {
    "analisis_id": "trujillo-cp02-2025--2026-05-30T...",
    "concurso": "...",
    "postor": "CONSORCIO SALUD TRUJILLO I",
    "fuente_excel": "02. Formato de evaluacion COMPLETADO ....xlsx",
    "version_contrato": "1.0.0",
    "generado_por": "claude-code"
  },

  // PARTE 1-2: postor
  "postor": {
    "formularios": [ /* anexos 1-6: presenta/no, folio */ ],
    "oferta_economica": { "monto": ..., "limite_inferior": ..., "cumple": ... },
    "experiencia_postor": [ /* contratos con monto, %, acredita */ ]
  },

  // PARTE 3: profesionales (info general)
  "profesionales": [
    {
      "n_prof": 1,
      "cargo": "GERENTE DE CONTRATO",
      "nombre": "...",
      "profesion": "...",
      "colegiatura": "...",
      "fecha_colegiatura": "YYYY-MM-DD",
      "profesion_valida": { "cumple": true, "detalle": "..." },
      "certificaciones": [ /* PMP, ISO, etc. con validez */ ],
      "folios": { "nombre": "...", "colegiatura": "..." }
    }
  ],

  // PARTE 4: experiencia por profesional (1 fila = 1 periodo, atómico)
  "experiencias": [
    {
      "n_correlativo": 1,
      "n_prof": 1,
      "proyecto": "...",
      "emisor": { "nombre": "...", "ruc": null },   // ruc: Claude puede dejar null
      "firmante": { "nombre": "...", "cargo_declarado": "Representante Legal" },
      "cargo_emisor_valido_claude": { "cumple": true, "detalle": "ASUMIDO" },
      "fecha_inicio": "YYYY-MM-DD",
      "fecha_fin": "YYYY-MM-DD",
      "dias": 753, "meses": 25.1, "anios": 2.06,   // Claude los calcula
      "folio": "...",
      "anterior_a_colegiatura": false,
      "cargo_ocupado": "...",
      "cargo_bases_valido": { "cumple": true, "detalle": "..." },
      "cert_antes_de_culminar": false,
      "incluye_covid": false,
      "tipo_obra_valido": { "cumple": true, "detalle": "..." },
      "nivel_categoria": "II-1",                    // capacidad nueva de Claude

      // ⚠ CAMPOS QUE CLAUDE DEJA null — EL SERVIDOR LOS LLENA:
      "_backend": {
        "fecha_creacion_emisor": null,        // SUNAT (ALT04)
        "alerta_antiguedad_emisor": null,     // ALT04
        "firmante_facultado_sunat": null,     // ALT12 — getRepLeg
        "vinculacion_postor_emisor": null,    // detección conflicto (nuevo)
        "codigo_ciu": null,                   // InfoObras
        "codigo_infoobras": null,             // InfoObras
        "paralizaciones": null,               // InfoObras
        "alerta_experiencia_antigua": null    // recálculo cutoff 25 años
      }
    }
  ],

  // PARTE 5: resumen de evaluación (factores A, B, C, E, J)
  "resumen_evaluacion": { /* puntajes por factor */ },

  // observaciones cualitativas de Claude (severidad + referencia)
  "observaciones_claude": [ /* ver schema_canonico §2 */ ]
}
```

> El bloque `_backend` es el **contrato explícito**: todo lo que está en `null`
> ahí es responsabilidad del servidor. Claude NO lo rellena. El validador, al
> recibir el JSON, sabe exactamente qué le toca.

---

## 4 · Transporte PC → servidor — **el cliente usa Claude Cowork**

**Dato confirmado (2026-05-30)**: Manuel usa **Claude Cowork** (corre dentro de
Claude Desktop). Cowork ejecuta MCPs — son el corazón de sus capacidades.

### La distinción que decide todo: MCP **local** vs MCP **remoto**

Verificado con doc Anthropic + confirmado por el cliente (2026-05-30):

| Tipo de MCP | Dónde corre el proceso | ¿Alcanza el servidor on-prem? |
|---|---|---|
| **Local** (stdio o HTTP local) | **En la máquina de Manuel**, como subproceso que Cowork lanza | ✅ **Sí**. Usa el stack de red de la PC → puede hacer requests a `http://192.168.x.x:puerto`, hostnames internos, VPN — igual que un `curl` desde su terminal. |
| **Remoto / hosted** (infra Anthropic o tercero) | En internet | ❌ **No**. Tendría que salir a internet y el servidor on-prem no está expuesto ahí. |

> **Corrección de un error previo de este doc**: yo había escrito "MCP
> descartado / Cowork corre en la nube". **Falso.** Un MCP **local** es un
> proceso en la PC de Manuel y alcanza la LAN sin problema. Lo único que NO
> sirve es el conector **remoto** (exigiría exponer el server a internet →
> viola on-prem). La distinción correcta es **local (sí) vs remoto (no)**.

### Caveats del MCP local → servidor on-prem (a resolver en implementación)

1. **Firewall del SO + reglas de red** siguen aplicando — el puerto del
   servidor debe estar abierto para la PC de Manuel en la LAN.
2. **Certificados internos**: si el servidor usa HTTPS con CA propia, el MCP
   debe confiar en esa CA (configurar CA bundle) o ir por HTTP en LAN cerrada.
3. **Auth**: el MCP necesita credencial para hablar con el servidor (token
   estático, mTLS, etc.). A definir según lo que use el backend.

### Patrón concreto para nuestro caso

MCP en Python (FastMCP) o TS, declarado como **local** en la config de Cowork,
exponiendo tools tipo `subir_y_validar(excel, json)` /
`consultar_estado(job_id)` que internamente hacen POST a
`http://servidor.lan:puerto`. El POST sale **de la PC de Manuel**, no de la
nube → on-prem intacto.

### Dos caminos de transporte (ambos viables)

**Camino A — MCP local (automático, con loop de corrección)**

```
Claude (Cowork) → tool subir_y_validar(excel, json)
   → MCP corre en la PC de Manuel → POST por LAN → servidor on-prem
   → servidor valida + cruza SUNAT/InfoObras
   → devuelve reporte → Claude corrige en la misma sesión y reenvía
```

Requiere: Manuel instala el MCP/plugin 1 vez + servidor alcanzable por IP LAN +
resolver los 3 caveats. Da la "sensación automática" sin violar on-prem.

**Camino B — Dropzone web (manual, cero instalación)**

```
Cowork escribe Excel + JSON en carpeta local de la PC de Manuel
   → Manuel los sube al panel (navegador en la LAN)
   → servidor valida + cruza → regenera Excel final + reporte
```

### Recomendación a este volumen (100-200/mes, 1 usuario)

**Empezar por B (dropzone) como MVP; A (MCP local) como upgrade fase 2.**
- B funciona hoy, cero instalación, ~15 s subir 2 archivos.
- A es más fluido pero suma: construir el MCP, instalarlo en la PC de Manuel y
  resolver firewall/CA/auth. Se justifica si crece el volumen o Manuel lo pide.
- **Clave de diseño**: el backend expone una **API HTTP desacoplada**. El
  dropzone Y el MCP llaman al **mismo endpoint** → agregar A después es casi
  gratis, sin retrabajo.

---

## 5 · Verificación SUNAT — **probada empíricamente** (2026-05-30) ✓

Se validó en esta laptop (con permiso explícito del cliente) que el portal
público de SUNAT expone los datos necesarios para ALT04 **y ALT12**, gratis,
sin clave SOL.

### ALT04 — fecha de creación del emisor

Ya funcionaba en `Alpamayo/src/scraping/sunat.py::consultar_ruc`. Devuelve
`fecha_inscripcion` / `fecha_inicio_actividades`. ✓

### ALT12 — firmante vs. representante facultado (NUEVO, antes era un supuesto)

- **Hallazgo**: `consultar_ruc` NO traía representantes. ALT12 nunca estuvo
  implementado de verdad; era un supuesto del plan.
- **Solución probada**: el endpoint `jcrS00Alias` con `accion: getRepLeg`
  devuelve la tabla de representantes legales:
  `Documento · Nro. Documento · Nombre · Cargo · Fecha Desde`.
- **Probado con 3 RUCs reales** del caso (empresa y dos consorcios): los tres
  respondieron al primer intento, status 200, tabla parseable.
- **Corrección importante**: los **consorcios CON RUC sí listan su apoderado**
  en SUNAT (yo había asumido que no). El caso "difícil" (certificado emitido
  por consorcio) **sí es verificable** si el consorcio tiene RUC.

### Lógica de negocio que el servidor debe implementar (no es scraping)

1. **Tabla de equivalencias de cargos**: SUNAT dice "APODERADO" /
   "GERENTE GENERAL"; el certificado dice "Representante Legal" /
   "Representante Común". El motor debe aceptar que esos cargos **facultan para
   firmar** (match semántico, no de string exacto).
2. **Vigencia temporal**: SUNAT da "fecha desde", no "fecha hasta". Validar
   `fecha_desde ≤ fecha_emision_cert`. Caveat: una baja de cargo no se ve →
   posible falso positivo.
3. **Detección de vinculación postor ↔ emisor** (capacidad nueva y valiosa):
   si el firmante del certificado aparece también como profesional del postor,
   o comparte apellido/RUC con el postor, marcar como **autocertificación
   intragrupo** → bandera para revisión humana. Claude solo NO detecta esto.

### Límites honestos (lo que queda a criterio humano)

- Emisor **sin RUC consultable** (persona natural) → "revisión manual".
- Si la autocertificación intragrupo **descalifica** o no → interpretación
  legal OSCE, **solo Manuel/abogado decide**. El sistema señala, no juzga.

---

## 5b · Verificación InfoObras — **probada empíricamente** (2026-05-30)

Probado en esta laptop con el caso Florencia de Mora (CUI 2258772).

### Por CUI (código) — ✓ funciona perfecto

`fetch_by_cui("2258772")` → obra 109442, nombre completo, entidad ESSALUD,
estado. Trae ficha + (cuando existen) supervisores, residentes, avances y
paralizaciones. **Confiable.**

### Por nombre — ⚠ funciona, PERO el extractor de keywords necesita afinarse

- **`buscar_obra_por_certificado()` con el nombre del CONCURSO completo → FALLÓ**
  (0 resultados).
- **Causa raíz confirmada**: el nombre que entrega Manuel es del *concurso de
  supervisión* (`"CONTRATACIÓN DEL SERVICIO DE CONSULTORÍA... HOSPITAL DE
  CONTINGENCIA FLORENCIA DE MORA..."`), pero en InfoObras la obra se llama
  `"MEJORAMIENTO Y AMPLIACION HOSPITAL I FLORENCIA DE MORA..."`. El extractor:
  1. No tiene `CONTRATACION` ni `CONTINGENCIA` en stopwords → las usa como
     keywords de alta prioridad.
  2. Esas palabras **no están en el nombre real** de la obra → la búsqueda por
     substring de InfoObras devuelve vacío.
- **Prueba real (output verificado)**: la búsqueda por nombre de InfoObras es
  por **substring contiguo**, no por tokens sueltos:
  - `"HOSPITAL FLORENCIA MORA"` → **0** (el nombre real intercala: "HOSPITAL **I**
    FLORENCIA **DE** MORA"; ese substring exacto no existe).
  - `"FLORENCIA DE MORA"` → **20** resultados (substring sí presente, pero
    genérico: plazas, colegios, etc. del distrito).
  - `"HOSPITAL I FLORENCIA"` → **2** resultados, **ambos CUI 2258772**. **El
    endpoint SÍ funciona**; lo que falla es la generación de la query.

- **Hallazgo nuevo e importante — el mismo CUI tiene DOS registros de obra**:
  - obraId **109442**: `"MEJORAMIENTO Y AMPLIACION HOSPITAL I FLORENCIA DE
    MORA..."` (el que `fetch_by_cui` devuelve como `obras[0]`).
  - obraId **537192**: `"HOSPITAL DE CONTINGENCIA FLORENCIA DE MORA:
    MEJORAMIENTO Y AMPLIACION..."` — **este coincide con el nombre del
    concurso** que evalúa Manuel.
  - ⚠ `fetch_by_cui` toma ciegamente el primero. Si los dos registros tienen
    datos distintos (avances, supervisores), podríamos leer el equivocado. El
    refactor debe **desambiguar cuando un CUI devuelve >1 obra** (elegir por
    estado/fecha/nombre, o traer ambos y marcar).

### Implicación para el refactor (acotada y arreglable)

- **Arreglo**: ampliar stopwords (`CONTRATACION`, `CONTINGENCIA`, `SERVICIO`,
  `CONSULTORIA`, `OBRA`, `PIP`, `RED`, `ASISTENCIAL`…) + extraer el bloque tras
  `"OBRA:"` o `"DEL PIP"` que suele contener el nombre real. **~0.5 día.**
- **Mejor aún**: cuando el documento trae **CUI** (como aquí), usar SIEMPRE el
  CUI como camino primario y el nombre solo como fallback/confirmación. El CUI
  es determinístico; el nombre es heurístico.
- **Caveat de cobertura**: obras en estado **"Sin Ejecución"** (como Florencia
  de Mora, que recién se licita) **no tienen** avances/paralizaciones/personal
  registrados — InfoObras no los tiene aún, no es falla del scraper. Para
  verificar *experiencias pasadas* de profesionales esto sí trae datos; para la
  obra que recién se licita, lógicamente está vacía.

> Nota de proceso: el nombre del concurso de Florencia de Mora coincide con el
> archivo `00. REQ. INTEGRADO - SUP. FLORENCIA 6.4.2026` en `docs/new/` — es la
> licitación **actual** que Manuel evalúa, no una experiencia pasada. Por eso
> está "Sin Ejecución". El cruce InfoObras aporta sobre todo en las
> **experiencias de los profesionales** (obras ya ejecutadas), donde sí hay
> avances y paralizaciones.

---

## 6 · Qué sobrevive y qué se descarta del plan original

| Componente | Estado | Nota |
|---|---|---|
| OCR local (PaddleOCR) | ❌ descartado | Claude lo hace mejor. Queda como fallback dormido. |
| Extracción LLM local (Qwen14B) | ❌ descartado | Reemplazado por Claude. |
| Motor de reglas re-evaluación Paso 4 | ❌ descartado | Claude evalúa; backend solo verifica. |
| 3 JSONs separados | ❌ reemplazado | Por 1 JSON espejo que incluye evaluación. |
| Esquema canónico (Fase 1) | ✓ revive | Como base del JSON espejo. |
| Diseño de subagentes (Fase 2) | ✓ revive | Para robustez a escala (propuestas de miles de folios). |
| Scraping SUNAT (ALT04) | ✓ se reusa | Ya funcionaba. |
| Scraping SUNAT representantes (ALT12) | ✓ nuevo, probado | `getRepLeg` — construir `consultar_representantes()`. |
| Scraping InfoObras | ✓ se reusa | Código CIU, paralizaciones. |
| Recálculo ALT03 (25 años) | ✓ se mantiene | Backend recalcula; Claude usó 20. |
| Validador determinístico del Excel | ✓ nuevo | Pieza central del refactor. |
| Excel final enriquecido | ✓ se mantiene | Servidor regenera, no parchea. |
| Panel web | ✓ se mantiene | Dropzone + histórico. Camino B (MVP). |
| MCP local (stdio/HTTP local) | ✓ viable (fase 2) | Subproceso en la PC de Manuel → usa su red → alcanza la LAN on-prem. Camino A. Ver §4 + caveats. |
| Conector MCP remoto (cloud) | ❌ descartado | Exigiría exponer el server a internet → viola on-prem. |
| Backend con API HTTP desacoplada | ✓ clave | Mismo endpoint sirve a dropzone Y a plugin MCP. Sin retrabajo. |

---

## 7 · Trabajo del refactor (~1 semana a 1½)

| # | Tarea | Días | Estado base |
|---|---|---|---|
| 1 | **Skill `/analisis-propuesta` en Cowork** — 3 subagentes: `agent-bases` (lee bases → requisitos/factores/personal clave), `agent-propuesta` (lee propuesta → profesionales/experiencias; se divide por profesional en propuestas grandes), `agent-evaluador` (cruza requisitos × experiencia → evalúa cumplimiento con razones literales). Orquestador consolida. Emite Excel + JSON espejo. | 2 | evoluciona Fase 2 |
| 2 | **Validador determinístico** — revisa Excel/JSON: experiencias omitidas (Nota 1), ISOs por código (Nota 4/14), solapes sin resaltar (Nota 9), fechas (Nota 13), conteo de periodos. | 1.5 | desde cero |
| 3 | **JSON espejo (contrato)** — schema Pydantic + bloque `_backend`. | 0.5 | revive de Fase 1 |
| 4 | **Cruces SUNAT** — `consultar_representantes()` (ALT12) + tabla equivalencias de cargos + match firmante + vinculación postor↔emisor. ALT04 ya opera. | 1 | scraping probado |
| 5 | **Cruces InfoObras** — ajuste extractor keywords + desambiguación CUI-doble + cableado paralizaciones a experiencias. | 1 | scraping probado |
| 6 | **Backend API HTTP + dropzone + Excel final** enriquecido. | 1.5 | base reusable |
| 7 | **Guía de uso + capacitación.** | 0.5 | — |
| | **TOTAL** | **~7.5-8 d** | |

> Nota: las tareas 4 y 5 tienen el **scraping ya probado** (§5, §5b) — el riesgo
> es bajo; lo que queda es cableado + lógica de negocio, no investigación.

---

## 8 · Económico (resumen — detalle fino en la llamada)

- Total acordado original: **S/. 9,600** (anticipo 2,880 ya cobrado).
- Pendiente: **S/. 6,720** (hito intermedio 3,840 + final 2,880).
- **Hito intermedio (3,840)**: corresponde a trabajo ya construido. El scraping
  —su componente más caro— es el **núcleo de este refactor**, no se tira.
- **Hito final (2,880)**: se redirige **íntegro** a este refactor, sin costo
  adicional, aunque suma la verificación de firmantes (ALT12) que no estaba en
  el alcance original — gesto por el cambio de rumbo.
- Total se mantiene; cambia el **contenido** por uno que el cliente sí usará.

---

## 9 · Decisiones (status)

| Decisión | Status |
|---|---|
| Claude = motor central (extracción + evaluación) | ✓ |
| Backend = verificación + enriquecimiento + persistencia (no re-evalúa) | ✓ |
| Validador corre en el **servidor**, no en la PC del ingeniero | ✓ |
| Contrato de datos = **Excel + JSON espejo** | ✓ |
| Servidor **regenera** el Excel final (no parchea el de Claude) | ✓ |
| JSON espejo incluye la evaluación de Claude + bloque `_backend` null | ✓ |
| ALT12 vía `getRepLeg` de SUNAT | ✓ (probado 2026-05-30) |
| Detección de vinculación postor↔emisor | ✓ (alcance nuevo) |
| Tabla de equivalencias de cargos (facultad de firma) | ✓ a implementar |
| Entorno del cliente = **Claude Cowork** (corre en Claude Desktop) | ✓ confirmado 2026-05-30 |
| Cowork SÍ ejecuta MCPs (plugins, conectores) | ✓ confirmado |
| MCP **plugin local** alcanza on-prem; **conector remoto** no | ✓ distinción clave §4 |
| Transporte MVP = **dropzone web** (Camino B) | ✓ cero instalación, funciona hoy |
| Transporte fase 2 = **plugin MCP local** (Camino A) | ⚠ verificar alcance LAN empíricamente |
| Backend expone **API HTTP desacoplada** (sirve a ambos caminos) | ✓ decisión de diseño |
| PC de Manuel alcanza el servidor por LAN | ✓ confirmado |
| Volumen = 100-200 análisis/mes, 1 usuario (Manuel) | ✓ confirmado |
| Tamaño de propuesta = grandes / miles de folios es lo normal | ✓ confirmado 2026-05-30 → subagentes = esencial, no opcional |
| ¿Formato Excel es definitivo? | ✓ **CONFIRMADO 2026-06-10**: el formato Libertador (`02. Formato de evaluacion COMPLETADO.xlsx`, hoja CLAUDE + hojas por profesional) es el definitivo — versión congelada |
| Cutoff ALT03: ¿20 o 25 años? | ✓ **CONFIRMADO 2026-06-10**: 25 años (decisión del cliente, ya no es discrepancia silenciosa) |
| ZIP de documentos InfoObras | ✓ **CONFIRMADO EN ALCANCE 2026-06-10**: sobre esos documentos se hace el análisis humano — ver `docs/backend/descarga_infoobras_experiencias.md` |
| ¿Claude puede emitir JSON espejo sin degradar el Excel? | ⚠ pendiente: corrida end-to-end de la skill (primer espejo real) |
| ¿Autocertificación intragrupo descalifica? | ⚠ criterio legal de Manuel ("no sabría" 2026-06-10) — el sistema solo marca la alerta |
