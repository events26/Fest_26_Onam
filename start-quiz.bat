@echo off
title Onotsavam Quiz Buzzer
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 goto nopython

echo.
echo   Starting the quiz server. Keep this window open.
echo   Close it, or press Ctrl-C, to stop the quiz.
echo.
python quiz-server.py
echo.
echo   The server has stopped.
pause
exit /b 0

:nopython
echo.
echo   Python is not installed on this computer.
echo.
echo   Get it from  https://www.python.org/downloads/
echo   During setup, TICK "Add Python to PATH" - without that
echo   this window will not find it.
echo.
echo   Then double-click this file again.
echo.
pause
exit /b 1
