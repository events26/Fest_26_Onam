@echo off
title Onotsavam Quiz Buzzer
cd /d "%~dp0"

rem A portable Python dropped in beside this file wins, so a locked-down laptop
rem that cannot run installers still works. See NO-ADMIN-SETUP.txt.
if exist "%~dp0python-embed\python.exe" (
  echo.
  echo   Using the portable Python in this folder.
  set "PY=%~dp0python-embed\python.exe"
  goto run
)

where python >nul 2>nul
if not errorlevel 1 (
  set "PY=python"
  goto run
)

where py >nul 2>nul
if not errorlevel 1 (
  set "PY=py"
  goto run
)

goto nopython

:run
echo.
echo   Starting the quiz server. Keep this window open.
echo   Close it, or press Ctrl-C, to stop the quiz.
echo.
"%PY%" quiz-server.py
echo.
echo   The server has stopped.
pause
exit /b 0

:nopython
echo.
echo   Python was not found on this computer.
echo.
echo   If you can install software:
echo     Get it from  https://www.python.org/downloads/
echo     During setup, TICK "Add python.exe to PATH".
echo.
echo   If you CANNOT install software (no admin rights):
echo     Read NO-ADMIN-SETUP.txt in this folder. There is a
echo     portable version that needs no installer at all.
echo.
pause
exit /b 1
