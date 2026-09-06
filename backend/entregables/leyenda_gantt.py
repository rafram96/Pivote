"""Significados compartidos por el Gantt editable y el de cada profesional."""
from entregables.certeza import (
    COLOR_INFERIDO, COLOR_PRIVADA, COLOR_SIN_IDENTIFICAR, COLOR_VERIFICADO,
)

COLORES_GANTT = (
    (COLOR_VERIFICADO, "Verde: CUI citado en el certificado o confirmado por un documento del MEF."),
    (COLOR_INFERIDO, "Violeta: identificación del proyecto inferida; requiere corroboración."),
    (COLOR_SIN_IDENTIFICAR, "Amarillo: proyecto pendiente de identificar, total o parcialmente."),
    (COLOR_PRIVADA, "Gris: experiencia privada; no requiere CUI."),
    ("F4B183", "Naranja: traslape entre experiencias; esos días se cuentan una sola vez."),
)

MARCAS_GANTT = (
    ("C", "C: fecha de firma del contrato del expediente; no es el inicio declarado del profesional."),
    ("R", "R: fecha de la resolución que aprueba el expediente; no es el fin declarado del profesional."),
    ("≈", "≈: fecha declarada solo con mes y año; se usa mes completo cuando la regla lo permite."),
    ("C/R", "C y R juntas: ambos hitos caen en el mismo bimestre, no necesariamente en el mismo mes o día. Las fechas figuran junto al proyecto."),
    ("Fechas", "Inicio / Fin: límites del período usado para el cálculo, en día/mes/año. Si fueron deducidos, se indica; no son días acreditados por una fuente externa."),
)

NOTAS_GANTT = (
    "Las barras representan los períodos declarados. Su color indica la certeza "
    "de identificación del proyecto, no la validez del período ni del cargo.",
    "Cada columna representa dos meses: Ene–Feb, Mar–Abr, May–Jun, Jul–Ago, Sep–Oct o Nov–Dic; el año figura arriba. "
    "La barra colorea los bimestres que toca el rango; los límites exactos figuran como Inicio / Fin. "
    "Varias marcas juntas comparten esa columna, no necesariamente la misma fecha. "
    "Sin barra: no hay período computable.",
    "Cruces de fechas: SÍ = orden temporal compatible; NO = discrepancia; "
    "POR VERIFICAR = falta información suficiente. La ausencia de C o R no prueba incumplimiento.",
)
