"""
generar_espejo_prueba.py — Espejo JSON sintético para probar el display.

Arma un JSON espejo v1.3.0 con 10 CUIs REALES de la base MEF local (obras de
salud, 10 departamentos distintos) repartidos en 3 profesionales sintéticos.
Sirve para ver cómo se muestran hoy el Excel y el panel sin quemar una corrida
de la skill. Los profesionales, DNIs y folios son inventados; los CUIs, nombres
de obra y entidades son los oficiales del MEF.

Uso (desde la raíz del Pivote, con el venv):
    venv/Scripts/python.exe src/tools/generar_espejo_prueba.py

Salidas en fixtures/prueba_display/:
    espejo_prueba_10cuis.json   (validado contra backend.schemas.espejo)
    prueba_10cuis.xlsx          (vía backend/scripts/generar_excel.py)
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
SALIDA = RAIZ / "fixtures" / "prueba_display"

# (cui, entidad_mef, nombre_oficial_mef, dpto) — muestreo seed=42 de inversiones.csv.gz
OBRAS = [
    ("2514715", "MUNICIPALIDAD DISTRITAL DE TORRES CAUSANA", "MEJORAMIENTO DE LOS SERVICIOS DE ATENCION BASICA EN EL PUESTO DE SALUD DE LA COMUNIDAD DE SANTA MARIA DE ANGOTEROS", "LORETO"),
    ("2446821", "MUNICIPALIDAD DISTRITAL DE CAMINACA", "MEJORAMIENTO DE LOS SERVICIOS DE SALUD DEL PUESTO DE SALUD I-1 DEL CENTRO POBLADO SAN PEDRO DE COLLANA", "PUNO"),
    ("2314581", "MINISTERIO DE SALUD", "MEJORAMIENTO DE LA CAPACIDAD DE LA ATENCION NEONATAL DEL CENTRO DE SALUD TREBOL AZUL DE LA RED DE SALUD SAN JUAN DE MIRAFLORES", "LIMA"),
    ("2655126", "GOBIERNO REGIONAL UCAYALI", "MEJORAMIENTO DEL SERVICIO DE ATENCION DE SALUD BASICOS EN PUESTO DE SALUD MAR DE PLATA, DISTRITO DE NESHUYA", "UCAYALI"),
    ("2337618", "GOBIERNO REGIONAL JUNIN", "MEJORAMIENTO Y AMPLIACION DE LOS SERVICIOS DE SALUD DEL ESTABLECIMIENTO DE SALUD PEDRO SANCHEZ MEZA", "JUNIN"),
    ("2312001", "GOBIERNO REGIONAL LAMBAYEQUE", "MEJORAMIENTO DE LA CAPACIDAD RESOLUTIVA DEL PUESTO DE SALUD SIPAN, DISTRITO DE ZAÑA, PROVINCIA DE CHICLAYO", "LAMBAYEQUE"),
    ("2716253", "MUNICIPALIDAD DISTRITAL DE PALLASCA", "MEJORAMIENTO Y AMPLIACION DEL SERVICIO DE ATENCION DE SALUD BASICOS EN CENTRO DE SALUD PALLASCA", "ANCASH"),
    ("2320997", "GOBIERNO REGIONAL PIURA", "MEJORAMIENTO DE LOS SERVICIOS DE SALUD EN EL ESTABLECIMIENTO DE SALUD TACALA, DISTRITO DE CASTILLA", "PIURA"),
    ("2325574", "MUNICIPALIDAD DISTRITAL DE ANGUIA", "CREACION DEL PUESTO DE SALUD SATELITE EN LA LOCALIDAD DE CHIUT, DISTRITO DE ANGUIA - CHOTA - CAJAMARCA", "CAJAMARCA"),
    ("2727722", "GOBIERNO REGIONAL AYACUCHO", "CONSTRUCCION DE CERCO Y/O PORTADA EN EL(LA) HOSPITAL REGIONAL DE AYACUCHO MIGUEL ANGEL MARISCAL LLERENA", "AYACUCHO"),
]

PROFESIONALES = [
    {
        "cargo": "JEFE DE SUPERVISIÓN",
        "cargo_bases_num": 1,
        "nombre": "CARLOS ALBERTO MENDOZA QUISPE",
        "dni": "40817263",
        "titulo": "INGENIERO CIVIL",
        "colegiatura": "CIP 78452",
        "fecha_colegiatura": "2005-04-12",
        "n_exps": 4,
    },
    {
        "cargo": "ESPECIALISTA EN ESTRUCTURAS",
        "cargo_bases_num": 2,
        "nombre": "MARIA ELENA TORRES HUAMANI",
        "dni": "42155908",
        "titulo": "INGENIERO CIVIL",
        "colegiatura": "CIP 91307",
        "fecha_colegiatura": "2008-09-03",
        "n_exps": 3,
    },
    {
        "cargo": "ESPECIALISTA EN INSTALACIONES SANITARIAS",
        "cargo_bases_num": 5,
        "nombre": "JORGE LUIS CACERES PAREDES",
        "dni": "43902741",
        "titulo": "INGENIERO SANITARIO",
        "colegiatura": "CIP 104882",
        "fecha_colegiatura": "2011-02-18",
        "n_exps": 3,
    },
]

CARGOS_EN_OBRA = {
    "JEFE DE SUPERVISIÓN": "SUPERVISOR DE OBRA",
    "ESPECIALISTA EN ESTRUCTURAS": "ESPECIALISTA EN ESTRUCTURAS",
    "ESPECIALISTA EN INSTALACIONES SANITARIAS": "ESPECIALISTA EN INSTALACIONES SANITARIAS",
}


def _experiencia(n: int, obra, cargo: str, inicio: date, dur_dias: int, folio: int) -> dict:
    cui, entidad, proyecto, dpto = obra
    fin = inicio + timedelta(days=dur_dias - 1)
    emision = fin + timedelta(days=20)
    return {
        "n": n,
        "entidad_emisora": entidad,
        "ruc_emisor": None,
        "proyecto": proyecto,
        "cui": cui,
        "cui_fuente": "certificado",
        "tipo_documento": "Constancia de prestación",
        "nombre_emisor": "Por verificar en folio",
        "cargo_emisor": "Jefe de la Oficina de Administración",
        "cargo_valido_emitir": "SÍ",
        "fecha_inicial": inicio.isoformat(),
        "fecha_final": fin.isoformat(),
        "fecha_emision": emision.isoformat(),
        "folio": str(folio),
        "dias": dur_dias,
        "meses": round(dur_dias / 30.44, 2),
        "anios": round(dur_dias / 365, 2),
        "anterior_colegiatura": "NO",
        "cargo_ocupado": CARGOS_EN_OBRA[cargo],
        "cargo_bases_valido": "SÍ",
        "funciones_similares": "SÍ",
        "cert_antes_culminar": "NO",
        "incluye_covid": "NO",
        "tipo_obra_valido": "SÍ",
        "traslape": "NO",
        "entidad_contratante": entidad,
        "ubicacion": dpto,
        "observaciones": "Dato de prueba interna (display). CUI y obra reales del MEF.",
    }


def construir() -> dict:
    profesionales = []
    idx_obra = 0
    for i, p in enumerate(PROFESIONALES, start=1):
        exps = []
        # Periodos consecutivos hacia atrás desde 2024, sin traslapes por profesional.
        cursor = date(2024, 6, 30)
        for j in range(p["n_exps"], 0, -1):
            dur = 200 + (idx_obra * 37) % 400          # 200–599 días, determinístico
            inicio = cursor - timedelta(days=dur - 1)
            exps.insert(0, _experiencia(j, OBRAS[idx_obra], p["cargo"], inicio, dur,
                                        folio=120 + idx_obra * 15))
            cursor = inicio - timedelta(days=90)        # hueco de ~3 meses entre obras
            idx_obra += 1
        total_dias = sum(e["dias"] for e in exps)
        profesionales.append({
            "n_prof": i,
            "cargo": p["cargo"],
            "cargo_bases_num": p["cargo_bases_num"],
            "cargo_bases_nombre": p["cargo"],
            "nombre": p["nombre"],
            "dni": p["dni"],
            "folio_nombre": str(10 + i),
            "titulo": p["titulo"],
            "folio_titulo": str(20 + i),
            "profesion_valida": "SÍ",
            "colegiatura": p["colegiatura"],
            "fecha_colegiatura": p["fecha_colegiatura"],
            "folio_colegiatura": str(30 + i),
            "certificaciones": None,
            "experiencia_total_declarada": round(total_dias / 365, 2),
            "requisitos": {
                "cargos_validos": f"{p['cargo']}; O EQUIVALENTE",
                "tipo_obra": "Establecimientos de salud, edificaciones y afines",
                "experiencia_minima_anios": 2,
            },
            "experiencias": exps,
            "total": {
                "dias": total_dias,
                "meses": round(total_dias / 30.44, 2),
                "anios": round(total_dias / 365, 2),
            },
            "notas": ["Profesional sintético para prueba de display; no corresponde a una propuesta real."],
            "cumple": "SÍ",
        })
    return {
        "_meta": {
            "analisis_id": "PRUEBA-DISPLAY-10CUI-2026-08",
            "slug": "prueba_display",
            "concurso": "PRUEBA INTERNA — Display 10 CUIs (no es un concurso real)",
            "postor": "CONSORCIO DE PRUEBA RAFAEL",
            "version_contrato": "1.3.0",
            "generado_por": "src/tools/generar_espejo_prueba.py",
        },
        "postor": {
            "detalle": "Postor sintético para prueba de display del panel y el Excel.",
            "formularios": [
                {"anexo": "ANEXO N° 1", "documento": "Declaración jurada de datos del postor",
                 "observacion": "Dato de prueba", "folio": "1"},
            ],
            "oferta_economica": {"cuantia": None, "limite_inferior": None, "propuesta": None,
                                 "detalle": "No aplica en la prueba de display"},
            "experiencia_postor": [],
            "postor_cumple": "SÍ",
        },
        "profesionales": profesionales,
        "resumen_evaluacion": {
            "factores": [],
            "puntaje_total": None,
            "nota": "Espejo sintético: solo para validar el display (panel + Excel).",
        },
        "observaciones_claude": [
            {"severidad": "info", "tipo": "prueba",
             "mensaje": "Archivo generado localmente con 10 CUIs reales del MEF y 3 profesionales sintéticos.",
             "referencia": "src/tools/generar_espejo_prueba.py"},
        ],
    }


def main() -> None:
    SALIDA.mkdir(parents=True, exist_ok=True)
    espejo = construir()

    sys.path.insert(0, str(RAIZ))
    from backend.schemas.espejo import JsonEspejo  # noqa: E402
    JsonEspejo.model_validate(espejo)
    print("✓ Espejo válido contra backend.schemas.espejo (v1.3.0)")

    ruta_json = SALIDA / "espejo_prueba_10cuis.json"
    ruta_json.write_text(json.dumps(espejo, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✓ {ruta_json.relative_to(RAIZ)}")

    ruta_xlsx = SALIDA / "prueba_10cuis.xlsx"
    r = subprocess.run(
        [sys.executable, str(RAIZ / "backend" / "scripts" / "generar_excel.py"),
         str(ruta_json), str(ruta_xlsx)],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        print(r.stdout); print(r.stderr)
        raise SystemExit("generar_excel.py falló")
    print(f"✓ {ruta_xlsx.relative_to(RAIZ)}")


if __name__ == "__main__":
    main()
