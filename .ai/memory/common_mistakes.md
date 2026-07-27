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
  propósito; no forzar con `-f`. **Y el repo es PÚBLICO**: no es una preferencia
  de orden, es que publicarías precios y cuentas por cobrar en internet, de forma
  irreversible (el historial queda). Antes de commitear un HTML nuevo, mirar si
  tiene montos, IP del servidor o postura de negociación. El 27-jul un dashboard
  con S/ 10,300 por cobrar y `192.168.100.5:8001` estaba en `docs/nuevos_modulos/`
  — la carpeta que se le comprime al cliente.
- **Crear issues sin leer `.ai/decisions/` primero**: el 27-jul se abrió la issue
  #50 re-derivando ADR-010 (decidido el 25-jul), con vocabulario distinto
  (`_meta.tipo_concurso` vs el real `concurso.tipo_evaluacion`) y reabriendo una
  pregunta que el cliente ya había cerrado (el concurso es homogéneo). **Antes de
  proponer un diseño, buscar en `decisions/` por el tema.**
- **Asumir que la skill instalada es la del repo**: durante 13 días
  `~/.claude/skills/` corrió una copia del 14-jul **sin el escudo de integridad**
  — podía subir corridas incompletas, que es justo la falla que el escudo arregla.
  Nada avisa cuando derivan. Hoy es un junction al repo; si alguna vez se
  reinstala como copia, la deriva vuelve.
- **`rm -rf` sobre un junction de Windows**: se recorre hacia adentro y borra el
  DESTINO. Así se perdió `backend/datos_pivote`. Para quitar un enlace:
  `cmd //c rmdir "<ruta>"` (sin `/S`) o `(Get-Item ruta).Delete()` en PowerShell.
- **Guardar respaldos dentro de `~/.claude/skills/`**: esa carpeta se
  auto-registra, y un respaldo aparece como skill invocable con la misma
  descripción que la real. Los respaldos van fuera.
