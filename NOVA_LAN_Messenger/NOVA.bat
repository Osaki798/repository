@echo off
chcp 65001 >nul
title NOVA MESSENGER
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 launcher.py
) else (
    python launcher.py
)
if errorlevel 1 (
    echo.
    echo Не удалось запустить NOVA.
    echo Установи Python 3.9+ с сайта python.org и отметь Add Python to PATH.
    pause
)
