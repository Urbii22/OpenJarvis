@echo off
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0"
set "ROOT=%CD%"
set "BACKEND_HOST=127.0.0.1"
set "BACKEND_PORT=8000"
set "HEALTH_URL=http://%BACKEND_HOST%:%BACKEND_PORT%/health"
set "BACKEND_TITLE=OpenJarvis Backend"

echo [OpenJarvis] Root: %ROOT%

if exist "%ROOT%\frontend\node_modules\.vite" (
  echo [OpenJarvis] Limpiando cache de Vite...
  rmdir /s /q "%ROOT%\frontend\node_modules\.vite"
)

if not exist "%ROOT%\.venv\Scripts\python.exe" (
  echo [ERROR] No se encontro el entorno virtual en "%ROOT%\.venv".
  echo Ejecuta primero la instalacion del proyecto y vuelve a intentarlo.
  pause
  exit /b 1
)

where npm >nul 2>nul
if errorlevel 1 (
  echo [ERROR] npm no esta disponible en PATH.
  echo Instala Node.js ^(>=20^) y vuelve a intentarlo.
  pause
  exit /b 1
)

set "BACKEND_LOG_OUT=%ROOT%\openjarvis-serve.out.log"
set "BACKEND_LOG_ERR=%ROOT%\openjarvis-serve.err.log"

echo [OpenJarvis] Comprobando backend en %HEALTH_URL% ...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "try { $r = Invoke-WebRequest -UseBasicParsing -Uri '%HEALTH_URL%' -TimeoutSec 2; if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 500) { exit 0 } else { exit 1 } } catch { exit 1 }"

if errorlevel 1 (
  echo [OpenJarvis] Backend no detectado. Iniciando backend en ventana separada...
  start "%BACKEND_TITLE%" cmd /k call "%ROOT%\scripts\start_openjarvis_backend.bat"
) else (
  echo [OpenJarvis] Backend ya activo.
)

echo [OpenJarvis] Esperando backend...
set /a _tries=0
:wait_backend
set /a _tries+=1
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "try { $r = Invoke-WebRequest -UseBasicParsing -Uri '%HEALTH_URL%' -TimeoutSec 2; if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 500) { exit 0 } else { exit 1 } } catch { exit 1 }"
if not errorlevel 1 goto backend_ok
if %_tries% GEQ 40 (
  echo [ERROR] El backend no respondio a tiempo.
  echo Revisa logs:
  echo   %BACKEND_LOG_OUT%
  echo   %BACKEND_LOG_ERR%
  pause
  exit /b 1
)
timeout /t 1 /nobreak >nul
goto wait_backend

:backend_ok
echo [OpenJarvis] Backend OK. Lanzando app Tauri...
cd /d "%ROOT%\frontend"
call npm run tauri dev
set "TAURI_EXIT=%ERRORLEVEL%"

cd /d "%ROOT%"
if not "%TAURI_EXIT%"=="0" (
  echo [ERROR] Tauri cerro con codigo %TAURI_EXIT%.
  pause
  exit /b %TAURI_EXIT%
)

exit /b 0
