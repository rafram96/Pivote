# Reglas de negocio

## Principio rector

El sistema es un **detector de mentiras** en experiencias declaradas. Asimetría
total: un falso "a revisión" cuesta minutos del evaluador; un falso CUMPLE
destruye el producto. **Ante ambigüedad, abstenerse y mostrar candidatos.**

## Resolución de identidad (qué proyecto es)

- Criterios de IDENTIDAD seleccionan (nombre, N° de institución, RUC, ubigeo,
  entidad, rubro). Criterios de VERACIDAD (fechas/valorizaciones) solo emiten
  veredicto — nunca eligen (evita lavar periodos falsos).
- CUI citado en el certificado = autoritativo si existe exacto (los certs citan
  componentes de proyectos integrales; COARs son concesiones multi-región cuya
  ubicación oficial difiere legítimamente).
- Dos municipalidades distritales distintas no contratan la misma obra.
- El MEF a veces registra la inversión bajo la sede de la entidad ejecutora,
  no la obra física → los vetos de ubicación exigen contradicción DECLARADA en
  ambos lados, nunca por ausencia de datos.

## Expedientes (camino A)

- El estudio precede a la construcción: NO se le exigen valorizaciones ni se
  descuentan días por la ventana de la obra posterior.
- Sustento: contrato del expediente + resolución de aprobación (08-A) + hito
  "Aprobación del proyecto" de InfoObras cuando no hay valorizaciones.
- Pedido del cliente (T-005, por desarrollar): inicio del profesional ≥ firma
  del contrato; término ≤ fecha de la resolución de aprobación.

## Obras (camino B)

- Días efectivos = clamp a la ventana de valorizaciones; paralizaciones se
  restan (las invertidas inicio>fin se descartan con observación).
- Cobertura de valorizaciones < 50% del periodo → revisión; umbral 0.2.
- NO CUMPLE frágiles (sin valorizaciones / fetch caído / fecha ilegible) →
  revisión provisional, nunca veredicto duro.

## Cargo declarado vs cargo exigido (evaluación del RTM)

- El cargo de CADA experiencia debe corresponder a uno de los
  `cargos_validos` que listan las bases. Esa lista varía solo en el
  sustantivo inicial (especialista / responsable / encargado / ingeniero /
  inspector / coordinador…); el **núcleo de especialidad es obligatorio**.
- **Núcleo compuesto = TODOS sus términos.** Si las bases piden
  «planeamiento **y** costos», un cargo con costos pero sin planeamiento NO
  cumple — y al revés tampoco. Caso real (Comité, 2026-07-25), Especialista
  en Planeamiento y Costos: «Ing. de Costos y Presupuestos», «Ingeniero de
  Costos y Valorizaciones» y «Especialista en Costos, Metrados y
  Valorizaciones» (costos sin planeamiento) + «Especialista en
  Planificación» (planeamiento sin costos) → **ninguna acredita el cargo**.
- **Segunda puerta — funciones**: si el título no coincide, la experiencia
  solo se salva acreditando FUNCIONES/actividades equivalentes con
  documento adicional. Un certificado que solo dice «desempeñando el cargo
  de X, del … al …, en la obra Y» **no acredita funciones**: sin documento
  extra → NO CUMPLE (criterio literal del Comité en el mismo caso).
- La lista válida se lee de las **Bases Integradas limpias**: el tachado
  marca lo ELIMINADO y las versiones difieren en qué cargos admiten (en el
  caso citado, la versión tachada admitía «coordinador» y la vigente no).
- ⚠ **Trampa para cualquier matcher**: por tokens compartidos, «Especialista
  en Costos, Metrados y Valorizaciones» comparte COSTOS con «Especialista de
  Planeamiento y Costos» → un match laxo da **falso CUMPLE**. Hoy
  `cargo_bases_valido` lo juzga el LLM sin candado determinístico
  (`skill/prompts/agent-evaluador.md`, paso 2); `match_cargo.js` resuelve
  otra cosa (a qué cargo del Cuadro postula el profesional, no si la
  experiencia vale). Gap conocido — ver `InfoObras/.ai/context/
  capabilities.md`.

## Otras reglas fijadas

- ALT-03 (exp. antes de titulación): cutoff **25 años** (no 20).
- ALT-12 (firmante = representante legal): **DESCARTADA** como regla automática
  (falsos positivos); el dato se muestra informativo.
- Experiencia del postor (req. 3.4): la computa el Comité manualmente, no el
  backend (`etapas_reales.py:447`).
- Oferta sin IGV (Ley 27037 Amazonía): homogeneizar ×1.18 antes del límite
  inferior — decisión de criterio del Comité, se marca.
- Certificados multi-obra con un solo vínculo = UNA experiencia (el tiempo no
  se multiplica); sub-obras en `obras[]`.
- Formato del Excel final: congelado por el cliente (2026-06-10); cambios solo
  aditivos (hojas nuevas).
