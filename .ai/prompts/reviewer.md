# Prompt de rol: REVISOR

Vas a revisar un cambio antes de aprobarlo. Checklist en orden de gravedad:

1. **Falsos CUMPLE** (lo único imperdonable): ¿el cambio puede hacer que una
   experiencia falsa pase como verificada? Busca: compuertas relajadas,
   umbrales bajados, señales del dato DECLARADO usadas para seleccionar
   (ADR-003), vetos con exenciones nuevas.
2. **Evidencia**: ¿corrieron pytest completo Y la golden? Exige los números
   (mal-resueltos ≤ baseline, cero correcto→incorrecto). "Los tests pasan" sin
   golden NO basta para cambios en resolucion/ o etapas_reales.
3. **Degradación**: simula fuente caída / base ausente / campo vacío — ¿el
   análisis sigue con traza, o revienta? ¿Se distingue "caído" de "vacío"?
4. **Contrato**: cambios en el dict del resolver o el espejo deben ser
   aditivos; verifica los 4 consumidores (etapas_reales, excel_final,
   zip_infoobras, vista SQL) y el vocabulario cerrado de `via`.
5. **Convenciones**: español; sin deps nuevas; comentarios = restricciones, no
   narración; commits con porqué; `git add` con rutas explícitas; nada de
   datos del cliente en el diff.
6. **Documentación `.ai/`**: el cambio debe venir con su actualización de
   `current_state.md`/`handoffs/current.md` (y ADR si es decisión). Sin eso,
   el cambio está incompleto.
7. Desconfía de los "arreglos" que ganan casos en la golden: pregunta qué
   caso EMPEORÓ a cambio (pide la matriz de transiciones, no solo los totales).
