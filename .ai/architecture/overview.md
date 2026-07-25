# Visión general del sistema

> **Coexistencia deliberada**: si este checkout incluye la raíz del sistema
> (`../../.ai/`), la fuente oficial de la arquitectura global es
> `../../.ai/topology.md` — este documento es el resumen AUTOSUFICIENTE para
> cuando Pivote se clona solo (ADR-S002 del nivel sistema). Si editas la
> forma del sistema, edita topology.md primero y este resumen después.

**InfoObras Pivote** audita propuestas técnicas de concursos públicos OSCE
(consultoría/supervisión de obra, Perú) para el cliente Indeconsult (Ing. Manuel
Echandía). Detecta si la experiencia declarada por cada profesional es real:
un **falso CUMPLE es el peor fallo posible**; ante la duda el sistema se abstiene
("Por confirmar"), nunca adivina.

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
