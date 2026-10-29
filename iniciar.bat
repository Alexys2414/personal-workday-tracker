@echo off
rem Jornada - lanzador para Windows (no necesita permisos de administrador).
rem Cierra esta ventana para detener la aplicacion.
setlocal
cd /d "%~dp0"
title Jornada

set "PY="
rem 1) Entorno virtual propio, si existe   2) Python portable en .\python\
rem 3) Python instalado para el usuario (lanzador py, python, python3)
if exist ".venv\Scripts\python.exe" call :try ".venv\Scripts\python.exe"
if not defined PY if exist "python\python.exe" call :try "python\python.exe"
if not defined PY call :try py -3
if not defined PY call :try python
if not defined PY call :try python3
if not defined PY goto :nopython

%PY% app.py --open
if errorlevel 1 (
  echo.
  echo La aplicacion se ha detenido con un error. Revisa el mensaje anterior.
  pause
)
exit /b

:try
rem Comprueba que el ejecutable funciona de verdad y es 3.10+ (descarta el acceso
rem directo de Microsoft Store que solo abre la tienda).
%* -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if not errorlevel 1 set "PY=%*"
exit /b

:nopython
echo.
echo  No se ha encontrado Python 3.10 o superior.
echo.
echo  Opciones que NO requieren administrador:
echo   a) Instalador de python.org: elige "Customize installation" y deja SIN
echo      marcar "Install for all users" (se instala solo para tu usuario).
echo   b) Python portable: descarga el "Windows embeddable package (64-bit)"
echo      de python.org y descomprimelo en una carpeta llamada "python"
echo      dentro de esta carpeta (debe quedar python\python.exe).
echo   c) Python desde Microsoft Store, si tu empresa lo permite.
echo.
echo  No hace falta pip ni instalar nada mas: las librerias van incluidas.
echo.
pause
exit /b 1
