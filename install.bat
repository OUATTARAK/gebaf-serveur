@echo off
REM Installation initiale - cree un venv hors OneDrive (recommande) puis installe les deps
setlocal
set VENV_DIR=C:\Users\Utilisateur\chantier-venv

echo === Verification de Python 3.13 ===
where py >nul 2>&1
if errorlevel 1 (
    echo Python n'est pas installe. Installation via winget...
    winget install Python.Python.3.13 --accept-package-agreements --accept-source-agreements --silent
)

if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo === Creation du venv dans %VENV_DIR% ===
    py -3.13 -m venv "%VENV_DIR%"
)

echo === Installation des dependances ===
"%VENV_DIR%\Scripts\python.exe" -m pip install --upgrade pip
"%VENV_DIR%\Scripts\pip.exe" install -r "%~dp0requirements.txt"

echo === Initialisation de la base et creation du compte admin ===
"%VENV_DIR%\Scripts\python.exe" -m scripts.init_db

echo.
echo Installation terminee. Pour demarrer l'application : run.bat
pause
