# Visión general del sistema

Investigación de identidad (2026-09-10): tras el primer resultado, la skill puede
obtener contexto por MCP y producir propuestas por caso con evidencia en un JSON
separado. No hay promoción al job ni llamadas IA desde backend. Implementado local;
pendiente validación real. Ver `skill/references/investigacion-identidad.md`.

> **Coexistencia deliberada**: si este checkout incluye la raíz del sistema
> (`../../.ai/`), la fuente oficial de la arquitectura global es
> `../../.ai/topology.md` — este documento es el resumen AUTOSUFICIENTE para
> cuando Pivote se clona solo (ADR-S002 del nivel sistema). Si editas la
> forma del sistema, edita topology.md primero y este resumen después.

**InfoObras Pivote** extrae datos y reúne fuentes para contrastar propuestas
técnicas de concursos públicos OSCE (consultoría/supervisión de obra, Perú).
Identifica proyecto, intervención y contratación; conserva diferencias y
documentos con su procedencia. La verificación y sustentación final pertenecen
al ingeniero (aclaración del usuario, 10-sep-2026). Los cálculos/rótulos
existentes son auxiliares; no certifican autenticidad ni dictamen final.
Ante ambigüedad de identidad, "Por confirmar", nunca adivinar.

## Arquitectura híbrida (regla inquebrantable)

```
[Máquina del cliente — Claude Code (Claude Max 5x)]
  Skill analizar-licitacion-osce (skill/ + plugin/ empaquetado)
  ├─ subagentes: bases ∥ propuesta-mapa → N×propuesta-profesional → evaluador
  └─ produce: espejo JSON + Excel "claude" + certificados.zip
        │  (MCP local mcp-server/ o dropzone del panel)
        ▼
[Backend on-prem (Servidor Windows) — FastAPI, backend/]      ⛔ JAMÁS llama APIs cloud de IA
  pipeline por job: ingesta → validación → resolución de CUI → InfoObras
  ∥ SUNAT → reglas/Paso 5 → Excel final + ZIP → persistencia
        ▼
[Panel Next.js — repo hermano Panel-InfoObras]
```

- El backend solo recibe JSON ya extraído; toda la IA corre en la suscripción
  del cliente. PDFs y datos del cliente NUNCA van al repo.
- Archivos = fuente de verdad (carpeta por job en `datos_pivote/`);
  Postgres = respaldo lógico opcional.

## Los dos caminos de verificación (por experiencia)

- **Camino A — Expedientes/estudios**: verificación MEF (contrato del expediente
  + resolución de aprobación del ET, Formato 08-A); sin exigencia de
  valorizaciones (el estudio precede a la construcción). Modo forzado por
  concurso: `PIVOTE_FORZAR_EXPEDIENTES=1`.
- **Camino B — Supervisión/ejecución de obra**: InfoObras (valorizaciones,
  paralizaciones, días efectivos con clamp, documentos al ZIP).

Detalle por capa: [`backend.md`](backend.md) · [`frontend.md`](frontend.md) ·
[`database.md`](database.md) · [`infrastructure.md`](infrastructure.md) ·
[`integrations.md`](integrations.md). Diagrama presentable:
`docs/nuevos_modulos/arquitectura-sistema.html`.
