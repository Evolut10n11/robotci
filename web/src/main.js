import "./styles.css";
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
  $("play-button").setAttribute("aria-label", "Play");
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
    `${state.time.toFixed(2)} of ${state.duration.toFixed(2)} seconds`,
  );
  $("time-display").textContent =
    `${state.time.toFixed(2)} / ${state.duration.toFixed(2)} s`;
  $("pose-time").textContent = `${state.time.toFixed(2)} s`;
  state.renderer?.setTime(state.time);
  const replay = state.scenario?.candidate.replay;
  if (replay) {
    const pose = sampleAt(replay.samples, state.time);
    $("live-pose").innerHTML = [
      ["x", pose.position.x, "m"],
      ["y", pose.position.y, "m"],
      ["z", pose.position.z, "m"],
      ["yaw", (pose.orientation.yaw * 180) / Math.PI, "°"],
    ]
      .map(
        ([key, value, unit]) =>
          `<div class="pose-cell">${key}<strong>${escape(formatNumber(value, 3))} ${unit}</strong></div>`,
      )
      .join("");
    $("sample-note").textContent =
      `${replay.samples.length.toLocaleString()} recorded samples · ${state.time > replay.samples.at(-1).t ? "holding final recorded pose" : "interpolated pose"}`;
  } else {
    $("live-pose").textContent = "No recorded pose";
    $("sample-note").textContent = "Result metrics remain available below.";
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
  $("play-button").setAttribute("aria-label", "Pause");
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
        `<div class="source-item"><span class="source-dot ${key}"></span><span>${key === "candidate" ? "Candidate" : "Baseline"}</span><span class="source-name" title="${escape(item[key].label)}">${escape(item[key].label)}</span>${badge(item[key].status, item[key].status === "PASS" ? "pass" : "fail")}</div>`,
    )
    .join("");
  $("scenario-title").textContent = item.name;
  document.title = `RobotCI · ${item.name}`;
  $("workspace-subtitle").textContent =
    state.mode === "compare"
      ? "Baseline and candidate. One timeline, recorded evidence."
      : "Inspect the trajectory. Understand what happened.";
  $("source-badge").textContent = synthetic
    ? "Synthetic demo"
    : session.gate
      ? "Suite evidence"
      : session.source === "suite"
        ? "Suite results"
        : "Replay v1";
  $("source-badge").className = `badge${synthetic ? " demo" : ""}`;
  $("scenario-count").textContent = session.scenarios.length;
  $("scenario-list").innerHTML = session.scenarios
    .map(
      (scenario, index) =>
        `<button class="scenario-button" data-scenario="${index}" aria-current="${scenario.name === item.name}"><span class="scenario-dot ${scenario.comparison?.status === "REGRESSION" ? "regression" : ""}"></span><span class="scenario-name">${escape(scenario.name)}</span></button>`,
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
    ? "↓ Export gate JSON"
    : "↓ Export replay";
  $("session-footnote").textContent = synthetic
    ? "Synthetic data · no gate verdict"
    : session.gate
      ? "Gate evaluated by the RobotCI regression engine"
      : "Read-only analysis · no gate verdict";
}
function renderInspector() {
  const item = state.scenario;
  $("run-status").textContent = `Run ${item.candidate.status}`;
  $("run-status").className =
    `badge ${item.candidate.status === "PASS" ? "pass" : "fail"}`;
  $("recorded-metrics").innerHTML =
    `<dl class="metric-list">${METRICS.map((metric) => `<div><dt>${escape(metric.label)}</dt><dd>${escape(formatNumber(item.candidate.metrics[metric.key]))}${Number.isFinite(item.candidate.metrics[metric.key]) && metric.unit ? ` ${metric.unit}` : ""}</dd></div>`).join("")}</dl>`;
  const gate = state.session.gate;
  if (gate) {
    const findings = item.comparison?.findings ?? [];
    $("gate-panel").innerHTML =
      `<div class="gate-title"><h3>Official suite gate</h3>${badge(gate.status, gate.status.toLowerCase())}</div><p>Compared suite results with matching task and execution evidence.</p><div class="gate-summary ${gate.status === "REGRESSION" ? "regression" : ""}">${badge(item.comparison?.status ?? "Unavailable", item.comparison?.status?.toLowerCase())} <span>This scenario · ${findings.length} finding${findings.length === 1 ? "" : "s"}</span></div>${findings.length ? `<ul class="finding-list">${findings.map((f) => `<li><span>${escape(METRICS.find((m) => m.key === f.metric)?.label ?? f.metric)}</span><strong>${escape(formatDelta(f.increase_unbounded ? Infinity : f.increase, f.unit))}</strong></li>`).join("")}</ul>` : ""}<p>Policy limits are shown below. Export the gate report for full precision.</p>`;
  } else {
    $("gate-panel").innerHTML =
      `<div class="gate-title"><h3>${item.baseline ? "Visual comparison" : "Recorded evidence"}</h3>${badge("No gate verdict")}</div><p>${escape(state.session.gate_notice)}</p>${!item.baseline ? '<button id="add-baseline" class="button">Open recordings to compare</button>' : ""}`;
    $("add-baseline")?.addEventListener("click", openDialog);
  }
}
function renderMetrics() {
  const item = state.scenario,
    comparison = !!item.baseline,
    verified = state.session.gate && item.comparison;
  $("evidence-title").textContent = comparison
    ? "Metric comparison"
    : "Recorded metrics";
  $("evidence-badge").textContent = verified
    ? "Policy evaluated"
    : comparison
      ? "Visual comparison"
      : "Final run values";
  $("metrics-head").innerHTML =
    `<tr><th scope="col">Metric</th>${comparison ? '<th scope="col">Baseline</th>' : ""}<th scope="col">Candidate</th>${comparison ? '<th scope="col">Change</th>' : ""}${verified ? '<th scope="col">Limit</th><th scope="col">Gate</th>' : ""}</tr>`;
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
    return `<tr class="${finding ? "metric-finding" : ""}"><td>${metric.label}</td>${comparison ? `<td title="${escape(base)}">${value(base)}</td>` : ""}<td title="${escape(candidate)}">${value(candidate)}</td>${comparison ? `<td class="${delta > 0 ? "increase" : delta < 0 ? "decrease" : ""}">${formatDelta(delta, metric.deltaUnit)}</td>` : ""}${verified ? `<td>≤ ${formatDelta(state.session.gate.policy[metric.policy], metric.deltaUnit)}</td><td>${finding ? "Exceeded" : "Within limit"}</td>` : ""}</tr>`;
  }).join("");
  $("metrics-note").textContent = item.alignment_notice
    ? "Deltas are hidden because these recordings do not align."
    : comparison
      ? `Changes are candidate − baseline. Duration and path use percent; other metrics use absolute units.${verified ? "" : " These differences are not a gate verdict."}`
      : "Final values from the recording or scenario result; they do not change with the playhead.";
}
function renderEvents() {
  state.events = timelineEvents(
    state.scenario,
    state.mode === "compare" && !state.scenario.alignment_notice,
  );
  const shown = state.events.slice(0, 1000);
  $("event-count").textContent =
    `${state.events.length} recorded${state.events.length > 1000 ? " · first 1,000 shown" : ""}`;
  $("event-list").innerHTML = shown.length
    ? shown
        .map(
          (event, index) =>
            `<button class="event-row" data-event="${index}" title="Seek to ${event.t} seconds"><time>${event.t.toFixed(2)} s</time><span><span class="event-description"><span class="source-dot ${event.source}"></span>${escape(event.type)} <span class="microcopy">${event.source}</span></span><small>${escape(event.message ?? "Recorded event")}</small></span></button>`,
        )
        .join("")
    : '<p class="microcopy">No timestamped events were recorded. Event counts may still be present in the result metrics.</p>';
  const tracks = Object.entries(recordings()).filter(([, replay]) => replay);
  $("event-tracks").innerHTML =
    tracks
      .map(
        ([source]) =>
          `<div class="event-track"><span>${source === "baseline" ? "Baseline" : "Candidate"}</span><div class="track-rail">${shown.map((event, index) => (event.source === source ? `<button class="track-event ${source}" data-event="${index}" style="left:${state.duration ? (event.t / state.duration) * 100 : 0}%" aria-label="${escape(`${source} ${event.type} at ${event.t} seconds`)}" title="${escape(`${event.type} · ${event.t}s`)}">◆</button>` : "")).join("")}<span class="track-cursor"></span></div></div>`,
      )
      .join("") ||
    '<span class="microcopy">A recorded trajectory is required for playback.</span>';
  $("sync-note").textContent =
    tracks.length > 1
      ? "Synced by elapsed time · final pose held"
      : "Elapsed time · seconds";
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
    ? `frame: ${(runs.candidate ?? runs.baseline).world.frame}`
    : "";
  $("legend").innerHTML = Object.keys(runs)
    .filter((key) => runs[key])
    .map(
      (key) =>
        `<span class="legend-item"><span class="legend-line ${key}"></span>${key === "candidate" ? "Candidate" : "Baseline"}</span>`,
    )
    .join("");
  $("legend").hidden = !available;
  if (!available) {
    $("plot-empty").innerHTML =
      `<strong>No trajectory available</strong><p>${escape(state.scenario.candidate.replay_notice ?? "Open a Replay v1 recording to inspect the trajectory.")}</p>`;
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
      "3D is unavailable in this browser. The top view still shows the full recorded trajectory.",
      true,
    );
  }
  $("view-hint").textContent =
    state.view === "3d"
      ? "Drag to orbit · scroll to zoom"
      : "Drag to pan · scroll to zoom";
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
      notices.push("Open a baseline recording to compare runs.");
    if (state.scenario.alignment_notice)
      notices.push(
        `${state.scenario.alignment_notice} Showing the candidate trajectory only.`,
      );
    if (state.scenario.baseline?.replay_notice)
      notices.push(`Baseline: ${state.scenario.baseline.replay_notice}`);
  }
  if (state.scenario.candidate.replay_notice && runs.baseline)
    notices.push(`Candidate: ${state.scenario.candidate.replay_notice}`);
  alert(notices.join(" "));
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
    throw new Error("Unsupported viewer session.");
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
  $("import-button").textContent = "Reading recordings…";
  try {
    const candidateFile = $("candidate-file").files[0],
      baselineFile = $("baseline-file").files[0];
    if (!candidateFile) throw new Error("Choose a candidate recording first.");
    const read = async (file) => {
      if (file.size > MAX_REPLAY_BYTES)
        throw new Error(`${file.name} exceeds the 32 MiB size limit.`);
      try {
        return parseReplay(await file.text());
      } catch (error) {
        throw new Error(`${file.name}: ${error.message}`);
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
    $("import-button").textContent = "Open workspace";
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
  const action = actions[event.key];
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
      throw new Error(`Viewer returned HTTP ${response.status}.`);
    acceptSession(await response.json());
  } catch (error) {
    $("source-badge").textContent = "Offline";
    alert(
      `Could not load the workspace. ${error.message} You can still open local recordings.`,
      true,
    );
    $("plot-empty").hidden = false;
    $("plot-empty").innerHTML =
      "<strong>Open a recording to begin</strong><p>Choose a candidate Replay v1 file, and optionally a baseline.</p>";
  }
}
void load();
