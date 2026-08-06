# Manual de usuario — Panel InfoObras

## 1. Acceso

Abra la dirección entregada por el administrador:

```text
http://<servidor-de-la-red>:3002
```

El Panel funciona en la red local. Si abre en el servidor pero no desde otra
computadora, normalmente debe revisarse la red, el firewall o la dirección fija.

## 2. Organización

La pantalla principal permite buscar concursos y profesionales. Dentro de cada
análisis se muestran avance, profesionales, veredictos, factores, alertas,
descargas y pasos ejecutados.

## 3. Crear un concurso y cargar un análisis

1. Entre a **Concursos** y cree un registro reconocible.
2. Ábralo y seleccione **Nuevo análisis**.
3. Si la skill no subió automáticamente, arrastre el espejo JSON, el Excel y el
   ZIP de constancias.
4. Confirme y espere que aparezca el trabajo.

No vuelva a cargar lo mismo solo porque una etapa tarde. Primero revise el
estado del trabajo existente.

## 4. Seguir el procesamiento

El Panel consulta periódicamente el estado. Es normal ver muchas respuestas
`200 OK` en el servidor: son actualizaciones automáticas de la pantalla. Un
`202 Accepted` al pedir el ZIP significa que todavía se está preparando y se
volverá a consultar; no es un error.

Los reintentos de InfoObras o SUNAT tampoco implican por sí solos un fallo. Lea
el diagnóstico final de la etapa.

## 5. Leer las pestañas

### Profesionales

Muestra cargos, periodos y experiencias. En certificados con varias obras, el
resumen indica cuántas subobras fueron identificadas y presenta nombre, CUI,
estado y vía. Una alerta de rubros mixtos invita a revisar cada caso.

### Veredictos y factores

Explican si la experiencia satisface el requisito y por qué. No interprete el
puntaje aislado de su razón, fechas y alertas.

### Alertas

Agrupa contradicciones, fuentes incompletas y decisiones pendientes. Una alerta
indica qué revisar; no siempre invalida la experiencia.

### Descargas

Permite obtener el Excel final y el ZIP. El ZIP tarda más porque reúne
documentos y construye un índice auditable.

### Pasos

Distingue una fuente que no aplica, una fuente temporalmente caída y una
búsqueda sin resultado.

## 6. Resolver “Por confirmar”

En la cola de revisión se puede, según el caso:

- elegir el candidato correcto;
- ingresar un CUI comprobado;
- indicar que la obra no está disponible en fuentes públicas;
- completar o confirmar la identidad SUNAT de una experiencia privada.

Compare nombre, entidad, ubicación, fechas y emisor. No elija solo por parecido
del nombre. Después de guardar, espere el recálculo y descargue nuevamente el
Excel.

## 7. Rutas pública, privada y mixta

- **Pública:** muestra CUI y fuentes oficiales aplicables. En expedientes puede
  incluir proceso y aprobación.
- **Privada:** indica que MEF, InfoObras y SEACE no aplican; se apoya en
  constancia y SUNAT.
- **Privada pendiente:** el RUC no es único o no se encontró; los días son
  provisionales.
- **Mixta:** cada experiencia o subobra conserva su propia ruta.

## 8. Descarga final

El documento entregable es el **Excel final del Panel**. Compruebe que abre sin
reparaciones, conserva imágenes, refleja las decisiones manuales y usa las
etiquetas correctas. El ZIP debe abrir, incluir su índice y no contener archivos
temporales.

## 9. Problemas frecuentes

| Síntoma | Qué hacer |
|---|---|
| El Panel no abre | Comprobar la red y avisar al administrador |
| El trabajo parece detenido | Revisar **Pasos** antes de duplicar la carga |
| Aparece “Por confirmar” | Leer la razón; es una abstención deliberada |
| El ZIP sigue preparándose | Volver después; el servidor conserva el trabajo |
| El ZIP baja como texto | Corregir la dirección de descarga del servidor |
| La base MEF está vencida | Solicitar actualización; obras recientes podrían faltar |

Eliminar un concurso o análisis retira historial y entregables. Hágalo solo si
existe respaldo o el caso ya no debe conservarse.
