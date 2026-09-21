import test from "node:test";
import assert from "node:assert/strict";
import {
  parseReplay,
  validateReplay,
  importedSession,
  alignmentNotice,
  metricDelta,
  timelineEvents,
  trajectoryBounds,
  displaySamples,
} from "../src/model.js";
const recording = () => ({
  schema_version: 1,
  scenario: "route",
  status: "PASS",
  runtime: "test",
  duration_sec: 2,
  robot: { type: "base" },
  world: { frame: "map", goal: { x: 2, y: 0, z: 0 } },
  samples: [0, 2].map((t) => ({
    t,
    position: { x: t, y: 0, z: 0 },
    orientation: { yaw: 0 },
  })),
  metrics: {
    duration_sec: 2,
    path_length_m: 2,
    distance_to_goal_m: 0,
    stuck_events: 0,
    recoveries: 0,
  },
  events: [
    { t: 2, type: "GOAL" },
    { t: 0, type: "START" },
  ],
});
test("accepts recorded failures and preserves their result status", () => {
  const replay = recording();
  replay.status = "FAIL";
  replay.result_status = "TIMEOUT";
  assert.equal(parseReplay(JSON.stringify(replay)).result_status, "TIMEOUT");
});
test("rejects ambiguous and malformed evidence before display", () => {
  assert.throws(
    () => parseReplay('{"schema_version":1,"schema_version":2}'),
    /Повторяющийся/,
  );
  assert.throws(() => parseReplay('{"x":1e999}'), /неконечное/);
  for (const mutate of [
    (r) => (r.schema_version = true),
    (r) => (r.status = "REGRESSION"),
    (r) => (r.samples[0].t = -1),
    (r) => (r.samples[1].position.x = Infinity),
    (r) => (r.metrics.duration_sec = 3),
    (r) => (r.events[0].t = 9),
    (r) => (r.result_status = "TIMEOUT"),
    (r) => (r.metrics.recoveries = 0.5),
  ]) {
    const replay = recording();
    mutate(replay);
    assert.throws(() => validateReplay(replay));
  }
});
test("duplicate detection respects escaped keys and independent objects", () => {
  assert.throws(() => parseReplay('{"a":1,"\\u0061":2}'), /Повторяющийся/);
  assert.equal(parseReplay(JSON.stringify(recording())).samples.length, 2);
});
test("an imported replay can never supply its own gate verdict", () => {
  const candidate = recording();
  candidate.gate = { status: "PASS" };
  const session = importedSession(
    candidate,
    recording(),
    "candidate",
    "baseline",
  );
  assert.equal(session.gate, null);
  assert.equal(session.scenarios[0].comparison, null);
  assert.equal(session.source, "replay");
});
test("different frames, scenarios, starts and goals disable spatial alignment", () => {
  assert.equal(alignmentNotice(recording(), recording()), null);
  for (const mutate of [
    (r) => (r.world.frame = "odom"),
    (r) => (r.scenario = "another"),
    (r) => (r.samples[0].position.x = 1),
    (r) => (r.world.goal.z = 1),
  ]) {
    const base = recording();
    mutate(base);
    assert.ok(alignmentNotice(recording(), base));
  }
});
test("missing values and zero baselines do not produce a false zero delta", () => {
  assert.equal(metricDelta(undefined, 1, "%"), null);
  assert.equal(metricDelta(0, 2, "%"), Infinity);
  assert.equal(metricDelta(0, 0, "%"), 0);
  assert.equal(metricDelta(10, 12, "%"), 20);
  assert.equal(metricDelta(0, 2, ""), 2);
});
test("events use their recorded times and identify their source", () => {
  const scenario = {
    candidate: { replay: recording() },
    baseline: { replay: recording() },
  };
  assert.deepEqual(
    timelineEvents(scenario, true).map((e) => [e.t, e.source]),
    [
      [0, "baseline"],
      [0, "candidate"],
      [2, "baseline"],
      [2, "candidate"],
    ],
  );
  assert.equal(timelineEvents(scenario, false).length, 2);
});
test("large trajectories retain endpoints without overflowing argument limits", () => {
  const replay = recording();
  replay.samples = Array.from({ length: 250_000 }, (_, i) => ({
    t: i,
    position: { x: i, y: -i, z: 0 },
  }));
  const bounds = trajectoryBounds([replay]);
  assert.ok(bounds.maxX > 249_999);
  assert.ok(bounds.minY < -249_999);
  const display = displaySamples(replay.samples);
  assert.ok(display.length <= 6000);
  assert.equal(display[0], replay.samples[0]);
  assert.equal(display.at(-1), replay.samples.at(-1));
  assert.equal(replay.samples.length, 250_000);
});
