# Convenciones de código

- **Español en todo**: código, comentarios, docstrings, mensajes, tests.
- Comentarios solo para restricciones que el código no puede expresar
  (decisiones con su porqué, 2-6 líneas); nunca narrar "qué hace la línea".
- **Sin dependencias nuevas** sin ADR (nada de pandas/duckdb/SQLite/ORM).
  rapidfuzz es dependencia dura; psycopg solo se usa si hay `PIVOTE_DB_URL`.
- Config por `os.getenv("PIVOTE_*", default)` leída en el punto de uso.
- Degradación segura SIEMPRE: fuente externa caída o dato ausente → el análisis
  sigue, con evento de traza/observación — jamás excepción que tumbe el job.
- Distinguir "portal caído" (PortalNoResponde) de "sin resultados" — nunca
  degradar en silencio.
- Cambios al contrato del resolver/espejo: solo ADITIVOS (los consumidores
  Excel/ZIP/panel/SQL leen claves específicas).
- Escritura de archivos de datos: atómica (tmp + os.replace), conservando la
  versión anterior si falla.
- Tests offline por defecto (fakes inyectables, fixtures mini); la red en vivo
  solo en scripts/sondas explícitas y con pausas entre llamadas.
- Windows dev: prints ASCII-safe o `sys.stdout.reconfigure(encoding="utf-8")`
  (la consola cp1252 revienta con flechas/emoji).
- Archivos temporales: NUNCA en la raíz del repo (usar scratchpad de la sesión
  o `backend/datos_pivote/` que está gitignored).

## Entorno de desarrollo

- **La skill instalada es un enlace al repo, no una copia** (27-jul-2026):

  ```
  ~/.claude/skills/analizar-licitacion-osce  →  Pivote\skill
  ```

  Es un **junction** de Windows (`New-Item -ItemType Junction`); el symlink real
  requiere modo desarrollador. Motivo: durante 13 días el entorno corrió una copia
  del 14-jul **sin el escudo de integridad**, y nada avisa cuando derivan. Con el
  enlace, cambiar de rama cambia la skill.

  Se descartó un script de sincronización: sigue dependiendo de que alguien lo
  corra, que es justo lo que falló.

  ⛔ **Nunca borrar ese enlace con `rm -rf`** — un junction se recorre hacia
  adentro y se lleva `Pivote/skill/` completo (así se perdió `datos_pivote`).
  Para quitarlo: `cmd //c rmdir "<ruta>"` sin `/S`.

  ⛔ **Los respaldos de skills no van dentro de `~/.claude/skills/`**: esa carpeta
  se auto-registra y el respaldo aparece como skill invocable.
