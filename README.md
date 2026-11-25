# Прозрачная вакансия

Прототип сервиса, который загружает вакансии Калининградской области (регион 39) с портала «Работа в России», проверяет, насколько понятно описаны условия работы, и сохраняет JSON-отчёт с конкретными уточнениями для редактора.

**Точка входа обработки:** `src/cli.py` (`python -m src.cli ...`). Настройка расписания — `config/config.json`, ключ `schedule`.

---

## Быстрый старт

Установите проект в окружение один раз — появятся команды `kantcod` (TUI) и `kantcod-cli` (консоль):

```bash
# из папки проекта
.venv/bin/pip install -e .        # Windows: .venv\Scripts\pip install -e .

kantcod                            # открыть TUI
kantcod-cli check                  # самопроверка
kantcod-cli run --ai rules         # загрузить вакансии и сохранить отчёт
kantcod-cli verify --ai rules --input data/sample/training_vacancies.json
```

После активации окружения (`source .venv/bin/activate`, Windows: `.venv\Scripts\Activate.ps1`) команды доступны просто как `kantcod` / `kantcod-cli`. Без установки работают `python -m src.tui` и `python -m src.cli ...`.

Запуск двойным кликом: `kantcod.bat` (Windows) или `kantcod.command` (macOS/Linux). В Linux-меню приложений появляется пункт «Прозрачная вакансия».

**Готово к передаче непрограммисту:** установка в один клик — `install.bat` (Windows) / `install.sh` (macOS/Linux); инструкция для пользователя — [docs/user_guide.md](docs/user_guide.md).

---

## Что делает сервис

1. **Рабочий режим** (`run`, `schedule`) — получает вакансии через `http://opendata.trudvsem.ru/api/v1/vacancies/region/39` постранично (`limit`/`offset`), анализирует и сохраняет отчёт. Ручной запуск — та же функция, что и по расписанию.
2. **Проверочный режим** (`verify`) — анализирует локальный JSON в формате ответа API (или список вакансий / объект `{"vacancy": ...}`) без обращения к порталу. Обрабатываются **все** переданные вакансии.
3. **Дополнительный сценарий** (`resume`) — черновик резюме под выбранную вакансию на основе вымышленного резюме соискателя.

Обрабатываются все вакансии, которые отдаёт источник (определять форму собственности работодателя не требуется). По умолчанию загружаются **2 страницы по 25 вакансий** = 50 вакансий.

### Устойчивость

- Повторные ID внутри одного прогона отбрасываются: в текущем отчёте всегда одна запись на ID (`stats.duplicates_skipped`).
- При недоступности API: 3 повтора с задержкой, затем ошибка в `data/reports/last_run.json`, ненулевой код выхода. **Последний успешный отчёт не перезаписывается**; копия также хранится в `report.last_success.json`.
- Запись отчёта атомарная (временный файл + `replace`), поэтому прерванный запуск не оставляет битый JSON.
- Ошибка ИИ на одной вакансии не роняет отчёт: для неё остаются правила, количество ошибок видно в `stats.ai_errors`.

---

## Установка

Python 3.10+ (проверено на 3.13).

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/Mac: source .venv/bin/activate
python -m pip install -r requirements.txt
python -m src.cli check       # самопроверка без сети и без ключей
python -m unittest discover -s tests -v
```

Зависимости: `requests`, `croniter`, `python-dotenv`.

---

## Настройки

Файл `config/config.json` (без секретов):

| Ключ | Значение по умолчанию | Что задаёт |
|---|---|---|
| `source_url` | `.../api/v1/vacancies/region/39` | URL источника |
| `schedule` | `0 9 * * *` | cron-расписание (ежедневно в 09:00) |
| `timezone` | `Europe/Kaliningrad` | часовой пояс для планировщика |
| `max_vacancies` | `50` | максимальное число вакансий за запуск |
| `page_size` | `25` | `limit` в запросе к API |
| `max_pages` | `2` | сколько страниц загружать |
| `request_timeout`, `retries`, `retry_backoff_seconds` | `20`, `3`, `1.0` | сеть и повторы |
| `ai.provider` | `auto` | `gigachat` / `ollama` / `rules` / `auto` |
| `ai.workers` | `4` | параллельные запросы к модели |
| `paths.*` | — | пути отчётов и учебных данных |

Переменные окружения переопределяют настройки: `VACANCY_SOURCE_URL`, `VACANCY_SCHEDULE`, `VACANCY_MAX`, `AI_PROVIDER`, `GIGACHAT_*`, `OLLAMA_*`. Скопируйте `.env.example` в `.env` и заполните его. **`.env` в репозиторий не попадает** (см. `.gitignore`).

---

## ИИ: модель, провайдер и шаг обработки

**Основной провайдер команды — GigaChat (Сбер), модель `GigaChat`** (переопределяется `GIGACHAT_MODEL`). Авторизация по `GIGACHAT_CLIENT_ID` + `GIGACHAT_CLIENT_SECRET` (scope `GIGACHAT_API_PERS`) через `https://ngw.devices.sberbank.ru:9443/api/v2/oauth`; токен кэшируется в памяти и обновляется. Можно задать готовый `GIGACHAT_ACCESS_TOKEN`.

**ИИ используется на отдельном шаге после извлечения фактов** (`src/analyzer.py` → `src/prompt.py`):

1. `src/facts.py` нормализует структурированные поля API и находит объективные пропуски/противоречия.
2. `src/prompt.py` передаёт модели компактный JSON полей вакансии и уже найденные замечания.
3. Модель возвращает **новые** замечания — неоднозначные формулировки и противоречия (например, «гибкий график» без дней и смен; «оплата по результатам» без чисел; адрес только до уровня области).
4. `src/analyzer.py` проверяет каждое замечание модели: цитата должна дословно присутствовать в указанном поле, для противоречия требуются два исходных значения, темы и поля ограничены справочником. Выдуманные цитаты и повторы отбрасываются. Только после валидации замечание попадает в отчёт.

Промпт прямо запрещает модели выдумывать факты и делать выводы о нарушении законодательства; рекомендация всегда звучит как просьба уточнить конкретные сведения.

### Как запустить проверочный режим жюри без покупки аккаунта

GigaChat требует регистрации, поэтому для жюри предусмотрен **бесплатный локальный провайдер Ollama без аккаунта и ключей**:

```bash
# 1. Установить Ollama с https://ollama.com
# 2. Скачать небольшую модель (поддерживает русский язык):
ollama pull qwen2.5:3b
# 3. Запустить проверочный режим:
python -m src.cli verify --ai ollama \
  --input data/sample/training_vacancies.json \
  --output data/reports/report_verify_ai.json
```

Если Ollama установлена, `--ai auto` выберет её автоматически при отсутствии ключей GigaChat. Ручной запуск с реальным API: `python -m src.cli run --ai ollama`.

Режим `--ai rules` отключает модель и оставляет только детерминированные правила — он нужен для smoke-тестов и воспроизводимости формата. Пример отчёта `data/reports/report_example.json` создан именно в этом режиме, чтобы его можно было открыть без ключей; чтобы получить отчёт с ИИ-замечаниями, перезапустите ту же команду с `--ai gigachat` или `--ai ollama`.

---

## Команды

Полная последовательность с виртуальным окружением (Windows PowerShell):

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m src.cli check
python -m src.cli run --ai rules
python -m src.cli verify --ai ollama --input data/sample/training_vacancies.json
python -m src.cli schedule --now
```

Для Linux/macOS вместо активации используйте `source .venv/bin/activate`. Дальше — отдельные команды с пояснениями:

```bash
# 0) Виртуальное окружение (один раз, перед всеми командами ниже)
python -m venv .venv
# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# Linux / macOS:
# source .venv/bin/activate
python -m pip install -r requirements.txt

# 1) Ручной запуск: загрузка 2 страниц API -> отчёт в data/reports/report.json
python -m src.cli run

# Ограничения и другой файл
python -m src.cli run --max 20 --pages 2 --output data/reports/my_report.json

# По расписанию (cron из config/config.json); --now — сразу выполнить первый запуск
python -m src.cli schedule --now

# Проверочный режим: локальный JSON, без обращения к порталу
python -m src.cli verify --input data/sample/training_vacancies.json \
                         --output data/reports/report_verify.json \
                         --ai ollama
# --strict-ai — не допускать тихий переход на rules

# Самопроверка формата (без сети и без ИИ)
python -m src.cli check

# Доп. сценарий: черновик резюме под вакансию из последней загрузки
python -m src.cli resume --vacancy-id <ID> --ai ollama
python -m src.cli resume --vacancy-id train-003 --input data/sample/training_vacancies.json --ai ollama
```

Подсказка: после `run` исходные вакансии сохраняются в `data/reports/last_input.json` — можно передать этот файл в `verify` или `resume`.

---

## TUI — кроссплатформенный интерфейс (Textual)

Современный TUI на Python [Textual](https://textual.textualize.io/) — работает в Windows, Linux и macOS:

```bash
# Windows: .venv\Scripts\python -m src.tui
.venv/bin/python -m src.tui
```

Что умеет панель:

- **Обзор** — сводка последнего отчёта (дата, режим, вакансии, по видам замечаний, провайдер) и кнопки:
  - *Запустить сейчас* — загрузка с портала + анализ (работает в фоне, UI не замораживается);
  - *Проверить файл* — проверка локального JSON без портала (поле с путём, по умолчанию `data/sample/training_vacancies.json`);
  - *Черновик резюма* — сценарий `resume` под указанную вакансию (поле ID);
  - *Открыть отчёт* — открытие отчёта в системном приложении.
- **Замечания** — детали каждого замечания из отчёта (тема, поле, суть, рекомендация, цитата).
- **Настройки** — пути, cron, лимиты; изменения сохраняются в `config/config.json` («Сохранить config.json»), путь отчёта можно менять без перезапуска.
- **Лог** — история действий и ошибок.

Выход: `Ctrl+Q` (или крестик окна). Для «Запустить сейчас» нужен ИИ-провайдер — см. выше (GigaChat или Ollama).

---

## Формат отчёта

`data/reports/*.json` — объект:

```json
{
  "generated_at": "2026-11-24T20:16:47+00:00",
  "mode": "verify",
  "source": "data/sample/training_vacancies.json",
  "ai": {"provider": "ollama", "model": "qwen2.5:3b"},
  "stats": {
    "vacancies_in": 5, "vacancies_in_report": 5, "duplicates_skipped": 0,
    "vacancies_with_findings": 2, "findings_total": 7,
    "by_kind": {"omission": 5, "contradiction": 2}, "ai_errors": 0
  },
  "fetch": {"pages_loaded": 2, "total_on_portal": 4232, "vacancies_loaded": 50},
  "vacancies": [
    {
      "id": "train-003",
      "url": "https://trudvsem.ru/vacancy/card/...",
      "findings": [
        {
          "kind": "contradiction",
          "topic": "оплата труда",
          "field": "salary",
          "quote": "до 30000 ↔ от 40000",
          "values": ["до 30000", "от 40000"],
          "issue": "Указанный минимум оплаты выше текстовой верхней границы.",
          "recommendation": "Сверьте текст вакансии и поле salary_min, укажите непротиворечивый диапазон."
        }
      ]
    }
  ]
}
```

- `vacancies` — по одному объекту на каждую входную вакансию; если замечаний нет, `findings: []`.
- `kind`: `omission` (пропуск), `ambiguity` (неоднозначность), `contradiction` (противоречие).
- `topic` — одна из семи тем: название должности, обязанности, требования, оплата труда, график работы, место работы, тип занятости.
- `field` — имя исходного поля API (например, `schedule`, `salary`, `requirement.education`, `addresses.address[].location`).
- `quote` — дословная цитата/значение из поля. Для пропуска `quote` всегда пустой. Для противоречия оба исходных значения также дублируются в `values`.
- `issue` — суть проблемы; `recommendation` — что именно уточнить.

Важно: если конкретные сведения есть в структурированном поле, отсутствие их повторения в тексте описания **не считается** проблемой и не попадает в отчёт.

Пример реального отчёта на учебных данных: [`data/reports/report_example.json`](data/reports/report_example.json). Учебный набор: [`data/sample/training_vacancies.json`](data/sample/training_vacancies.json).

---

## Дополнительный сценарий (по желанию)

`src/cli.py resume` помогает **соискателю**: берёт вымышленное резюме `data/sample/resume.json` (опыт, навыки, образование, контакты) и формулировки вакансии из API (название, обязанности, требования) и просит ИИ собрать черновик резюме с разделами «Цель / Опыт / Навыки / Образование / Почему подхожу». Модель не имеет права добавлять опыт, которого нет в исходном резюме. Результат — Markdown в `data/reports/resume_draft.md`.

---

## Структура репозитория

```
src/cli.py            точка входа: run / verify / schedule / check / resume
src/tui.py            TUI-панель на Textual (запуск: python -m src.tui)
src/config.py         конфигурация и env-переопределения
src/fetcher.py        постраничная загрузка API, повторы, ошибки
src/facts.py          нормализация полей, пропуски и проверяемые противоречия
src/prompt.py         промпт и подготовка данных для ИИ
src/analyzer.py       вызов ИИ, валидация и дедупликация замечаний
src/ai/*              провайдеры: GigaChat, Ollama, rules-only, factory
src/report.py         сборка и атомарная запись отчёта
src/resume.py         доп. сценарий черновика резюме
config/config.json    URL, расписание, лимиты, пути
data/sample/*         учебные данные и вымышленное резюме
data/reports/*        пример отчёта (остальные файлы создаются при запуске)
tests/test_pipeline.py тесты формата, правил, валидации ИИ и пагинации
```

## Видео

До сдачи добавить демо-ролик (до 3 минут) в `docs/demo.mp4`: показать `python -m src.cli run`, место вызова ИИ (`src/analyzer.py` / `src/prompt.py`) и результат в `data/reports/report.json`. Файл должен открываться у жюри без запроса доступа. Готовый сценарий записи — [`docs/demo_script.md`](docs/demo_script.md).

## Участники

Заполнить перед сдачей: ФИО, роль, вклад каждого участника (например: API и расписание; правила и валидация; промпт и GigaChat; тесты и README).
