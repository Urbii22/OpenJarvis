@echo off
setlocal EnableExtensions

cd /d "%~dp0\.."
set "ROOT=%CD%"
set "BACKEND_HOST=127.0.0.1"
set "BACKEND_PORT=8000"
set "BACKEND_LOG_OUT=%ROOT%\openjarvis-serve.out.log"
set "BACKEND_LOG_ERR=%ROOT%\openjarvis-serve.err.log"

echo [OpenJarvis Backend] Starting on %BACKEND_HOST%:%BACKEND_PORT% ...
uv run jarvis serve --host %BACKEND_HOST% --port %BACKEND_PORT% 1>>"%BACKEND_LOG_OUT%" 2>>"%BACKEND_LOG_ERR%"
