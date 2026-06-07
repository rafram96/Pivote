# `src/referencia/` — snapshots del backend Alpamayo-InfoObras

Esta carpeta contiene **copias de SOLO LECTURA** de módulos del backend de
producción `Alpamayo-InfoObras` que el pivote reusará tal cual.

## ⚠ Política de uso

- **No editar nada aquí.** Si necesitas cambios, se hacen en `Alpamayo-InfoObras`
  y se vuelve a copiar el snapshot. Estos archivos son referencia de diseño,
  no código de producción.
- **No importar desde aplicaciones reales.** El código de producción sigue
  viviendo en `Alpamayo-InfoObras/src/scraping/`. Estos archivos están aquí
  solo para que las sesiones de planeación del pivote tengan los módulos a
  mano sin abrir el otro repo.
- Cuando termine el pivote, esta carpeta puede borrarse — su utilidad es
  acelerar la fase de diseño.

## Snapshots actuales

| Carpeta | Fuente original | Snapshot |
|---|---|---|
| `scraping_alpamayo/sunat.py` | `Alpamayo-InfoObras/src/scraping/sunat.py` | 2026-05-27 |
| `scraping_alpamayo/sunat_cache.py` | `Alpamayo-InfoObras/src/scraping/sunat_cache.py` | 2026-05-27 |
| `scraping_alpamayo/infoobras.py` | `Alpamayo-InfoObras/src/scraping/infoobras.py` | 2026-05-27 |
| `scraping_alpamayo/__init__.py` | `Alpamayo-InfoObras/src/scraping/__init__.py` | 2026-05-27 |

## Rol en el pivote

Estos módulos son los que el nuevo endpoint `POST /api/analizar` del backend
invocará para enriquecer el JSON que viene desde Claude:

- `sunat.consultar_ruc(ruc)` → ALT04 (empresa creada después de inicio
  experiencia) y ALT12 (firmante ≠ representante legal). Llena las cols
  11-12 del Paso 3 que Claude deja vacías.
- `infoobras.fetch_by_cui(cui)` → cols 27-28 del manual (CIU + InfoObras)
  + paralizaciones para Paso 5 (días efectivos descontando suspensiones).
- `infoobras.verificar_profesional_en_obra(...)` → cruce de
  supervisor/residente declarado vs registrado en InfoObras.

## Para refrescar el snapshot

```bash
cp /c/Users/Holbi/Documents/Freelance/proyectos/InfoObras/Alpamayo-InfoObras/src/scraping/{__init__.py,sunat.py,sunat_cache.py,infoobras.py} src/referencia/scraping_alpamayo/
```

Y actualizar la fecha en la tabla de arriba.
