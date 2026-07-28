# Índice de `docs/` — Pivote InfoObras

> Mapa de toda la documentación del sistema organizada por componentes y dominios del **Pivote InfoObras**.

---

## 1. Fuentes de Verdad

| Documento | Descripción / Ámbito |
|---|---|
| [`../README.md`](../README.md) | Visión general del repositorio |
| [`arquitectura/vision_general.md`](arquitectura/vision_general.md) | **Arquitectura de alto nivel (las 4 piezas del pivote)** |
| [`despliegue/despliegue-runbook.md`](despliegue/despliegue-runbook.md) | **Runbook canónico de despliegue on-prem (Windows 11 + Docker)** |

---

## 2. Estructura Organizada de `docs/`

```text
docs/
├── arquitectura/       # Visión general y contratos de alto nivel
├── backend/            # Especificaciones técnicas y modularización del backend
├── despliegue/         # Runbooks y guías de instalación activa
├── frontend/           # Especificación del Panel Web (Panel-InfoObras)
├── ejemplos/           # Schemas JSON de referencia y datos de prueba
├── html_renders/       # Artefactos visuales HTML renderizados (organizados por categoría)
│   ├── backend/        # Vistas visuales de backend, esquemas y endpoints
│   ├── despliegue/     # Guías visuales de instalación y variables
│   └── panel_y_demos/  # Guías de uso, guiones de demo y maquetas del panel
├── comercial/          # Material comercial y cotizaciones (gitignored)
├── nuevos_modulos/     # Especificación de cotización de módulos adicionales
└── presentaciones/     # Decks de presentación en HTML
```

### 📐 `arquitectura/` — Visión de Alto Nivel
- [`vision_general.md`](arquitectura/vision_general.md) — Las 4 piezas del pivote y su flujo end-to-end.

### ⚙ `backend/` — Especificación y Auditoría del Backend
- [`README.md`](backend/README.md) — Mapa de componentes del backend.
- [`analisis_tamanio_y_modularizacion.md`](backend/analisis_tamanio_y_modularizacion.md) — **Diagnóstico de archivos monolíticos e issue `T-REFACTOR-004`**.
- [`resolucion_cui.md`](backend/resolucion_cui.md) — Motor de resolución CUI y desambiguación MEF/InfoObras.
- [`auditoria_backend.md`](backend/auditoria_backend.md) — Auditoría del backend.
- [`validador.md`](backend/validador.md) — Validador determinístico.
- [`modelo_datos.md`](backend/modelo_datos.md) — Modelo de datos PostgreSQL.
- [`orquestador.md`](backend/orquestador.md) — Pipeline de etapas del orquestador.
- [`descarga_infoobras_experiencias.md`](backend/descarga_infoobras_experiencias.md) — Scraping de experiencias InfoObras.
- [`futuro_modificaciones_plazo_excel.md`](backend/futuro_modificaciones_plazo_excel.md) — Modificaciones de plazo en entregable Excel.

### 🚀 `despliegue/` — Guías de Despliegue y Runbooks Activos
- [`despliegue-runbook.md`](despliegue/despliegue-runbook.md) — **Checklist canónico de despliegue on-prem** (Windows 11 + Docker Desktop + LAN).
- [`preparacion-pdfs-corrida.md`](despliegue/preparacion-pdfs-corrida.md) — Runbook de preparación previa de PDFs antes de correr el análisis.

### 🖥 `frontend/` — Especificación del Panel Web
- [`README.md`](frontend/README.md) — Especificación de pantallas del panel (`Panel-InfoObras`).
- [`plan.md`](frontend/plan.md) — Plan del frontend MVP.

### 📦 `ejemplos/` — Schemas JSON de Referencia
- Schemas JSON de prueba para licitaciones (`lircay_bases.json`, `lircay_experiencias.json`, `lircay_profesionales.json`, `arquitectura-claude-telegram.json`).

### 🎨 `html_renders/` — Renderizados Visuales HTML (Por categoría)
- **`backend/`**: `arquitectura_backend.html`, `modelo_datos.html`, `orquestador.html`, `pruebas_e2e.html`, `sunat_endpoints.html`, `json_espejo_explicado.html`.
- **`despliegue/`**: `despliegue-runbook.html`, `manual_instalacion.html`, `variables-entorno.html`.
- **`panel_y_demos/`**: `guia_panel.html`, `manual_usuario.html`, `maqueta_paso5.html`, `guion_demo.html`.

### 💼 `comercial/` *(gitignored)*
- Propuestas comerciales, adendas, cotizaciones y roadmaps.

### 🎬 `presentaciones/` & `nuevos_modulos/`
- Presentaciones HTML para demostraciones al cliente y propuestas de módulos extra.
