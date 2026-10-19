# LeRobot в RobotCI

Первый сценарий: до обучения или оценки checkpoint проверить локальные
метаданные датасета и размеры входов/выходов политики. Это позволяет заранее
заметить пропавшую камеру, несовпадение числа действий или случайно выбранный
датасет другого робота.

## Проверка без GPU, ROS и оборудования

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

## Область поддержки

| Вход | Что проверяется |
| --- | --- |
| LeRobotDataset v2.1 / v3.0 | Версия, FPS, счётчики, структура features, типы и размерности |
| `observation.state`, `action` | Положительные размеры, имена координат, соответствие явной схеме политики |
| Камеры | Наличие требуемых ключей и размеры, перевод HWC в CHW по именам осей |
| ACT / Diffusion / SmolVLA | Явные `input_features` и `output_features` в сохранённом policy config |
| Ожидания запуска | Совпадение `robot_type` и FPS, если они заданы флагами |
| Воспроизводимость | SHA-256 точных байтов каждого прочитанного JSON |

Проверяется совместимость feature-схем, а не полная валидность всех параметров
обучения. Для ACT/Diffusion требуется хотя бы VISUAL или ENV input; все камеры
Diffusion должны иметь одинаковые размеры. SmolVLA с `empty_cameras > 0`
помечается `UNSUPPORTED`, поскольку такие камеры добавляются программно.
Неизвестная версия датасета, неподдержанный тип политики или отсутствие
явной pretrained feature-схемы не получают положительного результата.
Старые сгруппированные `names` вида `{"motors": [...]}` помечаются
`UNSUPPORTED`; поддерживаются плоские списки имён и `null` для числовых features.
Название робота не выбирает 3D-модель: `so101_follower` нельзя автоматически
подменять Panda из каталога. Для геометрии нужен соответствующий URDF/MJCF.

## Результат для CI

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

## Следующий полезный сценарий

Предлагаемое продолжение: сравнение двух checkpoint ACT на одной задаче
манипуляции в закреплённом симуляторе. Сначала адаптер должен реально записывать
эпизоды, seed, версии модели/процессоров/окружения и измерения; затем можно
проверять успешность задачи, время выполнения, ошибки действий и задержку
инференса. Смена checkpoint должна менять реальные действия и результат.

Нужен отдельный контракт manipulation-result: навигационные метрики нельзя
заполнять выдуманными расстояниями или объявлять качество политики по одной
геометрии. Это направление ещё не реализовано. Внешние пилоты M8 сохраняют
собственные критерии и не закрываются этим preflight.

## Источники контракта

Проверено по LeRobot revision
`ae2b57f12223c8c5184fcd814eb63cd9ce7de203` от 13 октября 2026:

- [Feature conversion и names](https://github.com/huggingface/lerobot/blob/ae2b57f12223c8c5184fcd814eb63cd9ce7de203/src/lerobot/utils/feature_utils.py).
- [PolicyFeature](https://github.com/huggingface/lerobot/blob/ae2b57f12223c8c5184fcd814eb63cd9ce7de203/src/lerobot/configs/types.py).
- [PreTrainedConfig](https://github.com/huggingface/lerobot/blob/ae2b57f12223c8c5184fcd814eb63cd9ce7de203/src/lerobot/configs/policies.py).
- [ACT feature requirements](https://github.com/huggingface/lerobot/blob/ae2b57f12223c8c5184fcd814eb63cd9ce7de203/src/lerobot/policies/act/configuration_act.py).
- [Diffusion feature requirements](https://github.com/huggingface/lerobot/blob/ae2b57f12223c8c5184fcd814eb63cd9ce7de203/src/lerobot/policies/diffusion/configuration_diffusion.py).
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
исполнение политики не скачивались и не тестировались.
