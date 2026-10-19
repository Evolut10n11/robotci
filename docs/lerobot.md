# LeRobot в RobotCI

RobotCI проверяет совместимость локальных метаданных LeRobot и предоставляет
экспериментальный цикл исполнения обученной Diffusion-политики в симуляции PushT:
скачать закреплённые веса, записать повторяемые эпизоды, сравнить результат
изменения с эталоном и сохранить отчёт для CI.

## Три уровня проверки

| Команда | Что проверяется | Граница результата |
| --- | --- | --- |
| `robotci model inspect` | Структура URDF/MJCF или явная каталожная модель из YAML | `scope: static_reference`; CLI не читает файлы мешей и не проверяет управление или динамику |
| `robotci lerobot inspect` | Метаданные датасета и явная feature-схема ACT, Diffusion или SmolVLA | `scope: metadata_only`; `VALID` относится только к проверенным декларациям |
| `robotci lerobot run` и `compare` | Реальное исполнение закреплённой Diffusion-политики в CPU PushT, метрики эпизодов и регрессии | Отдельные артефакты `lerobot_pusht_evaluation` и `lerobot_pusht_comparison`; экспериментальная симуляция |

Описание геометрии не выбирает контроллер, а совпадение размеров датасета
не доказывает качество политики. Для третьего уровня нужны настоящие веса
и отдельное окружение с ML-зависимостями.

## 1. Проверить метаданные без GPU, ROS и оборудования

Команда использует Python core RobotCI. Установка LeRobot, PyTorch, FFmpeg и
доступ к Hugging Face не нужны. Пример из репозитория запускается и в PowerShell:

```powershell
robotci lerobot inspect examples/lerobot-preflight/dataset --policy examples/lerobot-preflight/policy --robot-type so101_follower --fps 30
robotci lerobot inspect examples/lerobot-preflight/dataset --policy examples/lerobot-preflight/policy --json
```

Пример намеренно содержит только **синтетические метаданные** SO-101 и ACT.
Это не демонстрации физического робота и не готовая политика управления.

Первый аргумент принимает директорию датасета или непосредственно `meta/info.json`.
`--policy` принимает `config.json` сохранённой политики или содержащую его папку.
URL и Hub ID автоматически не скачиваются. `--robot-type` и `--fps` являются
необязательными ожиданиями пользователя, а не выведенными свойствами политики.

### Поддерживаемые метаданные

| Вход | Что проверяется |
| --- | --- |
| LeRobotDataset v2.1 / v3.0 | Версия, FPS, счётчики, структура features, типы и размерности |
| `observation.state`, `action` | Положительные размеры, имена координат, соответствие явной схеме политики |
| Камеры | Наличие требуемых ключей и размеры, перевод HWC в CHW по именам осей |
| ACT / Diffusion / SmolVLA | Явные `input_features` и `output_features` в сохранённом policy config |
| Ожидания запуска | Совпадение `robot_type` и FPS, если они заданы флагами |
| Воспроизводимость | SHA-256 точных байтов каждого прочитанного JSON |

Проверяются требования поддерживаемого подмножества feature-схем:

- ACT требует хотя бы один вход `VISUAL` или `ENV`.
- Diffusion дополнительно требует именно `observation.state` с типом `STATE`;
  все визуальные входы должны иметь одинаковые размеры.
- SmolVLA требует `observation.state` с типом `STATE` и хотя бы одну камеру
  `VISUAL`. При `empty_cameras > 0` результат `UNSUPPORTED`, поскольку такие
  камеры добавляются программно и не описаны проверяемой входной схемой.

Неизвестная версия датасета, неподдержанный тип политики или отсутствие
явной pretrained feature-схемы не получают положительного результата.
Старые сгруппированные `names` вида `{"motors": [...]}` помечаются
`UNSUPPORTED`; поддерживаются плоские списки имён и `null` для числовых features.
Название робота не выбирает 3D-модель: `so101_follower` нельзя автоматически
подменять Panda из каталога. Для геометрии нужен соответствующий URDF/MJCF.

### Результат preflight для CI

JSON имеет `schema_version: 1`, `scope: metadata_only`, `status`, список `issues`
с кодом/путём/сообщением, сведения о входах и хеши. Исходники не переписываются,
загрузка в Hub, импорт Python-конфигураций и подключение к serial-портам отсутствуют.

| Статус | Код завершения | Значение |
| --- | ---: | --- |
| `VALID` | 0 | Проверенные метаданные согласованы |
| `INVALID` | 3 | Неверный файл, метаданные или несовместимые features/ожидания |
| `UNSUPPORTED` | 3 | Запрошенная схема вне проверяемого подмножества |

Это отдельный preflight. Статусы не записываются как Nav2 `PASS`/`REGRESSION` и не
означают, что датасет существует целиком или робот успешно выполнил задачу.
При неправильном синтаксисе командной строки Typer может вернуть код 2.

Не проверяются: Parquet-строки, MP4-кадры, временная синхронизация, статистика
нормализации, веса, преобразования процессоров, калибровка и физические пределы.
При использовании rename-map, resize или другой обработки сначала нужна явная
схема её выхода; текущая команда не исполняет такие преобразования. Совпадение
размеров не доказывает совпадение единиц измерения или семантики суставов.

## 2. Подготовить отдельное окружение для CPU PushT

Сценарий использует Python **3.12**, CPU и отдельное виртуальное окружение для
Linux/Windows x86-64. ROS, Docker и GPU не требуются. Обычное core-окружение
RobotCI сохраняйте отдельно: оно нужно для лёгких проверок, сравнения и Nav2-инструментов.

Команды ниже выполняются из корня checkout RobotCI. В PowerShell не требуется
активировать venv или менять политику исполнения скриптов:

```powershell
py -3.12 -m venv .venv-lerobot
.\.venv-lerobot\Scripts\python.exe -m pip install -r experiments/lerobot_pusht/requirements.txt
.\.venv-lerobot\Scripts\python.exe -m pip install -e .
$RobotCIPushT = Join-Path $PWD ".venv-lerobot\Scripts\robotci.exe"
& $RobotCIPushT lerobot run --help
```

Linux:

```bash
python3.12 -m venv .venv-lerobot
.venv-lerobot/bin/python -m pip install -r experiments/lerobot_pusht/requirements.txt
.venv-lerobot/bin/python -m pip install -e .
.venv-lerobot/bin/robotci lerobot run --help
```

[requirements.txt](../experiments/lerobot_pusht/requirements.txt) закрепляет
совместимый профиль: `lerobot[pusht]==0.3.3`, `torch==2.7.1+cpu`,
`torchvision==0.22.1+cpu`, `gym-pusht==0.1.5`, `gymnasium==0.29.1`,
`pymunk==6.11.1` и остальные перечисленные зависимости. CPU-колёса PyTorch
не требуют скачивать CUDA-библиотеки. Pymunk закреплён на версии с API,
которое использует выбранная версия gym-pusht.

Старый checkpoint хранит статистику нормализации в model state. Runner загружает
его с проверкой всех ключей и конечности этих статистик через LeRobot 0.3.3.
Произвольное обновление LeRobot может нарушить этот контракт.

На Linux установка upstream-зависимостей иногда собирает `evdev` из исходников;
если pip начинает такую сборку, в окружении требуется C-компилятор `gcc`.
Это Linux-зависимость; для Windows `evdev` не нужен. Фактическая платформа
испытаний и выявленные ограничения указаны в
[протоколе проверки](validation/lerobot-pusht-2026-10-19.md).

## 3. Явно скачать и проверить checkpoint

```powershell
& $RobotCIPushT lerobot fetch .robotci/lerobot-checkpoints/diffusion-pusht
```

Команда обращается к Hugging Face и скачивает около **1,05 ГБ**.
Поддерживается один источник:
[`lerobot/diffusion_pusht`](https://huggingface.co/lerobot/diffusion_pusht/tree/84a7c23178445c6bbf7e1a884ff497017910f653),
revision `84a7c23178445c6bbf7e1a884ff497017910f653`.

| Файл | Размер в байтах | SHA-256 |
| --- | ---: | --- |
| `config.json` | 1509 | `d391a7bf488accd1c26b2043482f0060b0855b1ec236f3d7358486918472c0a5` |
| `model.safetensors` | 1050862408 | `995d14d35db57d95c35ad9704c3d79c8612b7bc45f3877e5c46c2cdc516856a8` |

`fetch` проверяет точный размер и SHA-256 каждого файла и сохраняет
`robotci-checkpoint.json`. Уже существующий каталог только проверяется:
совпадающие файлы переиспользуются, изменённые или неполные вызывают ошибку.
Команда не заменяет веса в существующем checkpoint. `--json` выводит manifest.

При каждом `run` проверка закреплённых байтов выполняется до загрузки модели.
Дальнейший запуск локальный: Hub работает в offline-режиме, модель читается
с `local_files_only=True`. Поддержка произвольного checkpoint, другого типа
политики или автоматического скачивания во время `run` не заявляется.

## 4. Записать эталон и неизменённый повтор

В обоих запусках явно задаём одинаковые seeds, лимит шагов и число CPU-потоков.
Каждый `--output` должен указывать на **новый** каталог.

```powershell
& $RobotCIPushT lerobot run .robotci/lerobot-checkpoints/diffusion-pusht --output .robotci/lerobot-pusht/baseline --seed 1000 --seed 1001 --seed 1002 --max-steps 300 --inference-steps 10 --threads 1
& $RobotCIPushT lerobot run .robotci/lerobot-checkpoints/diffusion-pusht --output .robotci/lerobot-pusht/unchanged --seed 1000 --seed 1001 --seed 1002 --max-steps 300 --inference-steps 10 --threads 1
& $RobotCIPushT lerobot compare .robotci/lerobot-pusht/baseline .robotci/lerobot-pusht/unchanged --output .robotci/lerobot-pusht/reports/unchanged.json --markdown .robotci/lerobot-pusht/reports/unchanged.md
$LASTEXITCODE
```

Код `0` у **run** означает, что все эпизоды выполнены и записан валидный
`COMPLETED`-артефакт. Это возможно и при нулевой успешности. Проверку качества
выполняет **compare**; эталон с нулём успешных эпизодов получает `INFRA_ERROR`.

Неизменённый повтор нужен, чтобы сначала проверить пригодность эталона и
стабильность сравнения в своём окружении. Если первое сравнение возвращает
`INFRA_ERROR` или `REGRESSION`, разберите входы и результаты до оценки изменения.
Переименование неудачного результата в baseline или ручное исправление summary
не делает его пригодным эталоном: метрики пересчитываются по эпизодам.

В примере выбрано **10 шагов денойзинга** вместо 100, указанных в исходном
[`config.json`](https://huggingface.co/lerobot/diffusion_pusht/blob/84a7c23178445c6bbf7e1a884ff497017910f653/config.json).
Это ускоряет выбранный CPU-сценарий за счёт изменения режима инференса;
его качество надо измерять. Эти запуски не воспроизводят опубликованный
upstream-бенчмарк. Три seeds — небольшой контрольный набор, а не оценка
надёжности на всей задаче.

## 5. Изменить реальные действия и проверить регрессию

Следующий контроль оставляет checkpoint и протокол окружения прежними,
но меняет действия, передаваемые симулятору:

```powershell
& $RobotCIPushT lerobot run .robotci/lerobot-checkpoints/diffusion-pusht --output .robotci/lerobot-pusht/hold --seed 1000 --seed 1001 --seed 1002 --max-steps 300 --inference-steps 10 --threads 1 --action-scale 0
& $RobotCIPushT lerobot compare .robotci/lerobot-pusht/baseline .robotci/lerobot-pusht/hold --max-success-rate-drop 0 --max-reward-drop 0.05 --output .robotci/lerobot-pusht/reports/hold.json --markdown .robotci/lerobot-pusht/reports/hold.md
$LASTEXITCODE
```

При `--action-scale 1` в среду передаётся предсказанная политикой целевая позиция.
При `0` целевой становится текущая измеренная позиция агента: управление
удерживает её вместо выполнения предсказанного смещения. В обоих случаях
действует одинаковое ограничение координат `[0, 512]`; в траектории записаны
предсказанное и фактически переданное действие. Инференс продолжает выполняться.

Это изменение поведения внутри симуляции, а не подстановка плохой награды
в готовый JSON. Вердикт зависит от измеренных эпизодов и заданных порогов;
команда не назначает `REGRESSION` только по значению `action_scale`.

### Параметры запуска и сравнения

| Параметр | Значение по умолчанию | Смысл |
| --- | --- | --- |
| `run --seed` | 1000, 1001, 1002 | Флаг повторяется для каждого уникального seed; порядок сохраняется |
| `run --max-steps` | 300 | Лимит одного эпизода; CLI допускает 1–1000 |
| `run --inference-steps` | 10 | Число шагов денойзинга DDPM; CLI допускает 1–100 |
| `run --action-scale` | 1.0 | Масштаб смещения от текущей позиции к предсказанной, от 0 до 1 |
| `run --threads` | 1 | Число CPU-потоков Torch; CLI допускает 1–32 |
| `compare --max-success-rate-drop` | 0.0 | Допустимое абсолютное падение доли успешных эпизодов |
| `compare --max-reward-drop` | 0.05 | Допустимое абсолютное падение средней максимальной награды |

Обе метрики лежат в `[0, 1]`. Порог успешности `0.05` означает пять процентных
пунктов; порог награды `0.05` означает 0,05 единицы награды, а не относительное
изменение на 5%. Падение строго больше порога даёт `REGRESSION`; равенство
порогу проходит. Достаточно ухудшения одной из двух метрик. Время выполнения
и инференса присутствует в отчёте для диагностики и не влияет на вердикт.

## Контракт результатов и совместимость

В новом каталоге запуска сохраняются `result.json` и `episode-1000.json`,
`episode-1001.json`, `episode-1002.json` для выбранного примера. Результат содержит
источник и хеши checkpoint, параметры инференса, полный протокол и список эпизодов.
Для каждого эпизода сохраняются seed, число шагов, успех, `terminated`/`truncated`,
максимальная/финальная/суммарная награда, время и SHA-256 JSON-траектории.

Траектория хранит позиции, предсказанные и применённые действия, награды,
флаги окончания и хеши RGB-наблюдений. Сами RGB-кадры и видео в неё не входят.
Это формат `lerobot_pusht_trajectory`, отдельный от Nav2 replay;
команда `robotci view` пока не визуализирует такие файлы.

Сравнение требует полного совпадения `protocol`:

- Среда `gym_pusht/PushT-v0`, наблюдения `pixels_agent_pos`, изображение
  `[3, 96, 96]`, частота управления 10 Гц и лимит шагов.
- Тот же упорядоченный список seeds, повторная инициализация Python, NumPy,
  Torch и среды перед каждым эпизодом.
- CPU, `float32`, детерминированные алгоритмы Torch и число его потоков.
- Версия Python, строка платформы, архитектура CPU и фактические версии
  17 пакетов: `lerobot`, `torch`, `torchvision`, `diffusers`, `gym-pusht`,
  `gymnasium`, `pymunk`, `numpy`, `pygame`, `shapely`, `opencv-python`,
  `safetensors`, `scipy`, `scikit-image`, `opencv-python-headless`, `draccus`, `einops`.
- Версия правила преобразования действий и любые дополнительные поля протокола.

Изменение checkpoint, числа шагов инференса или масштаба действий относится
к `policy` и допустимо для сравнения. Сам CLI сейчас исполняет только закреплённый
checkpoint. Обновление зависимостей, другая платформа, число потоков или порядок
seeds требуют нового совместимого эталона. Файл requirements закрепляет
перечисленные в нём зависимости; фактические версии остальных зависимостей
также записываются в протокол. Это не обещание одинаковой физики на любых машинах.

Повтор с теми же настройками не обещает побайтово одинаковых JSON: время
измеряется заново, а численные награды могут отличаться в последних разрядах.
Детерминированным является вердикт для одинаковых валидированных входов и
порогов. Точные различия повторов и диагностическая погрешность проверок
траекторий фиксируются в протоколе испытаний отдельно от порогов gate.

Офлайн-reader использует только стандартную библиотеку Python, ограничивает
JSON 4 МиБ и отклоняет повторяющиеся ключи, NaN/Infinity, неполные эпизоды,
несогласованные флаги, награды и хеши неверного формата. Метрики пересчитываются
из эпизодов; поля summary не являются основанием вердикта. Сравнение проверяет
формат `trajectory_sha256`, но **не открывает сами траектории** и не удостоверяет
авторство входного JSON. Храните исходные результаты и траектории вместе.

`compare` можно выполнять в обычном core-окружении без LeRobot/PyTorch,
передавая каталоги запусков или отдельные `result.json`. `--json` печатает
машиночитаемый отчёт, `--output` сохраняет новый JSON, `--markdown` — новый
Markdown. Пути двух отчётов должны отличаться; существующие файлы не заменяются.
После неудачного запуска также выбирайте новый `--output`, чтобы сохранить
диагностику предыдущей попытки.

| Команда | Код | Значение |
| --- | ---: | --- |
| `fetch` | 0 | Закреплённые файлы успешно скачаны или повторно проверены |
| `run` | 0 | `COMPLETED`: эпизоды выполнены; успешность может быть нулевой |
| `compare` | 0 | `PASS`: совместимые результаты укладываются в пороги |
| `compare` | 4 | `REGRESSION`: превышен хотя бы один порог ухудшения |
| `fetch` / `run` / `compare` | 3 | `INFRA_ERROR`: ошибка входов, окружения, весов, записи или совместимости |

При неправильном синтаксисе командной строки Typer может вернуть код 2.
Ошибка среды или модели не превращается в неуспешный эпизод: результат имеет
`INFRA_ERROR`, при возможности сохраняет завершённые эпизоды и причину ошибки
и не допускается к регрессионному сравнению.

## Область готовности

Реализован экспериментальный цикл для одного закреплённого Diffusion checkpoint
и одной задачи PushT. ACT/SmolVLA доступны только в metadata preflight.
Подключение физических SO-100/SO-101, камер и serial-портов, калибровка,
обучение, произвольные manipulation-adapters и интеграция PushT с Nav2/3D replay
в него не входят. Запуск не требует прикладывать навигационные метрики
к задаче манипуляции: используется собственный версионированный контракт.

[Описание эксперимента](../experiments/lerobot_pusht/README.md) содержит
порядок повторов и контроль изменения действий.
[Протокол от 19 октября 2026](validation/lerobot-pusht-2026-10-19.md)
отделяет фактические измерения от тестовых fixtures и фиксирует ограничения.
Внешние пилоты M8 сохраняют собственные критерии и не закрываются этой
внутренней проверкой или preflight.

## Источники metadata-контракта

Preflight опирается на LeRobot revision
`ae2b57f12223c8c5184fcd814eb63cd9ce7de203` от 13 октября 2026. Это источник
проверяемой современной feature-схемы; optional runtime старого PushT checkpoint
отдельно закреплён на пакете LeRobot 0.3.3.

- [Feature conversion и names](https://github.com/huggingface/lerobot/blob/ae2b57f12223c8c5184fcd814eb63cd9ce7de203/src/lerobot/utils/feature_utils.py).
- [PolicyFeature](https://github.com/huggingface/lerobot/blob/ae2b57f12223c8c5184fcd814eb63cd9ce7de203/src/lerobot/configs/types.py).
- [PreTrainedConfig](https://github.com/huggingface/lerobot/blob/ae2b57f12223c8c5184fcd814eb63cd9ce7de203/src/lerobot/configs/policies.py).
- [ACT feature requirements](https://github.com/huggingface/lerobot/blob/ae2b57f12223c8c5184fcd814eb63cd9ce7de203/src/lerobot/policies/act/configuration_act.py).
- [Diffusion feature requirements](https://github.com/huggingface/lerobot/blob/ae2b57f12223c8c5184fcd814eb63cd9ce7de203/src/lerobot/policies/diffusion/configuration_diffusion.py).
- [Diffusion: использование `observation.state`](https://github.com/huggingface/lerobot/blob/ae2b57f12223c8c5184fcd814eb63cd9ce7de203/src/lerobot/policies/diffusion/modeling_diffusion.py).
- [SmolVLA: state и визуальные входы](https://github.com/huggingface/lerobot/blob/ae2b57f12223c8c5184fcd814eb63cd9ce7de203/src/lerobot/policies/smolvla/modeling_smolvla.py).
- [Формат LeRobotDataset v3](https://huggingface.co/docs/lerobot/lerobot-dataset-v3).

В v3 несколько эпизодов могут находиться в одном Parquet/MP4-файле. Этот
инспектор не предполагает соответствия «один файл = один эпизод» и не делает
проверок episode storage по метаданным `info.json`.

## Проверка на опубликованных метаданных

14 октября 2026 проверен неизменённый
[`lerobot/svla_so101_pickplace/meta/info.json`](https://huggingface.co/datasets/lerobot/svla_so101_pickplace/blob/f641879e22172be7e8161d5e6c1503c2d2feb657/meta/info.json)
на закреплённой ревизии `f641879e22172be7e8161d5e6c1503c2d2feb657`.
Скачаны только 3401 байт JSON; SHA-256:
`254909942a6cbfb4692a239e4d0aa5c68ec8eb16f81b6593985ea7f2bb2823e3`.

Проверка метаданных без политики вернула `VALID`: заявлены 50 эпизодов,
11939 кадров, 30 FPS, шестимерные state/action и камеры `up`/`side`.
Файл содержит `robot_type: so100_follower`, хотя имя репозитория включает
`so101`. При явном ожидании `--robot-type so101_follower` проверка возвращает
`INVALID` и код 3. Это проверка опубликованных деклараций; эпизоды, видео и
исполнение этой политики не скачивались и не тестировались.
