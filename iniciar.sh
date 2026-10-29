#!/bin/sh
# Jornada - lanzador para Linux/macOS. No necesita sudo ni instalar nada.
# Funciona desde una terminal, con doble clic en el gestor de archivos o desde
# el acceso directo (Jornada.desktop). Si Jornada ya está abierta, solo abre el navegador.

# Carpeta real del proyecto, aunque se haya movido o se llame mediante un enlace.
SELF=$(readlink -f "$0" 2>/dev/null || echo "$0")
cd "$(dirname "$SELF")" || exit 1

# Mensaje visible también cuando no hay terminal (doble clic / acceso directo).
aviso() {
    if [ -t 1 ]; then
        printf '\n%s\n\n' "$1"
        printf 'Pulsa Intro para salir...'; read -r _
    elif command -v zenity >/dev/null 2>&1; then
        zenity --error --title=Jornada --width=460 --text="$1" 2>/dev/null
    elif command -v kdialog >/dev/null 2>&1; then
        kdialog --title Jornada --error "$1" 2>/dev/null
    elif command -v notify-send >/dev/null 2>&1; then
        notify-send -i dialog-error Jornada "$1"
    elif command -v xmessage >/dev/null 2>&1; then
        xmessage -center "$1"
    fi
}

ok() { "$@" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; }

PY=""
for candidate in .venv/bin/python python/bin/python3 python3 python; do
    if ok "$candidate"; then PY="$candidate"; break; fi
done

if [ -z "$PY" ]; then
    aviso "No se ha encontrado Python 3.10 o superior.

Sin permisos de administrador puedes usar un Python portable descomprimido en
la carpeta «python» de Jornada (debe quedar python/bin/python3).
No hace falta pip: las librerías ya van incluidas."
    exit 1
fi

DATA_DIR=${WORKTIME_DATA_DIR:-data}
mkdir -p "$DATA_DIR"
LOG="$DATA_DIR/jornada.log"

if [ -t 1 ]; then
    "$PY" app.py --open "$@"
    status=$?
else
    # Sin terminal: la salida va a data/jornada.log.
    "$PY" app.py --open "$@" >> "$LOG" 2>&1
    status=$?
fi

if [ $status -ne 0 ]; then
    aviso "Jornada se ha detenido con un error.
Detalles en: $LOG (carpeta $(pwd))"
fi
exit $status
