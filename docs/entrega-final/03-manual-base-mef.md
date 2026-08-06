# Manual de usuario y operación — Base local MEF

## 1. Qué aporta

InfoObras mantiene una copia local actualizable de datos públicos del Banco de
Inversiones del MEF. Permite:

- encontrar una inversión por CUI, SNIP o nombre;
- recuperar denominación oficial, entidad, ubicación y situación;
- detectar CUIs omitidos o mal transcritos;
- comparar candidatos antes de consultar otras fuentes;
- distinguir una ausencia de una coincidencia solo parecida.

La carga preparada contiene más de 620 mil registros y más de 579 mil CUIs
distintos. La fecha y el volumen vigentes aparecen en el estado de salud y
cambian con cada actualización.

## 2. Cómo participa en un análisis

La consulta es automática para experiencias públicas. El evaluador no debe
buscar cada CUI. La base propone evidencia y el resolvedor aplica candados de
identidad; se abstiene cuando las señales se contradicen.

Una inversión desactivada no se descarta automáticamente: puede ser un CUI
histórico válido. Tampoco la ausencia demuestra que la experiencia sea falsa,
especialmente si la base está desactualizada.

La base MEF no se usa como fuente de obra pública en una experiencia privada.
En esa ruta corresponden SUNAT y la documentación presentada.

## 3. Búsqueda directa

El buscador acepta CUI o SNIP exacto, nombre parcial y filtros de ubicación o
entidad. Desde la red local:

```text
http://<servidor>:8001/api/pivote/mef/buscar?q=<consulta>&limite=10
```

Para soporte desde el contenedor:

```powershell
docker compose -f .\Pivote\deploy\docker-compose.yml exec backend `
  python -m scripts.buscar_mef "hospital abancay" --limite 5
```

La primera consulta después de iniciar el proceso puede tardar mientras se
carga el índice; las siguientes son rápidas.

## 4. Vigencia y estados

Consulte:

```text
http://<servidor>:8001/api/pivote/salud
```

El bloque `base_mef` informa antigüedad, último refresco y conexión a
PostgreSQL.

| Estado | Significado | Acción |
|---|---|---|
| `ok` | Carga válida y vigente | Ninguna |
| `stale` | Superó la antigüedad permitida | Actualizar |
| `refresco_fallido` | Falló el último intento; se conserva la carga anterior | Revisar causa y repetir |
| `missing` | No existe carga publicada | Instalar o restaurar |
| `invalid` | Los artefactos no son coherentes | Restaurar la última carga sana |

El umbral predeterminado es 10 días. Con una actualización semanal tolera un
retraso breve y avisa si se pierde el siguiente ciclo.

## 5. Actualización

Desde la raíz de Pivote:

```powershell
.\deploy\actualizar-mef.ps1
```

Si termina bien, registre la tarea semanal desde PowerShell como administrador:

```powershell
.\deploy\registrar-tarea-mef.ps1
```

Corre los domingos a las 03:00, evita actualizaciones simultáneas y guarda logs
en `%ProgramData%\InfoObras\logs`.

La publicación es atómica: un fallo no reemplaza la última base sana. El
backend adopta una carga nueva sin reinicio.

## 6. Comprobación posterior

1. Confirme que el script terminó sin error.
2. Abra `/api/pivote/salud` y compruebe `estado: ok`.
3. Compruebe que PostgreSQL está disponible.
4. Busque un CUI conocido y otra inversión por nombre.
5. Revise que no aparezca un aviso de desactualización.

Si el refresco falla, conserve el log. El análisis puede seguir con la carga
anterior, pero debe avisarlo para no interpretar la ausencia de una obra
reciente como conclusión definitiva.
