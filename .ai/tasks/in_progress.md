# En progreso

*(Actualizar al iniciar cualquier trabajo; mover a completed.md al cerrar.)*

- **Auditoría Lircay del ing. (28-jul PM) — diagnóstico CERRADO, 4 issues
  nuevas (#58-#61)**. El job es `371fa5a1e704` (postor A, Consorcio
  Supervisión Hospital Lircay = "bisbal"); su Excel es del server con código
  del 26-jul (pre-#51: por eso el resumen P5 traía efectivos imposibles —
  391>177; en `demo` actual salen 435/177/559/0 coherentes → **falta
  REDEPLOY + regenerar**, no hay bug vigente ahí). Certificados verificados
  FÍSICOS (Tomo II 213-216, imágenes extraídas con pdfimages):
  - **#58** DEDUP hereda obra solo por folio (E4 Lurigancho→Picota; folio
    corrido por la skill = 2º caso de #47, evidencia física en comentario).
  - **#59** CUI citado "exacto" aceptado con nombre+dpto+rubro contradichos
    (P9 Navarro: Yanahuanca/Pasco → veredas Ferreñafe; posible colisión
    CUI↔SNIP en `cui_exacto`).
  - **#60** el Excel rotula el CUI resuelto como "(del certificado)" —
    probado que los certificados NO citan CUI (`cert_marco`,
    excel_final.py:1283).
  - **#61** `ruc_match` eligió la fase equivocada (registro del ET vs obra,
    Santa Anita) — 5º caso de la exención ruc_match de la golden ancha,
    primero con documento físico.
  E1/E2 de Minchola: identificación CORRECTA (no tocar). #2 cerrada
  (absorbida por ADR-010). ⚠ #58/#59/#61 tocan `cui.py` → golden
  obligatoria en cada una; refuerzan mantener `cui.py` FUERA de
  T-REFACTOR-004 hasta que estas cierren.

- **🔴 PRIORIDAD MÁXIMA vigente (2026-07-28): issues #47, #52 y #53**
  (`prioridad-critica` en GitHub).
  - **#52 y #53 — tren backend, arrancable ya**: parser de oferta desde la
    prosa de DETALLE + candado ruidoso de 3 celdas vacías (#52); guardrail
    0/N con ítem de revisión de primer nivel — el 3.4 es ADMISIÓN (#53).
    Ambas `aprobado` en `backlog.md` con alcance re-escopado (contraste
    plan vs código del 28-jul).
  - **#47 — REABIERTA el 2026-07-28**: el candado de `folios.py` (41ea419)
    solo cubre el **0.3% del corpus** (2 de 729 recortes traen capa de
    texto); el caso que originó la issue (`95af90f1578e` p1e1, folio 358 vs
    359) es un escaneo y el módulo se abstiene. Lo implementado queda firme
    (la abstención ES el comportamiento correcto; nada de corregir por
    páginas vecinas). El fix real va **del lado de la skill**, ANTES del
    recorte: `agent-propuesta-profesional` ya lee los folios como imagen y
    puede confirmar que la página muestra al emisor.
- **#45 y #46 CERRADAS el 2026-07-28** — estaban sustancialmente
  implementadas en `demo` (`recalculo.py` + `integridad.py` #45;
  `excel_final.py:367`/`:1375` + ADR-013 validado con la golden ancha #46).
  Remanente desprendido y NO olvidado: la pata skill de #45 (podar
  agent-evaluador, se solapa con #49).
- **⚠ CORRECCIÓN (2026-07-28, desarrollador): la skill es de Claude Code, NO
  de Cowork → los cambios de skill NO requieren rebuild de plugin.** Cae el
  argumento de "agrupar todo en una sola rebuild": #47, #49, #50/ADR-010,
  #54 y la pata prompt de #53 **pueden desplegarse por separado**, cada una
  cuando esté lista. Lo que sí conviene seguir agrupando es la **prueba viva
  end-to-end** (es cara en tokens/tiempo y de paso ejercita
  `funciones_similares` de #31, pendiente desde su merge) — pero es una
  decisión de eficiencia de QA, ya no una restricción de despliegue.

- T-TAREA-ADR011 (Issue #26) CERRADA el 2026-07-25 — ver `completed.md`.
  PR #35 REVISADA Y MERGEADA a `demo` (2026-07-26, merge `506815d`); issues #26 y #30 cerradas.
- **Issue #31 — candado de correspondencia de cargo**: código MERGEADO a `demo`
  (2026-07-26) e issue cerrada. Queda **prueba viva** (correr un concurso
  end-to-end con la skill nueva — es lo único que ejercita
  `funciones_similares` de verdad) y **deploy**: la skill cambió, así que va
  con rebuild del plugin de Cowork. Ver
  `.ai/decisions/ADR-012-candado-cargo-nucleo.md`.
- **Panel: las sub-obras no se ven** → rafram96/panel-infoObras#1. El hueco es
  de dos lados: el backend no expone `sub_obras` en
  `GET /jobs/{id}/profesionales` (`api/app.py:674-681`, ~2 líneas) y el panel no
  lo lee. Hoy una experiencia multi-obra se renderiza SIN información de obra,
  en silencio.
- **Issue #51 — Falso CUMPLE**: CERRADA el 2026-07-27 (PR [#56](https://github.com/rafram96/Pivote/pull/56) mergeado a `demo`, 619 tests passed).
- **Issue #57 — Columna TOTAL**: Issue de seguimiento abierta para desambiguar la suma de la columna TOTAL.
- **Nuevas Tareas Creadas (Defectos 8, 9, 10, 11)**:
  - `T-TAREA-ISSUE52` (Defecto 8): Oferta económica incompleta en celdas de entregable.
  - `T-TAREA-ISSUE53` (Defecto 9): Experiencia del postor no computada cuantitativamente.
  - `T-TAREA-ISSUE54` (Defecto 10): Inconsistencia / No-determinismo en sustento textual de veredictos.
  - `T-TAREA-ISSUE55` (Defecto 11): Jerga técnica filtrada en celdas del evaluador.
- Ninguna otra tarea de código activa.
- Fase comercial: preparar/realizar la reunión de cotización con el cliente
  (materiales listos en `docs/nuevos_modulos/` v3 + interno en
  `docs/comercial/planeacion-v2-para-rafael.md`, gitignored).
