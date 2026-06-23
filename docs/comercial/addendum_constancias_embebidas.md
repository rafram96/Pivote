# Addendum al contrato — Constancias embebidas en el Excel

> Para leer antes de la llamada con Manuel. Es **un solo ítem extra**, planteado
> con honestidad: la mayor parte del trabajo adicional entró **sin costo** bajo
> las iteraciones que el contrato ya incluye. Esto es lo único que sí es módulo nuevo.

---

## El extra: constancias dentro del Excel
**Antes** (lo que define el contrato): el Excel tiene 5 hojas de **datos**
(Resumen, Base de Datos, Evaluación RTM, Alertas, Verificación InfoObras), y los
documentos van **en el ZIP aparte**. Para ver una constancia, el evaluador abre el
PDF de ~2,000 folios y la busca.

**Ahora** (lo que sumamos): **cada constancia queda incrustada como imagen dentro
del Excel**, en el bloque de su experiencia. El evaluador **ya no abre el PDF** —
ve el sustento al lado del análisis.

## Por qué es un extra (y no "ajuste incluido")
El contrato ya incluye **3 iteraciones de ajuste** (Sección 13: *formatos de Excel,
prompts, reglas, según casuística real*). Bajo eso entró —**sin cobro**— casi todo:
- el reformato del Excel a tu formato revisado (marco por certificado, Parte 5, colores),
- los ajustes de prompts/reglas de la skill,
- la cobertura de obras de educación además de salud.

Lo de las constancias embebidas **es distinto**: no es calibrar un formato, es una
**capacidad nueva** que no estaba en el alcance (el módulo de Excel definía hojas
de datos, no documentos embebidos). Por eso es lo único que planteo cobrar.

## Qué se construyó (para que se entienda que es trabajo real)
Una cadena nueva de punta a punta:
1. la **skill** recorta del PDF las páginas exactas de cada constancia,
2. el **backend** las renderiza a imagen (motor PyMuPDF) y las **incrusta** en el Excel,
3. se resolvió el detalle **folio ≠ página** (el folio impreso no coincide con la
   página del PDF) con un dato extra (`paginas_pdf`) para no traer la imagen equivocada.

Esfuerzo real: ~2 a 2.5 días.

## Propuesta económica
- **S/. 600 – 900** como módulo adicional (precio modesto, a propósito, por la relación).
- Se mantiene todo lo demás del contrato sin cambios.

## Lo que NO se cobra (buena fe — mencionar en la llamada)
Para que quede claro que esto no es "inflar la cuenta": entró **sin costo
adicional** el reformato del Excel a tu gusto, los blindajes de calidad de la skill,
la cobertura de educación, la optimización de velocidad (resultados en ~1 min) y el
ZIP de documentos con nombres compatibles con Windows. Eso es bastante más trabajo
que este único ítem que sí propongo cobrar.

---

## Puntos para la llamada (3 frases)
1. *"De todo lo extra que salió en el camino, casi todo entró sin costo bajo las
   iteraciones que ya cubre el contrato."*
2. *"Lo único que es módulo nuevo de verdad son las constancias incrustadas en el
   Excel — ya no abres el PDF para verlas. Eso no estaba en el alcance."*
3. *"Lo pongo en S/. 600–900, modesto. El resto del contrato sigue igual."*
