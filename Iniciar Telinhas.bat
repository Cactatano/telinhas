@echo off
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo O Python nao foi encontrado.
  echo Instale em https://www.python.org/downloads/ e marque "Add python.exe to PATH".
  pause
  exit /b
)
where pythonw >nul 2>nul && (start "" pythonw ponte.py --abrir) || (start "" python ponte.py --abrir)
