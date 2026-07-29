# Feedback del ing. — auditoría "bisbal" (WhatsApp, 29-jul 5:46-8:06 a.m.)

> **Documento vivo**: se van agregando los lotes conforme lleguen.
> **⚠ HALLAZGO META (verificado contra los datos)**: el ing. está auditando el
> **ENTREGABLE VIEJO** — el ZIP/Excel del análisis del **27-jul** (job
> `371fa5a1e704`), anterior a TODOS los fixes del 28-jul. Pruebas: (1) su
> "EXPERIENCIA 1 = Parcona, folio 35-36" es la numeración del job viejo (13:1);
> en el nuevo (`e7c0fff6afb1`) E1 = LaFora y Parcona = E4; (2) su carpeta
> descargada dice 28/07 11:22 a.m., horas ANTES de la corrida de urgente1;
> (3) en el job nuevo los docs de P13 SÍ corresponden (LaFora para LaFora).
> **Primera acción: entregarle el paquete NUEVO** y re-verificar cada
> observación contra ese paquete antes de tocar código.

## OBSERVACIONES (errores señalados — estado verificado)

| # | Qué dice | Verificación local (28/29-jul) | Estado |
|---|---|---|---|
| O1 | "Tú dices inicio 1/12/2024 pero InfoObras dice 11/11/2024" (LaFora/Guadalupe) | En el job NUEVO la ficha dice `fecha_inicio=2024-12-03` y el portal muestra 11/11/2024. El hito `fuera_de_ventana` del nuevo arranca justo 2024-11-11 → tenemos el dato bueno en un lado y el malo en otro | 🔴 **VIGENTE también en el nuevo** — investigar de dónde toma `fecha_inicio` la ficha (¿primera valorización en vez del campo "FECHA DE INICIO DE LA OBRA" de DatosEjecución?) |
| O2 | "Paralizado desde febrero 2025, pero InfoObras me reporta otra cosa… es raro, es el mismo CUI" | Nuevo: paral `2025-02-03 → 2025-12-31`. Sus capturas del portal muestran meses "Paralizado" distintos. Puede ser flakiness conocida del portal (tablas varían entre corridas) o derivación distinta (huecos vs estado) | 🟡 A verificar contra el portal (no se puede desde la laptop) |
| O3 | "El especialista M.A. tiene 4 obras públicas pero me reportas solo un contrato con info de InfoObras" | **Job nuevo: 4/4 con ficha + valorizaciones + CUI.** Era el viejo | ✅ Resuelto por el entregable nuevo — confirmar cuando lo tenga |
| O4 | "Me reporta Llata… que no tiene nada que ver" (PDF de valorización E.S. Llata/Huamalíes en la carpeta del M.A.) | Llata NO existe en ningún enriquecimiento (ni viejo ni nuevo). En el nuevo, P13_E1 trae los docs CORRECTOS. El PDF Llata salió del ZIP viejo — origen exacto por confirmar si él insiste con el paquete nuevo | ✅ Presunto resuelto — ⚠ si reaparece en el nuevo, es bug grave de descarga |
| O5 | "Del jefe bisbal me das 5 experiencias y ninguna es" (docs de Yanahuanca/Los Ángeles en sus carpetas) | Job nuevo: P2 tiene 4 exps con folios verificados 4/4 contra páginas físicas; Yanahuanca es de OTRO profesional (P9 Navarro) | ✅ Presunto resuelto (el cruce era del viejo) — confirmar |

## PEDIDOS NUEVOS (alcance nuevo, no errores)

| # | Pedido (sus palabras) | Lectura técnica |
|---|---|---|
| P1 | «si ella sabe la fecha exacta de la paralización **que muestre la fuente, que pegue la imagen** de esa fecha donde lo encuentra en InfoObras» · «debes mostrarme una imagen donde me demuestres esa fecha y de dónde la sacas» | **Evidencia visual de las fechas afirmadas**: junto a cada paralización/fecha de inicio usada en los hitos, insertar la captura del "Detalle del Avance de Obra" de InfoObras (él lo hace a mano hoy). El backend ya tiene los DATOS de esa pantalla (DatosEjecución) y baja adjuntos — falta renderizar/insertar la evidencia como imagen en la hoja |
| P2 | «tú haces esto pero **debes incluir lo VERDE — es el que realmente uso**» · «para construir lo verde necesito la fecha de inicio» (muestra fila `plazo real 3/03/2022–4/12/2022 · 277`) | **Fila "PLAZO REAL" (verde)** al cierre del cuadro de hitos de cada experiencia: rango efectivo real (inicio real → fin real) con sus días — y la fecha de inicio respaldada con la evidencia de P1 |
| P3 | «no me interesa el cliente, me interesa el **nombre del proyecto** — o le agregas la columna» (tabla resumen P5) | Columna PROYECTO/OBRA prominente en la tabla resumen declarado-vs-efectivo de la PARTE 5 (verificar si existe y quedó fuera de vista, o falta) |

## Urgente operativo

«PASAME TODO CORRECTO… VENGO A TRABAJAR Y NO ME SIRVE» → entregarle **HOY** el
paquete del job nuevo `e7c0fff6afb1`: `final.xlsx` regenerado (28-jul: oferta
completa, jerga 0, celdas que hablan) + su `infoobras.zip` + certificados. Cada
observación se re-audita contra ESE paquete.
