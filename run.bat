@echo off
title PyMkvPropEdit v3.8 - Launcher
echo ============================================
echo   PyMkvPropEdit v3.8 - Batch GUI mkvpropedit
echo ============================================
echo.

:: Verifier Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERREUR] Python n'est pas installe ou pas dans le PATH.
    echo Telechargez Python 3.10+ sur https://www.python.org/downloads/
    echo Cochez "Add Python to PATH" lors de l'installation.
    pause
    exit /b 1
)

echo [OK] Python detecte.

:: Installer les dependances si necessaire
echo Installation/verification des dependances...
pip install -r "%~dp0requirements.txt" --quiet --disable-pip-version-check
if errorlevel 1 (
    echo [ATTENTION] Certaines dependances n'ont pas pu etre installees.
    echo L'application peut fonctionner en mode degrade (sans Audio Sync).
)

echo.
echo Demarrage de PyMkvPropEdit...
start "" pythonw "%~dp0PyMkvPropEdit v3.7.pyw"
