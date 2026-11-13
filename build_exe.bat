@echo off
rem Crea dist\Promemoria.exe (un solo file, nessun Python richiesto per usarlo)
cd /d "%~dp0"
python -m pip install --upgrade pyinstaller >nul
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name Promemoria ^
  --icon promemoria\ui\assets\promemoria.ico ^
  --add-data "promemoria\ui\assets;promemoria\ui\assets" ^
  --hidden-import win32com.shell --hidden-import win32com.propsys ^
  --collect-submodules google_auth_oauthlib --collect-submodules google.oauth2 ^
  --exclude-module pytest ^
  main.py
