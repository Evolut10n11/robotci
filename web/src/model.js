/** Replay v1 boundary and presentation helpers. Gate verdicts only come from Python. */
export const MAX_REPLAY_BYTES = 32 * 1024 * 1024;
export const MAX_REPLAY_SAMPLES = 250_000;
export const METRICS = [
  {
    key: "duration_sec",
    label: "Duration",
    unit: "s",
    policy: "max_duration_increase_pct",
    deltaUnit: "%",
  },
  {
    key: "path_length_m",
    label: "Path length",
    unit: "m",
    policy: "max_path_length_increase_pct",
    deltaUnit: "%",
  },
  {
    key: "distance_to_goal_m",
    label: "Final distance to goal",
    unit: "m",
    policy: "max_distance_to_goal_increase_m",
    deltaUnit: "m",
  },
  {
    key: "stuck_events",
    label: "Stuck events",
    unit: "",
    policy: "max_stuck_events_increase",
    deltaUnit: "",
  },
  {
    key: "recoveries",
    label: "Recoveries",
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
    : fail(`${name} must be an object.`);
const number = (value, name) =>
  typeof value === "number" && Number.isFinite(value)
    ? value
    : fail(`${name} must be a finite number.`);
const string = (value, name) =>
  typeof value === "string" && value.trim()
    ? value
    : fail(`${name} must be a non-empty string.`);
const position = (value, name) => {
  object(value, name);
  for (const key of ["x", "y", "z"]) number(value[key], `${name}.${key}`);
};
const close = (a, b, tolerance = 1e-6) => Math.abs(a - b) <= tolerance;

export function validateReplay(replay) {
  object(replay, "Replay");
  if (replay.schema_version !== 1) fail("Only Replay v1 JSON is supported.");
  string(replay.scenario, "Scenario");
  if (!["PASS", "FAIL"].includes(replay.status))
    fail("Replay status must be PASS or FAIL.");
  const result = Object.hasOwn(replay, "result_status")
    ? replay.result_status
    : replay.status;
  if (!["PASS", "FAIL", "TIMEOUT", "INFRA_ERROR"].includes(result))
    fail("Unsupported result status.");
  if (replay.status !== (result === "PASS" ? "PASS" : "FAIL"))
    fail("Replay and result statuses disagree.");
  string(replay.runtime, "Runtime");
  if (number(replay.duration_sec, "Duration") <= 0)
    fail("Duration must be greater than zero.");
  string(object(replay.robot, "Robot").type, "Robot type");
  string(object(replay.world, "World").frame, "Coordinate frame");
  position(replay.world.goal, "Goal");
  if (!Array.isArray(replay.samples) || replay.samples.length < 2)
    fail("At least two pose samples are required.");
  if (replay.samples.length > MAX_REPLAY_SAMPLES)
    fail("Recording exceeds 250,000 samples.");
  let previous = -Infinity;
  replay.samples.forEach((sample, index) => {
    object(sample, `Sample ${index}`);
    number(sample.t, "Sample timestamp");
    if (sample.t < 0 || sample.t < previous || sample.t > replay.duration_sec)
      fail("Sample timestamps must be ordered and within the recording.");
    previous = sample.t;
    position(sample.position, `Sample ${index}`);
    number(object(sample.orientation, "Orientation").yaw, "Yaw");
  });
  object(replay.metrics, "Metrics");
  for (const { key } of METRICS) {
    const value = number(replay.metrics[key], key);
    if (value < 0) fail(`${key} must be non-negative.`);
    if (
      ["stuck_events", "recoveries"].includes(key) &&
      !Number.isInteger(value)
    )
      fail(`${key} must be an integer.`);
  }
  if (
    !close(
      replay.metrics.duration_sec,
      replay.duration_sec,
      Math.max(0.002, replay.duration_sec * 1e-6),
    )
  )
    fail("Duration and metrics disagree.");
  if (!Array.isArray(replay.events)) fail("Events must be an array.");
  replay.events.forEach((event) => {
    object(event, "Event");
    number(event.t, "Event timestamp");
    if (event.t < 0 || event.t > replay.duration_sec)
      fail("Event timestamp is outside the recording.");
    if (
      !["START", "REPLAN", "STUCK", "RECOVERY", "GOAL", "FAIL"].includes(
        event.type,
      )
    )
      fail("Unsupported event type.");
    if (event.message != null && typeof event.message !== "string")
      fail("Event message must be text.");
  });
  return replay;
}

export function parseReplay(text) {
  if (new TextEncoder().encode(text).length > MAX_REPLAY_BYTES)
    fail("Recording exceeds the 32 MiB size limit.");
  let value;
  try {
    value = JSON.parse(text, (_key, item) => {
      if (typeof item === "number" && !Number.isFinite(item))
        fail("JSON contains a non-finite number.");
      return item;
    });
  } catch (error) {
    fail(`Cannot read JSON: ${error.message}`);
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
      if (top.keys.has(key)) fail(`Duplicate JSON key: ${key}`);
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
    ? value.toLocaleString("en-US", { maximumFractionDigits: digits })
    : "—";
export function formatDelta(value, unit = "") {
  if (value === null) return "—";
  if (!Number.isFinite(value)) return "Unbounded";
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
