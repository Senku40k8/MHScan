@echo off
rem MHScan : menu de lancement (double-clic). Les textes sont sans accents pour s'afficher partout.
setlocal
cd /d "%~dp0"
title MHScan

where python >nul 2>nul
if errorlevel 1 (
    echo Python est introuvable : installe-le depuis https://www.python.org en cochant "Add python.exe to PATH".
    pause
    exit /b 1
)

:menu
cls
echo ==============================
echo            MHScan
echo ==============================
echo.
echo   1. Scanner l'ecurie
echo   2. Ouvrir le rapport
echo   3. Verifier la detection (check)
echo   4. Scanner en mode assiste
echo   Q. Quitter
echo.
choice /c 1234Q /n /m "Ton choix (1, 2, 3, 4 ou Q) : "
if errorlevel 5 exit /b 0
if errorlevel 4 goto assiste
if errorlevel 3 goto check
if errorlevel 2 goto rapport
goto scan

:scan
python -m mhscan scan
goto fin

:assiste
python -m mhscan scan --assiste
goto fin

:rapport
python -m mhscan rapport
goto fin

:check
python -m mhscan check
goto fin

:fin
echo.
pause
goto menu
