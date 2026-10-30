@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto install
py -3.12 -m venv .venv
if not errorlevel 1 goto install
python -c "import sys; assert sys.version_info[:2] == (3,12)"
if errorlevel 1 goto pythonmissing
python -m venv .venv
if errorlevel 1 goto failed
:install
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
".venv\Scripts\python.exe" scripts\SupremeDeityFarmer.py --check
if errorlevel 1 goto failed
echo.
echo Setup finished. Double-click Start Supreme Deity.vbs to open the GUI.
pause
exit /b 0
:pythonmissing
echo Install Python 3.12 for Windows, including tkinter and the Python launcher, then run Setup again.
pause
exit /b 1
:failed
echo Setup failed. See the error above before starting the bot.
pause
exit /b 1
