# Descarga de archivos InfoObras + ZIP por EXPERIENCIA (alcance futuro)

> Estado: ⏳ **pendiente de detallar** — el cliente dará más detalle más adelante.
> Doc creado tras la **aprobación del pivote** (2026-06-01).

## Hito: pivote aprobado ✓

El cliente (Ing. Manuel Echandía / Indeconsult-Alpamayo) **aprobó el pivote**
tras la demo de:
- Arquitectura híbrida (Claude extrae en su máquina + backend on-prem verifica).
- Skill con subagentes + MCP local.
- Cruces en vivo SUNAT + InfoObras (ALT04, ALT12, Paso 5).

→ Se pasa de planeación a implementación. Este doc captura un **nuevo bloque de
alcance** que surgió en esa conversación.

## Nuevo alcance: profundizar la extracción de InfoObras

Hasta ahora el scraping de InfoObras devuelve **datos estructurados** (obra,
supervisores, residentes, avances, paralizaciones). El nuevo requerimiento va
más allá: **descargar los archivos/documentos** que InfoObras expone y
**empaquetarlos en un ZIP con carpetas estructuradas por EXPERIENCIA**.

### Lo que se pidió (literal, alto nivel)
1. **Descargar a un directorio cada archivo** disponible en InfoObras para la
   obra/experiencia.
2. **Construir un ZIP** con esos archivos organizados en **carpetas, una por
   EXPERIENCIA**.

> "más detalle más adelante" — el cliente especificará nombres exactos y qué
> archivos exactamente. La **jerarquía de carpetas ya está definida** (abajo).

### Estructura de carpetas del ZIP (definida por el cliente · 2026-06-01)

Jerarquía de 4 niveles: **Proyecto → Profesional → Experiencia → Archivos**.

```
<Nombre_de_Proyecto>/                  ← ej. "...Urcos" (el concurso/obra)
├── <Profesional 1>/                   ← cada profesional listado en la propuesta
│   ├── <Experiencia 1>/               ← cada experiencia dentro de ese profesional
│   │   └── (archivos extraídos de InfoObras para esa experiencia)
│   ├── <Experiencia 2>/
│   │   └── (archivos…)
│   └── …
├── <Profesional 2>/
│   ├── <Experiencia 1>/
│   │   └── (archivos…)
│   └── …
└── …
```

- **Nivel 1 — Proyecto**: nombre del concurso/obra (ej. "Urcos").
- **Nivel 2 — Profesional**: una carpeta por cada profesional listado.
- **Nivel 3 — Experiencia**: una carpeta por cada experiencia de ese profesional.
- **Nivel 4 — Archivos**: los binarios extraídos de InfoObras para esa experiencia.

> Pendiente de afinar: la **nomenclatura exacta** de cada nivel (cómo nombrar
> proyecto/profesional/experiencia) y **qué archivos** concretos van en el nivel 4.

## Preguntas abiertas (resolver con el cliente antes de implementar)

| # | Pregunta | Por qué importa |
|---|---|---|
| 1 | **¿Qué archivos exactamente?** ¿Documentos adjuntos de la obra en InfoObras (actas, conformidades, anexos), imágenes de avance, PDFs de registro? | Define qué endpoints/descargas scrapear (nivel 4 del árbol) |
| 2 | ~~¿Qué define una "EXPERIENCIA"?~~ ✓ **Resuelto**: nivel 3 del árbol = una experiencia por profesional. | — |
| 3 | **¿Nomenclatura exacta de cada nivel?** (cómo nombrar la carpeta de proyecto, profesional y experiencia) | Estructura ya definida; falta el naming exacto, consistente con el Excel Lircay |
| 4 | **¿Una experiencia puede compartir archivos con otra?** (mismo profesional en obras distintas, o misma obra entre profesionales) | ¿Se duplica el archivo en cada carpeta o se referencia? |
| 5 | **¿Dónde corre?** ¿Parte de la Fase A (enriquecimiento backend on-prem) o utilitario aparte? | Encaje arquitectónico |
| 6 | **¿Entregable?** ¿El ZIP se adjunta al job/panel, va al share de red, o ambos? | Define el output del flujo |

## Encaje arquitectónico (tentativo, a confirmar)

- Vive en el **backend on-prem** (no expone nada a internet; InfoObras es portal
  público que el backend ya consulta).
- Reusa la infra de scraping de `Alpamayo-InfoObras/src/scraping/infoobras.py`
  (sesión, fetch por CUI). Habría que **descubrir los endpoints de descarga de
  archivos** (hoy solo extraemos datos estructurados, no binarios).
- Se dispara junto con el enriquecimiento de cada obra/experiencia, o como paso
  adicional que produce un artefacto `ZIP` por análisis.

## Relación con piezas existentes

- **BD de Experiencias (Paso 3)** — define la lista de experiencias (las filas);
  cada una mapearía a una carpeta del ZIP.
- **`src/scraping/infoobras.py`** — base para descubrir descargas de archivos.
- **Encargo separado de Manuel** (descargar certificados de SU empresa + correo
  confirmatorio + PDF al share) — *relacionado pero distinto*: aquel parte del
  Excel y usa certificados propios; este parte de InfoObras y arma un ZIP por
  experiencia. **No confundir.** Ver conversación previa.

## TODO cuando llegue el detalle del cliente
- [ ] Confirmar las 6 preguntas abiertas de arriba.
- [ ] Investigar endpoints de descarga de archivos en InfoObras (¿qué binarios expone por obra?).
- [ ] Definir estructura del ZIP (árbol de carpetas + nomenclatura).
- [ ] Estimar e incorporar a la cotización de implementación.
