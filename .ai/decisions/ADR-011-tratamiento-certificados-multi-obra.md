# ADR-011 · Tratamiento de certificados multi-obra: extracción por sub-obras, resolución por resolver() completo y principio de no adivinar fechas

- Fecha: 2026-07-25 · Estado: **aprobado, pendiente de implementar**

## Contexto

Los certificados de trabajo multi-obra documentan un único vínculo laboral/contractual que abarca múltiples proyectos o infraestructuras. Existen dos realidades físicas y documentales distintas:

1. **Escenario A — Paquete Simultáneo por Diseño** (ej. HV Contratistas, Paquete 6): Un único contrato contractual que agrupa varios establecimientos ejecutados en paralelo con un mismo equipo técnico. El certificado emite un único rango global (`01/03/2022 – 31/07/2023`). El solape del 100% entre obras no es un artificio, es la realidad del encargo.
2. **Escenario B — Rotación Secuencial Declarada**: El profesional rotó entre obras en fechas distintas dentro del periodo contractual, y dichas sub-fechas vienen expresamente declaradas en el certificado o anexo.

### Problemas Técnicos e Importancia de OSCE:
- **No Adivinar / No Fabricar Evidencia**: Si el certificado impreso solo otorga un periodo global, particionar arbitrariamente el rango por cuenta propia ante el Comité de OSCE constituye una afirmación sin respaldo documental.
- **Riesgo de Falsos NO CUMPLE por Paralizaciones**: Si en un paquete simultáneo una sub-obra se paraliza pero las demás continúan activas, el profesional sigue trabajando. Recomputar tiempo o paralizaciones a nivel de sub-obra en el Escenario A castigaría injustamente al postulante.
- **Evitar Re-introducción de Falsos Positivos**: La resolución por sub-obra debe invocar la tubería completa de resolución (`resolver()`), no búsquedas léxicas "peladas" contra el MEF, para mantener los candados de seguridad (tokens distintivos, compuerta de rubro, vetos de ubicación/entidad).
- **Atribución de Rubro (Salud vs. Vial)**: Si las sub-obras pertenecen a rubros distintos y no se declaran sub-fechas, la asignación de tiempo por especialidad resulta genuinamente indecidible sin un anexo formal.

## Decisión

1. **Extracción en la Skill (`agent-propuesta-profesional.md`)**:
   - Conserva el nombre literal completo en `proyecto` (fidelidad legal del certificado).
   - Desglosa cada infraestructura limpia en `obras: [{ "proyecto": "...", "cui": null }]`, retirando conectores (*"Y EL"*, *"Y LA"*) y etiquetas de paquete (*"(PAQUETE 6)"*).
   - Mantiene `fecha_inicial`/`fecha_final` de cada sub-obra en `null` salvo que el documento o anexo las explicite literalmente (Escenario B).
2. **Cómputo de Días y Solape (En la Experiencia Madre)**:
   - El cómputo formal de tiempo y días acumulados se mantiene **en la Experiencia Madre** (rango contractual del certificado).
   - Para sub-obras con `fechas == null` (Escenario A), heredan el rango global y el motor de traslapos absorbe el solape del 100% entre ellas, acreditando los días netos exactos del contrato del certificado.
3. **Reuso de `resolver()` Completo en Backend**:
   - El backend procesa cada sub-obra invocando `resolver()` de `resolucion/cui.py` con todas sus compuertas de seguridad.
   - **Paquete Parcialmente Resuelto (1 de N)**: La experiencia cuenta como válida (respaldada por el certificado), pero el reporte visualiza explícitamente qué sub-obra no cargó CUI.
4. **Candado Multi-Rubro**:
   - Si las sub-obras resueltas pertenecen a rubros distintos (ej. Salud + Vial) o si una sub-obra no resuelve y existe indicio de mixtura, y el documento no trae sub-fechas declaradas, el backend asigna: **`POR CONFIRMAR — Certificado Multi-Rubro requiere Anexo de Desglose Temporal`**.
5. **Visualización en el Excel Final (`excel_final.py`)**:
   - Renderiza cada sub-obra verificada como un bloque completo e independiente de experiencia (Exp X.1, Exp X.2) con su recuadro MEF/InfoObras a la derecha.

## Alternativas consideradas

- **Recalcular paralizaciones por sub-obra en el Escenario A**: Descartado por generar falsos *NO CUMPLE* cuando 1 de N obras se paraliza pero el profesional continúa activo en las demás.
- **Particionar arbitrariamente las fechas cuando no hay anexo**: Descartado por violar el principio anti-alucinación (fabricación de evidencia ante OSCE).
- **Búsqueda léxica directa en `base_mef.py` sin `resolver()`**: Descartado por re-introducir falsos positivos (coincidencias débiles sin comprobación de emisor o rubro).

## Consecuencias

- **Positivas**: Resolución limpia y segura del caso real HV Contratistas; protección total ante el Comité de OSCE; cero duplicidad de días; candado automático para casos ambiguos multi-rubro.
- **Limitaciones**: Si un certificado multi-rubro no incluye anexo con sub-fechas, requerirá intervención humana para confirmar el desglose por especialidad.
