#!/usr/bin/env bash
# Установка «Прозрачная вакансия» (Linux / macOS). Двойной щелчок — и всё.
cd "$(dirname "$0")" || exit 1
echo "============================================"
echo "  Установка программы «Прозрачная вакансия»"
echo "============================================"
echo

if ! command -v python3 >/dev/null 2>&1; then
    echo "[!] Не найден Python 3."
    echo "    macOS: https://www.python.org/downloads/ (при первом запуске может попросить установить инструменты командной строки)"
    echo "    Ubuntu/Debian: sudo apt install python3 python3-venv"
    echo
    read -r -p "Нажмите Enter, чтобы закрыть..." _
    exit 1
fi

if [ ! -x .venv/bin/python ]; then
    echo "[*] Создаю рабочую папку программы..."
    python3 -m venv .venv
    if [ ! -x .venv/bin/python ]; then
        echo "[!] Не удалось создать окружение. Проверьте установку Python."
        read -r -p "Нажмите Enter, чтобы закрыть..." _
        exit 1
    fi
fi

echo "[*] Устанавливаю компоненты (нужен доступ в интернет)..."
.venv/bin/python -m pip install --quiet --upgrade pip
if ! .venv/bin/python -m pip install --quiet -r requirements.txt; then
    echo "[!] Ошибка установки. Проверьте подключение к интернету и повторите."
    read -r -p "Нажмите Enter, чтобы закрыть..." _
    exit 1
fi

echo
echo "[OK] Установка завершена!"
echo "    Запустите программу: двойной щелчок по файлу kantcod.command"
echo "    (в Linux-меню приложений — «Прозрачная вакансия»)"
echo
read -r -p "Нажмите Enter, чтобы закрыть..." _
