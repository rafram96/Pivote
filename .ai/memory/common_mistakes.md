# Errores ya cometidos (no repetir)

- **Clasificar por un solo campo**: el tipo expediente/obra se leía solo de
  `proyecto`; el certificado dice "Elaboración del ET: «X»" y la skill guardaba
  solo «X» → 51/68 expedientes tratados como obra. Clasificar por TODA la
  evidencia (proyecto + objeto + cargo).
- **Usar el dato bajo auditoría para decidir**: el solape con el periodo
  declarado elegía la obra → podía lavar mentiras (ADR-003). Revisar esta
  trampa en cada señal nueva.
- **Más candidatos sin más disciplina**: fusionar la base MEF sin candados
  SUBIÓ los mal-resueltos de 16 a 26 (F6). Toda ampliación de recall necesita
  su contrapeso de abstención.
- **Resolver CUIs desde la skill**: ~3M tokens quemados en una corrida
  investigando 60 CUIs por web — trabajo que el backend hace en milisegundos.
- **`git add` de carpetas**: se colaron XLSX de una sonda (`tools/_sonda_seace/`)
  a un commit; hubo que amendear. Rutas explícitas siempre.
- **Fiarse del departamento para desempatar homónimos**: viven en el mismo
  departamento; y el MEF a veces registra la sede de la entidad, no la obra —
  por eso el veto exige provincia declarada en AMBOS lados.
- **Cola geográfica de 2 niveles**: "…, HUARI, ANCASH" — el término previo al
  departamento puede ser distrito o localidad, no provincia; inferir provincia
  solo con 3 niveles.
- **Prints Unicode en Windows**: la consola cp1252 revienta con `→`/emoji;
  reconfigurar stdout a utf-8 o usar ASCII.
- **Asumir que la verdad auditada es perfecta**: al menos 2 casos de la
  auditoría humana apuntan al CUI equivocado (Tocache/Loreto,
  Cotabambas/Antabamba) — ante discrepancia sistemática, cuestionar también la
  referencia.
- **Documentos comerciales al repo**: `docs/comercial/` está gitignored a
  propósito; no forzar con `-f`.
