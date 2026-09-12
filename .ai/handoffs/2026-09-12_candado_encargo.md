---
timestamp: "2026-09-12"
agent: "candado_encargo"
session_status: "complete"
---

# Guardas de identidad SEACE y encargo

Se modificó `backend/validacion/candado_seace.py`: la promoción requiere la
señal fuerte `adjudicatario` a favor además de al menos dos señales fuertes y
cero contradicciones; entidad+objeto ya no confirma. `resumen_proceso` conserva
`contratos` con `id`, `titulo`, `award_id`, además de `descripcion` e `items` del
tender. Cuando hay IDs de contrato distintos, el resultado queda pendiente con
motivo explícito y mantiene las señales/candidatos. El rótulo confirmado habla
de coincidencias de metadatos y no de verificación íntegra del documento o
encargo. `confirmado_sin_adjudicatario` rechaza expresamente el rescate por
entidad+objeto.

`backend/reglas/cruces_fechas.py` comparte la guarda de pluralidad cuando el
resumen está bajo `proceso` y rechaza históricos cuya identidad solo tiene
entidad+objeto antes de cruzar fechas. Fechas y contradicciones fuertes siguen
siendo observaciones/reglas existentes.

Pruebas focales: `venv\\Scripts\\pytest.exe -q backend/tests/test_candado_seace.py
backend/tests/test_cruces_fechas.py` → **96 passed**. Una corrida adicional de
consumidores (`test_etapas_reales`, cronologías, aplicar identidad) dejó 112
pasadas y 10 expectativas antiguas que aún codifican entidad+objeto como gate
válido; requieren actualización coordinada por el integrador.

Corrección posterior: el candado persiste `contratos_multiples: true` solo cuando
`resumen_proceso` detecta IDs distintos; los gates lo respetan, y el gate histórico
exige además la señal exacta adjudicatario fuerte a favor. Se actualizaron las
expectativas circulares de SUNAT y los positivos de Gantt para incluir adjudicatario.
Suite de consumidores actualizada: **104 passed**.

El gate no acepta señales desconocidas/hipotéticas: retorna falso y deja la
consulta SUNAT normal. Suite combinada final: **201 passed**.
