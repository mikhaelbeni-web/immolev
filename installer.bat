@echo off
REM Installation de l'agent Optizien sur le PC du magasin (Windows 10/11).
chcp 65001 >nul
cd /d "%~dp0"

REM 1. Python : on cherche un vrai Python (pas le raccourci du Microsoft Store)
set PY=
py -3 --version >nul 2>&1 && set PY=py -3
if not defined PY (
  python --version 2>nul | findstr /r "^Python 3" >nul && set PY=python
)
if not defined PY (
  echo Python est absent : installation de Python 3.12 avec winget...
  winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
  if errorlevel 1 goto echec_python
  echo.
  echo Python est installe. FERME cette fenetre et relance installer.bat.
  pause
  exit /b 0
)
echo Python trouve :
%PY% --version

REM 2. Environnement et dependances
if not exist .venv (
  %PY% -m venv .venv
  if errorlevel 1 goto echec
)
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -r requirements.txt
if errorlevel 1 goto echec

REM 3. Tests (attendu : 24 passed)
.venv\Scripts\python -m pytest -q tests
if errorlevel 1 (
  echo.
  echo Des tests ont echoue : envoie une capture de cette fenetre dans le fil.
  pause
  exit /b 1
)

REM 4. Secrets et messagerie
.venv\Scripts\python configurer.py
if errorlevel 1 goto echec

echo.
echo Installation terminee. Lance l'agent avec lancer.bat
pause
exit /b 0

:echec_python
echo.
echo Installation automatique de Python impossible.
echo Installe-le depuis https://www.python.org/downloads/ en cochant "Add python.exe to PATH",
echo puis relance installer.bat.
pause
exit /b 1

:echec
echo.
echo L'installation a echoue a l'etape ci-dessus : envoie une capture de cette fenetre dans le fil.
pause
exit /b 1
