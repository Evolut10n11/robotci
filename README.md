![RobotCI: measure behavior, gate regressions](docs/assets/robotci-banner.svg)

<p align="center">
  <a href="https://github.com/Evolut10n11/robotci/actions/workflows/ci.yml"><img src="https://github.com/Evolut10n11/robotci/actions/workflows/ci.yml/badge.svg?branch=main" alt="Core CI"></a>
  <a href="pyproject.toml"><img src="https://img.shields.io/badge/Python-3.12-3776AB" alt="Python 3.12"></a>
  <a href="docs/quickstart.md"><img src="https://img.shields.io/badge/alpha-0.1.0a1-0D9488" alt="Public alpha 0.1.0a1"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-64748B" alt="Apache 2.0 license"></a>
</p>

<p align="center">
  <a href="docs/quickstart.md">Quickstart</a> ·
  <a href="docs/README.md">Documentation</a> ·
  <a href="examples/nav2-loopback/README.md">Example</a> ·
  <a href="docs/roadmap.md">Roadmap</a> ·
  <a href="CONTRIBUTING.md">Contributing</a>
</p>

# RobotCI

[Описание на русском](#о-проекте) · [Импорт робота](#конфигурация-робота-и-3d-модель) · [English overview and quickstart](#english-overview)

## О проекте

RobotCI проверяет, не стал ли робот хуже выполнять свои задачи после изменения
кода, алгоритмов или настроек. Это открытый инструмент регрессионного тестирования
поведения роботов: он запускает сценарии в симуляции, измеряет результат и
сравнивает его с ранее сохранённой рабочей версией.

Проект нужен разработчикам робототехнических систем, которым недостаточно
проверить, что программа собирается и проходит обычные тесты. Робот может
по-прежнему доезжать до цели, но делать это медленнее, выбирать более длинный путь
или чаще застревать. RobotCI помогает обнаруживать такие изменения на этапе
разработки, до испытаний на физическом роботе.

Первая целевая аудитория проекта: команды, использующие ROS 2 и Nav2 для навигации
и желающие включить проверку поведения в процесс проверки изменений кода и
автоматические проверки CI. RobotCI не заменяет навигационный стек или симулятор,
а связывает сценарии, измерения, сравнение версий и разбор результатов.

## Что уже умеет RobotCI

| Возможность | Для чего нужна |
| --- | --- |
| Сценарии в YAML | Задать карту, начальную позицию, цель, ограничение времени и требования к данным, подтверждающим результат |
| Запуск навигационных тестов | Выполнить один сценарий или набор сценариев в ROS 2 Jazzy / Nav2 Loopback через нативное Linux-окружение или Docker |
| Измерение поведения | Собрать время выполнения, длину пути, расстояние до цели, случаи застревания, восстановительные действия и показатели качества телеметрии |
| Сравнение с эталоном | Сохранить проверенный запуск под именем, сравнить с ним новую версию и выявить ухудшения по настраиваемым порогам |
| Интеграция с CI | Сформировать JSON, Markdown и JUnit-отчёты; через GitHub Action завершить проверку с ошибкой при обнаружении регрессии |
| Визуальный разбор | Открыть запись траектории в локальном интерфейсе на русском, посмотреть её в 2D/3D и синхронно сравнить два запуска |
| Импорт робота | Вставить URDF/MJCF, определить приблизительный тип по структуре и показать собственную геометрию или явно выбранную модель из локального каталога |
| Проверка перед запуском | Через CLI разобрать URDF/MJCF (`static_reference`) и проверить совместимость метаданных LeRobot с feature-схемой ACT, Diffusion или SmolVLA (`metadata_only`) без ROS, GPU и оборудования |
| LeRobot в симуляции PushT | В отдельном CPU-окружении запустить закреплённую обученную Diffusion-политику, записать эпизоды и сравнить успешность и награду с эталоном; экспериментальный сценарий без ROS и Docker |
| Интеграция с AI-агентами | Через MCP читать результаты и, при явном разрешении, запускать, отслеживать, отменять симуляции и сравнивать их с эталоном |

Эталонный запуск называется `baseline`, проверяемая новая версия называется
`candidate`. Сравнение выполняется только для совместимых задач и окружений.
Ошибки инфраструктуры, несовместимые входные данные и недостаточная телеметрия
отделяются от ухудшения поведения робота.

Решение о регрессии принимается по формальным правилам, а не языковой моделью.
При одинаковых валидированных результатах и настройках проверки вердикт одинаков;
сами измерения в симуляции могут различаться между запусками.

## Как это используется

```text
Проверенная версия → сценарии в симуляции → сохранённый эталон
Изменение кода или настроек → повторный запуск тех же сценариев
→ сравнение метрик → отчёт для CI → разбор отличий в replay
```

Например, разработчик меняет настройки контроллера движения. Робот всё ещё
достигает цели, но тратит больше времени и чаще выполняет восстановительные
действия. Если отличия превышают допустимые пороги, RobotCI отмечает регрессию,
возвращает блокирующий код завершения и показывает изменившиеся метрики.
Записанные траектории помогают разобраться, на каком участке поведение отличается.

Для знакомства без запуска симулятора доступно демо:

```powershell
robotci view --demo
```

Установка описана [ниже](#start-here). Демо использует синтетические данные и не
выдаёт вердикт о качестве реального робота.

## Конфигурация робота и 3D-модель

В просмотрщике можно вставить описание робота, а не выбирать только условный
силуэт. Приложение разбирает звенья и суставы, определяет приблизительный тип
конструкции и показывает доступную геометрию. Если данных недостаточно,
оно сообщает об этом, а не подменяет робота похожей моделью.

### Попробовать без ROS и Docker

После [установки](#start-here) откройте локальное демо на свободном порту:

```powershell
robotci view --demo --port 0
```

В окне **«Описание робота»** вставьте следующий текст и нажмите
**«Распознать и встроить»**:

```yaml
robot:
  model: unitree_go2
```

Это готовый пример для диалога выбора модели, не полный файл сценариев.
В 3D появится каталожная модель Go2; данные демо при этом останутся синтетическими.

| Робот | Идентификатор для `robot.model` | Представление |
| --- | --- | --- |
| Unitree Go2 | `unitree_go2` | Четвероногий робот |
| Unitree G1 | `unitree_g1` | Гуманоид |
| Franka Emika Panda | `franka_emika_panda` | Манипулятор с захватом |

Каталог содержит исходную геометрию моделей из закреплённой версии MuJoCo
Menagerie, собранную в опорной позе. Модели и лицензии включены в пакет;
при просмотре они не скачиваются из интернета.

### Свой робот и автоматическое распознавание

Вместо YAML можно вставить URDF/MJCF, выбрать файл описания или папку с ним
и локальными OBJ/STL. Приложение показывает число звеньев и суставов,
приблизительный тип и предупреждения о недостающих данных.

Точное совпадение с закреплённым описанием MJCF позволяет автоматически выбрать
каталожную модель. Для других поддерживаемых описаний строится собственная
структура с доступной геометрией. Одного названия `Go2` или `G1` для подстановки
каталога недостаточно; `robot.model` является явным выбором пользователя.

Если файлов геометрии нет, отображаются доступные примитивы или кинематический
каркас с предупреждением о неполной модели. Произвольный YAML с одними
параметрами контроллера не описывает форму робота: потребуется URDF/MJCF.
Xacro и внешние include не выполняются; нужен готовый развёрнутый XML.

### Модель в новых записях

Добавьте поле `robot.model` в секцию `robot` существующего валидного
`robotci.yaml`. Следующий запуск сохранит выбранную модель в метаданных replay,
и просмотрщик подставит её автоматически. Для разового просмотра достаточно
диалога; кнопка **«Из записи»** отменяет ручной выбор. Сам импорт не переписывает
сохранённые записи: траектории, метрики и официальный вердикт не меняются.

Импорт отвечает за отображение, а не за управление: модель сохраняет опорную
позу суставов и перемещается по записанной траектории. Движения ног или захватов
не выводятся из Nav2-координат; 2D-маркер остаётся условным. Выбор Go2, G1 или
Panda не переключает симулятор и не создаёт контроллер этого робота.

Поддерживаемые конструкции, работа с локальными мешами и ограничения описаны
в [руководстве по импорту](docs/robot-model-import.md).
[Протокол проверки импорта](docs/validation/robot-model-import-2026-10-13.md)
содержит проверку сборки моделей и браузерных действий.

### Проверить описание из командной строки

```powershell
robotci model list
robotci model inspect examples/robot-models/go2.yaml --json
robotci model inspect examples/robot-models/mimic-gripper.urdf
```

Можно передать собственный URDF/MJCF или YAML с `robot.model`. Команда выводит
тип конструкции, число звеньев/суставов, происхождение каталожной модели и
предупреждения. URDF `mimic` поддерживает связанные суставы, включая пальцы
захвата Panda, в согласованной опорной позе. CLI читает только описание;
проверка файлов геометрии и управление роботом в него не входят.

### LeRobot: проверить метаданные и выполнить политику в PushT

```powershell
robotci lerobot inspect examples/lerobot-preflight/dataset --policy examples/lerobot-preflight/policy --robot-type so101_follower --fps 30
```

Офлайн-проверка LeRobot читает локальные `meta/info.json` v2.1/v3.0 и
явную feature-схему сохранённой политики ACT, Diffusion или SmolVLA: размеры
состояния/действий, наличие камер и порядок осей изображения. `--json` выдаёт
отчёт с хешами входов; несовместимость возвращает код 3. Пример выше содержит
синтетические метаданные, без эпизодов и весов. `VALID` означает только
согласованность проверенных метаданных.

Для реального исполнения обученной политики добавлен экспериментальный CPU
сценарий PushT. Создайте отдельное окружение Python 3.12 из корня репозитория;
эти команды PowerShell не требуют активации окружения, ROS, Docker или GPU:

```powershell
py -3.12 -m venv .venv-lerobot
.\.venv-lerobot\Scripts\python.exe -m pip install -r experiments/lerobot_pusht/requirements.txt
.\.venv-lerobot\Scripts\python.exe -m pip install -e .
$RobotCIPushT = Join-Path $PWD ".venv-lerobot\Scripts\robotci.exe"
& $RobotCIPushT lerobot fetch .robotci/lerobot-checkpoints/diffusion-pusht
& $RobotCIPushT lerobot run .robotci/lerobot-checkpoints/diffusion-pusht --output .robotci/lerobot-pusht/baseline --seed 1000 --seed 1001 --seed 1002 --inference-steps 10
& $RobotCIPushT lerobot run .robotci/lerobot-checkpoints/diffusion-pusht --output .robotci/lerobot-pusht/unchanged --seed 1000 --seed 1001 --seed 1002 --inference-steps 10
& $RobotCIPushT lerobot compare .robotci/lerobot-pusht/baseline .robotci/lerobot-pusht/unchanged --output .robotci/lerobot-pusht/reports/unchanged.json --markdown .robotci/lerobot-pusht/reports/unchanged.md
```

`fetch` явно скачивает около 1,05 ГБ с закреплённой ревизии
`lerobot/diffusion_pusht`, проверяет размеры и SHA-256 и сохраняет manifest.
Существующий checkpoint повторно проверяется; веса, каталоги запусков и отчёты
не перезаписываются. После скачивания `run` использует только локальные файлы.

Код `0` у `run` означает `COMPLETED`, даже если политика не решила ни одного
эпизода. Качество проверяет `compare`: `0` — `PASS`, `4` — `REGRESSION`,
`3` — `INFRA_ERROR`. Эталону нужен хотя бы один успех; окружение, версии
зависимостей и упорядоченные seeds должны совпадать. Первый повтор позволяет
проверить неизменённую политику, после чего можно сравнить реальное изменение
действий через `--action-scale 0`. Полный пример и правила сравнения находятся
в [руководстве LeRobot](docs/lerobot.md).

В примере используются 10 шагов денойзинга вместо 100 из исходного config;
это самостоятельная проверка RobotCI, а не воспроизведение upstream-бенчмарка.
Поддерживается один закреплённый Diffusion checkpoint и среда PushT.
Исполнение ACT/SmolVLA, управление физическим манипулятором и подключение
PushT-траекторий к Nav2/3D replay в этот сценарий не входят.
[Протокол внутренних испытаний](docs/validation/lerobot-pusht-2026-10-19.md)
содержит фактические результаты и ограничения окружения.

В сохранённой CPU-проверке эталон и неизменённый повтор решили по 3 из 3
эпизодов, сравнение вернуло `PASS`. Кандидат с удержанием позиции решил 0 из 3;
сравнение обнаружило `REGRESSION`. Это внутренний контроль на трёх seeds;
исходные [результаты и траектории](experiments/lerobot_pusht/evidence/2026-10-19/manifest.json)
сохранены отдельно от unit-test fixtures и внешних пилотов.

### Что проверено в физическом симуляторе

Отдельный [эксперимент с моделями](experiments/robot_models/README.md) проверяет
Go2, G1 и Panda в MuJoCo: удержание позы, точность управления суставами и
реакцию на ослабление регулятора. Это реальные расчёты физики моделей,
но не испытания оборудования, обученная ходьба или готовые адаптеры RobotCI.
[Измеренные результаты](docs/validation/model-probes-2026-10-13.md) учитываются
отдельно от визуального импорта и основного Nav2-процесса.

## Текущее состояние и ограничения

Текущая версия: публичная альфа `0.1.0a1`. Основной цикл от запуска сценариев до
сравнения, CI-отчёта и визуального разбора реализован. Внешняя проверка на проектах
других команд пока продолжается; наличие внутренних тестов не означает, что
совместимость подтверждена для любого робота или симулятора.

Основное поддерживаемое направление сейчас: навигация ROS 2 / Nav2.
Интеграция Nav2 с Gazebo Harmonic доступна как экспериментальная и имеет отдельный
[журнал проверок](docs/validation/runtime-acceptance.md).

Проверка конфигурации, планирование и просмотр записей доступны на Windows без
ROS и Docker. Для навигационных симуляций нужен Ubuntu с ROS 2 / Nav2, работающий
Docker с Linux-контейнерами или отдельный Ubuntu runner. Экспериментальный
LeRobot PushT использует отдельное окружение Python 3.12 и CPU; его установка
и контракт результатов описаны независимо от Nav2.

Модели ровера, четвероногого робота и гуманоида в просмотрщике меняют только
визуальное представление. Они не означают поддержку управления этими роботами
или воспроизведение движений их суставов. RobotCI также не является системой
сертификации безопасности и не заменяет испытания на физическом оборудовании.

## Что планируется дальше

Ближайший приоритет: подтвердить полезность основного сценария на внешних проектах,
а затем расширять продукт на основе реальных задач пользователей.

| Направление | Планируемое развитие |
| --- | --- |
| Внешние пилоты и надёжность | Проверить полный цикл на проектах других команд, собрать результаты и ограничения; расширить измеренные Nav2/Gazebo-проверки на новые маршруты и окружения |
| Новые роботы и симуляторы | На основе отдельных MuJoCo-экспериментов с Go2, G1 и Panda проработать полноценные адаптеры, суставную телеметрию и контроллеры. Визуальный импорт уже доступен, поддержка их исполнения всем продуктом пока не заявляется |
| Визуальная диагностика и AI | Развивать контекст карты и событий в replay по задачам пользователей; поверх существующего MCP исследовать диагностику причин регрессий, связь с изменениями кода и интеграции LangGraph/LangChain. Итоговый вердикт останется детерминированным |
| Командная работа | После подтверждения потребности в пилотах проработать общие эталоны, постоянную историю запусков, динамику метрик между изменениями и совместные правила проверки |

В перспективе новые адаптеры могут расширить проверки за пределы навигации:
например, на падения, проскальзывание ног, расход энергии и ограничения суставов.
Сейчас эти метрики не входят в поддерживаемую схему результатов.

Это направления развития, а не список уже готовых возможностей или обещание
сроков. Подробные статусы находятся в [дорожной карте](docs/roadmap.md),
а назначение и принципы развития описаны в [продуктовом плане](docs/product.md).

## English overview

Behavior regression testing for ROS 2 / Nav2 with deterministic verdicts.

Run repeatable navigation scenarios in simulation, compare a candidate with a
known-good baseline, and block changes that make robot behavior worse. RobotCI
records the measurements and produces reports your CI pipeline can act on.

An experimental LeRobot path also evaluates one pinned pretrained Diffusion
policy in CPU PushT, records per-seed evidence, and gates success-rate and reward
regressions. Metadata preflight supports ACT, Diffusion and SmolVLA configurations;
policy execution is limited to the pinned Diffusion PushT profile. See the
[LeRobot guide](docs/lerobot.md) for isolated setup, repeats and a real action intervention.

**Public alpha · `0.1.0a1`** — available from this repository. The core workflow
is implemented; external validation is in progress. Start with simulation.

## What you can do today

| Capability | What you get |
| --- | --- |
| Define a suite | Validated YAML scenarios with explicit start, goal, map, timeout, and evidence policy |
| Run navigation tests | ROS2 Jazzy / Nav2 Loopback on Ubuntu 24.04 or through a Linux Docker runtime |
| Measure behavior | Duration, path length, distance to goal, stuck events, recoveries, and feedback quality |
| Gate a change | Named local baselines, compatibility checks, deterministic thresholds, and blocking exit codes |
| Review results in CI | JSON, Markdown, JUnit, and a reusable GitHub Action |
| Inspect a run | 2D/3D replay with robot visual profiles, synchronized comparison, observed stuck/recovery events, and six read-only MCP tools |
| Import a robot | Bounded URDF/MJCF inspection, approximate structural classification, local OBJ/STL geometry, and bundled Go2/G1/Panda reference models |
| Inspect configurations offline | `model list/inspect` reports `static_reference`; `lerobot inspect` checks ACT/Diffusion/SmolVLA feature metadata; no hardware or ML dependencies |
| Evaluate LeRobot in PushT | Explicit pinned-checkpoint download, optional CPU Diffusion execution, episode artifacts and deterministic comparisons; no ROS or Docker required |
| Orchestrate a simulation | Explicitly enabled MCP start/status/cancel/compare tools with isolated evidence and owned runtime cleanup |

Navigation success alone is not enough. A robot can reach its goal and still take
a longer path or require more recoveries. RobotCI measures those changes against
the baseline. Missing telemetry or an incompatible environment produces an
infrastructure/input error rather than a misleading behavioral verdict.

Verdicts are deterministic for the same validated artifacts and policy.
Simulation measurements can vary; unchanged runs must establish a usable
baseline before a controller intervention is accepted.

## Start here

Python **3.12** is required. The alpha is source-distributed; keep the checkout
for runtime scripts and Docker resources.

<details open>
<summary><strong>Windows · PowerShell</strong></summary>

```powershell
git clone https://github.com/Evolut10n11/robotci.git
cd robotci
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .

robotci version
robotci validate
robotci plan
```

</details>

<details>
<summary><strong>Linux · Bash</strong></summary>

```bash
git clone https://github.com/Evolut10n11/robotci.git
cd robotci
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e .

robotci version
robotci validate
robotci plan
```

</details>

These checks run without ROS or Docker. To explore the local replay viewer:

```powershell
robotci view --demo
```

The viewer UI is in Russian. See the [Russian guide](docs/replay-viewer.ru.md).
If port 8765 is busy, pass `--port 8766` or `--port 0` to choose a free port.

The demo is synthetic and has no gate verdict. Open a recorded replay to inspect
an actual run.

### Import a robot description

Open **«Описание робота»**, paste URDF/MJCF or choose a local description file,
then click **«Распознать и встроить»**. Select a folder to provide local OBJ/STL
meshes. The viewer builds the supported description's structure and reports
missing geometry instead of silently substituting a catalog robot.

To explicitly select a bundled model, paste `robot: {model: unitree_go2}`.
Available identifiers are `unitree_go2`, `unitree_g1`, and `franka_emika_panda`.
Set the same `robot.model` field in an existing valid `robotci.yaml` to carry the
selection into new recordings. Catalog geometry is packaged locally; automatic
catalog recognition requires an exact pinned description match, not a brand name.

This is reference-pose visualization, not dynamics, joint animation or an automatic
controller. Controller-only YAML cannot determine physical geometry. Existing
`robot.visual_profile` remains an approximate presentation fallback, not an exact
robot identity. See the [import guide](docs/robot-model-import.md) and
[visual profile contract](docs/contracts.md#robot-visual-profile).

### Run your first suite

With a working Linux-container Docker backend, run from the checkout:

```powershell
robotci doctor
robotci run --runtime docker
```

For native ROS2 Jazzy/Nav2 on Ubuntu 24.04, follow the
[runtime setup](docs/quickstart.md#native-runtime-setup) and use
`robotci run --runtime native`.

| Environment | Core tools | Nav2 simulation execution |
| --- | --- | --- |
| Windows / PowerShell | Supported | Requires a working Linux Docker backend or remote Ubuntu runner |
| Ubuntu 24.04 | Supported | Native ROS2 Jazzy/Nav2 or Docker |
| GitHub Actions | Windows and Ubuntu core checks | Ubuntu native and Docker runtime workflows |

### Save a baseline, then compare a change

After reviewing a successful suite:

```powershell
robotci-baseline save main-nav --suite .robotci/suite-result.json
robotci-baseline show main-nav
```

Make a real controller/planner/configuration change, then run the same suite in
the same execution environment:

```powershell
robotci run --runtime docker
robotci-baseline gate main-nav --candidate .robotci/suite-result.json
robotci view --suite .robotci/suite-result.json --baseline-name main-nav --port 0
```

The default regression policy allows up to **10%** more duration and path length,
**0.1 m** more final goal distance, and **no additional** stuck events or recoveries.
Thresholds are configurable. Changed tasks or incompatible runtime fingerprints
must be resolved before comparison.

| Exit code | Meaning |
| ---: | --- |
| `0` | PASS |
| `1` | Robot behavior FAIL |
| `2` | Navigation TIMEOUT |
| `3` | INFRA_ERROR or invalid/incompatible comparison input |
| `4` | REGRESSION detected by a comparison command |

Read the [full quickstart](docs/quickstart.md) for an external project and the
[baseline guide](docs/baselines.md) for reports and policy options.

## Bring it into your workflow

- **GitHub Actions:** the [suite regression action](docs/github-action.md)
  writes JSON, Markdown, and JUnit reports before returning a blocking verdict.
- **Replay:** `robotci view --replay .robotci/results/simple_route.replay.json`
  opens a recorded trajectory. Compare full suites with `--suite` and
  `--baseline-suite`, or open replay files directly in the browser. See the
  [viewer guide](docs/replay-viewer.md).
- **MCP:** install `python -m pip install -e ".[mcp]"`, then run `robotci-mcp`.
  The [MCP guide](docs/mcp.md) lists the six default inspection tools and four
  opt-in managed simulation tools. Execution requires an explicit project,
  configuration and `--allow-execution`; the model does not decide gate verdicts.
  The [reference workflow](examples/mcp-agent/README.md) demonstrates diagnosis,
  owned execution, polling, cancellation and deterministic comparison.
- **Your simulator:** use the [native adapter contract](docs/native-runtime-adapter.md)
  to integrate an existing Nav2 environment. Verify compatibility for that environment.
- **Experimental Gazebo:** the [Jazzy/Harmonic TurtleBot example](examples/nav2-gazebo/README.md)
  launches a fresh physical simulation and verifies readiness, controller
  settings, local-costmap frame, telemetry and owned cleanup. Its
  [acceptance record](docs/validation/runtime-acceptance.md) tracks measured
  baseline stability and controller interventions. Two independent map-frame
  experiments each passed all 20 within-cohort comparisons and both controls,
  then detected sole duration regressions of +120.816% and +102.056%. Runner
  dependency changes produced separate fingerprints; direct cross-cohort gates
  remain incompatible.

## Project status

| Area | Status |
| --- | --- |
| M0–M7: execution, metrics, regression, reproducibility, CI, public alpha | Implemented |
| M8: real-world validation | In progress; external evidence pending |
| M9: visual replay | Local workbench with description import, bundled reference models, playback, 2D/3D, synchronized comparison, and suite gate evidence |
| M10: additional robot adapters | Bounded Go2/G1/Panda MuJoCo probes exist; production adapters and joint-trajectory integration remain future work |
| LeRobot | Offline metadata preflight plus experimental pinned Diffusion PushT execution and comparison; separate artifacts, no physical-robot or ACT/SmolVLA runtime claim |
| M11: agent integration | Six inspection tools, four opt-in managed simulation tools and a reference MCP workflow |
| Nav2 / Gazebo acceptance | Experimental setup succeeded in two separately fingerprinted internal experiments; each passed 20/20 baseline gates and both controls, and detected the real speed regression |
| M12: team capabilities | Requires evidence from external pilots |

See the [roadmap](docs/roadmap.md) for scope and the
[validation register](docs/validation/README.md) for M8 evidence.

The current alpha targets Nav2 simulation. It is not a hardware safety
certification. Parallel suites sharing runtime/output resources are not supported;
broad simulator compatibility remains future work. See [runtime limitations](docs/runtime-integrity.md).

## Documentation and development

The [documentation index](docs/README.md) covers configuration, result contracts,
runtime integrity, reproducibility, integrations, and product direction.

To contribute from the activated environment:

```powershell
python -m pip install -e ".[dev]"
robotci validate
ruff check .
pytest -q
```

The Python core runs independently of ROS. See [CONTRIBUTING.md](CONTRIBUTING.md)
for repository structure, checks, and the branch lifecycle.

Found a problem? [Open a bug report](https://github.com/Evolut10n11/robotci/issues/new?template=bug_report.yml).
Tried a real project? [Share pilot feedback](https://github.com/Evolut10n11/robotci/issues/new?template=public_alpha_feedback.yml).

RobotCI code is licensed under [Apache 2.0](LICENSE). Bundled robot models retain
their upstream licenses alongside the assets in [the local catalog](robotci/model_catalog).
