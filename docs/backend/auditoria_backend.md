# Auditoría del Backend — Proyecto Pivote

Este informe detalla la auditoría técnica del backend del Proyecto Pivote realizada sobre el código del repositorio en la rama `demo`. Se evalúa la alineación de las reglas con la normativa de OSCE, la robustez del orquestador, resolvedor de CUI, scrapers y entregables, y se consolida el estado de mitigación de los hallazgos operativos detectados.

---

## 1. Alineación con las Reglas de Negocio de OSCE

El motor de reglas (`backend/reglas/calculo.py`) y el orquestador implementan fielmente las convenciones y reglas de evaluación requeridas:

1. **Conteo Inclusivo de Días**: 
   Toda diferencia de fechas se calcula como `(fin - inicio) + 1` (inclusive). Esto se alinea exactamente con los cálculos manuales del evaluador humano para acreditar periodos completos.
   
2. **Ajuste a la Ventana de Valorizaciones (Clamp - Fase 1)**:
   Se implementa el descuento de los tramos del certificado que caen fuera del periodo de ejecución real de la obra (antes de la primera valorización o después de la última).
   * **Implementación limpia**: En lugar de modificar las funciones puras en `reglas/`, la etapa de InfoObras calcula estos tramos excedentes e inyecta intervalos de tipo `"fuera_de_ventana"` en la lista de paralizaciones del enriquecimiento (`enr["paralizaciones"]`). De este modo, la fórmula `brutos - paralizaciones - traslapes` descuenta el tiempo no respaldado de forma natural.
   * **Guardas críticas**: 
     - Si la obra no tiene avances, todo el certificado se descuenta (0 días efectivos), marcando la experiencia en revisión como "obra sin valorizaciones".
     - Si la consulta al portal falla por red (ventana desconocida), el motor **no clampa a cero** (lo que causaría un falso rechazo), sino que mantiene el cálculo original y marca el veredicto como **provisional** enviándolo a revisión.

3. **Traslapes y Solapes (ALT11)**:
   Se fusionan los intervalos de experiencia del mismo profesional para evitar el doble conteo de días en periodos superpuestos. La lógica calcula la unión de intervalos y resta los días duplicados de manera exacta.

4. **Regla de Antigüedad (ALT03)**:
   Se calcula la fecha límite de antigüedad (25 años) restando el periodo a la fecha de presentación de la propuesta. El algoritmo maneja correctamente los años bisiestos (29 de febrero retrocede a 28 de febrero).

---

## 2. Auditoría de Módulos y Arquitectura

### A. Orquestador y Motor (`backend/orquestador/`)
* **Checkpoint y Resiliencia**: El `Motor` guarda el estado (`ResultadoEtapa`) tras cada etapa en la base de datos (o JSON local). Si un job se interrumpe, la reanudación salta las etapas que terminaron con estado `OK`.
* **Contención de Errores**: Las excepciones o fallas parciales (ej. una consulta de InfoObras fallida para un profesional) no detienen el pipeline completo. Se marca como `ERROR_PARCIAL` y el orquestador continúa con las demás experiencias del postor.
* **Flujo Human-in-the-loop**: Al resolver una revisión desde el panel (ej. ingresar un CUI manual), el motor ejecuta únicamente las etapas "aguas abajo" de ese item específico (`solo_items`), evitando regenerar descargas o consultas del resto del postor.

### B. Validador Determinístico (`backend/validacion/`)
* El módulo `notas.py` analiza el JSON espejo para comprobar la consistencia interna sin hacer llamadas externas ni requerir los PDFs:
  - **NOTA 1**: Cruza el total de experiencias y días extraídos contra el cuadro resumen del Anexo 16.
  - **NOTA 7**: Verifica que las experiencias de cada profesional estén ordenadas por fecha de finalización ascendente.
  - **NOTA 9**: Compara los traslapes detectados contra el campo estructurado `traslape` emitido por Claude.
  - **NOTA 10**: Valida que la bandera `incluye_covid` sea coherente con la ventana de emergencia nacional del Perú (`16/03/2020` al `30/06/2020`).
  - **Checks adicionales**: Verifica que los veredictos no estén vacíos, que la suma de días coincida con los totales y que el puntaje total del resumen coincida con la suma de factores.

### C. Resolución de CUI (`backend/resolucion/`)
* El resolvedor de CUI (`cui.py`) uniformiza todos los códigos CUI a 7 dígitos.
* Emplea un filtro estricto por substring exacta (`coincide_codigo`) para evitar colisiones de CUI parciales (por ejemplo, que SNIP `95555` coincida incorrectamente con la obra `2595555`).
* En caso de indisponibilidad del portal de Contraloría, propaga la excepción `PortalNoResponde` para guiar al evaluador en lugar de asumir erróneamente un resultado vacío.

### D. Capa de Scraping (`backend/scraping/`)
* Los scrapers (`infoobras.py`, `sunat.py`) realizan descargas directas sin navegador.
* **Warmup robusto**: La inicialización de la sesión HTTP en InfoObras cuenta con reintentos automáticos y backoff exponencial para resistir microcaídas.
* **SUNAT**: Clasifica de forma precisa las respuestas de RUC inexistente/inválido en lugar de reportar un error genérico de estructura, evitando falsas alarmas operativas.

### E. Entregables (`backend/entregables/`)
* **Excel Final Enriquecido**: Regenera un archivo estructurado con:
  - Hoja "CLAUDE" con la evaluación del LLM.
  - Hoja "Base de Datos" con todas las experiencias y autofiltros.
  - Hojas individuales por profesional que detallan el cuadro de hitos, desglose de días efectivos (Paso 5) y, a la derecha, la ficha oficial de InfoObras junto con sus valorizaciones y modificaciones de plazo (ampliaciones/suspensiones).
* **Columna "ARCHIVOS (ZIP)"**: Indica explícitamente si una valorización tiene sustento documental adjunto (`Sí (N)` o `—`) para que el evaluador audite rápidamente antes de abrir el ZIP.
* **Agrupación en ZIP**: Organiza los documentos descargados de forma estructurada: `Proyecto → Profesional → Experiencia → Valorizaciones → AAAA-MM MES → Documento`.

---

## 3. Estado de los Gaps Operativos Identificados y Corregidos

Durante el desarrollo de la auditoría se identificaron y solucionaron los siguientes puntos en la rama `demo`:

| Hallazgo / Vulnerabilidad | Impacto | Estado | Mitigación Aplicada |
|---|---|---|---|
| **Falta de retry en warmup GET** de InfoObras | Alto. Timeout en home abortaba la experiencia entera. | **Solucionado** | Se envolvió el GET inicial en `_crear_session()` en un bucle de 3 reintentos con backoff y logger warning. |
| **Falsas alertas en SUNAT** para RUC inexistente | Medio. Reportaba `estructura_desconocida` y warning en log. | **Solucionado** | Se actualizó `diagnosticar_html_sunat()` para capturar la frase "no es válido" y retornar `"ruc_inexistente"`, registrándolo como `logger.info`. |
| **Falta de departamentos en resolvedor** (`DEPTOS`) | Medio. Búsquedas difusas de obras en Callao, Arequipa, etc. fallaban. | **Solucionado** | Se expandió la lista `DEPTOS` en `cui.py` a los 25 departamentos del Perú en orden alfabético. |
| **No-determinismo** por nombres idénticos o límites de búsqueda | Medio. Diferentes corridas de CUI por nombre arrojaban resultados distintos. | **Solucionado** | Se validó el bypass de `obra_id` contra la cobertura real; si es ~0% pero existe otra con cobertura >0%, se ignora el bypass y se realiza una selección basada en la ventana de valorizaciones. Se agregó desempate por menor `codigoObra`. |

---

## 4. Verificación de Correctitud

Toda la suite de pruebas unitarias y de integración offline del backend se encuentra en estado **verde**:
* **Total de tests**: 112 pruebas ejecutadas y aprobadas.
* **Cobertura**: Incluye pruebas específicas para la lógica de clamp, desempate determinístico, reintentos de InfoObras, validación de notas (N1, N7, N9, N10), y la estructura del Excel y del ZIP final.

---

## 5. Recomendaciones de Evolución y Siguientes Pasos

1. **Integración del Cache de SUNAT**:
   El módulo `sunat_cache.py` (basado en PostgreSQL) está desarrollado pero aún no se utiliza en `EtapaSunatReal`. Se recomienda integrarlo cuando se active la base de datos PostgreSQL en el servidor para reducir llamadas y evitar bloqueos por límite de peticiones de SUNAT.
2. **Normalización de Cargos (ALT12)**:
   Actualmente la validación del firmante en SUNAT requiere correspondencia de cargos. Es conveniente formalizar la tabla de equivalencias de cargos (ej: "Apoderado", "Gerente General" correspondientes a "Representante Legal") para automatizar completamente la verificación de facultades.
3. **Monitoreo de Captchas en SUNAT**:
   Dado que SUNAT utiliza controles de tráfico, se debe mantener el monitoreo sobre la etiqueta `"captcha_real"` en los reportes de ejecución para reaccionar rápidamente si se endurecen las medidas de seguridad del portal.
