@echo off
title USB Device Control ^& Monitoring Framework

echo.
echo =========================================================
echo   USB DEVICE CONTROL ^& MONITORING FRAMEWORK
echo   Windows Security Tool - Admin Launcher
echo =========================================================
echo.

:: -------------------------------------------------------
:: Verify that the Python launcher (py) or python is
:: available before proceeding.
:: -------------------------------------------------------
where py >nul 2>&1
if %errorLevel% == 0 (
    set PYTHON_CMD=py -3
) else (
    where python >nul 2>&1
    if %errorLevel% neq 0 (
        echo [ERROR] Python not found in PATH.
        echo         Install Python 3 and ensure it is in your PATH.
        pause
        exit /b 1
    )
    set PYTHON_CMD=python
)

:: -------------------------------------------------------
:: Check whether we already have Administrator privileges.
:: net session is a reliable way to test this on Windows.
:: -------------------------------------------------------
net session >nul 2>&1
if %errorLevel% == 0 (
    echo [OK] Running with Administrator privileges.
    echo.
    %PYTHON_CMD% "%~dp0usb_monitor.py"
    pause
    exit /b 0
)

:: -------------------------------------------------------
:: Re-launch this same batch file with elevation via
:: PowerShell's Start-Process -Verb RunAs.
:: -------------------------------------------------------
echo [INFO] Administrator privileges required.
echo [INFO] A UAC prompt will appear - please click Yes.
echo.

powershell -NoProfile -Command ^
    "Start-Process cmd -ArgumentList '/c cd /d ""%~dp0"" && py -3 usb_monitor.py && pause' -Verb RunAs"

exit /b 0
