@echo off
title Polygraph - DEV
cd /d "%~dp0"

echo.
echo   Polygraph - REZHIM RAZRABOTKI
echo   Server SAM podhvatyvaet izmeneniya v kode (.py).
echo   Menyaesh fayl -^> sohranyaesh -^> obnovi stranicu v brauzere (F5).
echo   Perezapuskat ne nuzhno!
echo.
echo   Ostanovit - zakroy eto okno.
echo.

python web.py --dev

pause
