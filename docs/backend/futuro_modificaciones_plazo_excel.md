# Futuro — Mostrar "Modificaciones de plazo / datos de la obra" en el Excel

> Estado: **PENDIENTE (diseño)**. No implementado a propósito — anotado para un
> posible futuro tras la conversación del 2026-06-16. La data **ya se captura y
> ya viaja al Excel**; lo único que falta es renderizarla.

## Qué dispara esto

En la ficha de InfoObras de cada obra hay secciones ricas que hoy NO se muestran
en el entregable, pero que suman al criterio del evaluador. Caso real: obra
CUI 2164051 (Hospital El Carmen, Huancayo) tiene **6 ampliaciones de plazo**
(372, 403, 324, 479, 157, 65 días) que explican por qué la obra siguió "viva"
años después de su fin contractual original — contexto directo para juzgar una
experiencia certificada.

## Lo que YA está hecho (no rehacer)

1. **Parseo** — `backend/scraping/infoobras.py` ya modela TODO en `WorkInfo`:
   `modificaciones_plazo` (`ModificacionPlazoInfo`: tipo, causal, dias_aprobados,
   fecha_aprobacion, fecha_fin), `contratistas` (`ContratistaInfo`: tipo_empresa,
   ruc, nombre_empresa, monto, fechas), `supervisores`, `residentes`, `adendas`,
   `cronogramas`, `controversias`.
   - Ojo: las modificaciones de plazo vienen como **tabla HTML**, no como var JS
     (`lModificacionPlazo` está vacía) — ya resuelto con
     `_parsear_modificaciones_html`. Ver memoria `infoobras-secciones-tabla-html`.
2. **Enriquecimiento** — `backend/orquestador/etapas_reales.py` (~L310) ya guarda
   `enr["modificaciones_plazo"]` como lista de dicts
   `{tipo, causal, dias, fecha_aprobacion, fecha_fin}`.
3. **Transporte al Excel** — el mismo archivo (~L749) ya mete
   `"modificaciones_plazo"` dentro del `ficha` que recibe `construir_hoja_profesional`.

➡ **Conclusión**: el dato llega hasta `fichas[(n_prof, n_exp)]["modificaciones_plazo"]`.
Falta SOLO el render.

## Lo que falta (el trabajo real)

En `backend/entregables/excel_final.py`, dentro de `construir_hoja_profesional`,
agregar un bloque (debajo del cuadro de valorizaciones o al costado del cuadro
emisor) que liste las modificaciones de plazo de la obra de esa experiencia:

```
MODIFICACIONES DE PLAZO (InfoObras) — contexto, NO cuentan como experiencia
N° | TIPO                  | CAUSAL                          | DÍAS | APROBADA   | NUEVA FECHA FIN
1  | Ampliación del plazo  | Otro                            | 372  | 16/06/2016 | 05/03/2018
2  | Ampliación del plazo  | Atrasos no atribuibles…         | 324  | 14/11/2016 | 01/03/2020
…
```

Opcional (decisión del cliente):
- **Datos de la obra**: contratista (RUC + razón social + monto), supervisor/
  inspector, residente — un mini-cuadro de identificación de la obra.
- Resaltar las suspensiones de plazo (coinciden con los periodos sin valorización
  que el Paso 5 ya descuenta).

## Consideraciones

- **Solo presentación**: estas modificaciones NO entran al cálculo de días
  efectivos (eso lo gobiernan las valorizaciones/paralizaciones). Es contexto.
- Encaja en la banda derecha o como bloque nuevo bajo valorizaciones; reusar
  `FILL_PARTE`/`F_PARTE` y `BORDER` ya existentes.
- Hay fichas con muchas filas (6+ ampliaciones); usar altura/wrap como en las
  valorizaciones.

## Esfuerzo estimado

~0.5 día: una función `render_modificaciones(...)` análoga a `render_emisor`, su
test en `test_entregables.py`, y regenerar un Excel de muestra para validar con
el cliente. Sin tocar scraping ni enriquecimiento (ya están).
