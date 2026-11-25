#!/usr/bin/env bash
# Двойной клик в Finder (macOS) или файловом менеджере Linux: запускает TUI в терминале.
cd "$(dirname "$0")" || exit 1
if [ -x ".venv/bin/python" ]; then
    exec .venv/bin/python -m src.tui
fi
echo "Не найдено виртуальное окружение .venv"
echo "Создайте его: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
read -r -p "Нажмите Enter, чтобы закрыть..." _
