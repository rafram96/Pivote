# Pendientes del proyecto — cierre del contrato

> Fuente única de lo que falta para cerrar. Última actualización: 2026-07-13.
> ✅ hecho · ⏳ pendiente · ❌ descartado.
>
> Los bloques B (core), C (deuda técnica) y D (alcance nuevo) se sacaron de
> esta lista: lo hecho quedó en el historial de git; lo nuevo se cotiza aparte.

## 🔴 A — Cerrar el contrato (hito final S/. 2,880)
| # | Pendiente | Estado | Esfuerzo |
|---|---|---|---|
| A1 | Desplegar en el servidor de Manuel | ✅ hecho (2026-07-12): compose backend+panel+Postgres, 3 contenedores healthy | — |
| A3 | Capacitación (2 h) | ⏳ agendar (tras A6/A7) | 2 h |
| A4 | Manual de usuario | ✅ hecho | — |
| A5 | PostgreSQL cableado al backend | ✅ implementado Y **validado en local** (2026-07-13): 201 tests con pg real + job e2e en esqueleto → jobs/documentos/profesionales se llenan. OJO: en esta laptop hay un Postgres local de Windows en el 5432 — para pruebas usar otro puerto (55432). En el server no aplica (red interna del compose) | — |
| A6 | Instalar skill + MCP en el Claude Code de Manuel | ⏳ `npm install` en mcp-server + `claude mcp add` con SERVER_URL=IP LAN del server. Skill ya sincronizada al repo | ~1 h (AnyDesk) |
| A7 | Prueba de fuego: 1-2 propuestas REALES de punta a punta en su máquina (skill → MCP → server → panel → Excel/ZIP), ideal una con expedientes (ejercita el Paso 4.5/MEF) | ⏳ la validación que de verdad cuenta | ~2 h (AnyDesk) |

**Camino:** A5 (validar en local) → A6 → A7 → A3 (capacitación) → **cobrar hito 3**.

## ⚪ E — Frentes aparte (FUERA del contrato; vida y cobro propios)
| Ticket | Frente | Estado |
|---|---|---|
| T-003 | **Verificación SEACE + MEF** (expedientes: contrato/contratista/resolución) | ✅ CONSTRUIDO (13-jul): Paso 4.6 en la skill (SEACE bases+contrato, SSI sin captcha, Formato 08-A, contraste en observaciones_claude) + prompt manual suelto (`docs/prompt-verificacion-expediente.md`). **Cobrar S/ 2,100** — enviar cotización ANTES de entregar. Upsell: integración panel/Excel (~S/4,600) |
| T-002 | **Radar SEACE** (concursos diarios, VR/plazo/cociente) | reunión por agendar; guion en `docs/comercial/radar-seace-reunion.html`. Reemplaza al viejo E3 (cotizador) |
| — | **Jurisprudencia lexcontrataciones** (resoluciones TCP, control de calidad ≈ supervisión) | skill de Manuel por revisar; adaptar Playwright→Chrome MCP; login lo hace el humano; cotizar tras ver la skill |
| T-004 | **Segundo cerebro oficina** (índice del NAS, 8 personas) | 🧊 ASPIRACIONAL — Manuel confirmó "ahora no es así, es para proyectar" (12-jul). NO trabajar hasta reunión + caso de uso + piloto cotizado. Diseño: índice local + NAS solo-lectura; consultas del equipo SIN IA (Excel/buscador en server) |
| — | **RENIPRESS / obras privadas** | solo idea; discovery primero; frontera explícita: lo privado NO está en InfoObras/MEF/SEACE |
| E1 | Telegram bot (puente al Claude del Ingeniero) | en pruebas; falta acceso a red (E:/NAS) + PC prendida |
| E2 | Claude-Odoo | solo mención; discovery primero |
| E4 | **Web HK** | cotización LISTA (S/1,500, `docs/comercial/cotizacion-web-hk.html`) — solo falta ENVIARLA; subida con dominio dispara el cobro |
| — | **Bolsa mensual de horas** | diseñada (`docs/comercial/estrategia-extras.html`) — presentar CON la entrega final |

---

## Plan acordado
- **Ahora:** cerrar el **bloque A** (A5 local → A6/A7 por AnyDesk → capacitación) y **cobrar el hito 3**.
- **En la entrega final:** presentar el paquete comercial de una vez — bolsa mensual + cotización T-003 + web HK.
- **E y tickets:** cotización aparte, cada uno gana su lugar con reunión/caso de uso; nada se empieza sin OK y adelanto.
