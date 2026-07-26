# Handoff — punto de continuación

> Actualizado: **2026-07-23**. Si eres un agente nuevo: lee esto completo,
> luego `context/current_state.md` y los ADRs. No necesitas ninguna
> conversación previa.

## Nota de mantenimiento (2026-07-23) — el checklist de deploy RECAYÓ una vez

La auditoría de migración de la base `.ai` (dos niveles) encontró que
`context/roadmap.md` y `context/current_state.md` volvían a resumir el
checklist de deploy — el mismo patrón que ADR-S002 ya había corregido — y
los resúmenes eran peligrosos: omitían el merge del Panel y la regla de
orden de ADR-007 (plugin SOLO después del backend nuevo). Fase 1 de la
corrección ejecutada: ambos quedaron reducidos a puntero a
`InfoObras/.ai/tasks/active.md` (fuente única; verificado que ahí la regla
de orden está literal y el paso del Panel existe). Si ves el checklist
copiado en cualquier otro archivo, es una regresión: bórralo y deja puntero.

Más tarde el mismo día: **merge fast-forward `sonda/refactor-cui` → `demo`**
(`c31f71a`, solo local — push pendiente de confirmación del desarrollador;
la sonda no recibe más commits) y **Fase 2 de la corrección cerrada** sobre
`demo` (commits `c7045a7…`): coexistencia overview↔topology declarada, lista
T-00x consolidada en `vision.md` (raíz), tareas reubicadas por nivel,
ADR-S004 en la raíz, conteo de la golden con fuente única en
`architecture/backend.md`.

## Nota (2026-07-25) — ADR-011 arrancó, y un bug que apareció de paso

`EtapaResolucionCui.correr` (`etapas_reales.py`) acumulaba observaciones
`MULTI_OBRA` / `PROBABLE` / `PRIVADA` y **no las pasaba a `_res`**: se perdían
en el return, así que nunca llegaban al job ni al panel (solo quedaban, a
medias, en el enriquecimiento). Corregido en PR-1 del Issue #26. Si ves una
etapa que arma una lista `obs` y no la devuelve, es el mismo patrón.

## Nota (2026-07-26) — PRs 33/34/35 revisadas, corregidas y mergeadas a demo

Orquestación completa: #33 (pestañas/nombres) la mergeó el desarrollador;
#34 (SUNAT histórico) se mergeó tras corregir el hallazgo H2 del review
(`d59f900`: «habido durante la obra» exigía solo que un tramo TOCARA el
periodo → verde con días sin dato; ahora pide cobertura completa y degrada a
«No verificable» con los huecos listados); #35 (ADR-011 multi-obra) mergeó
limpia; #36 arregló el choque de integración 33×35 (tests con nombre de
pestaña viejo). Suite en demo: **333 passed**. H1 del review (fixture
`hacer_motor` sin `extras_sunat` → pytest puede tocar la red) quedó SIN
corregir por decisión del desarrollador. Pendientes que dejaron los merges:
**un solo rebuild del plugin** (33/34/35 tocaron skill/schemas — ADR-007:
viaja con el backend), **regenerar `golden_cui_baseline.json`** desde demo
(el actual es pre-refactor y da −10 falsos), y los issues del panel
(sub-obras panel#1 + render SUNAT).

25-jul: **issue #30 — el emisor del certificado en SUNAT** (rama
`rafram96/issue-30-mostrar-representante-legal`). Sondeada y cableada la
consulta "Información Histórica" (`getinfHis`, sin captcha) además de los
representantes legales (`getRepLeg`, ya existía sin usar). El bloque emisor del
Excel ahora responde **¿estaba HABIDO al emitir el certificado y durante la
obra?** con la pregunta en el título del campo, lista los representantes
(informativo — ADR-008 descartó ALT-12), y suma un cuadro histórico contiguo
(R:U) que corrió el de representante de obra a W:Z. Falta el render en el
panel (repo `Panel-InfoObras`): el JSON ya viaja con `representantes`,
`historico` y `habido`.
## Nota (2026-07-26) — issue #32, el factor de evaluación en cada hoja P

Rama `rafram96/issue-32-embeber-el-factor-2` (`17b1e04`), sobre demo ya con
33/34/35 dentro. Lo que un agente nuevo necesita para retomarlo:

- **Falta lo único que no se puede hacer offline**: correr un job real y MIRAR
  el recorte. No basta `regenerar_excel_final`: hay que re-correr
  `extraer_certificados.js` con `bases.pdf` y volver a subir el ZIP, porque los
  `certs/` en disco no tienen el `P{n}_FACTOR.pdf`. No re-scrapea nada.
- **El riesgo vivo es el número de página**, no el código: lo elige un LLM
  (`agent-bases`), y un recorte de la página equivocada se ve legítimo. El
  script valida el rango y avisa por stdout; la corrección real es mirarlo.
- **No agrava el pendiente de rebuild del plugin**: el cambio es compatible en
  ambos sentidos (un `P{n}_FACTOR.pdf` en un backend viejo se ignora; un
  backend nuevo sin el archivo genera la hoja como antes). Viaja con el rebuild
  único que ya deben 33/34/35.
- **Pendiente de cliente**: confirmar si el TDR y el Anexo 16 se quedan al
  INICIO de la hoja (hoy) o bajan junto al factor. Son dos líneas en
  `excel_final.py`.

## ¿Qué se estaba haciendo?

Semana 20-22 jul: **refactor completo del resolver de CUI** (rama
`sonda/refactor-cui`, 13 commits) — base local MEF, público-primero, camino
expedientes/obra, candados de abstención — validado con una auditoría golden de
277 casos (errores silenciosos 16→10, cero regresiones) y corridas reales.
Además: optimización de la skill (Paso 4.5), rescate del análisis San Isidro, y
actualización del paquete comercial de extras (T-003…T-008).

## ¿Qué falta? (en orden recomendado)

1. **Deploy como paquete** (cross-repo: backend + panel + plugin + server) —
   el checklist canónico vive en **`InfoObras/.ai/tasks/active.md`** (nivel
   sistema); aquí no se copia. Regla clave: NO entregar el plugin sin el
   backend nuevo (ADR-007).
2. Pulido camino A (filtro de secciones de obra en descargas/Excel).
3. Reunión de cotización (materiales: `docs/nuevos_modulos/*.html` v3).
4. Resto: `tasks/backlog.md`.

## Archivos clave

- Resolver: `backend/resolucion/cui.py` (+ `base_mef.py`, `texto.py`).
- Orquestación: `backend/orquestador/etapas_reales.py` (caller del resolver,
  camino A/B, clamps) y `motor.py`.
- Validación: `backend/scripts/golden_cui.py` + baselines en
  `backend/datos_pivote/golden_cui_*.json` (gitignored pero presentes local).
- Skill: `skill/SKILL.md` (Paso 4.5) y `skill/prompts/agent-propuesta-profesional.md`.
- Jobs de referencia local: `b4f385c31811` (San Isidro camino A, entregado),
  `c9c769976750` (replay BNP con `revision_manual.md`).

## Nota (2026-07-26) — #28 paso 1: el dato que estaba y nadie leía

Antes de agregar columnas a la base MEF, revisar si el campo ya está cargado.
`estado_dataset` viajaba en `base_mef.py` desde F3, se exponía en la ficha del
candidato y **ningún consumidor lo leía**: 229k de 494k filas son DESACTIVADAS
y competían de igual a igual con las vivas. Usarlo rompió el empate de Sullana
de 4 a 2 y liberó el 23% del presupuesto de consultas al portal, sin regenerar
el artefacto (PR #39). El alcance original de la #28 arrancaba por regenerar la
base; el orden correcto era al revés.

**Regla que salió de acá:** las señales de la base MEF son DESEMPATE, jamás
filtro. 15 de 191 verdades auditadas viven en filas DESACTIVADA (un CUI
reformulado queda desactivado y el certificado cita al viejo). Y el guard exige
el dato en AMBOS lados: un CUI ausente de la base es DESCONOCIDO, no vivo —
resolver apoyándose en la ausencia de información es adivinar.

**Trampas del dataset de 68 campos, medidas (para el paso 2):**
- `DES_TIPOLOGIA` está VACÍA en los dos CUIs de referencia (2483109, 2502652);
  0% en desactivadas, 32.6% global. No sirve como veto.
- `TIPO_INVERSION` no es binario "PROYECTO vs IOARR": son 8 valores y las obras
  ARCC del caso HV son `INTERVENCIONES IRI`. Un veto por tipo mata al correcto.
- Las DESACTIVADAS no traen `PRIMER/ULTIMO_DEVENGADO` (solo el acumulado).
- `golden_cui.py:190` arma la experiencia con `fecha_inicial: None` → cualquier
  regla de ventana temporal es INERTE en el golden. Para medirla hay que
  enriquecer el corpus con las fechas del cert (join `job` + `prof:exp` contra
  los `espejo.json`).

## Riesgos vivos

- Server en producción corre el código VIEJO hasta el deploy.
- Los baselines/caches de la golden viven solo en esta laptop (datos_pivote
  gitignored) — no borrarlos; sin ellos la re-validación exige corrida en vivo
  (~1.5 h contra InfoObras).
- Límite de gasto mensual de la cuenta Claude alcanzado (21-jul): subagentes
  pueden morir a mitad; preferir trabajo directo o esperar el ciclo.
- 2 verdades de auditoría dudosas (ver `tasks/backlog.md`).

## Regla de oro antes de tocar el resolver

Cualquier cambio se valida así, en este orden:
`pytest backend/tests -q` (offline) → `golden_cui.py --con-base --solo-cache`
→ comparar contra `golden_cui_baseline.json`. Criterio: mal-resueltos nunca
suben, cero correcto→incorrecto. Nunca relajar compuertas para "ganar" casos
(ADR-005).
