# Jornada — fichaje personal

Herramienta local para tu control personal de la jornada: cuánto llevas, cuánto te queda,
a qué hora exacta puedes salir y tu balance de horas de más o de menos.
No es un sistema oficial ni impone reglas: solo informa.

## Inicio con doble clic (sin administrador)

### Linux: acceso directo en el escritorio y en el menú

Una sola vez, desde la carpeta del proyecto:

```bash
./instalar-escritorio.sh
```

El script solo escribe en tu carpeta de usuario y no necesita `sudo`. Crea tres archivos:

- `~/.local/share/applications/jornada.desktop`: Jornada en el menú de aplicaciones (búscala como «Jornada»).
- `~/Escritorio/Jornada.desktop`: el icono del escritorio (o `~/Desktop`, según tu idioma).
- `Jornada.desktop` dentro del proyecto, para lanzarla desde el gestor de archivos.

Si tu escritorio muestra el icono como «no confiable» o no lo ejecuta al hacer doble clic:

| Escritorio | Qué hacer (una sola vez) |
|---|---|
| GNOME / Ubuntu | Clic derecho en el icono → **Permitir lanzar** («Allow Launching»). El script ya intenta marcarlo con `gio set … metadata::trusted true`. |
| KDE Plasma | Al primer doble clic, elige **Ejecutar** / marca «No volver a preguntar». |
| XFCE | Al primer doble clic, elige **Marcar como ejecutable** o **Iniciar de todas formas**. |
| Cinnamon / MATE | Clic derecho → Propiedades → Permisos → **Permitir ejecutar como programa**. |

En GNOME, si no ves iconos en el escritorio, falta la extensión «Desktop Icons NG».
Usa el acceso del menú de aplicaciones, que funciona siempre.

Si mueves la carpeta del proyecto, vuelve a ejecutar `./instalar-escritorio.sh`.
Para quitar los accesos directos: `./instalar-escritorio.sh --quitar`. Esto no toca tus datos.

También puedes usar directamente **`iniciar.sh`**, con doble clic o `./iniciar.sh`.
El lanzador encuentra su carpeta aunque lo llames desde otro sitio o mediante un enlace.
Si no hay terminal, su salida se guarda en `data/jornada.log` y los errores se muestran en una ventana emergente.

### Windows

Doble clic en **`iniciar.bat`**. Se abre una consola: cerrarla detiene Jornada.

### Cómo funciona el arranque

- **Solo hace falta Python 3.10 o superior.** Flask y el resto de librerías van incluidas
  en la carpeta `vendor/`: no hace falta `pip`, `venv`, `sudo`, internet ni instalar nada.
- Todo queda dentro de esta carpeta: los datos se guardan en `data/`.
- El servidor escucha **solo en `127.0.0.1`**, así que no es accesible desde otros equipos.
  Además, rechaza cualquier petición que no llegue como `127.0.0.1` o `localhost`.
- **Puerto 8765** por defecto. Si otro programa lo usa, Jornada prueba 8766, 8767… hasta 8784,
  sin tocar ni detener ese programa.
- El navegador se abre cuando el servidor ya está escuchando.
- **Sin duplicados:** al arrancar, Jornada escribe `data/.jornada-run.json` con su PID y su puerto.
  Un segundo doble clic lee ese archivo y confirma en `/api/ping` que responde esa misma Jornada,
  con el mismo PID. Si es así, solo abre el navegador. No se busca ni se detiene ningún otro proceso.
- No se inicia con el equipo ni se instala como servicio.

## Cerrar Jornada por completo

- Botón **⏻ «Cerrar Jornada»**, arriba a la derecha → confirmar. Espera a que termine cualquier
  escritura en curso, detiene el servidor, libera el puerto, borra el archivo de control y muestra
  «Jornada se ha cerrado» en el navegador. Después ya puedes cerrar la pestaña.
- Cerrar la pestaña **no** detiene el servidor. Puedes volver a abrir la aplicación con el icono
  y verás los contadores al día.
- Si la arrancaste desde una terminal o con `iniciar.bat`, también la detienen Ctrl+C o cerrar esa ventana.
- Seguridad adicional: si nadie la usa durante **12 horas** (ninguna pestaña abierta), se cierra sola.
  Para cambiarlo, usa `JORNADA_IDLE_HOURS=4` o `JORNADA_IDLE_HOURS=0` (nunca).

### Si no tienes Python

La aplicación no puede funcionar sin Python 3.10 o superior, y el lanzador lo avisa.
Opciones que **no requieren administrador**:

- **Windows:** usa el instalador de python.org con *Customize installation* y deja **sin marcar**
  *Install for all users*. Así se instala solo para tu usuario.
- **Windows, portable:** descarga el *Windows embeddable package* de python.org y descomprímelo en
  una carpeta `python\` dentro de este proyecto (debe quedar `python\python.exe`).
  El lanzador lo detecta solo.
- **Linux:** casi todas las distribuciones traen `python3`. Si no, descomprime un Python portable
  (por ejemplo, python-build-standalone) en `./python/` (debe quedar `python/bin/python3`).

Si tu empresa bloquea también estas vías, la única alternativa es pedir Python al departamento
de informática. No hay forma de ejecutar código Python sin un intérprete.

### Arranque manual

```bash
python3 app.py --open                 # --open abre el navegador
python3 app.py --port 9000            # otro puerto preferido (también: PORT=9000)
WORKTIME_DATA_DIR=/ruta python3 app.py   # otra carpeta de datos
```

## Uso diario

1. **Iniciar jornada** por la mañana.
2. **Iniciar descanso / Terminar descanso** tantas veces como quieras.
3. **Finalizar jornada** cuando te vayas, hayas completado o no las horas.
   Si te equivocas, **Reanudar jornada** convierte el hueco en descanso.

Cualquier registro, también los cerrados, se puede editar o eliminar. Los días que olvidaste
fichar se añaden con **Añadir jornada**.

## Perfiles de horario

En **Ajustes** hay tres perfiles editables: entrada y salida de referencia, tiempo efectivo,
descanso mínimo y descanso opcional.

| Perfil | Por defecto |
|---|---|
| Horario normal | 08:00–18:00 · 8 h 30 min efectivas · descanso 60 min + 30 opcionales |
| Viernes intensivo | 08:00–15:00 · 7 h efectivas · descansos configurables (0 por defecto) |
| Intensivo de verano | 08:00–15:00 · 7 h efectivas · descansos configurables (0 por defecto) |

- **Semana habitual:** cada día tiene su perfil (por defecto, lunes a jueves normal y viernes intensivo),
  además de si es laborable y su modalidad.
- **Intensivo de verano por fechas:** añade uno o varios períodos (por ejemplo, del 1/7 al 31/8)
  y elige a qué días se aplica (por defecto, de lunes a viernes). Las dos fechas se incluyen.
  Fuera del período vuelve la semana habitual, con los viernes intensivos.
- **Perfil manual de un día:** en el editor de la jornada, «Perfil de horario». Ahí eliges «Automático»
  o un perfil concreto, que adopta sus objetivos. Después aún puedes retocarlos a mano.

**Prioridad:** perfil manual del día > período de verano > semana habitual.

Cada jornada guarda el perfil, el objetivo y las reglas de descanso que tenía ese día.
Si cambias un perfil o un período, las jornadas pasadas **no cambian**. La de hoy, si sigue abierta,
y los días futuros que ya hayas planificado sí adoptan los nuevos valores, salvo que los ajustaras a mano.
El calendario, la vista semanal y las estadísticas usan el objetivo de cada día: 7 h en un día de 7 h
dan balance 0, nunca déficit.

Los ajustes de versiones anteriores se migran solos al abrir la aplicación.
El archivo anterior queda guardado como `data/settings.json.bak`.

## Flexibilidad y balance

- Puedes trabajar más o menos de lo previsto, saltarte o acortar un descanso y finalizar
  cuando quieras. La aplicación solo **avisa**, nunca bloquea.
- Balance **diario, semanal, mensual y acumulado total** (todas las jornadas registradas).
  Ejemplo: +25, −15, +40, −10 min → **+40 min acumulados**.
- El balance es **informativo**: no cambia el objetivo de los días siguientes ni te obliga a compensar.
- Una jornada **en curso** solo suma su tiempo extra. Lo que le falta se muestra como «pendiente»
  y pasa a ser déficit cuando la finalizas.
- No cuentan como déficit los días futuros, los no laborables, los marcados como *Libre*
  ni los días pasados **sin ningún registro**.

Las únicas validaciones que quedan evitan datos imposibles: una salida anterior a la entrada,
descansos solapados o fuera de la jornada, y horas en el futuro.

## Cómo se calcula

- **Trabajo efectivo** = (salida o ahora) − entrada − descansos.
- **Salida prevista** = ahora + trabajo restante + descanso obligatorio aún no hecho.
  También se muestra la salida sin ese descanso y la salida usando el descanso opcional.
  Ejemplo: entrada 07:53 y pausa de 14:50 a 15:49 → te queda 1 h 33 min → **17:22**.
  Si completas el minuto de pausa que falta, la salida es a las **17:23**.
- Los contadores se recalculan siempre a partir de las marcas guardadas y la hora actual.
  Siguen siendo exactos aunque cierres el navegador, apagues la aplicación o el equipo se suspenda.
- Zona horaria `Europe/Madrid`, con los cambios de horario de verano e invierno incluidos.

## Datos

- `data/records.json` y `data/settings.json` se crean automáticamente.
- Escritura atómica: se escribe en un archivo temporal, se fuerza a disco con `fsync` y se sustituye con `os.replace`.
  Se guarda la versión anterior como `*.json.bak`. Un archivo corrupto se aparta como
  `*.corrupt-*.json` y se recupera desde la copia.
- Copia de seguridad: basta con copiar la carpeta `data/`.

## Pruebas

```bash
python3 -m unittest -v
```

## Estructura

```text
iniciar.bat / iniciar.sh   lanzadores (doble clic)
instalar-escritorio.sh     crea los accesos directos de Linux (sin sudo)
Jornada.desktop            acceso directo (lo regenera instalar-escritorio.sh)
static/img/jornada.*       icono de la aplicación
app.py                     servidor Flask (solo 127.0.0.1) y API
core.py                    cálculos, validación y estadísticas
storage.py                 JSON con escritura atómica
templates/ static/         interfaz (fuente Inter incluida, sin CDN)
vendor/                    Flask y dependencias incluidas (Python puro)
tests/                     pruebas automáticas
data/                      tus datos (se crea sola)
```

`requirements.txt` solo hace falta si prefieres crear tu propio entorno virtual en `.venv/`.
Si existe, los lanzadores lo usan; si no, no es necesario.

Licencias de terceros: Flask, Werkzeug, Jinja2, MarkupSafe, itsdangerous, Click y Blinker
(BSD-3-Clause) y tzdata (Apache-2.0) tienen sus textos de licencia en `vendor/*.dist-info/`.
La fuente Inter (`static/fonts/`) se distribuye con licencia SIL Open Font License 1.1.
