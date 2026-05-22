@echo off
REM Lance le serveur web sur http://localhost:8000
setlocal
set VENV_DIR=C:\Users\Utilisateur\chantier-venv
cd /d "%~dp0"

if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo Le venv n'existe pas. Lancez d'abord install.bat
    pause
    exit /b 1
)

echo === Demarrage du serveur sur http://localhost:8000 ===
echo Acces depuis cet ordinateur : http://localhost:8000
echo Acces depuis un autre appareil du reseau : http://%COMPUTERNAME%:8000
echo.
echo (Ctrl+C pour arreter)
echo.

REM --host 0.0.0.0 = accessible depuis le telephone/tablette sur le meme WiFi
"%VENV_DIR%\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
