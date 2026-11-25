@echo off
rem Двойной клик: запускает TUI в этом окне (Windows).
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m src.tui
) else (
    echo Не найдено виртуальное окружение .venv
    echo Создайте его:
    echo    python -m venv .venv
    echo    .venv\Scripts\pip install -r requirements.txt
    pause
)
endlocal
