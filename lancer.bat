@echo off
REM Lance l'agent : fenetre Chrome dediee + ecoute du groupe Telegram. Laisser cette fenetre ouverte.
chcp 65001 >nul
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
  echo L'agent n'est pas installe : lance d'abord installer.bat
  pause
  exit /b 1
)
if exist connecteurs.json set CONNECTEURS=connecteurs.json
.venv\Scripts\python -m agent.telegram
pause
