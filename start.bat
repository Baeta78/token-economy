@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Token Economy
python server.py %*
pause
