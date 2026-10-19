@echo off
setlocal
cd /d "%~dp0"
py -m pip install --upgrade pip
py -m pip install -r requirements.txt
if errorlevel 1 goto error
py -m PyInstaller --noconfirm --clean --onefile --windowed --name TrackTagger app.py
if errorlevel 1 goto error
echo.
echo Build complete: dist\TrackTagger.exe
pause
exit /b 0
:error
echo Build failed. Check the error above.
pause
exit /b 1
