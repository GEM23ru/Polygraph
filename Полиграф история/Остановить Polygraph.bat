@echo off
title Polygraph - stop
echo.
echo   Ostanavlivayu Polygraph...
taskkill /F /IM pythonw.exe >nul 2>&1
taskkill /F /IM python.exe >nul 2>&1
echo   Gotovo. Server ostanovlen.
echo.
timeout /t 2 >nul
