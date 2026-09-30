import test from "node:test";
import assert from "node:assert/strict";
import { visualProfile } from "../src/robot-profiles.js";
import {
  parseReplay,
  validateReplay,
  importedSession,
  alignmentNotice,
  metricDelta,
  timelineEvents,
  trajectoryBounds,
  displaySamples,
  firstMetricEvent,
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
test("visual profiles are optional, strictly validated, and preview never mutates evidence", () => {
  const legacy = recording();
  assert.equal(visualProfile(validateReplay(legacy)), "rover");
  assert.equal(Object.hasOwn(legacy.robot, "visual_profile"), false);
  for (const profile of ["rover", "quadruped", "humanoid"]) {
    const replay = recording();
    replay.robot.visual_profile = profile;
    const before = JSON.stringify(replay);
    assert.equal(visualProfile(validateReplay(replay)), profile);
    assert.equal(visualProfile(replay, "humanoid"), "humanoid");
    assert.equal(JSON.stringify(replay), before);
    assert.equal(importedSession(replay, legacy, "candidate", "baseline").gate, null);
  }
  for (const invalid of [null, "", "dog", [], {}, 1, true]) {
    const replay = recording();
    replay.robot.visual_profile = invalid;
    assert.throws(() => validateReplay(replay), /профиль/);
  }
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
test("recovery batches preserve their observed timestamp and full counter delta", () => {
  const replay = recording();
  replay.metrics.recoveries = 4;
  replay.events.push({ t: 1, type: "RECOVERY", count: 4 });
  const decoded = parseReplay(JSON.stringify(replay));
  assert.equal(decoded.events.at(-1).count, 4);
  assert.equal(firstMetricEvent(decoded, "recoveries").t, 1);
  for (const count of [0, -1, true, 1.5, "2", null, 2 ** 53]) {
    replay.events.at(-1).count = count;
    assert.throws(() => validateReplay(replay));
  }
});
test("metric navigation uses recorded events, never inferred times from counters", () => {
  const replay = recording();
  replay.metrics.stuck_events = 2;
  assert.equal(firstMetricEvent(replay, "stuck_events"), null);
  assert.equal(firstMetricEvent(null, "stuck_events"), null);
  replay.events.push({ type: "STUCK", t: 1.5 }, { type: "STUCK", t: 0.5 });
  assert.equal(firstMetricEvent(replay, "stuck_events").t, 0.5);
  assert.equal(firstMetricEvent(replay, "duration_sec"), null);
  assert.equal(firstMetricEvent(replay, "recoveries"), null);
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

const observedRecording = () => ({
  ...recording(),
  recording: { pose_source: "observed", max_interpolation_gap_sec: 1 },
  world: { frame: "map", start: { x: 0, y: 0, z: 0 }, goal: { x: 2, y: 0, z: 0 } },
});

test("observed recordings accept zero or one sample and keep the configured start", () => {
  for (const count of [0, 1, 2]) {
    const replay = observedRecording();
    replay.samples = replay.samples.slice(0, count);
    const before = JSON.stringify(replay);
    assert.equal(validateReplay(replay), replay);
    assert.deepEqual(parseReplay(before), replay);
    assert.equal(JSON.stringify(replay), before);
  }
  for (const count of [0, 1]) {
    const legacy = recording();
    legacy.samples = legacy.samples.slice(0, count);
    assert.throws(() => validateReplay(legacy), /не менее двух/);
  }
});

test("observation metadata requires a finite positive policy and an explicit valid start", () => {
  for (const mutate of [
    (r) => (r.recording = null),
    (r) => (r.recording = []),
    (r) => (r.recording.pose_source = "synthetic"),
    (r) => delete r.recording.pose_source,
    (r) => delete r.recording.max_interpolation_gap_sec,
    (r) => delete r.world.start,
    (r) => (r.world.start = null),
    (r) => (r.world.start.x = Infinity),
    (r) => (r.world.start.y = "0"),
    (r) => delete r.world.start.z,
    (r) => (r.samples = null),
  ]) {
    const replay = observedRecording();
    mutate(replay);
    assert.throws(() => validateReplay(replay));
  }
  for (const invalid of [0, -1, NaN, Infinity, "1", true, null]) {
    const replay = observedRecording();
    replay.recording.max_interpolation_gap_sec = invalid;
    assert.throws(() => validateReplay(replay));
  }
});

test("observed timestamps are strictly increasing while legacy duplicate behavior remains", () => {
  for (const firstTime of [0, 2]) {
    const replay = observedRecording();
    replay.samples[0].t = firstTime;
    replay.samples[1].t = firstTime;
    assert.throws(() => validateReplay(replay), /Временные метки/);
    delete replay.recording;
    assert.equal(validateReplay(replay), replay);
  }
});

test("alignment compares configured starts independently of first feedback and gap policy", () => {
  const candidate = observedRecording();
  candidate.samples = [];
  const baseline = observedRecording();
  baseline.recording.max_interpolation_gap_sec = 0.25;
  baseline.samples = [baseline.samples[1]];
  assert.equal(alignmentNotice(candidate, baseline), null);
  assert.equal(alignmentNotice(candidate, recording()), null);
  assert.equal(importedSession(candidate, baseline, "candidate", "baseline").gate, null);
  baseline.world.start.x = 1;
  assert.match(alignmentNotice(candidate, baseline), /start/);
});

test("trajectory bounds include configured start and goal when observations are absent", () => {
  const replay = observedRecording();
  replay.samples = [];
  replay.world.start = { x: -20, y: 10, z: 0 };
  replay.world.goal = { x: 30, y: -40, z: 0 };
  const bounds = trajectoryBounds([replay]);
  assert.ok(bounds.minX < -20 && bounds.maxX > 30);
  assert.ok(bounds.minY < -40 && bounds.maxY > 10);
});
