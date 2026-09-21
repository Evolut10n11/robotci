/** Replay v1 boundary and presentation helpers. Gate verdicts only come from Python. */
export const MAX_REPLAY_BYTES = 32 * 1024 * 1024;
export const MAX_REPLAY_SAMPLES = 250_000;
export const METRICS = [
  {
    key: "duration_sec",
    label: "Длительность",
    unit: "с",
    policy: "max_duration_increase_pct",
    deltaUnit: "%",
  },
  {
    key: "path_length_m",
    label: "Длина пути",
    unit: "м",
    policy: "max_path_length_increase_pct",
    deltaUnit: "%",
  },
  {
    key: "distance_to_goal_m",
    label: "Расстояние до цели",
    unit: "м",
    policy: "max_distance_to_goal_increase_m",
    deltaUnit: "м",
  },
  {
    key: "stuck_events",
    label: "Застревания",
    unit: "",
    policy: "max_stuck_events_increase",
    deltaUnit: "",
  },
  {
    key: "recoveries",
    label: "Восстановления",
    unit: "",
    policy: "max_recoveries_increase",
    deltaUnit: "",
  },
];
const fail = (message) => {
  throw new Error(message);
};
const object = (value, name) =>
  value && typeof value === "object" && !Array.isArray(value)
    ? value
    : fail(`${name}: ожидается объект.`);
const number = (value, name) =>
  typeof value === "number" && Number.isFinite(value)
    ? value
    : fail(`${name}: ожидается конечное число.`);
const string = (value, name) =>
  typeof value === "string" && value.trim()
    ? value
    : fail(`${name}: ожидается непустая строка.`);
const position = (value, name) => {
  object(value, name);
  for (const key of ["x", "y", "z"]) number(value[key], `${name}.${key}`);
};
const close = (a, b, tolerance = 1e-6) => Math.abs(a - b) <= tolerance;

export function validateReplay(replay) {
  object(replay, "Replay");
  if (replay.schema_version !== 1) fail("Поддерживаются только JSON-записи Replay v1.");
  string(replay.scenario, "Сценарий");
  if (!["PASS", "FAIL"].includes(replay.status))
    fail("Статус записи должен быть PASS или FAIL.");
  const result = Object.hasOwn(replay, "result_status")
    ? replay.result_status
    : replay.status;
  if (!["PASS", "FAIL", "TIMEOUT", "INFRA_ERROR"].includes(result))
    fail("Неподдерживаемый статус результата.");
  if (replay.status !== (result === "PASS" ? "PASS" : "FAIL"))
    fail("Статусы записи и результата не совпадают.");
  string(replay.runtime, "Среда выполнения");
  if (number(replay.duration_sec, "Длительность") <= 0)
    fail("Длительность должна быть больше нуля.");
  string(object(replay.robot, "Робот").type, "Тип робота");
  string(object(replay.world, "Мир").frame, "Система координат");
  position(replay.world.goal, "Цель");
  if (!Array.isArray(replay.samples) || replay.samples.length < 2)
    fail("Нужно не менее двух отсчётов положения робота.");
  if (replay.samples.length > MAX_REPLAY_SAMPLES)
    fail("Запись содержит больше 250 000 отсчётов.");
  let previous = -Infinity;
  replay.samples.forEach((sample, index) => {
    object(sample, `Отсчёт ${index}`);
    number(sample.t, "Время отсчёта");
    if (sample.t < 0 || sample.t < previous || sample.t > replay.duration_sec)
      fail("Временные метки должны идти по порядку и находиться в пределах записи.");
    previous = sample.t;
    position(sample.position, `Отсчёт ${index}`);
    number(object(sample.orientation, "Ориентация").yaw, "Курс");
  });
  object(replay.metrics, "Метрики");
  for (const { key } of METRICS) {
    const value = number(replay.metrics[key], key);
    if (value < 0) fail(`${key}: значение не может быть отрицательным.`);
    if (
      ["stuck_events", "recoveries"].includes(key) &&
      !Number.isInteger(value)
    )
      fail(`${key}: ожидается целое число.`);
  }
  if (
    !close(
      replay.metrics.duration_sec,
      replay.duration_sec,
      Math.max(0.002, replay.duration_sec * 1e-6),
    )
  )
    fail("Длительность записи и значение в метриках не совпадают.");
  if (!Array.isArray(replay.events)) fail("События должны быть массивом.");
  replay.events.forEach((event) => {
    object(event, "Событие");
    number(event.t, "Время события");
    if (event.t < 0 || event.t > replay.duration_sec)
      fail("Время события находится за пределами записи.");
    if (
      !["START", "REPLAN", "STUCK", "RECOVERY", "GOAL", "FAIL"].includes(
        event.type,
      )
    )
      fail("Неподдерживаемый тип события.");
    if (event.message != null && typeof event.message !== "string")
      fail("Описание события должно быть текстом.");
  });
  return replay;
}

export function parseReplay(text) {
  if (new TextEncoder().encode(text).length > MAX_REPLAY_BYTES)
    fail("Размер записи превышает 32 МиБ.");
  let value;
  try {
    value = JSON.parse(text, (_key, item) => {
      if (typeof item === "number" && !Number.isFinite(item))
        fail("JSON содержит неконечное число.");
      return item;
    });
  } catch (error) {
    fail(`Не удалось прочитать JSON: ${error instanceof SyntaxError ? "проверьте синтаксис файла." : error.message}`);
  }
  // JSON.parse silently accepts duplicate keys; reject ambiguous evidence instead.
  const stack = [];
  for (const match of text.matchAll(/"(?:\\.|[^"\\])*"|[{}\[\]:,]/g)) {
    const token = match[0],
      top = stack.at(-1);
    if (token === "{") stack.push({ keys: new Set(), key: true });
    else if (token === "[") stack.push({});
    else if (token === "}" || token === "]") stack.pop();
    else if (token === "," && top?.keys) top.key = true;
    else if (token === ":" && top?.keys) top.key = false;
    else if (token.startsWith('"') && top?.key) {
      const key = JSON.parse(token);
      if (top.keys.has(key)) fail(`Повторяющийся ключ JSON: ${key}`);
      top.keys.add(key);
    }
  }
  return validateReplay(value);
}

export function alignmentNotice(candidate, baseline) {
  if (!candidate || !baseline) return null;
  if (candidate.scenario !== baseline.scenario)
    return "The recordings describe different scenarios.";
  if (candidate.world.frame !== baseline.world.frame)
    return "The recordings use different coordinate frames.";
  for (const [label, a, b] of [
    ["start", candidate.samples[0].position, baseline.samples[0].position],
    ["goal", candidate.world.goal, baseline.world.goal],
  ])
    if (["x", "y", "z"].some((key) => !close(a[key], b[key])))
      return `The recordings have different ${label} positions.`;
  return null;
}

export function importedSession(
  candidate,
  baseline,
  candidateLabel,
  baselineLabel,
) {
  validateReplay(candidate);
  if (baseline) validateReplay(baseline);
  const run = (replay, label) => ({
    label,
    replay,
    status: replay.result_status ?? replay.status,
    runtime: replay.runtime,
    metrics: replay.metrics,
    replay_notice: null,
  });
  return {
    schema_version: 1,
    source: "replay",
    selected_scenario: candidate.scenario,
    candidate_label: candidateLabel,
    baseline_label: baseline ? baselineLabel : null,
    gate: null,
    gate_notice:
      "Replay files show recorded behavior. A verified gate requires suite results.",
    scenarios: [
      {
        name: candidate.scenario,
        candidate: run(candidate, candidateLabel),
        baseline: baseline ? run(baseline, baselineLabel) : null,
        alignment_notice: alignmentNotice(candidate, baseline),
        comparison: null,
      },
    ],
  };
}

export function metricDelta(baseline, candidate, unit) {
  if (!Number.isFinite(baseline) || !Number.isFinite(candidate)) return null;
  if (unit !== "%") return candidate - baseline;
  if (baseline === 0) return candidate === 0 ? 0 : Infinity;
  return ((candidate - baseline) / baseline) * 100;
}
export const formatNumber = (value, digits = 2) =>
  Number.isFinite(value)
    ? value.toLocaleString("ru-RU", { maximumFractionDigits: digits })
    : "—";
export function formatDelta(value, unit = "") {
  if (value === null) return "—";
  if (!Number.isFinite(value)) return "∞";
  return `${value > 0 ? "+" : ""}${formatNumber(value)}${unit ? ` ${unit}` : ""}`;
}
export function timelineEvents(scenario, includeBaseline) {
  const events = [];
  for (const source of includeBaseline
    ? ["baseline", "candidate"]
    : ["candidate"]) {
    for (const event of scenario[source]?.replay?.events ?? [])
      events.push({ ...event, source });
  }
  return events.sort((a, b) => a.t - b.t || a.source.localeCompare(b.source));
}
export function trajectoryBounds(replays) {
  let minX = Infinity,
    maxX = -Infinity,
    minY = Infinity,
    maxY = -Infinity;
  for (const replay of replays.filter(Boolean)) {
    for (const { position: p } of replay.samples) {
      minX = Math.min(minX, p.x);
      maxX = Math.max(maxX, p.x);
      minY = Math.min(minY, p.y);
      maxY = Math.max(maxY, p.y);
    }
    const p = replay.world.goal;
    minX = Math.min(minX, p.x);
    maxX = Math.max(maxX, p.x);
    minY = Math.min(minY, p.y);
    maxY = Math.max(maxY, p.y);
  }
  if (!Number.isFinite(minX)) return { minX: -1, maxX: 1, minY: -1, maxY: 1 };
  const padding = Math.max(0.5, Math.max(maxX - minX, maxY - minY) * 0.16);
  return {
    minX: minX - padding,
    maxX: maxX + padding,
    minY: minY - padding,
    maxY: maxY + padding,
  };
}
export function displaySamples(samples, limit = 6000) {
  if (samples.length <= limit) return samples;
  const step = Math.ceil((samples.length - 1) / (limit - 1));
  return samples.filter(
    (_sample, index) => index % step === 0 || index === samples.length - 1,
  );
}
