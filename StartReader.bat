@echo off
setlocal EnableExtensions

cd /d "%~dp0"

call :detect_python
if errorlevel 1 (
    echo [Error] Python 3 was not found in PATH.
    echo Please install Python 3.9+ and enable "Add Python to PATH".
    pause
    exit /b 1
)

call :prepare_python_env
if errorlevel 1 (
    echo [Error] Python environment paths could not be prepared.
    pause
    exit /b 1
)

echo [Info] Using Python command: %PY_CMD%
echo [Info] Python root: %PY_ROOT%

call :ensure_pip
if errorlevel 1 (
    echo [Error] pip could not be prepared automatically.
    pause
    exit /b 1
)

call :ensure_requirements
if errorlevel 1 (
    echo [Error] Automatic dependency installation failed.
    echo You can try this manually:
    echo     %PY_CMD% -m pip install -r "%~dp0requirements.txt"
    pause
    exit /b 1
)

if defined PYW_CMD (
    start "" /D "%~dp0" %PYW_CMD% "%~dp0main.py"
) else (
    start "" /D "%~dp0" %PY_CMD% "%~dp0main.py"
)
exit /b 0

:detect_python
set "PY_CMD="
set "PYW_CMD="

python -c "import sys" >nul 2>nul
if not errorlevel 1 (
    set "PY_CMD=python"
    pythonw -c "import sys" >nul 2>nul
    if not errorlevel 1 set "PYW_CMD=pythonw"
    exit /b 0
)

py -3 -c "import sys" >nul 2>nul
if not errorlevel 1 (
    set "PY_CMD=py -3"
    exit /b 0
)

exit /b 1

:prepare_python_env
set "PY_ROOT="
set "PY_LIB="
set "PY_SITE_PACKAGES="

for /f "usebackq delims=" %%I in (`%PY_CMD% -c "from pathlib import Path; import sys; print(str(Path(sys.executable).resolve().parent))"`) do (
    set "PY_ROOT=%%I"
)

if not defined PY_ROOT exit /b 1
if not "%PY_ROOT:~-1%"=="\" set "PY_ROOT=%PY_ROOT%\"

set "PY_LIB=%PY_ROOT%Lib"
set "PY_SITE_PACKAGES=%PY_LIB%\site-packages"

if defined PYTHONPATH (
    set "PYTHONPATH=%PY_LIB%;%PY_SITE_PACKAGES%;%PYTHONPATH%"
) else (
    set "PYTHONPATH=%PY_LIB%;%PY_SITE_PACKAGES%"
)

exit /b 0

:ensure_pip
%PY_CMD% -c "import pip" >nul 2>nul
if not errorlevel 1 exit /b 0

echo [Info] pip not found, trying to install it...
%PY_CMD% -m ensurepip --upgrade
if errorlevel 1 exit /b 1

%PY_CMD% -c "import pip" >nul 2>nul
if not errorlevel 1 exit /b 0

echo [Warn] ensurepip finished, but pip still could not be imported.
exit /b 1

:ensure_requirements
if not exist "%~dp0requirements.txt" (
    echo [Error] requirements.txt was not found.
    exit /b 1
)

%PY_CMD% -c "import PyQt6, requests, bs4, chardet; from Crypto.Cipher import AES" >nul 2>nul
if not errorlevel 1 exit /b 0

echo [Info] Missing Python packages detected. Installing requirements...
if defined VIRTUAL_ENV (
    %PY_CMD% -m pip install --disable-pip-version-check -r "%~dp0requirements.txt"
) else (
    %PY_CMD% -m pip install --disable-pip-version-check --upgrade --target "%PY_SITE_PACKAGES%" -r "%~dp0requirements.txt"
)
if errorlevel 1 exit /b 1

echo [Info] Verifying installation...
%PY_CMD% -c "import PyQt6, requests, bs4, chardet; from Crypto.Cipher import AES" >nul 2>nul
exit /b %errorlevel%
