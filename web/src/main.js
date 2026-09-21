import "./styles.css";
import { sourceLabel, statusLabel, eventLabel, eventMessage, displayLabel, noticeText, formatTime, displayUnit } from "./ru.js";
import shell from "./shell.html?raw";
import { sampleAt } from "./playback.js";
import { TopView } from "./top-view.js";
import {
  METRICS,
  MAX_REPLAY_BYTES,
  parseReplay,
  validateReplay,
  importedSession,
  formatNumber,
  metricDelta,
  formatDelta,
  timelineEvents,
} from "./model.js";

document.querySelector("#root").innerHTML = shell;
const $ = (id) => document.getElementById(id);
const escape = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (char) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        char
      ],
  );
const badge = (label, kind = "") =>
  `<span class="badge ${escape(kind)}">${escape(label)}</span>`;
const state = {
  session: null,
  scenario: null,
  mode: location.hash === "#compare" ? "compare" : "replay",
  view: "top",
  time: 0,
  duration: 0,
  playing: false,
  speed: 1,
  loop: false,
  events: [],
  renderer: null,
  renderVersion: 0,
  frame: null,
  lastTick: null,
};
function alert(message, error = false) {
  $("app-alert").title = "";
  $("app-alert").textContent = message || "";
  $("app-alert").hidden = !message;
  $("app-alert").classList.toggle("error", error);
}
function stop() {
  state.playing = false;
  cancelAnimationFrame(state.frame);
  state.frame = null;
  state.lastTick = null;
  $("play-button").textContent = "▶";
  $("play-button").setAttribute("aria-label", "Воспроизвести");
}
function recordings() {
  const item = state.scenario;
  return {
    candidate: item?.candidate.replay,
    baseline:
      state.mode === "compare" && !item?.alignment_notice
        ? item?.baseline?.replay
        : null,
  };
}
function setTime(value) {
  state.time = Math.max(0, Math.min(state.duration, value));
  $("seek").value = state.time;
  $("seek").setAttribute(
    "aria-valuetext",
    `${formatTime(state.time)} из ${formatTime(state.duration)} секунд`,
  );
  $("time-display").textContent =
    `${formatTime(state.time)} / ${formatTime(state.duration)} с`;
  $("pose-time").textContent = `${formatTime(state.time)} с`;
  state.renderer?.setTime(state.time);
  const replay = state.scenario?.candidate.replay;
  if (replay) {
    const pose = sampleAt(replay.samples, state.time);
    $("live-pose").innerHTML = [
      ["x", pose.position.x, "м"],
      ["y", pose.position.y, "м"],
      ["z", pose.position.z, "м"],
      ["Курс", (pose.orientation.yaw * 180) / Math.PI, "°"],
    ]
      .map(
        ([key, value, unit]) =>
          `<div class="pose-cell">${key}<strong>${escape(formatNumber(value, 3))} ${unit}</strong></div>`,
      )
      .join("");
    $("sample-note").textContent =
      `Отсчётов: ${formatNumber(replay.samples.length, 0)} · ${state.time > replay.samples.at(-1).t ? "последнее записанное положение" : "интерполяция положения"}`;
  } else {
    $("live-pose").textContent = "Нет записи положения";
    $("sample-note").textContent = "Метрики результата доступны ниже.";
  }
  document.querySelectorAll(".track-cursor").forEach((cursor) => {
    cursor.style.left = `${state.duration ? (state.time / state.duration) * 100 : 0}%`;
  });
  $("previous-event").disabled = !state.events.some(
    (event) => event.t < state.time - 0.001,
  );
  $("next-event").disabled = !state.events.some(
    (event) => event.t > state.time + 0.001,
  );
}
function tick(timestamp) {
  if (!state.playing) return;
  if (state.lastTick !== null) {
    const next =
      state.time +
      Math.min((timestamp - state.lastTick) / 1000, 0.25) * state.speed;
    if (next >= state.duration && !state.loop) {
      setTime(state.duration);
      stop();
      return;
    }
    setTime(state.loop ? next % state.duration : next);
  }
  state.lastTick = timestamp;
  state.frame = requestAnimationFrame(tick);
}
function play() {
  if (!state.duration) return;
  if (state.playing) {
    stop();
    return;
  }
  if (state.time >= state.duration) setTime(0);
  state.playing = true;
  state.lastTick = null;
  $("play-button").textContent = "Ⅱ";
  $("play-button").setAttribute("aria-label", "Пауза");
  state.frame = requestAnimationFrame(tick);
}
function jump(direction) {
  const event =
    direction > 0
      ? state.events.find((e) => e.t > state.time + 0.001)
      : state.events.findLast((e) => e.t < state.time - 0.001);
  if (event) {
    stop();
    setTime(event.t);
  }
}
function selectMode(mode) {
  state.mode = mode;
  history.replaceState(null, "", `#${mode}`);
  if (state.scenario) renderScenario();
}
function renderSources() {
  const session = state.session,
    item = state.scenario;
  const synthetic =
    session.source === "demo" ||
    item.candidate.replay?.runtime === "deterministic_demo";
  $("source-summary").innerHTML = ["baseline", "candidate"]
    .filter((key) => item[key])
    .map(
      (key) =>
        `<div class="source-item"><span class="source-dot ${key}"></span><span>${sourceLabel(key)}</span><span class="source-name" title="${escape(item[key].label)}">${escape(displayLabel(item[key].label))}</span>${badge(statusLabel(item[key].status), item[key].status === "PASS" ? "pass" : "fail")}</div>`,
    )
    .join("");
  $("scenario-title").textContent = synthetic && item.name === "deterministic_demo" ? "Демонстрационный маршрут" : item.name;
  document.title = `RobotCI · ${$("scenario-title").textContent}`;
  $("workspace-subtitle").textContent =
    state.mode === "compare"
      ? "Эталон и новый прогон на общей временной шкале."
      : "Изучайте траекторию, события и поведение робота.";
  $("source-badge").textContent = synthetic
    ? "Демонстрационные данные"
    : session.gate
      ? "Проверенные результаты"
      : session.source === "suite"
        ? "Результаты сценариев"
        : "Replay v1";
  $("source-badge").className = `badge${synthetic ? " demo" : ""}`;
  $("scenario-count").textContent = session.scenarios.length;
  $("scenario-list").innerHTML = session.scenarios
    .map(
      (scenario, index) =>
        `<button class="scenario-button" data-scenario="${index}" aria-current="${scenario.name === item.name}"><span class="scenario-dot ${scenario.comparison?.status === "REGRESSION" ? "regression" : ""}"></span><span class="scenario-name">${escape(session.source === "demo" && scenario.name === "deterministic_demo" ? "Демонстрационный маршрут" : scenario.name)}</span></button>`,
    )
    .join("");
  document
    .querySelectorAll("[data-mode]")
    .forEach((button) =>
      button.setAttribute(
        "aria-current",
        button.dataset.mode === state.mode ? "page" : "false",
      ),
    );
  prepareExport();
  $("export-button").textContent = session.gate
    ? "↓ Скачать отчёт JSON"
    : "↓ Скачать запись";
  $("session-footnote").textContent = synthetic
    ? "Демонстрационные данные · без проверки регрессий"
    : session.gate
      ? "Результат рассчитан модулем проверки регрессий RobotCI"
      : "Просмотр без изменений · без проверки регрессий";
}
function renderInspector() {
  const item = state.scenario;
  $("run-status").textContent = statusLabel(item.candidate.status);
  $("run-status").title = item.candidate.status;
  $("run-status").className =
    `badge ${item.candidate.status === "PASS" ? "pass" : "fail"}`;
  $("recorded-metrics").innerHTML =
    `<dl class="metric-list">${METRICS.map((metric) => `<div><dt>${escape(metric.label)}</dt><dd>${escape(formatNumber(item.candidate.metrics[metric.key]))}${Number.isFinite(item.candidate.metrics[metric.key]) && metric.unit ? ` ${metric.unit}` : ""}</dd></div>`).join("")}</dl>`;
  const gate = state.session.gate;
  if (gate) {
    const findings = item.comparison?.findings ?? [];
    $("gate-panel").innerHTML =
      `<div class="gate-title"><h3>Проверка регрессий</h3>${badge(statusLabel(gate.status), gate.status.toLowerCase())}</div><p>Сравнены результаты с совместимыми задачами и параметрами среды.</p><div class="gate-summary ${gate.status === "REGRESSION" ? "regression" : ""}">${badge(statusLabel(item.comparison?.status ?? "Недоступно"), item.comparison?.status?.toLowerCase())} <span>Превышений в сценарии: ${findings.length}</span></div>${findings.length ? `<ul class="finding-list">${findings.map((f) => `<li><span>${escape(METRICS.find((m) => m.key === f.metric)?.label ?? f.metric)}</span><strong>${escape(formatDelta(f.increase_unbounded ? Infinity : f.increase, displayUnit(f.unit)))}</strong></li>`).join("")}</ul>` : ""}<p>Допуски указаны ниже. Скачайте отчёт для значений с полной точностью.</p>`;
  } else {
    $("gate-panel").innerHTML =
      `<div class="gate-title"><h3>${item.baseline ? "Сравнение записей" : "Данные прогона"}</h3>${badge("Без проверки")}</div><p title="${escape(state.session.gate_notice)}">${escape(noticeText(state.session.gate_notice))}</p>${!item.baseline ? '<button id="add-baseline" class="button">Открыть записи для сравнения</button>' : ""}`;
    $("add-baseline")?.addEventListener("click", openDialog);
  }
}
function renderMetrics() {
  const item = state.scenario,
    comparison = !!item.baseline,
    verified = state.session.gate && item.comparison;
  $("evidence-title").textContent = comparison
    ? "Сравнение метрик"
    : "Записанные метрики";
  $("evidence-badge").textContent = verified
    ? "Допуски проверены"
    : comparison
      ? "Сравнение записей"
      : "Итоговые значения";
  $("metrics-head").innerHTML =
    `<tr><th scope="col">Метрика</th>${comparison ? '<th scope="col">Эталон</th>' : ""}<th scope="col">Новый прогон</th>${comparison ? '<th scope="col">Изменение</th>' : ""}${verified ? '<th scope="col">Допуск</th><th scope="col">Проверка</th>' : ""}</tr>`;
  $("metrics-body").innerHTML = METRICS.map((metric) => {
    const base = item.baseline?.metrics[metric.key],
      candidate = item.candidate.metrics[metric.key];
    const delta = item.alignment_notice
      ? null
      : metricDelta(base, candidate, metric.deltaUnit);
    const finding = item.comparison?.findings.find(
      (f) => f.metric === metric.key,
    );
    const value = (number) =>
      `${formatNumber(number, 6)}${Number.isFinite(number) && metric.unit ? ` ${metric.unit}` : ""}`;
    return `<tr class="${finding ? "metric-finding" : ""}"><td>${metric.label}</td>${comparison ? `<td title="${escape(base)}">${value(base)}</td>` : ""}<td title="${escape(candidate)}">${value(candidate)}</td>${comparison ? `<td class="${delta > 0 ? "increase" : delta < 0 ? "decrease" : ""}">${formatDelta(delta, metric.deltaUnit)}</td>` : ""}${verified ? `<td>≤ ${formatDelta(state.session.gate.policy[metric.policy], metric.deltaUnit)}</td><td>${finding ? "Превышен" : "В допуске"}</td>` : ""}</tr>`;
  }).join("");
  $("metrics-note").textContent = item.alignment_notice
    ? "Разница скрыта: записи несовместимы для сравнения траекторий."
    : comparison
      ? `Изменение = новый прогон − эталон. Длительность и путь — в процентах, остальные метрики — в абсолютных единицах.${verified ? "" : " Эта разница сама по себе не определяет регрессию."}`
      : "Итоговые значения из записи или результата сценария. Они не меняются при перемотке.";
}
function renderEvents() {
  state.events = timelineEvents(
    state.scenario,
    state.mode === "compare" && !state.scenario.alignment_notice,
  );
  const shown = state.events.slice(0, 1000);
  $("event-count").textContent =
    `Всего: ${formatNumber(state.events.length, 0)}${state.events.length > 1000 ? " · показаны первые 1 000" : ""}`;
  $("event-list").innerHTML = shown.length
    ? shown
        .map(
          (event, index) =>
            `<button class="event-row" data-event="${index}" title="Перейти к ${formatTime(event.t)} с"><time>${formatTime(event.t)} с</time><span><span class="event-description"><span class="source-dot ${event.source}"></span>${escape(eventLabel(event.type))} <span class="microcopy">${sourceLabel(event.source)}</span></span><small>${escape(eventMessage(event.message))}</small></span></button>`,
        )
        .join("")
    : '<p class="microcopy">События с временными метками не записаны. Их количество может быть указано в метриках результата.</p>';
  const tracks = Object.entries(recordings()).filter(([, replay]) => replay);
  $("event-tracks").innerHTML =
    tracks
      .map(
        ([source]) =>
          `<div class="event-track"><span>${sourceLabel(source)}</span><div class="track-rail">${shown.map((event, index) => (event.source === source ? `<button class="track-event ${source}" data-event="${index}" style="left:${state.duration ? (event.t / state.duration) * 100 : 0}%" aria-label="${escape(`${sourceLabel(source)}: ${eventLabel(event.type)}, ${formatTime(event.t)} с`)}" title="${escape(`${eventLabel(event.type)} · ${formatTime(event.t)} с`)}">◆</button>` : "")).join("")}<span class="track-cursor"></span></div></div>`,
      )
      .join("") ||
    '<span class="microcopy">Для воспроизведения нужна запись траектории.</span>';
  $("sync-note").textContent =
    tracks.length > 1
      ? "Общее время · в конце — последнее положение"
      : "Время от начала · секунды";
}
async function mountViewport() {
  const version = ++state.renderVersion;
  state.renderer?.dispose();
  state.renderer = null;
  $("viewport").replaceChildren();
  const runs = recordings(),
    available = Object.values(runs).some(Boolean);
  $("plot-empty").hidden = available;
  $("fit-button").disabled = !available;
  $("scene-button").disabled = !available;
  $("top-button").setAttribute("aria-pressed", state.view === "top");
  $("scene-button").setAttribute("aria-pressed", state.view === "3d");
  $("frame-label").textContent = (runs.candidate ?? runs.baseline)?.world.frame
    ? `Система координат: ${(runs.candidate ?? runs.baseline).world.frame}`
    : "";
  $("legend").innerHTML = Object.keys(runs)
    .filter((key) => runs[key])
    .map(
      (key) =>
        `<span class="legend-item"><span class="legend-line ${key}"></span>${sourceLabel(key)}</span>`,
    )
    .join("");
  $("legend").hidden = !available;
  if (!available) {
    $("plot-empty").innerHTML =
      `<strong>Траектория недоступна</strong><p title="${escape(state.scenario.candidate.replay_notice)}">${escape(noticeText(state.scenario.candidate.replay_notice) || "Откройте запись Replay v1 для просмотра траектории.")}</p>`;
    return;
  }
  try {
    if (state.view === "3d") {
      const { SceneView } = await import("./scene-view.js");
      if (version !== state.renderVersion) return;
      state.renderer = new SceneView($("viewport"), runs);
    } else state.renderer = new TopView($("viewport"), runs);
  } catch {
    if (version !== state.renderVersion) return;
    state.view = "top";
    $("viewport").replaceChildren();
    state.renderer = new TopView($("viewport"), runs);
    $("top-button").setAttribute("aria-pressed", "true");
    $("scene-button").setAttribute("aria-pressed", "false");
    alert(
      "3D недоступен в этом браузере. Полная записанная траектория доступна в виде сверху.",
      true,
    );
  }
  $("view-hint").textContent =
    state.view === "3d"
      ? "Перетаскивание — поворот · колесо — масштаб"
      : "Перетаскивание — сдвиг · колесо — масштаб";
  state.renderer?.setTime(state.time);
}
function renderScenario() {
  stop();
  const runs = recordings();
  state.duration = Math.max(
    0,
    ...Object.values(runs)
      .filter(Boolean)
      .map((replay) => replay.duration_sec),
  );
  state.time = 0;
  $("seek").max = state.duration || 1;
  $("seek").disabled = !state.duration;
  $("play-button").disabled = !state.duration;
  const notices = [];
  if (state.mode === "compare") {
    if (!state.scenario.baseline)
      notices.push("Откройте эталонную запись для сравнения прогонов.");
    if (state.scenario.alignment_notice)
      notices.push(
        `${noticeText(state.scenario.alignment_notice)} Показана только траектория нового прогона.`,
      );
    if (state.scenario.baseline?.replay_notice)
      notices.push(`Эталон: ${noticeText(state.scenario.baseline.replay_notice)}`);
  }
  if (state.scenario.candidate.replay_notice && runs.baseline)
    notices.push(`Новый прогон: ${noticeText(state.scenario.candidate.replay_notice)}`);
  alert(notices.join(" "));
  $("app-alert").title = [state.scenario.alignment_notice, state.scenario.baseline?.replay_notice, state.scenario.candidate.replay_notice].filter(Boolean).join(" ");
  renderSources();
  renderInspector();
  renderMetrics();
  renderEvents();
  setTime(0);
  void mountViewport();
}
function acceptSession(session) {
  if (
    session.schema_version !== 1 ||
    !Array.isArray(session.scenarios) ||
    !session.scenarios.length
  )
    throw new Error("Неподдерживаемый формат данных просмотра.");
  for (const scenario of session.scenarios)
    for (const key of ["candidate", "baseline"])
      if (scenario[key]?.replay) validateReplay(scenario[key].replay);
  state.session = session;
  state.scenario =
    session.scenarios.find(
      (scenario) => scenario.name === session.selected_scenario,
    ) ?? session.scenarios[0];
  renderScenario();
}
function openDialog() {
  stop();
  $("import-error").hidden = true;
  $("open-dialog").showModal();
}
function prepareExport() {
  const link = $("export-button");
  if (state.exportURL) URL.revokeObjectURL(state.exportURL);
  state.exportURL = null;
  const value = state.session.gate ?? state.scenario.candidate.replay;
  link.setAttribute("aria-disabled", String(!value));
  if (!value) {
    link.removeAttribute("href");
    link.tabIndex = -1;
    return;
  }
  link.tabIndex = 0;
  link.download = state.session.gate
    ? "robotci-suite-gate.json"
    : `${state.scenario.name.replace(/[^a-zA-Z0-9_-]/g, "_")}.replay.json`;
  state.exportURL = URL.createObjectURL(
    new Blob([JSON.stringify(value, null, 2) + "\n"], {
      type: "application/json",
    }),
  );
  link.href = state.exportURL;
}

$("play-button").addEventListener("click", play);
$("previous-event").addEventListener("click", () => jump(-1));
$("next-event").addEventListener("click", () => jump(1));
$("seek").addEventListener("input", (event) => {
  stop();
  setTime(Number(event.target.value));
});
$("speed").addEventListener("change", (event) => {
  state.speed = Number(event.target.value);
});
$("loop").addEventListener("change", (event) => {
  state.loop = event.target.checked;
});
$("fit-button").addEventListener("click", () => state.renderer?.fit());
$("top-button").addEventListener("click", () => {
  state.view = "top";
  void mountViewport();
});
$("scene-button").addEventListener("click", () => {
  state.view = "3d";
  void mountViewport();
});
$("open-button").addEventListener("click", openDialog);
$("help-button").addEventListener("click", () => {
  stop();
  $("help-dialog").showModal();
});

document.querySelector(".brand").addEventListener("click", (event) => {
  event.preventDefault();
  selectMode("replay");
});
document
  .querySelectorAll("[data-mode]")
  .forEach((button) =>
    button.addEventListener("click", () => selectMode(button.dataset.mode)),
  );
document
  .querySelectorAll("[data-close]")
  .forEach((button) =>
    button.addEventListener("click", () => $(button.dataset.close).close()),
  );
$("scenario-list").addEventListener("click", (event) => {
  const button = event.target.closest("[data-scenario]");
  if (button) {
    state.scenario = state.session.scenarios[Number(button.dataset.scenario)];
    renderScenario();
  }
});
for (const id of ["event-list", "event-tracks"])
  $(id).addEventListener("click", (event) => {
    const button = event.target.closest("[data-event]");
    if (button) {
      stop();
      setTime(state.events[Number(button.dataset.event)].t);
    }
  });
$("open-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("import-error").hidden = true;
  $("import-button").disabled = true;
  $("import-button").textContent = "Чтение записей…";
  try {
    const candidateFile = $("candidate-file").files[0],
      baselineFile = $("baseline-file").files[0];
    if (!candidateFile) throw new Error("Сначала выберите запись нового прогона.");
    const read = async (file) => {
      if (file.size > MAX_REPLAY_BYTES)
        throw new Error(`${file.name}: размер превышает 32 МиБ.`);
      try {
        return parseReplay(await file.text());
      } catch (error) {
        throw new Error(`${file.name}: ${error instanceof DOMException ? "не удалось прочитать файл. Выберите его ещё раз." : error.message}`);
      }
    };
    const [candidate, baseline] = await Promise.all([
      read(candidateFile),
      baselineFile ? read(baselineFile) : null,
    ]);
    state.mode = baseline ? "compare" : "replay";
    history.replaceState(null, "", `#${state.mode}`);
    acceptSession(
      importedSession(
        candidate,
        baseline,
        candidateFile.name,
        baselineFile?.name,
      ),
    );
    $("open-dialog").close();
    $("open-form").reset();
  } catch (error) {
    $("import-error").textContent = error.message;
    $("import-error").hidden = false;
  } finally {
    $("import-button").disabled = false;
    $("import-button").textContent = "Открыть";
  }
});
document.addEventListener("keydown", (event) => {
  if (
    event.ctrlKey ||
    event.metaKey ||
    event.altKey ||
    document.querySelector("dialog[open]") ||
    event.target.closest("input,select,textarea,button,a,[contenteditable]")
  )
    return;
  const actions = {
    " ": play,
    ArrowLeft: () => {
      stop();
      setTime(state.time - 1);
    },
    ArrowRight: () => {
      stop();
      setTime(state.time + 1);
    },
    Home: () => {
      stop();
      setTime(0);
    },
    End: () => {
      stop();
      setTime(state.duration);
    },
    "[": () => jump(-1),
    "]": () => jump(1),
    f: () => state.renderer?.fit(),
    o: openDialog,
    "?": () => {
      stop();
      $("help-dialog").showModal();
    },
  };
  const aliases = { "а": "f", "щ": "o", "х": "[", "ъ": "]" };
  const key = event.key.length === 1 ? event.key.toLowerCase() : event.key;
  const action = actions[aliases[key] ?? key];
  if (action) {
    event.preventDefault();
    action();
  }
});
document.addEventListener("visibilitychange", () => {
  if (document.hidden) stop();
});
window.addEventListener("pagehide", () => {
  stop();
  state.renderVersion++;
  state.renderer?.dispose();
});
async function load() {
  try {
    const response = await fetch("/api/session", { cache: "no-store" });
    if (!response.ok)
      throw new Error(`Сервер вернул HTTP ${response.status}.`);
    acceptSession(await response.json());
  } catch (error) {
    const reason = error instanceof TypeError ? "Проверьте, запущен ли локальный сервер." : error instanceof SyntaxError ? "Сервер вернул некорректный JSON." : error.message;
    $("source-badge").textContent = "Нет соединения";
    alert(
      `Не удалось загрузить данные. ${reason} Вы можете открыть локальные записи.`,
      true,
    );
    $("plot-empty").hidden = false;
    $("plot-empty").innerHTML =
      "<strong>Откройте запись для начала</strong><p>Выберите запись нового прогона в формате Replay v1. При желании добавьте эталон.</p>";
  }
}
void load();
