@echo off
title Polygraph
cd /d "%~dp0"

echo.
echo   Polygraph zapuskaetsya...
echo   Brauzer otkroetsya sam, kogda server budet gotov.
echo   Eto okno NE zakryvay - poka ono otkryto, rabotaet chat.
echo.

python web.py

pause
