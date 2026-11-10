@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Painel de tokens
python server.py %*
pause
