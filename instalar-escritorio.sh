#!/bin/sh
# Crea el acceso directo de Jornada SOLO para tu usuario (sin sudo):
#   - Jornada.desktop en esta carpeta
#   - ~/.local/share/applications/jornada.desktop   (menú de aplicaciones)
#   - Jornada.desktop en tu Escritorio
#
# Uso:  ./instalar-escritorio.sh            instala o actualiza los accesos directos
#       ./instalar-escritorio.sh --quitar   los elimina (no toca tus datos)
#
# Si mueves la carpeta del proyecto, vuelve a ejecutarlo para actualizar las rutas.
set -e

SELF=$(readlink -f "$0" 2>/dev/null || echo "$0")
DIR=$(cd "$(dirname "$SELF")" && pwd)
APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
DESKTOP_DIR=$(xdg-user-dir DESKTOP 2>/dev/null || true)
if [ -z "$DESKTOP_DIR" ] || [ "$DESKTOP_DIR" = "$HOME" ] || [ ! -d "$DESKTOP_DIR" ]; then
    DESKTOP_DIR=""
    for d in "$HOME/Escritorio" "$HOME/Desktop"; do
        [ -d "$d" ] && DESKTOP_DIR=$d && break
    done
fi
[ "$DESKTOP_DIR" = "$HOME" ] && DESKTOP_DIR=""

MENU_FILE="$APPS/jornada.desktop"
DESK_FILE="${DESKTOP_DIR:+$DESKTOP_DIR/Jornada.desktop}"

if [ "$1" = "--quitar" ]; then
    rm -f "$MENU_FILE" ${DESK_FILE:+"$DESK_FILE"}
    command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$APPS" 2>/dev/null || true
    echo "Accesos directos eliminados. Tus datos (carpeta data/) no se han tocado."
    exit 0
fi

chmod +x "$DIR/iniciar.sh"

# Escapado de la ruta para la línea Exec (especificación freedesktop):
# dentro de comillas se escapan \ " ` $ y el % se duplica.
EXEC_PATH=$(printf '%s' "$DIR/iniciar.sh" | sed -e 's/\\/\\\\\\\\/g' -e 's/"/\\\\"/g' -e 's/`/\\\\`/g' -e 's/\$/\\\\$/g' -e 's/%/%%/g')

write_desktop() {
    cat > "$1" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=Jornada
GenericName=Control de jornada
Comment=Fichaje personal: cuánto llevas, cuánto te queda y a qué hora sales
Exec="$EXEC_PATH"
Path=$DIR
Icon=$DIR/static/img/jornada.png
Terminal=false
StartupNotify=false
Categories=Office;
Keywords=fichaje;horas;jornada;trabajo;reloj;
EOF
    chmod +x "$1"
    # GNOME (escritorio con «Desktop Icons NG»): marca el lanzador como de confianza.
    if command -v gio >/dev/null 2>&1; then
        gio set "$1" metadata::trusted true 2>/dev/null || true
    fi
}

write_desktop "$DIR/Jornada.desktop"
echo "✓ $DIR/Jornada.desktop"

mkdir -p "$APPS"
write_desktop "$MENU_FILE"
command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$APPS" 2>/dev/null || true
echo "✓ Menú de aplicaciones: $MENU_FILE"

if [ -n "$DESK_FILE" ]; then
    write_desktop "$DESK_FILE"
    echo "✓ Escritorio: $DESK_FILE"
else
    echo "· No se ha encontrado la carpeta del Escritorio; usa el menú de aplicaciones."
fi

echo
echo "Listo. Si al hacer doble clic el escritorio muestra un aviso de seguridad,"
echo "haz clic derecho sobre el icono y elige «Permitir lanzar» (o «Confiar y lanzar»)."
