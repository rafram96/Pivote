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
    ("C", "C: firma del contrato, según la fuente documental disponible."),
    ("R", "R: resolución de aprobación del expediente, según la fuente disponible."),
    ("≈", "≈: fecha declarada solo con mes y año; se usa mes completo cuando la regla lo permite."),
    ("T1–T4", "T1: ene–mar · T2: abr–jun · T3: jul–sep · T4: oct–dic."),
    ("Meses", "E F M A M J J A S O N D: meses de enero a diciembre, en ese orden."),
)

NOTAS_GANTT = (
    "Las barras representan los períodos declarados. Su color indica la certeza "
    "de identificación del proyecto, no la validez del período ni del cargo.",
    "Una columna representa el mes, trimestre o año indicado, no un día. "
    "Varias marcas juntas comparten esa columna, no necesariamente la misma fecha. "
    "Sin barra: no hay período computable.",
    "Cruces de fechas: SÍ = orden temporal compatible; NO = discrepancia; "
    "POR VERIFICAR = falta información suficiente. La ausencia de C o R no prueba incumplimiento.",
)
