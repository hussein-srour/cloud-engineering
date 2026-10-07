@echo off
setlocal
cd /d "%~dp0"
echo AG Energies Quotation Studio
echo.
if exist ".venv\Scripts\python.exe" goto run
where py >nul 2>nul
if errorlevel 1 goto pythonfallback
py -3 -m venv .venv
if errorlevel 1 goto failed
goto install
:pythonfallback
python -m venv .venv
if errorlevel 1 goto missing
:install
echo Installing the application. Internet is needed for this first setup only.
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto failed
:run
.venv\Scripts\python.exe -c "import flask,reportlab,PIL,waitress" >nul 2>nul
if errorlevel 1 goto install
.venv\Scripts\python.exe app.py
if errorlevel 1 goto failed
goto end
:missing
echo Python was not found. Install Python 3.10 or newer from python.org.
echo Enable "Add Python to PATH" during installation, then run this file again.
pause
exit /b 1
:failed
echo.
echo The app could not start. Review the error above.
echo If port 8765 is already in use, close the other AG Energies window first.
pause
exit /b 1
:end
endlocal
