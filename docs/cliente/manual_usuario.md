# Manual de usuario — InfoObras Analyzer

Cómo evaluar una propuesta de principio a fin. Tú intervienes **dos veces**: al
subir los archivos y al revisar/descargar el resultado.

---

## ¿Qué hace el sistema?
Lee las **bases** del concurso y la **propuesta** del postor, evalúa el personal
clave (cumple / no cumple, con la razón literal), **cruza con InfoObras y SUNAT**,
calcula los **días efectivos** de experiencia (descontando paralizaciones) y entrega:
- un **Excel de evaluación** (con las constancias incrustadas), y
- un **ZIP** con los documentos descargados de InfoObras.

Lo que antes tomaba **6–12 horas** por propuesta, ahora son **minutos**.

---

## Paso 1 — Correr el análisis (en tu PC, con Claude)
1. Abre **Claude Desktop** (Cowork).
2. Escribe el comando con los dos PDFs:
   ```
   /analizar-licitacion-osce bases.pdf propuesta.pdf
   ```
   (o arrastra los dos PDFs al chat y pide analizarlos).
3. Claude lee, evalúa y arma el resultado. **Tarda según el tamaño** — una propuesta
   de miles de folios puede tomar varios minutos.
4. El resultado **se sube solo** al servidor (por el MCP). Si no, lo subes a mano por
   el panel (Paso 2, botón *Nuevo análisis*).

> El **veredicto y el Excel** quedan listos enseguida. La **descarga de los
> documentos de InfoObras** (lo más pesado, ~1 GB) sigue **en segundo plano** — no
> tienes que esperarla para ver los resultados.

## Paso 2 — Revisar en el panel (navegador)
1. Abre **`http://<servidor>:3002`** desde cualquier PC de la red.
2. Entra a **Concursos** → tu análisis.
3. Verás el **veredicto por profesional**, las **alertas** y los **"por confirmar"**.

### Casos "por confirmar"
Cuando el sistema no logra identificar una obra (CUI) con certeza, te lo pide:
- **Pega el CUI** correcto, o
- marca **"no existe"** si la obra no está en InfoObras.

El análisis se **re-procesa solo** ese punto y actualiza el resultado.

### Descargar
- **Excel de evaluación** — con las constancias adentro y el cálculo de días.
- **ZIP de documentos** — todo lo descargado de InfoObras, ordenado por profesional.
  (La primera descarga puede tardar si los documentos aún se están bajando.)

---

## Leer el Excel
- **Hoja CLAUDE** — resumen general del concurso.
- **Base de Datos** — todas las experiencias en una tabla.
- **Una hoja por profesional (P1, P2…)** — su evaluación, las **constancias
  incrustadas**, y el **cuadro de días efectivos** (Paso 5).

**Colores:**
| Color | Significado |
|---|---|
| 🟩 Verde | Cumple |
| 🟨 Amarillo | Declarado / a observar |
| 🟦 Cyan | Verificado / días efectivos |
| 🟥 Rojo | Alerta / periodo paralizado |

---

## Qué decides TÚ (el sistema señala, no juzga)
El sistema marca; la decisión legal es tuya:
- **Equivalencias de cargo** dudosas (las deja anotadas para el Comité).
- **Conflicto de interés** (firmante ligado al postor) — lo marca; tú decides.
- **Oferta económica en el filo** — la señala; es criterio del Comité.
- **Experiencia del postor (req. 3.4)** — hoy se revisa **manualmente** (montos,
  conversión de moneda, ventana de 20 años): el Excel te organiza los datos, pero
  la admisibilidad la decides tú.

---

## Problemas comunes
- **"El ZIP tarda en descargar"** — la primera vez baja ~1 GB; espera o reintenta.
- **"Una obra sale SIN DOCUMENTOS"** — su CUI no se resolvió o no aplica → revísala
  en *"por confirmar"*.
- **"Veo reintentos de InfoObras en el proceso"** — el portal es intermitente; el
  sistema reintenta solo, es normal.
- **"No abre el panel"** — confirma que estás en la red interna y que el servidor está encendido.
