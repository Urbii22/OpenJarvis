@echo off
setlocal EnableExtensions

set "PORT=8000"
echo [OpenJarvis] Cerrando procesos en puerto %PORT%...

for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":%PORT%" ^| findstr LISTENING') do (
  echo [OpenJarvis] Finalizando PID %%p
  taskkill /PID %%p /T /F >nul 2>nul
)

echo [OpenJarvis] Listo.
exit /b 0
