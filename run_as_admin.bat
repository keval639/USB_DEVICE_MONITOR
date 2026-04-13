@echo off
cd /d "%~dp0"
powershell -Command "Start-Process powershell -ArgumentList '-NoExit', '-Command', '& """%~dp0\.venv\Scripts\python.exe""" """%~dp0\usb_monitor.py"""' -Verb RunAs"
pause
