# Reglas de negocio

## Principio rector

El sistema es un **detector de mentiras** en experiencias declaradas. Asimetría
total: un falso "a revisión" cuesta minutos del evaluador; un falso CUMPLE
destruye el producto. **Ante ambigüedad, abstenerse y mostrar candidatos.**

## Resolución de identidad (qué proyecto es)

- Criterios de IDENTIDAD seleccionan (nombre, N° de institución, RUC, ubigeo,
  entidad, rubro). Criterios de VERACIDAD (fechas/valorizaciones) solo emiten
  veredicto — nunca eligen (evita lavar periodos falsos).
- CUI citado en el certificado = autoritativo si existe exacto (los certs citan
  componentes de proyectos integrales; COARs son concesiones multi-región cuya
  ubicación oficial difiere legítimamente).
- Dos municipalidades distritales distintas no contratan la misma obra.
- El MEF a veces registra la inversión bajo la sede de la entidad ejecutora,
  no la obra física → los vetos de ubicación exigen contradicción DECLARADA en
  ambos lados, nunca por ausencia de datos.

## Expedientes (camino A)

- El estudio precede a la construcción: NO se le exigen valorizaciones ni se
  descuentan días por la ventana de la obra posterior.
- Sustento: contrato del expediente + resolución de aprobación (08-A) + hito
  "Aprobación del proyecto" de InfoObras cuando no hay valorizaciones.
- Pedido del cliente (T-005, por desarrollar): inicio del profesional ≥ firma
  del contrato; término ≤ fecha de la resolución de aprobación.

## Obras (camino B)

- Días efectivos = clamp a la ventana de valorizaciones; paralizaciones se
  restan (las invertidas inicio>fin se descartan con observación).
- Cobertura de valorizaciones < 50% del periodo → revisión; umbral 0.2.
- NO CUMPLE frágiles (sin valorizaciones / fetch caído / fecha ilegible) →
  revisión provisional, nunca veredicto duro.

## Otras reglas fijadas

- ALT-03 (exp. antes de titulación): cutoff **25 años** (no 20).
- ALT-12 (firmante = representante legal): **DESCARTADA** como regla automática
  (falsos positivos); el dato se muestra informativo.
- Experiencia del postor (req. 3.4): la computa el Comité manualmente, no el
  backend (`etapas_reales.py:447`).
- Oferta sin IGV (Ley 27037 Amazonía): homogeneizar ×1.18 antes del límite
  inferior — decisión de criterio del Comité, se marca.
- Certificados multi-obra con un solo vínculo = UNA experiencia (el tiempo no
  se multiplica); sub-obras en `obras[]`.
- Formato del Excel final: congelado por el cliente (2026-06-10); cambios solo
  aditivos (hojas nuevas).
