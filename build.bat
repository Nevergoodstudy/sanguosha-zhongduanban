@echo off
setlocal
cd /d "%~dp0" || exit /b 1
python -m pip install ".[build]" || exit /b 1
python build.py %*
exit /b %errorlevel%
