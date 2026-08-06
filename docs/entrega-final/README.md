# Entrega final de InfoObras

Este directorio reúne la documentación que acompaña la entrega del sistema.
Está escrita para dos perfiles:

- **evaluador:** usa la skill y el Panel para analizar propuestas;
- **administrador:** instala, verifica y mantiene el servicio y la base MEF.

## Documentos

1. [Manual de la skill](01-manual-skill.md): iniciar un análisis y reconocer una
   salida lista para revisar.
2. [Manual del Panel](02-manual-panel.md): concursos, resultados, revisiones y
   descargas.
3. [Manual de la base MEF](03-manual-base-mef.md): qué valida, cómo buscar y
   cómo comprobar su vigencia.
4. [Setup e instalación](04-setup-instalacion.md): servidor, computadora del
   evaluador y pruebas de aceptación.

## Orden recomendado de capacitación

1. Ejecutar una propuesta controlada con la skill.
2. Seguir el análisis desde el Panel.
3. Resolver un caso marcado **Por confirmar**.
4. Descargar y revisar el Excel y el ZIP de evidencias.
5. Mostrar una búsqueda directa en la base MEF.
6. Explicar al administrador el estado de salud, la actualización MEF y los
   respaldos.

## Criterio general de lectura

InfoObras cruza información y conserva evidencia, pero no reemplaza el juicio
del comité evaluador. Cuando las fuentes no permiten sostener una conclusión,
el sistema se abstiene y muestra **Por confirmar**. Eso es una protección contra
falsos cumplimientos, no un fallo del análisis.

## Control previo a la entrega

- [ ] Panel y backend accesibles desde otra computadora de la red local.
- [ ] PostgreSQL y base MEF en estado saludable.
- [ ] Skill enlazada y transporte automático probado.
- [ ] Un análisis de prueba llega a estado terminal.
- [ ] Excel y ZIP abren y corresponden al mismo análisis.
- [ ] Una revisión manual persiste después de reiniciar los servicios.
- [ ] Actualización MEF manual y tarea semanal verificadas.
- [ ] Respaldo y restauración ensayados.
- [ ] Capacitación realizada y responsable de operación identificado.
