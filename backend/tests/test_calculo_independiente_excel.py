"""El cálculo se ejecuta aunque los generadores no se puedan importar."""
import subprocess
import sys
from pathlib import Path

import pytest

from reglas.conclusiones import conclusion_expedientes, conclusion_tiempo_efectivo


def test_calculo_en_proceso_frio_sin_excel_ni_etapas():
    codigo = '''
import importlib.abc
import sys
class SinGeneradores(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] == 'openpyxl' or fullname in (
            'scripts.generar_excel', 'entregables.excel_final',
            'orquestador.etapas_reales', 'api.app'):
            raise AssertionError('Dependencia prohibida: ' + fullname)
sys.meta_path.insert(0, SinGeneradores())
from reglas.resultados_profesionales import reconciliar_resultados_profesionales, inyectar_veredicto_backend
from reglas.conclusiones import conclusion_expedientes
from reglas.factor_a import recalcular_factor_a
from entregables import reconciliar_resultados_profesionales as legado
assert legado is reconciliar_resultados_profesionales
for tipo in ('expedientes', 'obras'):
    espejo = {'_meta': {'tipo_evaluacion': tipo}, 'profesionales': [{
        'n_prof': 1, 'requisitos': {'texto': 'Experiencia mínima: 1 día'},
        'experiencias': [{'n': 1, 'fecha_inicial': '2020-01-01', 'fecha_final': '2020-01-01'}]}]}
    enr = {'1:1': {'via': 'CUI_TEXTO', 'cui': '1111111'}}
    assert reconciliar_resultados_profesionales(espejo, enr)[1]['dias_efectivos'] == 1
    inyectar_veredicto_backend(espejo, enr)
    recalcular_factor_a(espejo, enr)
    assert espejo['profesionales'][0]['dias_efectivos_backend'] == 1
assert 'CUMPLE' in conclusion_expedientes({'requisitos': {'texto': 'Experiencia mínima: 1 día'}}, 1, 0, 0, 0, False)
assert 'openpyxl' not in sys.modules
print('CALCULO_INDEPENDIENTE_OK')
'''
    salida = subprocess.run([sys.executable, "-c", codigo],
                            cwd=Path(__file__).resolve().parents[1],
                            capture_output=True, text=True, timeout=40)
    assert salida.returncode == 0, salida.stderr
    assert "CALCULO_INDEPENDIENTE_OK" in salida.stdout


@pytest.mark.parametrize("dias,esperado", [(364, "NO CUMPLE"), (365, "CUMPLE")])
def test_conclusion_usa_dias_exactos(dias, esperado):
    prof = {"requisitos": {"texto": "Experiencia mínima: 1 año"}}
    texto = conclusion_expedientes(prof, dias, 5, 0, 0, False)
    assert texto.startswith(esperado)
    assert f"{dias} días efectivos" in texto
    assert "5 días de traslape" in texto


def test_conclusion_no_reemplaza_la_provisional_por_cumple():
    prof = {"requisitos": {"texto": "Experiencia mínima: 1 año"},
            "cumple_backend": "POR VERIFICAR — falta lectura del certificado."}
    texto = conclusion_expedientes(prof, 500, 0, 100, 30, True)
    assert texto.startswith("POR VERIFICAR")
    assert "100 días" in texto and "30 días" in texto


def test_conclusion_de_obra_conserva_veredicto_original_para_color():
    resultado = conclusion_tiempo_efectivo({"cumple": "NO CUMPLE — 99 días"}, 100, 2)
    assert resultado["veredicto"] == "NO CUMPLE — 99 días"
    assert "100 días declarados" in resultado["texto"]
    assert resultado["texto"].startswith("NO CUMPLE")


def test_conclusion_del_backend_no_se_reescribe_con_dias_declarados():
    resultado = conclusion_tiempo_efectivo({"cumple_backend": "POR VERIFICAR — 50 días efectivos"}, 100, 2)
    assert resultado["texto"] == "POR VERIFICAR — 50 días efectivos"


def test_generador_por_archivo_funciona_fuera_del_repo(tmp_path):
    import json
    entrada = tmp_path / "espejo.json"
    entrada.write_text(json.dumps({"_meta": {}, "profesionales": [], "postor": {},
                                  "resumen_evaluacion": {}}), encoding="utf-8")
    salida = tmp_path / "prueba.xlsx"
    script = Path(__file__).resolve().parents[1] / "scripts" / "generar_excel.py"
    resultado = subprocess.run([sys.executable, "-I", str(script), str(entrada), str(salida)],
                               cwd=tmp_path, capture_output=True, text=True, timeout=40)
    assert resultado.returncode == 0, resultado.stderr
    assert salida.is_file()
    assert "0 profesionales" in resultado.stdout
