"""Текстовый интерфейс (TUI) на Python Textual — работает в Windows, Linux и macOS.

Запуск:  .venv/bin/python -m src.tui
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any

from croniter import croniter
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Log,
    Static,
    TabbedContent,
    TabPane,
)

from .ai.factory import AIUnavailable, create_provider
from .analyzer import analyze_all
from .config import DEFAULT_CONFIG_PATH, ROOT, Config
from .facts import text
from .fetcher import FetchError, fetch_vacancies
from .report import build_report, save_success
from .resume import draft_resume, find_vacancy, load_vacancies

__all__ = ["VacancyTUI", "main"]


def _relative(path: Path) -> str:
    """Путь относительно корня проекта, если возможно — для config/config.json."""
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


class VacancyTUI(App):
    """TUI-обёртка вокруг pipeline командной строки: run / verify / resume."""

    BINDINGS = [("ctrl+q", "quit", "Выход")]
    CSS = """
    #actions { height: auto; }
    #inputs { height: auto; }
    #config_text { height: auto; margin-bottom: 1; }
    #status { color: $text-muted; }
    """

    def __init__(self) -> None:
        super().__init__()
        self._cfg: Config = Config.load()
        self._report: dict[str, Any] | None = None

    # ---------- compose / mount ----------

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent():
            with TabPane("Обзор"):
                with VerticalScroll(id="dashboard"):
                    yield Static("Последний отчёт — нет данных", id="summary")
                    yield Static("", id="status")
                    with Horizontal(id="actions"):
                        yield Button("Запустить сейчас", id="btn_run")
                        yield Button("Проверить файл", id="btn_verify")
                        yield Button("Черновик резюма", id="btn_resume")
                        yield Button("Открыть отчёт", id="btn_open")
                    with Horizontal(id="inputs"):
                        yield Input(placeholder="Файл для проверки (ответ API)", id="verify_path")
                        yield Input(placeholder="ID вакансии для резюма", id="resume_id")
            with TabPane("Замечания"):
                with VerticalScroll(id="findings_area"):
                    yield Static("Данных нет — запустите анализ или проверку", id="findings")
            with TabPane("Настройки"):
                with VerticalScroll(id="config_area"):
                    yield Static(id="config_text")
                    yield Input(placeholder="Путь к config/config.json", id="config_path")
                    yield Button("Сохранить config.json", id="btn_save_config")
                    yield Input(placeholder="Путь к отчёту", id="report_path")
                    yield Button("Применить путь отчёта", id="btn_set_report_path")
            with TabPane("Лог"):
                yield Log(id="log", highlight=True)
        yield Footer()

    def on_mount(self) -> None:
        self.title = "Прозрачная вакансия — TUI"
        self.query_one("#report_path", Input).value = str(self._cfg.report_path)
        self._refresh_dashboard()
        self._refresh_findings()
        self._refresh_config()
        self._log("TUI готов. Нажмите «Запустить сейчас» или «Проверить файл».")

    # ---------- лог ----------

    def _log(self, message: str) -> None:
        line = f"[{datetime.now().strftime('%H:%M:%S')}] {text(message)}"
        self.query_one("#log", Log).write_line(line)

    # ---------- dashboard / findings / config ----------

    def _dashboard_text(self) -> str:
        cfg = self._cfg
        report = self._report
        lines: list[str] = []
        if report is None:
            lines.append(f"Последний отчёт: {cfg.report_path} (нет данных)")
        else:
            stats = report.get("stats", {})
            ai = report.get("ai", {})
            lines.append(f"Последний отчёт: {cfg.report_path}")
            lines.append(
                "Сгенерирован: {generated_at} · Режим: {mode} · Источник: {source}".format(**report)
            )
            lines.append(
                "Вакансий: {vacancies_in_report} · Дубликатов: {duplicates_skipped} · "
                "Замечаний: {findings_total} · Ошибок ИИ: {ai_errors}".format(**stats)
            )
            by_kind = stats.get("by_kind") or {}
            if by_kind:
                lines.append("По видам: " + ", ".join(f"{k}: {v}" for k, v in sorted(by_kind.items())))
            lines.append(f"ИИ: {ai.get('provider')}/{ai.get('model')}")
        status = self._run_status()
        if status:
            lines.append(status)
        next_run = self._next_run()
        if next_run:
            lines.append(f"Следующий запуск по расписанию: {next_run}")
        return "\n".join(lines)

    def _run_status(self) -> str:
        if not self._cfg.run_status_path.exists():
            return ""
        try:
            data = json.loads(self._cfg.run_status_path.read_text(encoding="utf-8"))
        except Exception:
            return ""
        if data.get("status") == "error":
            return f"[Ошибка источника] {text(data.get('error'))} (последний успешный отчёт сохранён)"
        return ""

    def _next_run(self) -> str | None:
        try:
            try:
                from zoneinfo import ZoneInfo

                tz = ZoneInfo(self._cfg.timezone)
            except Exception:
                tz = None
            return croniter(self._cfg.schedule, datetime.now(tz)).get_next(datetime).isoformat(timespec="seconds")
        except Exception:
            return None

    def _findings_text(self) -> str:
        report = self._report
        if not report:
            return "Нет отчёта — запустите анализ."
        blocks: list[str] = []
        for vacancy in report.get("vacancies", []):
            findings = vacancy.get("findings") or []
            if not findings:
                continue
            header = str(vacancy.get("id")) + (f" — {vacancy['url']}" if vacancy.get("url") else "")
            lines = [header]
            for finding in findings:
                lines.append(f"  [{finding.get('kind')}] {finding.get('topic')} — поле: {finding.get('field')}")
                lines.append(f"    Суть: {finding.get('issue')}")
                lines.append(f"    Рекомендация: {finding.get('recommendation')}")
                if finding.get("quote"):
                    lines.append(f"    Цитата: {finding.get('quote')}")
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks) if blocks else "Замечаний в отчёте нет."

    def _config_text(self) -> str:
        cfg = self._cfg
        return "\n".join(
            [
                f"source_url: {cfg.source_url}",
                f"schedule: {cfg.schedule} (timezone {cfg.timezone})",
                f"max_vacancies: {cfg.max_vacancies} · page_size: {cfg.page_size} · max_pages: {cfg.max_pages}",
                f"request_timeout: {cfg.request_timeout} · retries: {cfg.retries}",
                f"ai.provider: {cfg.ai_provider} · workers: {cfg.ai_workers}",
                f"ai.models: gigachat={cfg.gigachat_model}, ollama={cfg.ollama_model} ({cfg.ollama_url})",
                f"paths.report: {cfg.report_path}",
                f"paths.last_input: {cfg.last_input_path}",
                f"paths.resume_draft: {cfg.resume_draft_path}",
            ]
        )

    def _refresh_dashboard(self) -> None:
        self.query_one("#summary", Static).update(self._dashboard_text())
        self.query_one("#status", Static).update(
            f"Статус расписания: {self._next_run() or 'недоступно'}"
        )

    def _refresh_findings(self) -> None:
        self.query_one("#findings", Static).update(self._findings_text())

    def _refresh_config(self) -> None:
        self.query_one("#config_text", Static).update(self._config_text())
        self.query_one("#report_path", Input).value = str(self._cfg.report_path)

    # ---------- события / кнопки ----------

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn_run":
            self.cmd_run()
        elif event.button.id == "btn_verify":
            self.cmd_verify(self.query_one("#verify_path", Input).value.strip() or None)
        elif event.button.id == "btn_resume":
            vacancy_id = self.query_one("#resume_id", Input).value.strip()
            if not vacancy_id:
                self._log("Укажите ID вакансии в поле над кнопкой.")
                return
            self.cmd_resume(vacancy_id)
        elif event.button.id == "btn_open":
            self._open_file(self._cfg.report_path)
        elif event.button.id == "btn_save_config":
            self.save_config()
        elif event.button.id == "btn_set_report_path":
            value = self.query_one("#report_path", Input).value.strip()
            if value:
                self._cfg = replace(self._cfg, report_path=Path(value))
                self._refresh_dashboard()
                self._log(f"Путь отчёта обновлён: {self._cfg.report_path}")

    def _open_file(self, path: Path) -> None:
        if not path.exists():
            self._log(f"[ОШИБКА] Файл не найден: {path}")
            return
        try:
            if sys.platform == "win32":
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as exc:
            self._log(f"[ОШИБКА] Не удалось открыть {path}: {exc}")
            return
        self._log(f"[OK] Открыто в системном приложении: {path}")

    # ---------- workers (анализ в потоках — UI не замораживается) ----------

    @work(thread=True)
    def cmd_run(self) -> None:
        cfg = self._cfg
        self.call_from_thread(self._log, "Начало анализа: загрузка вакансий...")
        try:
            provider = create_provider(cfg, None)
        except AIUnavailable as exc:
            self.call_from_thread(self._log, f"[ОШИБКА] {exc}")
            return
        try:
            fetched = fetch_vacancies(cfg)
        except FetchError as exc:
            self.call_from_thread(self._log, f"[ОШИБКА] Источник недоступен: {exc}")
            return
        self.call_from_thread(
            self._log, f"Загружено вакансий: {len(fetched.vacancies)} (страниц: {fetched.pages_loaded})."
        )
        entries, ai_errors = analyze_all(fetched.vacancies, provider, cfg)
        report = build_report(
            entries,
            mode="manual",
            provider=provider,
            source=fetched.source_url,
            ai_errors=ai_errors,
            fetch_info={
                "pages_loaded": fetched.pages_loaded,
                "total_on_portal": fetched.total,
                "vacancies_loaded": len(fetched.vacancies),
            },
        )
        save_success(report, cfg.report_path)
        self._report = report
        self.call_from_thread(self._log, f"[OK] Отчёт сохранён: {cfg.report_path}")
        self.call_from_thread(self._log_summary, report)
        if ai_errors:
            self.call_from_thread(self._log, f"[WARN] Пример ошибки ИИ: {ai_errors[0]}")
        self.call_from_thread(self._refresh_dashboard)
        self.call_from_thread(self._refresh_findings)

    def _log_summary(self, report: dict[str, Any]) -> None:
        stats = report["stats"]
        self._log(
            f"Вакансий: {stats['vacancies_in_report']}, замечаний: {stats['findings_total']}, "
            f"провайдер: {report['ai']['provider']}/{report['ai']['model']}"
        )

    @work(thread=True)
    def cmd_verify(self, path: str | None) -> None:
        cfg = self._cfg
        try:
            vacancies = load_vacancies(path, cfg)
        except Exception as exc:
            self.call_from_thread(self._log, f"[ОШИБКА] {exc}")
            return
        self.call_from_thread(self._log, f"Проверка файла: {path or cfg.sample_input} ({len(vacancies)} вакансий).")
        try:
            provider = create_provider(cfg, None)
        except AIUnavailable as exc:
            self.call_from_thread(self._log, f"[ОШИБКА] {exc}")
            return
        entries, ai_errors = analyze_all(vacancies, provider, cfg)
        report = build_report(
            entries,
            mode="verify",
            provider=provider,
            source=str(path or cfg.sample_input),
            ai_errors=ai_errors,
        )
        self._report = report
        self.call_from_thread(self._log, f"[OK] Проверочный отчёт сформирован (замечаний: {report['stats']['findings_total']}).")
        self.call_from_thread(self._refresh_dashboard)
        self.call_from_thread(self._refresh_findings)

    @work(thread=True)
    def cmd_resume(self, vacancy_id: str) -> None:
        cfg = self._cfg
        try:
            vacancies = load_vacancies(None, cfg)
            vacancy = find_vacancy(vacancies, vacancy_id)
            resume = json.loads(cfg.resume_path.read_text(encoding="utf-8"))
            provider = create_provider(cfg, None, strict=True)
            draft = draft_resume(vacancy, resume, provider, cfg)
        except Exception as exc:
            self.call_from_thread(self._log, f"[ОШИБКА] {exc}")
            return
        output = cfg.resume_draft_path
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(draft.rstrip() + "\n", encoding="utf-8")
        self.call_from_thread(self._log, f"[OK] Черновик резюма сохранён: {output}")

    # ---------- настройки ----------

    def _config_path(self) -> Path:
        value = self.query_one("#config_path", Input).value.strip()
        return Path(value) if value else DEFAULT_CONFIG_PATH

    def save_config(self) -> None:
        cfg = self._cfg
        raw = {
            "source_url": cfg.source_url,
            "schedule": cfg.schedule,
            "timezone": cfg.timezone,
            "max_vacancies": cfg.max_vacancies,
            "page_size": cfg.page_size,
            "max_pages": cfg.max_pages,
            "request_timeout": cfg.request_timeout,
            "retries": cfg.retries,
            "retry_backoff_seconds": cfg.retry_backoff_seconds,
            "ai": {
                "provider": cfg.ai_provider,
                "workers": cfg.ai_workers,
                "temperature": cfg.temperature,
                "max_chars_per_field": cfg.max_chars_per_field,
                "gigachat_model": cfg.gigachat_model,
                "ollama_model": cfg.ollama_model,
                "ollama_url": cfg.ollama_url,
            },
            "paths": {
                "report": _relative(cfg.report_path),
                "last_success": _relative(cfg.last_success_path),
                "run_status": _relative(cfg.run_status_path),
                "last_input": _relative(cfg.last_input_path),
                "sample_input": _relative(cfg.sample_input),
                "sample_report": _relative(cfg.sample_report),
                "resume": _relative(cfg.resume_path),
                "resume_draft": _relative(cfg.resume_draft_path),
            },
        }
        path = self._config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self._cfg = Config.load(path)
        self._log(f"[OK] Конфиг записан: {path}")
        self._refresh_config()
        self._refresh_dashboard()


def main() -> None:
    app = VacancyTUI()
    app.run()


if __name__ == "__main__":
    main()
