# Lecciones aprendidas (con evidencia medida)

- **El nombre no identifica proyectos estatales**: fuzzy top-1 = 67% de
  precisión; incluso a score 100 se estanca en ~84% — el Estado registra
  proyectos DISTINTOS con nombres idénticos. El nombre genera candidatos
  (verdad en top-10: 82-85%); la identidad dura decide (N° institución, RUC,
  ubigeo, entidad).
- **Abstenerse es barato, adivinar es carísimo**: mover casos dudosos a
  revisión con candidatos visibles costó ~6 correctos y eliminó 16 riesgos de
  falso CUMPLE. El evaluador resuelve una revisión en un clic.
- **La cobertura de las fuentes por era importa**: Datos Abiertos del MEF
  cubren 2001-2026 SOLO uniendo activas+cerradas+desactivadas; CONOSCE/OCDS
  arrancan 2018 (86% de las experiencias reales); pre-2018 = SNIP-only y
  seacev2 sin projectID. Diseñar fallbacks por era, no asumir cobertura.
- **El CUI citado en el certificado no es infalible** (84% coincide con la
  verdad): SNIPs viejos, reformulaciones (2140959→2448758), CUIs de otro
  componente. Verificar siempre; preferir codUniqInv de 7 dígitos.
- **Los certificados de expedientes envuelven el nombre** ("Elaboración del
  ET: …") y las obras de esos proyectos se ejecutan DESPUÉS — cruzar fechas del
  estudio contra valorizaciones de construcción castiga inocentes.
- **Skill en tokens del cliente = presupuesto real**: cada paso de la skill se
  paga; lo determinístico (OCR Tesseract, scripts node) y lo transferible al
  backend deben salir del LLM. El OCR por CPU (Camino A) cuesta ~10× menos que
  la visión de Claude por página.
- **Medir con datos propios convence**: todas las decisiones grandes de esta
  etapa salieron de correr contra los 29 concursos / 1042 experiencias / 641
  CUIs auditados reales — no de benchmarks sintéticos. Mantener esa vara
  (golden) viva es lo que permite refactorizar sin miedo.
