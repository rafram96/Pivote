# Pendientes del proyecto — inventario A–E

> Fuente única de lo que falta. Última actualización: 2026-06-23.
> ✅ hecho · ⏳ pendiente · ❌ descartado.

## ✅ Ya hecho (no re-decidir)
Manual de instalación · manual de usuario · plan de BD (modelo "Base de Datos") ·
constancias embebidas · informes de control · ZIP nombres cortos · razones literales
en "no cumple" · blindajes de la skill (veredicto + anti-contaminación) · descarga
diferida · observabilidad (resumen + métricas) · **B1 (la ausencia no invalida)** ·
**B2 (resumen "X de Y no encontrados")**.

---

## 🔴 A — Cerrar el contrato (hito final S/. 2,880)
| # | Pendiente | Estado | Esfuerzo |
|---|---|---|---|
| A1 | Desplegar en el servidor de Manuel | ⏳ runbook listo, falta ejecutar | ~0.5 d |
| A2 | Correr propuestas reales + que las apruebe | ⏳ depende de Manuel | — |
| A3 | Capacitación (2 h) | ⏳ pendiente | 2 h |
| A4 | Manual de usuario | ✅ hecho | — |
| A5 | PostgreSQL (lo cobra el contrato; hoy archivos) | ⏳ decisión: cablear o aceptar archivos v1 | ~1.5–2 d |
| A6 | Reiniciar el backend (activa /zip atómico + nombres cortos) | ⏳ pendiente | minutos |

## 🟡 B — Mejoras del core
| # | Pendiente | Estado | Esfuerzo |
|---|---|---|---|
| B1 | Regla "no encontrado = válido + alerta" | ✅ hecho | — |
| B2 | Resumen "X de Y proyectos no encontrados" | ✅ hecho | — |
| B3 | Mejorar precisión buscador nombre→CUI | ❌ descartado | — |
| B4 | Completar factores / las "15 alertas" | ⏳ pendiente | ~1 d |
| B6 | Cruce de conteo roster vs bases (validador) | ⏳ pendiente | ~0.5 d |
| B7 | Nomenclatura: agregar el apellido a carpetas/hojas | ⏳ pendiente | ~0.25 d |

## 🟣 C — Deuda técnica / robustez
| # | Pendiente | Estado | Esfuerzo |
|---|---|---|---|
| C2 | /zip async (servir estático + 202 "en preparación") | ⏳ pendiente | ~1 d |
| C3 | Lock compartido motor↔API (race del backfill, multi-usuario) | ⏳ pendiente | ~0.5 d |
| C4 | Re-empaquetar el plugin de Cowork (`build.ps1`) | ⏳ si se despliega como plugin | ~0.25 d |

## 🔵 D — Alcance nuevo (se cotiza aparte)
| # | Pendiente | Estado | Esfuerzo |
|---|---|---|---|
| D1 | Experiencia del postor 3.4 (automatizar) | ⏳ pendiente | ~2–3 d |
| D2 | Recortes-imagen de bases B.1/B.2 + Anexo (gap del .docx SINTAXIS) | ⏳ confirmar con Manuel | ~1 d |
| D3 | Rediseño del panel (Stitch → código) | ⏳ pendiente | ~2–3 d |
| D4 | Persona maestra deduplicada por DNI (BD v2) | ⏳ pendiente | ~1 d |

## ⚪ E — Side-projects (FUERA del analizador; vida y cobro propios)
- **E1** Telegram bot (puente al Claude del Ingeniero) — en pruebas; falta acceso a red (E:/NAS) + PC prendida.
- **E2** Dispatch (acceso móvil a proyectos locales) — sin refinar.
- **E3** Cotizador (búsqueda diaria de convocatorias) — falla la búsqueda en la web del Estado.

---

## Plan acordado
- **Ahora:** B1 ✅ + B2 ✅.
- **Sigue:** todo el **bloque A** (cerrar el contrato), y luego **detalles del panel**.
- **B3 descartado** (complejidad alta, retorno incierto).
- **D y E:** cotización aparte, no entran en este contrato.
