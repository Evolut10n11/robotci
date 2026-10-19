# Эксперимент: обученная LeRobot Diffusion-политика в CPU PushT

Этот профиль проверяет реальное исполнение checkpoint `lerobot/diffusion_pusht`
в `gym_pusht/PushT-v0` и детерминированное сравнение записанных эпизодов.
Последовательность: эталон, неизменённый повтор, изменение применяемых действий,
сравнение успешности и награды. Синтетические unit-test fixtures не считаются
результатами физической симуляции.

Пользовательские команды PowerShell, описание всех флагов и кодов завершения
находятся в [руководстве LeRobot](../../docs/lerobot.md).
Фактические измерения и платформа испытаний фиксируются в
[протоколе от 19 октября 2026](../../docs/validation/lerobot-pusht-2026-10-19.md).
Этот файл описывает процедуру и не обещает заранее выбранный результат
на новой машине.

## Сохранённая внутренняя проверка

Результаты на seeds `1000`, `1001`, `1002` от 19 октября 2026:

| Запуск | Успешные эпизоды | Mean max reward | Шаги по seeds |
| --- | ---: | ---: | --- |
| [Baseline](evidence/2026-10-19/baseline/result.json) | 3 / 3 | 1.0 | 161, 212, 128 |
| [Неизменённый повтор](evidence/2026-10-19/unchanged/result.json) | 3 / 3 | 1.0 | 161, 212, 128 |
| [Удержание позиции](evidence/2026-10-19/degraded/result.json) | 0 / 3 | 0.08549931 | 300, 300, 300 |

CLI вернул `PASS`/код 0 для [повтора](evidence/2026-10-19/reports/unchanged.md)
и `REGRESSION`/код 4 для [изменённых действий](evidence/2026-10-19/reports/degraded.md).
Исходные JSON и траектории сохранены с
[manifest SHA-256](evidence/2026-10-19/manifest.json). Побайтовая идентичность
всех повторных траекторий не заявляется: отдельные промежуточные награды имеют
различия в последних разрядах. Подробная проверка этих различий отражена
в датированном протоколе. Это измерения одного небольшого внутреннего набора.

## Изолированная установка

Работайте из корня checkout RobotCI. Требуется Python 3.12, профиль CPU x86-64.
ROS, Docker и GPU не используются. Зависимости эксперимента ставятся в отдельную
`.venv-lerobot`; установка `pip install -e .` в обычное core-окружение не
добавляет LeRobot или Torch.

PowerShell:

```powershell
py -3.12 -m venv .venv-lerobot
.\.venv-lerobot\Scripts\python.exe -m pip install -r experiments/lerobot_pusht/requirements.txt
.\.venv-lerobot\Scripts\python.exe -m pip install -e .
$RobotCIPushT = Join-Path $PWD ".venv-lerobot\Scripts\robotci.exe"
& $RobotCIPushT lerobot fetch .robotci/lerobot-checkpoints/diffusion-pusht
```

Linux:

```bash
python3.12 -m venv .venv-lerobot
.venv-lerobot/bin/python -m pip install -r experiments/lerobot_pusht/requirements.txt
.venv-lerobot/bin/python -m pip install -e .
.venv-lerobot/bin/robotci lerobot fetch .robotci/lerobot-checkpoints/diffusion-pusht
```

Если Linux-установка upstream-зависимостей собирает `evdev` из исходников,
нужен `gcc`. На Windows этот Linux-компонент не требуется.

Точные рекомендуемые версии находятся в [requirements.txt](requirements.txt):
LeRobot 0.3.3, Torch 2.7.1+cpu, Torchvision 0.22.1+cpu, gym-pusht 0.1.5,
Gymnasium 0.29.1 и Pymunk 6.11.1. У исходного checkpoint нормализация хранится
в model state; runner требует строгой загрузки ключей и конечных статистик,
а не пропускает их ради совместимости с новой версией библиотеки.

## Происхождение модели

`fetch` загружает около 1,05 ГБ только по явной команде. Источник закреплён в
[`robotci/lerobot_checkpoint.py`](../../robotci/lerobot_checkpoint.py):

- Репозиторий: [`lerobot/diffusion_pusht`](https://huggingface.co/lerobot/diffusion_pusht/tree/84a7c23178445c6bbf7e1a884ff497017910f653).
- Revision: `84a7c23178445c6bbf7e1a884ff497017910f653`.
- `config.json`: 1509 байт, SHA-256 `d391a7bf488accd1c26b2043482f0060b0855b1ec236f3d7358486918472c0a5`.
- `model.safetensors`: 1050862408 байт, SHA-256 `995d14d35db57d95c35ad9704c3d79c8612b7bc45f3877e5c46c2cdc516856a8`.

Manifest `robotci-checkpoint.json` сохраняется после проверки скачанных файлов.
Существующий каталог проверяется без перезаписи. Каждый запуск снова проверяет
manifest, размеры и хеши до импорта модели. Само исполнение использует offline
режим Hugging Face и `local_files_only=True`.

## Порядок испытания

Для трёх запусков используются seeds `1000`, `1001`, `1002` в том же порядке,
300 шагов на эпизод, один поток Torch и 10 шагов денойзинга. В исходном config
указано 100 шагов денойзинга; выбранный здесь режим отличается и не является
воспроизведением upstream-бенчмарка.

Команды Linux; эквивалентный полный PowerShell-пример есть в
[руководстве](../../docs/lerobot.md#4-записать-эталон-и-неизменённый-повтор):

```bash
.venv-lerobot/bin/robotci lerobot run .robotci/lerobot-checkpoints/diffusion-pusht --output .robotci/lerobot-pusht/baseline --seed 1000 --seed 1001 --seed 1002 --max-steps 300 --inference-steps 10 --threads 1
.venv-lerobot/bin/robotci lerobot run .robotci/lerobot-checkpoints/diffusion-pusht --output .robotci/lerobot-pusht/unchanged --seed 1000 --seed 1001 --seed 1002 --max-steps 300 --inference-steps 10 --threads 1
.venv-lerobot/bin/robotci lerobot compare .robotci/lerobot-pusht/baseline .robotci/lerobot-pusht/unchanged --output .robotci/lerobot-pusht/reports/unchanged.json --markdown .robotci/lerobot-pusht/reports/unchanged.md
```

Сначала разберите неизменённый повтор. При `INFRA_ERROR` или `REGRESSION`
этот набор результатов пока не подтверждает пригодность сравнения изменений.
Baseline должен содержать хотя бы один успешный эпизод. Когда контроль
неизменённой политики пройден, запишите кандидат с удержанием позиции:

```bash
.venv-lerobot/bin/robotci lerobot run .robotci/lerobot-checkpoints/diffusion-pusht --output .robotci/lerobot-pusht/hold --seed 1000 --seed 1001 --seed 1002 --max-steps 300 --inference-steps 10 --threads 1 --action-scale 0
.venv-lerobot/bin/robotci lerobot compare .robotci/lerobot-pusht/baseline .robotci/lerobot-pusht/hold --max-success-rate-drop 0 --max-reward-drop 0.05 --output .robotci/lerobot-pusht/reports/hold.json --markdown .robotci/lerobot-pusht/reports/hold.md
```

`--action-scale 0` меняет действительно применяемое действие:
`action = clip(agent_pos + action_scale * (policy_action - agent_pos), 0, 512)`.
Нулевой масштаб задаёт текущую позицию как цель. Политика продолжает выполнять
инференс, а лог содержит её предсказание и переданную в среду float32-команду.
Награда получается из PushT. Наличие регрессии определяется по эпизодам,
а не по названию каталога или значению флага.

Все каталоги `run --output` должны быть новыми. Сохранение через
`compare --output` и `--markdown` также требует новых, разных путей файлов.
После неудачной попытки выбирайте новый путь и сохраняйте её диагностику.

## Что считается результатом

| Объект | Содержание |
| --- | --- |
| `result.json` | `schema_version: 1`, статус, checkpoint и хеши, protocol, episode records, пересчитанные метрики |
| `episode-1000.json` и остальные seeds | Начальное наблюдение, позиции, предсказанные/применённые действия, награды, окончания и хеши изображений |
| JSON/Markdown comparison | Совместимость входов, baseline/candidate metrics, пороги, `PASS`/`REGRESSION`/`INFRA_ERROR` |

`run` возвращает код 0 для `COMPLETED`, в том числе с нулём успехов. Ошибка
модели, зависимости, веса или записи даёт `INFRA_ERROR`/код 3; частично
собранные эпизоды не становятся валидным итогом для сравнения.

`compare` возвращает 0 для `PASS`, 4 для `REGRESSION`, 3 для `INFRA_ERROR`.
Пороги по умолчанию: нулевое падение success rate и не более 0,05 абсолютного
падения mean max reward. Граничное равенство проходит. Время исполнения
и инференса не определяет вердикт.

Сравнивается весь protocol: среда и параметры наблюдения, seeds и порядок,
лимит шагов, правила seed/action, CPU/float32, потоки Torch, Python, ОС,
архитектура CPU и фактические версии 17 ML/симуляторных пакетов. Другой
protocol даёт `INFRA_ERROR`; для него нужен отдельный эталон. Число шагов
инференса и масштаб действий находятся в policy и могут отличаться.

Повтор с теми же настройками не обещает побайтово одинаковых JSON: время
измеряется заново, а численные награды могут отличаться в последних разрядах.
Детерминированным является вердикт для одинаковых валидированных входов и
порогов. Различия повторов, проверка фактических хешей trace-файлов и допустимая
численная погрешность диагностической проверки фиксируются в протоколе
испытаний отдельно от порогов gate.

SHA-256 каждой trajectory записан в результате. Офлайн-команда сравнения
проверяет его формат, но не открывает соседний файл и не подтверждает авторство
артефакта. Храните исходные trace-файлы вместе с результатом. RGB-кадры заменены
хешами; эти JSON не являются видео или Nav2 replay и пока не открываются в 3D viewer.

## Граница эксперимента

Здесь исполняется одна готовая Diffusion-политика в одной симуляторной задаче.
Metadata preflight ACT/Diffusion/SmolVLA и импорт статической геометрии остаются
отдельными возможностями. Эксперимент не добавляет управление физическими
SO-100/SO-101, калибровку, обучение, исполнение ACT/SmolVLA или production-adapter
манипулятора. Внешние пилоты M8 и проверка на оборудовании имеют свои критерии.
