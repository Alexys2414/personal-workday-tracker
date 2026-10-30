<p align="center">
  <img src="docs/banner.png" alt="Jornada: cuánto llevas, cuánto te queda y a qué hora exacta puedes irte a casa" width="100%">
</p>

<p align="center">
  <a href="LICENSE"><img alt="Licencia MIT" src="https://img.shields.io/badge/licencia-MIT-0f766e"></a>
  <img alt="Python 3.10 o superior" src="https://img.shields.io/badge/python-3.10%2B-0f766e">
  <img alt="Flask 3.1 incluido" src="https://img.shields.io/badge/flask-3.1%20incluido-0f766e">
  <img alt="Sin Node.js" src="https://img.shields.io/badge/node.js-no%20necesario-b5561a">
  <img alt="Sin base de datos" src="https://img.shields.io/badge/datos-JSON%20local-b5561a">
  <img alt="Idiomas: español e inglés" src="https://img.shields.io/badge/idiomas-ES%20%C2%B7%20EN-946a00">
  <img alt="Versión 2.1" src="https://img.shields.io/badge/versi%C3%B3n-2.1-0f766e">
</p>

<p align="center">
  <b>Español</b> · <a href="README.en.md">English</a>
</p>

<p align="center">
  <a href="#instalación-rápida-en-linux">Instalación</a> ·
  <a href="#cómo-utilizar-jornada">Uso</a> ·
  <a href="#novedades-de-jornada-21">Novedades 2.1</a> ·
  <a href="#atajos-de-teclado">Atajos</a> ·
  <a href="#exportación-e-importación">Exportar e importar</a> ·
  <a href="#persistencia-y-privacidad">Privacidad</a> ·
  <a href="#solución-de-problemas">Problemas</a>
</p>

---

**Jornada** es una pequeña aplicación web que se ejecuta en tu propio ordenador y te dice, de un vistazo,
cuánto llevas trabajado, cuánto te queda y **a qué hora exacta puedes salir**, con tus descansos incluidos.
Funciona sin conexión, guarda todo en un archivo JSON local y no necesita permisos de administrador.

> [!IMPORTANT]
> Jornada es una **herramienta personal**. No es un sistema oficial de registro de jornada y no tiene validez laboral ni legal.
> Sirve para llevar tu propio control.

## Índice

1. [Capturas y demostración](#capturas-y-demostración)
2. [Características principales](#características-principales)
3. [Requisitos](#requisitos)
4. [Instalación rápida en Linux](#instalación-rápida-en-linux)
5. [Instalación rápida en Windows](#instalación-rápida-en-windows)
6. [Crear un acceso directo en el escritorio](#crear-un-acceso-directo-en-el-escritorio)
7. [Cómo utilizar Jornada](#cómo-utilizar-jornada)
8. [Novedades de Jornada 2.1](#novedades-de-jornada-21)
   [Copias de seguridad](#1-copias-de-seguridad-y-restauración) ·
   [Modo compacto](#2-modo-compacto-flotante) ·
   [Avisos](#3-avisos-inteligentes) ·
   [Simulador](#4-simulador-de-hora-de-salida) ·
   [Festivos y vacaciones](#5-festivos-vacaciones-y-ausencias) ·
   [Estadísticas](#6-estadísticas-avanzadas) ·
   [Objetivo semanal](#7-objetivo-semanal-y-compensación-simulada) ·
   [Personalización](#8-personalización-visual)
9. [Horarios normales e intensivos](#horarios-normales-e-intensivos)
10. [Atajos de teclado](#atajos-de-teclado)
11. [Exportación e importación](#exportación-e-importación)
12. [Idiomas y temas](#idiomas-y-temas)
13. [Persistencia y privacidad](#persistencia-y-privacidad)
14. [Limitaciones del navegador](#limitaciones-del-navegador)
15. [Arquitectura del proyecto](#arquitectura-del-proyecto)
16. [Desarrollo y pruebas](#desarrollo-y-pruebas)
17. [Solución de problemas](#solución-de-problemas)
18. [Roadmap](#roadmap)
19. [Contribuciones](#contribuciones)
20. [Licencia](#licencia)

## Capturas y demostración

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/screenshots/dashboard-dark.png">
    <img src="docs/screenshots/dashboard-light.png" alt="Panel principal: cuenta atrás, hora de salida y acción de fichaje" width="860">
  </picture>
</p>

<p align="center">
  <img src="docs/demo.gif" alt="Demostración: iniciar jornada, descanso, vuelta al trabajo y jornada completada" width="760"><br>
  <sub>Iniciar jornada → descanso → vuelta al trabajo → jornada completada (grabación real, datos ficticios).</sub>
</p>

<table>
  <tr>
    <td width="50%"><img src="docs/screenshots/dashboard-light.png" alt="Panel en modo claro"><br><sub><b>Modo claro</b>: trabajando, con la salida prevista.</sub></td>
    <td width="50%"><img src="docs/screenshots/dashboard-dark.png" alt="Panel en modo oscuro"><br><sub><b>Modo oscuro</b>: los mismos estados, con colores ajustados para la noche.</sub></td>
  </tr>
  <tr>
    <td><img src="docs/screenshots/simulator.png" alt="Simulador de jornada con la comparativa actual frente a simulada"><br><sub><b>Simulador</b> (2.1): prueba descansos y horas de salida sin tocar tus fichajes.</sub></td>
    <td><img src="docs/screenshots/stats.png" alt="Estadísticas avanzadas: mapa de actividad, promedios, balance y comparativa semanal"><br><sub><b>Estadísticas</b> (2.1): actividad, promedios, evolución y semanas.</sub></td>
  </tr>
  <tr>
    <td><img src="docs/screenshots/weekly.png" alt="Tarjeta de objetivo semanal y próximos días libres"><br><sub><b>Esta semana</b> (2.1): objetivo semanal, balance cerrado y próximos festivos.</sub></td>
    <td><img src="docs/screenshots/calendar-settings.png" alt="Ajustes de festivos, vacaciones y reglas de cada tipo de día"><br><sub><b>Festivos y vacaciones</b> (2.1): recurrentes, rangos, importación y reglas.</sub></td>
  </tr>
  <tr>
    <td><img src="docs/screenshots/alerts.png" alt="Ajustes de avisos"><br><sub><b>Avisos</b> (2.1): cuenta atrás, jornada completada y descansos.</sub></td>
    <td><img src="docs/screenshots/backup.png" alt="Copias de seguridad en Ajustes, Datos"><br><sub><b>Copias de seguridad</b> (2.1): un único JSON con todo.</sub></td>
  </tr>
  <tr>
    <td><img src="docs/screenshots/accents.png" alt="Acento coral en modo claro y violeta con densidad compacta en modo oscuro"><br><sub><b>Personalización</b> (2.1): acentos, densidad y animaciones.</sub></td>
    <td align="center"><img src="docs/screenshots/compact.png" alt="Vista compacta: estado, cuenta atrás, salida y acción principal" width="280"><br><sub><b>Modo compacto</b> (2.1): un widget para tener al lado.</sub></td>
  </tr>
  <tr>
    <td><img src="docs/screenshots/calendar.png" alt="Calendario mensual, detalle del día y vista semanal"><br><sub><b>Historial</b>: calendario, detalle con notas y vista semanal.</sub></td>
    <td><img src="docs/screenshots/shortcuts.png" alt="Editor de atajos de teclado"><br><sub><b>Atajos</b>: asigna cualquier combinación, como en un videojuego.</sub></td>
  </tr>
  <tr>
    <td><img src="docs/screenshots/settings.png" alt="Ajustes de perfiles de horario"><br><sub><b>Ajustes</b>: perfiles, semana habitual y verano.</sub></td>
    <td><img src="docs/screenshots/import.png" alt="Vista previa de una importación CSV con duplicados"><br><sub><b>Importar</b>: vista previa antes de guardar nada.</sub></td>
  </tr>
  <tr>
    <td><img src="docs/screenshots/report.png" alt="Informe imprimible en A4"><br><sub><b>Informe PDF</b>: listo para imprimir en A4.</sub></td>
    <td align="center"><img src="docs/screenshots/mobile.png" alt="Versión móvil con el botón de fichaje abajo" width="230"><br><sub><b>Móvil</b>: el fichaje queda al alcance del pulgar.</sub></td>
  </tr>
</table>

<sub>Todas las capturas son de la aplicación real con datos ficticios.</sub>

## Características principales

| | |
|---|---|
| ⏱️ **Cuenta atrás en vivo** | El tiempo que te queda se actualiza cada segundo. Se calcula a partir de las marcas guardadas, así que sigue siendo exacto aunque cierres el navegador o el equipo se suspenda. |
| 🏁 **Hora exacta de salida** | Incluye el descanso obligatorio pendiente. Muestra también a qué hora saldrías sin él y usando el descanso opcional. |
| ☕ **Descansos múltiples** | Durante la pausa, el trabajo se congela y otro contador mide el descanso. Te avisa si falta descanso mínimo. |
| 🎉 **Jornada completada** | Celebración discreta al llegar al objetivo; si sigues trabajando, cuenta el tiempo extra. |
| ⚖️ **Balance flexible** | Horas de más y de menos por día, semana, mes y acumulado total. Avisa, pero nunca bloquea. |
| 🗓️ **Horarios** | Horario normal, viernes intensivo e intensivo de verano por fechas, con un perfil manual para cualquier día. |
| 📝 **Notas** | Una nota para cada jornada y otra para cada descanso. Nunca cambian los cálculos. |
| ⌨️ **Atajos configurables** | Cualquier combinación para las acciones principales, con detección de conflictos. |
| 📤 **CSV y PDF** | Exporta historial, semana, mes o rango de fechas. Informe A4 imprimible. |
| 📥 **Importación segura** | Vista previa, gestión de duplicados y copia de seguridad antes de guardar. |
| 🌍 **Español e inglés** | Cambia al instante, sin recargar. |
| 🌗 **Claro y oscuro** | Tema claro, oscuro o según el sistema; diseño adaptado a escritorio, tableta y móvil. |
| ♿ **Accesible** | Navegación completa por teclado con foco visible, botones del tamaño adecuado en pantallas táctiles y respeto de `prefers-reduced-motion`. |
| 💾 **Copias completas** *(2.1)* | Un solo JSON con jornadas, ajustes y festivos; restauración validada, con copia automática previa. |
| 🪟 **Modo compacto** *(2.1)* | Widget de 360 px en la misma pestaña, en una ventana aparte o flotando encima (si el navegador lo permite). |
| 🔔 **Avisos** *(2.1)* | A 30, 15, 5, 1 min o los que elijas; jornada completada y descansos. Dentro de Jornada, en el escritorio o con sonido. |
| 🧪 **Simulador** *(2.1)* | «¿Y si descanso 20 min más?», «¿y si salgo a las 17:00?»… sin tocar nunca tus fichajes. |
| 🏖️ **Festivos y vacaciones** *(2.1)* | Festivos (también cada año), vacaciones por rangos, permisos, bajas y ausencias; tú decides cómo computa cada tipo. |
| 📊 **Estadísticas** *(2.1)* | Mapa de actividad, evolución del balance, promedios y comparativa semanal, en SVG y con tablas de datos. |
| 🎯 **Objetivo semanal** *(2.1)* | Calculado de tus horarios o personalizado, con simulación informativa de compensación. |
| 🎨 **Personalización** *(2.1)* | Cinco acentos, densidad cómoda o compacta, animaciones reducidas/normales/expresivas y tarjetas a la carta. |

## Requisitos

- **Python 3.10 o superior.** Es lo único que necesitas tener. Flask y sus dependencias ya vienen
  incluidas en la carpeta [`vendor/`](vendor/).
- Un navegador moderno: Firefox, Chrome, Edge o Safari.

**No** necesitas `pip`, `npm`, Node.js, Docker, una base de datos, conexión a internet ni permisos de administrador.

> [!NOTE]
> Jornada no es un ejecutable autónomo: sin Python no puede funcionar. Si tu equipo no lo tiene,
> mira [cómo conseguirlo sin administrador](#no-se-encuentra-python).

## Instalación rápida en Linux

**Opción A: con Git**

```bash
git clone https://github.com/<tu-usuario>/jornada.git
cd jornada
./iniciar.sh
```

**Opción B: descargando el ZIP**

1. En GitHub, pulsa **Code → Download ZIP**.
2. Descomprímelo dentro de tu carpeta de usuario, por ejemplo en `~/jornada`.
3. Abre una terminal en esa carpeta y ejecuta `./iniciar.sh`.

El navegador se abre en `http://127.0.0.1:8765`. Para tener un icono en el escritorio, sigue el apartado
[Crear un acceso directo](#crear-un-acceso-directo-en-el-escritorio).

## Instalación rápida en Windows

1. Descarga el proyecto, con `git clone` o como ZIP, y descomprímelo en tu carpeta de usuario.
2. Haz doble clic en **`iniciar.bat`**.
3. Se abre una consola, que es el servidor, y el navegador con Jornada.

Si el lanzador no encuentra Python, te explica alternativas que **no requieren administrador**.
Mira también [No se encuentra Python](#no-se-encuentra-python).

## Crear un acceso directo en el escritorio

En **Linux**, una sola vez y sin `sudo`:

```bash
./instalar-escritorio.sh
```

Esto crea:

- `~/.local/share/applications/jornada.desktop`: Jornada aparece en el menú de aplicaciones.
- `~/Escritorio/Jornada.desktop` (o `~/Desktop`): el icono del escritorio.
- `Jornada.desktop` dentro del proyecto, para arrancar desde el gestor de archivos.

Si tu escritorio marca el icono como «no confiable», autorízalo una vez:

| Escritorio | Qué hacer |
|---|---|
| GNOME / Ubuntu | Clic derecho en el icono → **Permitir lanzar**. |
| KDE Plasma | En el primer doble clic, **Ejecutar** y «No volver a preguntar». |
| XFCE | **Marcar como ejecutable** o **Iniciar de todas formas**. |
| Cinnamon / MATE | Propiedades → Permisos → **Permitir ejecutar como programa**. |

Si mueves la carpeta del proyecto, vuelve a ejecutar el script. Para quitar los accesos directos,
usa `./instalar-escritorio.sh --quitar`; tus datos no se tocan.

En **Windows**, crea un acceso directo a `iniciar.bat` (clic derecho → *Enviar a → Escritorio*).

## Cómo utilizar Jornada

### Abrir y cerrar

- **Abrir:** doble clic en el icono, en `iniciar.sh` o en `iniciar.bat`. Si Jornada ya estaba abierta,
  solo se abre el navegador; nunca se crea una segunda instancia.
- **Cerrar por completo:** botón **⏻**, arriba a la derecha → *Cerrar Jornada*. Detiene el servidor
  y libera el puerto. Cerrar solo la pestaña no detiene el servidor.
- **Cierre automático:** si nadie la usa durante 12 horas, se cierra sola. Puedes cambiarlo con
  `JORNADA_IDLE_HOURS`; con `0` no se cierra nunca.

### Un día de ejemplo

Con el horario normal: 8 h 30 min de trabajo efectivo y 1 h de descanso obligatorio.

| Momento | Qué haces | Qué muestra Jornada |
|---|---|---|
| **07:53** | Pulsas **Iniciar jornada** | Salida prevista **17:23** (07:53 + 8 h 30 min + 1 h de descanso). |
| **12:00** | Consultas el panel | Trabajado **4 h 07 min**; te quedan **4 h 23 min**; salida, **17:23**. |
| **14:50** | **Iniciar descanso** | El contador de trabajo se congela; otro mide la pausa. |
| **15:49** | **Terminar descanso** (59 min) | Antes de la pausa: 6 h 57 min. Te quedan **1 h 33 min**: puedes salir a las **17:22**. Falta **1 min** de descanso obligatorio; si lo completas, la salida es a las **17:23**. |
| **17:22** | — | **¡Jornada completada! Ya puedes salir.** A partir de aquí cuenta como tiempo extra. |
| **17:45** | **Finalizar jornada** | Trabajado **8 h 53 min**: balance del día **+23 min**. |

El balance se acumula sin obligarte a compensarlo. Con +25, −15, +40 y −10 minutos en cuatro días,
el balance de la semana es **+40 min**. Puedes revisarlo en el apartado **Balance** (hoy, semana, mes y acumulado)
y en el calendario, donde cada día muestra sus horas y su exceso o déficit.

### Corregir fichajes

- **Editar** abre el editor del día: entrada, salida, descansos, perfil, objetivo y notas.
  La salida y los descansos se validan: no puede haber salida antes de la entrada, descansos solapados ni horas futuras.
- **Añadir jornada** registra un día que olvidaste fichar.
- **Reanudar jornada** deshace un «Finalizar» por error: el hueco se cuenta como descanso.

### Notas

- **Nota del día:** icono 📝 en la tarjeta «Hoy» o «Añadir nota» en el detalle de cualquier día.
- **Nota de un descanso:** icono 📝 junto a cada descanso, en la línea de tiempo o en el detalle.
- Hay sugerencias rápidas, como «Reunión con el equipo» o «Cita médica». Las notas se ven discretamente en el calendario y se incluyen al exportar.
  **Nunca modifican los cálculos de tiempo.**

## Novedades de Jornada 2.1

Ocho funciones nuevas, todas opcionales y agrupadas en *Ajustes* o en vistas propias para no recargar el panel.
Ninguna cambia los cálculos de las jornadas existentes ni necesita instalar nada.

### 1. Copias de seguridad y restauración

*Ajustes → Datos → Copias de seguridad.*

- **Descargar copia completa** genera `jornada-backup-AAAA-MM-DD.json` con **todo**: jornadas, descansos, notas,
  perfiles, semana habitual, períodos de verano, festivos y ausencias, idioma, tema, acento, densidad, animaciones,
  tarjetas visibles, atajos, objetivo semanal, avisos y reglas de cada tipo de día.
- **Restaurar una copia…**: eliges el archivo y Jornada lo **analiza y valida entero** (formato, versión, estructura,
  cada fecha y hora, cada ajuste y una suma de comprobación SHA-256). Te muestra qué tienes ahora y qué tendrás después,
  y te avisa de que **se reemplazarán** tus datos actuales. Hace falta marcar una casilla y confirmar.
- Antes de escribir, Jornada guarda una copia de lo actual en `data/backups/pre-restauracion-…/`.
  Los tres archivos se escriben como **una sola operación**: si algo falla a mitad, los que ya se habían sustituido
  vuelven a su contenido anterior. Nunca quedan ajustes de una copia con registros de otra.
- Se rechazan archivos de más de 10 MB, JSON inválido, archivos que no son de Jornada, copias de una versión futura,
  claves inesperadas, datos incoherentes o copias modificadas a mano (la suma no coincide). En esos casos no se escribe nada.
- Si los datos cambian entre la vista previa y la confirmación (por ejemplo, fichas desde otra ventana), se pide repetir el proceso.

<details>
<summary><b>Formato del archivo (versión de esquema 1)</b></summary>

```json
{
  "format": "jornada-backup",
  "schema_version": 1,
  "app_version": "2.1.0",
  "created_at": "2026-10-30T18:05:00+01:00",
  "checksum": "sha256:…",
  "counts": { "days": 120, "calendar_days": 14, "recurring": 9, "…": "…" },
  "data": {
    "records":  { "version": 1, "days": { "2026-10-29": { "clock_in": "…", "breaks": [ … ] } } },
    "settings": { "version": 3, "profiles": { … }, "accent": "teal", "notifications": { … } },
    "calendar": { "version": 1, "days": { "2026-12-08": { "type": "holiday", "label": "…" } }, "recurring": { "12-25": { "label": "Navidad" } } }
  }
}
```

- `checksum` es el SHA-256 de `data` serializado de forma canónica (claves ordenadas, sin espacios).
  Es opcional al restaurar, pero si está debe coincidir.
- Las versiones futuras podrán leer este esquema y migrarlo. Esta versión rechaza `schema_version` mayores que 1.
- Las copias de 2.0, con ajustes de versión 2 y sin `calendar`, se aceptan y se migran al restaurar.
</details>

### 2. Modo compacto flotante

Botón **Modo compacto** (icono de una ventana con un recuadro pequeño) en la barra superior:

| Opción | Qué hace |
|---|---|
| **Ver en compacto aquí** | La pestaña muestra solo el widget (`/compact`). El botón ↗ vuelve a la aplicación completa. |
| **Abrir en ventana aparte** | Una ventana pequeña del navegador (~380 × 460) para tenerla al lado mientras trabajas. |
| **Mantener encima** | Solo aparece si el navegador admite la [Document Picture-in-Picture API](https://developer.mozilla.org/docs/Web/API/Document_Picture-in-Picture_API) (Chrome y Edge 116+ de escritorio). La ventana flota sobre las demás. |

El widget muestra el estado, la cuenta atrás, la hora de salida, el porcentaje completado y la acción principal.

- **Sincronización:** el panel y el widget se avisan mediante `BroadcastChannel` (con `localStorage` como alternativa)
  y piden el estado al servidor cada 30 s. El contador se calcula en local, sin peticiones cada segundo.
- **Sin duplicados:** cada acción viaja con el estado que la ventana esperaba. Si otra ventana ya cambió la jornada,
  el servidor la rechaza y la ventana se actualiza.

> [!NOTE]
> «Mantener encima» depende del navegador. En Firefox o Safari no está disponible y se usa una ventana normal,
> que el sistema no mantiene encima de las demás.

### 3. Avisos inteligentes

*Ajustes → Avisos.*

- **Antes de terminar:** a 30, 15, 5 y 1 min (cada uno se activa por separado) o cualquier intervalo propio (hasta 8 en total).
- **Jornada completada.**
- **Descansos (opcionales):** recordatorio del descanso obligatorio pendiente tras X horas de trabajo,
  descanso mínimo completado y descanso configurado superado.
- **Cómo:** mensaje dentro de Jornada, notificación de escritorio y sonido discreto (generado al vuelo, sin archivos).
  El permiso de escritorio **solo se pide al activar esa opción**. El sonido solo suena después de haber interactuado con la página,
  como exigen los navegadores.
- **Sin repeticiones:** cada aviso se registra por día y se comparte entre pestañas y ventanas. Al recargar no se repite y,
  si al abrir ya pasó el momento, no se avisa tarde. Si editas la jornada y vuelve a faltar más tiempo, el aviso se rearma.

> [!IMPORTANT]
> Los avisos se calculan en el navegador. **Solo funcionan mientras Jornada está en marcha y abierta** en alguna pestaña o ventana.
> No se garantizan con el servidor cerrado, el navegador cerrado o el equipo suspendido. No hay ningún proceso en segundo plano.

### 4. Simulador de hora de salida

Botón **Simular jornada** (icono de varita) en la tarjeta «Hoy», o <kbd>Alt</kbd>+<kbd>Mayús</kbd>+<kbd>S</kbd>.

- Ajusta la entrada, las horas objetivo, el descanso realizado y el adicional (con *sliders*), el uso del descanso opcional
  y una salida deseada. El resultado cambia al instante.
- Atajos con las preguntas habituales: «¿Y si descanso 20 min más?», «¿y si salgo a las 17:00 / 18:30?»,
  «¿y con el descanso opcional?» o, para mañana, «¿y si empiezo a las 07:45?».
- **Actual frente a simulada:** salida, tiempo trabajado, descansos y balance, con la diferencia de cada uno y una barra visual.
- Usa **exactamente el mismo cálculo** que el panel (`core.compute_day`) sobre una copia de la jornada.
  **Nunca escribe en `records.json`**; hay pruebas que comprueban que ningún archivo cambia.

### 5. Festivos, vacaciones y ausencias

*Ajustes → Calendario*, o **Tipo de día** en el detalle de cualquier día del calendario.

- **Tipos:** festivo, vacaciones, día libre, permiso, baja y ausencia personalizada (con nombre).
- **Festivos:** crear, editar y eliminar, como fecha concreta o **cada año** en la misma fecha. Se pueden importar desde
  JSON (`[{"date": "2026-12-08", "label": "…"}]`) o CSV (`fecha;nombre;recurrente`, con fechas `2026-12-08`, `08/12/2026` o `12-25` para cada año).
  Jornada **no incluye calendarios oficiales**: tú añades tus festivos, sin depender de ninguna API.
- **Vacaciones por rango:** eliges desde y hasta. Antes de confirmar, ves cuántos días se marcarán. Solo se marcan
  tus días laborables y se respetan los festivos.
- **Cómo computa cada tipo:** lo decides tú, en *Ajustes → Calendario*:
  - **Sin objetivo** (por defecto): no genera déficit y reduce el objetivo semanal.
  - **Mantiene objetivo:** si no trabajas, cuenta como déficit.
- **Fichajes existentes:** marcar un día que ya tiene fichajes **nunca cambia sus horas**. Jornada pregunta:
  - **Solo marcar:** se ve la etiqueta y la jornada no cambia.
  - **Aplicar reglas:** su objetivo pasa a ser el del tipo, con una copia previa en `data/backups/`.
- Si trabajas un festivo, todo el tiempo cuenta como extra.
- **En el calendario**, cada estado se distingue también sin color:

| Estado | Cómo se ve |
|---|---|
| Sin registro | Casilla vacía |
| No laborable | Borde discontinuo |
| Festivo, vacaciones u otra ausencia | Rayado diagonal + icono del tipo (🚩, maleta, palmera…) |
| Jornada incompleta | Rojo con el déficit (−0:25) |
| Completada | Verde con el exceso (+0:35) |

### 6. Estadísticas avanzadas

Botón **Estadísticas avanzadas** en el apartado *Balance*. Se abren en una vista propia para no recargar el panel.

- **Actividad del mes:** mapa de calor con jornadas completadas, incompletas, en curso, días libres, no laborables y sin registro.
- **Evolución del balance:** línea del balance acumulado por **semanas** (12) o **meses** (12).
- **Promedios:** entrada y salida medias, trabajo efectivo, descanso, y los días con más y menos horas.
  Se calculan solo con días fichados; la salida, el trabajo y los descansos, solo con jornadas cerradas.
  Puedes verlos para el mes o para todo el historial.
- **Comparativa semanal:** objetivo frente a horas realizadas en las últimas 8 semanas, con el balance encima.
- Una jornada **todavía abierta** nunca se interpreta como déficit: solo suma su tiempo extra.
- Accesibles: cada gráfico tiene descripción y leyenda, y un botón **Ver datos** con la tabla equivalente. Al pasar el ratón, cada punto, barra o día muestra su detalle.
  Son SVG dibujado a mano, sin librerías.

### 7. Objetivo semanal y compensación simulada

Tarjeta **Esta semana** en el panel y *Ajustes → Horario → Objetivo semanal*.

- **Según mis horarios** (por defecto): suma los objetivos de cada día. Con los perfiles predeterminados,
  4 × 8 h 30 min + 7 h = **41 h**. Usa tus valores reales, el viernes intensivo, el verano y los festivos.
- **Personalizado:** la cifra que quieras; los festivos y vacaciones descuentan su jornada.
- La tarjeta separa el **progreso** (horas hechas frente al objetivo: restante y horas extra) del **balance cerrado**
  (suma de las jornadas ya finalizadas). Así, una jornada en curso nunca aparece como déficit.
- **Compensación simulada** (se puede desactivar): «Llevas +0:45: ¿y si sales antes?». Elige minutos y día, y verás
  a qué hora saldrías, el balance de ese día y cómo quedaría la semana. **Es solo informativa**: no se guarda nada y
  Jornada no impone ninguna regla de compensación.

### 8. Personalización visual

*Ajustes → Apariencia.* Los cambios se ven al instante y se deshacen si cancelas.

- **Tema:** claro, oscuro o según el sistema.
- **Acento:** verde azulado, azul, violeta, coral o ámbar. El contraste de cada uno está comprobado (≥ 4,5:1) en ambos temas.
  Con coral y ámbar, el descanso pasa a un azul (y con ámbar, la jornada cumplida a verde azulado) para no confundir estados.
- **Densidad:** cómoda o compacta. Cambia espacios y tamaños; no oculta información.
  (No tiene nada que ver con el *modo compacto*, que es la ventana flotante.)
- **Animaciones:** reducidas, normales o expresivas, estas últimas con una entrada escalonada y una celebración algo mayor.
  Si tu sistema pide **menos movimiento**, se respeta siempre, elijas lo que elijas.
- **Tarjetas del panel:** muestra u oculta las estadísticas rápidas, el balance acumulado, el resumen semanal,
  los próximos festivos y el historial. El contador, la salida prevista y los botones de fichaje no se pueden ocultar.

## Horarios normales e intensivos

| Perfil | Por defecto (editable en *Ajustes → Horario*) |
|---|---|
| Horario normal | 08:00–18:00 · 8 h 30 min efectivas · descanso de 60 min + 30 opcionales |
| Viernes intensivo | 08:00–15:00 · 7 h efectivas |
| Intensivo de verano | 08:00–15:00 · 7 h efectivas · aplicable por fechas, por ejemplo del 1/7 al 31/8 |

- Cada día de la semana tiene su perfil, si es laborable y su modalidad (oficina o teletrabajo).
- **Prioridad:** perfil elegido a mano para un día > período de verano > semana habitual.
- Cada jornada **conserva el perfil y el objetivo** que tenía, así que cambiar los ajustes no reescribe el pasado.
- 7 h trabajadas en un día de 7 h dan balance 0, nunca déficit.

## Atajos de teclado

*Ajustes → Atajos.* Pulsa **Asignar tecla** y después la combinación que quieras.

| Acción | Predeterminado |
|---|---|
| Iniciar jornada | <kbd>Alt</kbd> + <kbd>Mayús</kbd> + <kbd>I</kbd> |
| Iniciar descanso | <kbd>Alt</kbd> + <kbd>Mayús</kbd> + <kbd>D</kbd> |
| Finalizar descanso | <kbd>Alt</kbd> + <kbd>Mayús</kbd> + <kbd>V</kbd> |
| Finalizar jornada | <kbd>Alt</kbd> + <kbd>Mayús</kbd> + <kbd>F</kbd> |
| Abrir calendario | <kbd>Alt</kbd> + <kbd>Mayús</kbd> + <kbd>C</kbd> |
| Abrir estadísticas | <kbd>Alt</kbd> + <kbd>Mayús</kbd> + <kbd>B</kbd> |
| Abrir ajustes | <kbd>Alt</kbd> + <kbd>Mayús</kbd> + <kbd>A</kbd> |
| Cambiar tema claro/oscuro | <kbd>Alt</kbd> + <kbd>Mayús</kbd> + <kbd>T</kbd> |
| Editar el día actual | <kbd>Alt</kbd> + <kbd>Mayús</kbd> + <kbd>E</kbd> |
| Simular jornada *(2.1)* | <kbd>Alt</kbd> + <kbd>Mayús</kbd> + <kbd>S</kbd> |

- **Duplicados:** Jornada los detecta y no los asigna.
- **Atajos reservados:** avisa de los que suelen pertenecer al navegador o al sistema (por ejemplo, <kbd>Ctrl</kbd>+<kbd>T</kbd>).
- **Gestión:** puedes quitar una asignación o restaurar los valores predeterminados.
- **Cuándo actúan:** solo con la pestaña de Jornada activa, nunca mientras escribes en un campo ni con una ventana abierta.
- **Qué ejecutan:** solo acciones válidas en ese momento; por ejemplo, «Finalizar descanso» no hace nada si no estás descansando.
- **Teclas físicas:** se identifican por su posición (`KeyboardEvent.code`), así que funcionan igual en cualquier distribución de teclado.
- **Sin atajos globales:** no se instala ningún atajo del sistema.

## Exportación e importación

Desde **Historial → Exportar o importar**, o desde *Ajustes → Datos*.
Para guardar **todo** (también ajustes y festivos) en un solo archivo, usa la [copia de seguridad completa](#1-copias-de-seguridad-y-restauración).

### Exportar

- **Qué:** todo el historial, la semana actual, el mes seleccionado o un rango de fechas.
- **CSV:** compatible con Excel y LibreOffice (UTF-8, separado por punto y coma). Una columna por dato: fecha,
  modalidad, perfil, entrada, salida, trabajo efectivo, objetivo, balance, notas y cada descanso con su nota.
- **Informe PDF:** se abre una página lista para imprimir o *Guardar como PDF* en A4, con tabla de jornadas
  y resumen del período (trabajado, objetivo, descansos, tiempo de más y de menos).

### Importar

1. Elige o arrastra un CSV. Puede ser uno exportado por Jornada, también si lo has vuelto a guardar con Excel.
2. Jornada valida **todo** el archivo (fechas, horas, descansos y estructura) y muestra una vista previa: nuevas, ya existentes y con errores.
3. Para las fechas que ya existen, elige **omitirlas** o **sobrescribir solo las que marques**. Sobrescribir pide confirmación.
4. Al confirmar se guarda **una copia de seguridad** en `data/backups/` y los cambios se escriben de una sola vez.

Si algo cambia entre la vista previa y la confirmación, la importación se detiene sin escribir nada.
Exportar y volver a importar conserva todos los datos relevantes; hay pruebas automáticas que lo comprueban.

## Idiomas y temas

- **Idioma:** español (predeterminado) o inglés, desde el botón 🌐 de la barra superior o en *Ajustes → Apariencia*.
  El cambio es inmediato, sin recargar, y se guarda.
- **Tema:** claro, oscuro o según el sistema (botón ☀️/🌙 o *Ajustes → Apariencia*).
- **Formatos:** hora en 24 h o 12 h, y duraciones como `02:34:18` o `2 h 34 min`.

Los textos viven en [`static/i18n/`](static/i18n/). Para añadir un idioma, copia `es.json` con otro nombre,
tradúcelo y añade su código a `LANGUAGES` en [`i18n.py`](i18n.py).

## Persistencia y privacidad

- 🏠 **Todo se guarda en tu equipo**, en la carpeta `data/`. No hay cuentas, ni base de datos externa, ni sincronización en la nube.
- 🔒 **Solo localhost:** el servidor escucha únicamente en `127.0.0.1` y rechaza las peticiones con otro nombre de host.
- 📴 **Sin conexión:** no se usa ninguna CDN; la fuente y los iconos van incluidos.
- 💾 **Guardado seguro:** cada cambio se escribe al instante y de forma atómica (archivo temporal, `fsync` y `os.replace`).
  La versión anterior queda como `*.json.bak`.

| Archivo | Contenido |
|---|---|
| `data/records.json` | Tus jornadas: fichajes, descansos, notas, perfil y objetivo de cada día |
| `data/settings.json` | Perfiles, semana, verano, atajos, idioma, apariencia, avisos, objetivo semanal y reglas de tipos de día |
| `data/calendar.json` *(2.1)* | Festivos (concretos y recurrentes), vacaciones y ausencias |
| `data/backups/` | Copias automáticas: antes de importar, de restaurar, de aplicar un tipo de día a jornadas existentes y de migrar ajustes |

Los festivos van en su propio archivo porque son datos que crecen con los años, no ajustes. Las preferencias nuevas
amplían `settings.json` en lugar de crear más archivos.

**Migración a 2.1:** al primer arranque, `settings.json` pasa de la versión 2 a la 3. Antes se guarda una copia en
`data/backups/pre-migracion-ajustes-v2-…/`. Solo se **añaden** claves nuevas con sus valores predeterminados; ningún ajuste
existente se sobrescribe. `records.json` no cambia de formato: las jornadas creadas en un día marcado incluyen
el campo opcional `day_type`.

> [!WARNING]
> **No subas `data/` a ningún repositorio.** El `.gitignore` del proyecto ya la excluye, junto con el acceso directo generado,
> que contiene rutas de tu equipo.

## Limitaciones del navegador

Jornada usa solo funciones estándar del navegador. Algunas dependen de él y del sistema, y por eso no se presentan como garantizadas:

| Función | Depende de |
|---|---|
| Notificaciones de escritorio | Que concedas el permiso al sitio `127.0.0.1` y del gestor de notificaciones del sistema. |
| Sonido de los avisos | Que hayas interactuado con la página (política de reproducción automática). |
| Avisos en general | Que Jornada esté en marcha y abierta en alguna pestaña; los navegadores ralentizan las pestañas en segundo plano, así que un aviso puede llegar con unos segundos de retraso. |
| Mantener el widget encima | Document Picture-in-Picture (Chrome y Edge de escritorio). En los demás, ventana normal. |
| Ventana aparte | Que el navegador no bloquee la ventana emergente para `127.0.0.1`. |
| Sincronización entre ventanas | `BroadcastChannel` o, si falta, `localStorage`; además, cada 30 s se consulta el servidor. |

## Arquitectura del proyecto

```text
jornada/
├── app.py                 Servidor Flask (solo 127.0.0.1), API, ciclo de vida y puerto
├── core.py                Cálculos, perfiles, tipos de día, validación y notas (sin Flask)
├── insights.py            Simulador, objetivo semanal, compensación y estadísticas (2.1, puro)
├── daymarks.py            Rangos de vacaciones e importación de festivos (2.1, puro)
├── backup.py              Formato y validación de la copia completa (2.1)
├── csvio.py               Exportación e importación CSV
├── i18n.py                Traducciones del servidor (usa los mismos JSON que el navegador)
├── storage.py             JSON con escritura atómica, recuperación y escritura conjunta de varios archivos
├── templates/
│   ├── index.html         Interfaz (llega ya traducida desde el servidor)
│   ├── compact.html       Vista compacta /compact (2.1)
│   ├── _icons.html        Iconos SVG compartidos
│   └── report.html        Informe imprimible A4
├── static/
│   ├── css/style.css      Sistema visual: tokens, acentos, densidad, estados, responsive y movimiento
│   ├── js/                common.js · app.js · notify.js · calendar.js · insights.js · compact.js ·
│   │                      i18n.js · shortcuts.js · datatools.js (sin frameworks)
│   ├── i18n/              es.json · en.json
│   ├── fonts/             Plus Jakarta Sans (OFL)
│   └── img/               Icono
├── vendor/                Flask y dependencias (Python puro, con sus licencias)
├── tests/                 Pruebas automáticas
├── iniciar.sh · iniciar.bat · instalar-escritorio.sh
└── docs/                  Banner, capturas y demostración
```

Principios: las duraciones se calculan en UTC a partir de marcas guardadas, nunca con un contador en memoria.
Las horas se interpretan en `Europe/Madrid`, con los cambios de horario incluidos. La interfaz es HTML, CSS y JavaScript sin dependencias.

## Desarrollo y pruebas

```bash
python3 -m unittest -v        # 179 pruebas
python3 app.py --open         # arranque manual
python3 app.py --port 9000    # otro puerto preferido (también PORT=9000)
WORKTIME_DATA_DIR=/tmp/pruebas python3 app.py   # datos de prueba en otra carpeta
```

Las pruebas cubren:

- **Cálculos:** el ejemplo de 07:53, el cambio de horario, perfiles y prioridades.
- **Validaciones, notas y preferencias.**
- **Exportación e importación:** ida y vuelta, duplicados, archivos vueltos a guardar con Excel y protección frente a fórmulas.
- **Traducciones:** las mismas claves en ambos idiomas y ninguna clave usada sin traducir.
- **Arranque real:** segunda instancia, puerto ocupado y cierre limpio.
- **Versiones:** que todo elemento que usa la interfaz exista en la página y que una instancia abierta durante una actualización no mezcle versiones.
- **Copias de seguridad (2.1):** exportación completa, ida y vuelta exacta, archivos corruptos o manipulados, versiones futuras,
  copias antiguas de 2.0, cambios entre vista previa y confirmación, y **fallo a mitad de escritura** sin pérdida de datos.
- **Simulador (2.1):** que coincida al segundo con la salida del panel, descansos, intensivos, horas extra, salida anticipada
  y que **no modifique ningún archivo**.
- **Festivos y vacaciones (2.1):** recurrentes, rangos, festivos dentro del intensivo, no laborables, reglas configurables
  y fichajes históricos intactos.
- **Estadísticas y objetivo semanal (2.1):** promedios exactos, semanas incompletas, jornadas abiertas, meses vacíos,
  balance acumulado, vacaciones y compensación.
- **Personalización, avisos y modo compacto (2.1):** persistencia, contraste de los acentos, movimiento reducido,
  ninguna acción duplicada entre ventanas y el planificador de avisos **ejecutado en Chrome headless** (sin Node.js).
- **Navegador real (2.1):** si hay Chrome o Chromium, se cargan el panel, el simulador, las estadísticas, los ajustes
  y la vista compacta con datos ficticios, y se comprueba que no hay errores de JavaScript. Si no lo hay, estas pruebas se omiten.

## Solución de problemas

<details>
<summary><b>No se encuentra Python</b></summary>

- **Linux:** casi todas las distribuciones incluyen `python3`. Sin permisos de administrador puedes descomprimir un Python
  portable en `./python/`, de modo que quede `python/bin/python3`.
- **Windows:** usa el instalador de python.org con *Customize installation*, sin marcar *Install for all users*
  (se instala solo para tu usuario). Otra opción es descomprimir el *Windows embeddable package* en una carpeta `python\` dentro del proyecto.
- Si tu empresa bloquea todas estas vías, la única alternativa es pedir Python al departamento de informática.
</details>

<details>
<summary><b>El puerto 8765 está ocupado</b></summary>

Jornada prueba automáticamente 8766, 8767… hasta 8784, sin tocar el programa que ocupa el puerto.
También puedes elegir otro con `--port`.
</details>

<details>
<summary><b>El doble clic no abre nada en Linux</b></summary>

Autoriza el icono (tabla de [acceso directo](#crear-un-acceso-directo-en-el-escritorio)) y vuelve a ejecutar `./instalar-escritorio.sh`
si moviste la carpeta. Si arrancas sin terminal, los mensajes quedan en `data/jornada.log`.
</details>

<details>
<summary><b>He actualizado Jornada con la aplicación abierta</b></summary>

Jornada lo detecta y muestra un aviso: «Jornada se ha actualizado». Ciérrala con **⏻** y vuelve a abrirla para usar
la nueva versión del servidor. La página siempre se sirve de forma coherente con los archivos instalados, así que no se mezclan versiones.
</details>

<details>
<summary><b>No me llegan las notificaciones de escritorio</b></summary>

Comprueba en *Ajustes → Avisos* que la opción está activa. Si el navegador las bloqueó, permítelas para `127.0.0.1` en la configuración
del sitio (icono del candado o de información junto a la dirección). Recuerda que Jornada debe estar abierta en alguna pestaña.
Usa **Probar aviso** para comprobarlo.
</details>

<details>
<summary><b>No aparece la opción «Mantener encima»</b></summary>

Tu navegador no admite Document Picture-in-Picture. Usa «Abrir en ventana aparte»: es una ventana normal y pequeña.
</details>

<details>
<summary><b>Una copia de seguridad no se puede restaurar</b></summary>

Jornada explica el motivo: no es JSON, no es una copia de Jornada, es de una versión más nueva, está dañada o se editó a mano.
No se ha modificado nada. Si la copia es de una versión futura, actualiza Jornada.
</details>

<details>
<summary><b>Un atajo no hace nada</b></summary>

Comprueba que la pestaña de Jornada tiene el foco, que no estás escribiendo en un campo y que no hay ninguna ventana abierta.
Si Jornada te avisa de que la combinación está reservada, el navegador puede quedársela: elige otra.
</details>

<details>
<summary><b>Excel muestra caracteres extraños al abrir el CSV</b></summary>

El CSV está en UTF-8 con BOM, que Excel reconoce. Si lo abres con *Datos → Desde texto*, elige UTF-8 y el separador «;».
Jornada también importa archivos que Excel haya vuelto a guardar con coma o en Windows-1252.
</details>

## Roadmap

Ideas que podrían llegar; no están implementadas:

- Más idiomas (catalán, gallego, euskera, portugués…), sin cambiar el código.
- Paquete ejecutable autónomo para equipos sin Python.
- Copias de seguridad automáticas periódicas a una carpeta elegida.

Ya disponibles en 2.1: recordatorio de descanso, objetivos semanales y gráfica de evolución del balance.

## Contribuciones

Las contribuciones son bienvenidas. Mantén el espíritu del proyecto: **pequeño, local y sin dependencias que instalar**.

1. Abre un *issue* describiendo el cambio.
2. Ejecuta `python3 -m unittest` antes de enviar un *pull request* y añade pruebas para lo nuevo.
3. Todo texto visible va en `static/i18n/es.json` y `en.json`, con las mismas claves.
4. Nunca incluyas datos reales en ejemplos, capturas ni pruebas.

## Licencia

El código de Jornada se publica con licencia [MIT](LICENSE). Los componentes de terceros conservan las suyas:

- Flask, Werkzeug, Jinja2, MarkupSafe, itsdangerous, Click y Blinker: BSD-3-Clause.
- tzdata: Apache-2.0.
- Plus Jakarta Sans: SIL OFL 1.1.

Los textos están en `vendor/*.dist-info/` y `static/fonts/`.
