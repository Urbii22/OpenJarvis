@echo off
setlocal
cd /d D:\UTILS\CODEX\JARVIS

D:\UTILS\CODEX\JARVIS\.venv\Scripts\python.exe -u D:\UTILS\CODEX\JARVIS\scripts\windows_hotkey_voice.py --hotkey ctrl+alt+j --min-seconds 0.6 --language es --agent orchestrator --stt-model tiny --input-device 15 --live-ui --theme hacker

if errorlevel 1 (
  echo.
  echo Voice UI stopped with error.
  pause
)
