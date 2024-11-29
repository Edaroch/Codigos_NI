@echo off
echo =========================================================
echo BIENVENIDO A LA CONFIGURACION DEL PROYECTO
echo =========================================================

:: Aviso sobre NI MAX
echo Paso 1: Este proyecto requiere que NI MAX esté instalado.
echo ¿Está NI MAX instalado en este equipo? (s/n)
set /p nimax_installed="Respuesta: "

if /i "%nimax_installed%"=="s" (
    echo Continuando con la configuración...
) else (
    echo =========================================================
    echo DESCARGUE E INSTALE NI MAX DESDE: https://www.ni.com
    echo Luego de instalarlo, vuelva a ejecutar este script.
    echo =========================================================
    pause
    exit /b
)

:: Verificar instalación de Python 3.10
echo Paso 2: Verificando instalación de Python 3.10...
python --version | findstr "3.10" >nul
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Python 3.10 no está instalado o no está en el PATH.
    echo Descargue Python 3.10 desde: https://www.python.org/downloads/
    pause
    exit /b
)
echo Python 3.10 está instalado.

:: Verificar existencia de requirements.txt
if not exist requirements.txt (
    echo ERROR: No se encontró el archivo requirements.txt en el directorio actual.
    echo Asegúrese de que el archivo esté en la carpeta raíz del proyecto.
    pause
    exit /b
)
echo Archivo requirements.txt encontrado.

:: Crear entorno virtual
echo Paso 3: Creando entorno virtual de Python (.venv)...
python -m venv .venv
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: No se pudo crear el entorno virtual.
    pause
    exit /b
)

:: Activar entorno virtual e instalar paquetes
echo Paso 4: Activando el entorno virtual e instalando paquetes...
call .venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: No se pudieron instalar los paquetes especificados en requirements.txt.
    deactivate
    pause
    exit /b
)
deactivate

echo =========================================================
echo CONFIGURACIÓN COMPLETADA EXITOSAMENTE.
echo =========================================================
echo Presione cualquier tecla para salir...
pause
