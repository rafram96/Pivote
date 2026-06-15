"""Verifica las afirmaciones del plan sobre el caso Egoavil Pando (1:4):

  Q1. ¿La búsqueda por codSnip='95555' hace match por SUBSTRING? ¿trae 509097
      (codUniqInv 2595555, Amazonas)?  → Fallo 1
  Q2. ¿El proyecto Egoavil tiene varias obras bajo el mismo codSnip/CUI
      (64149 contingencia + 66057 principal)?  → Fallo 2
  Q3. ¿La API acepta el CUI de 7 dígitos en el campo codSnip? por_codigo
      ('2157301') ¿devuelve las obras reales?  → viabilidad del fix propuesto
  Q4. ¿codUniqInv viene poblado y consistente en cada registro?
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from resolucion.cui import ConsultaInfoObras  # noqa: E402

C = ConsultaInfoObras()


def dump(titulo, obras):
    print(f"\n=== {titulo} → {len(obras)} registro(s) ===")
    for o in obras:
        print(f"  obra={o.get('codigoObra')!s:>8} | codSnip={o.get('codSnip')!s:>8} "
              f"| codUniqInv={o.get('codUniqInv')!s:>9} | {o.get('nombrDepartamento'):<12} "
              f"| {o.get('estObra'):<12} | {(o.get('nombrObra') or '')[:55]}")


# Q1 + Q2
dump("por_codigo('95555')", C.por_codigo("95555"))
# Q3: ¿busca por CUI de 7 dígitos?
dump("por_codigo('2157301')  [CUI 7 díg del proyecto Egoavil]", C.por_codigo("2157301"))
# control: el CUI colisión
dump("por_codigo('2595555')  [CUI de la obra ajena 509097]", C.por_codigo("2595555"))
# búsqueda por nombre, como hace resolver() en PASO 2
dump("buscar('Mejora de la Capacidad Resolutiva y Operativa del Hospital Roman Egoavil Pando')",
     C.buscar("Mejora de la Capacidad Resolutiva y Operativa del Hospital Roman Egoavil Pando"))
