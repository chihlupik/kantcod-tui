@echo off
rem Установка «Прозрачная вакансия» (Windows). Двойной щелчок — и всё.
setlocal
cd /d "%~dp0"
echo ============================================
echo   Установка программы "Прозрачная вакансия"
echo ============================================
echo.

rem Ищем Python: сначала python, затем лаунчер py -3
set "PYCMD="
python --version >nul 2>nul
if not errorlevel 1 set "PYCMD=python"
if not defined PYCMD (
    py -3 --version >nul 2>nul
    if not errorlevel 1 set "PYCMD=py -3"
)
if not defined PYCMD (
    echo [!] Не найден Python.
    echo     Скачайте его с https://www.python.org/downloads/
    echo     При установке поставьте галочку "Add Python to PATH".
    echo.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo [*] Создаю рабочую папку программы...
    %PYCMD% -m venv .venv
    if not exist ".venv\Scripts\python.exe" (
        echo [!] Не удалось создать окружение. Проверьте установку Python.
        pause
        exit /b 1
    )
)

echo [*] Устанавливаю компоненты (нужен доступ в интернет)...
".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt
if errorlevel 1 (
    echo [!] Ошибка установки. Проверьте подключение к интернету и повторите.
    pause
    exit /b 1
)

echo.
echo [OK] Установка завершена!
echo     Запустите программу: двойной щелчок по файлу kantcod.bat
echo.
pause
