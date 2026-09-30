import test from "node:test";
import assert from "node:assert/strict";
import { sampleAt, poseAt, recordingGaps, trajectorySegments } from "../src/playback.js";

const pose = (t, x, yaw = 0) => ({
  t,
  position: { x, y: x * 2, z: x / 2 },
  orientation: { yaw },
});

test("clamps to recorded poses outside the sample interval", () => {
  const samples = [pose(2, 0), pose(4, 2)];
  assert.equal(sampleAt(samples, 0), samples[0]);
  assert.equal(sampleAt(samples, 8), samples[1]);
  assert.equal(sampleAt([samples[0]], 3), samples[0]);
});

test("interpolates irregular timestamps and takes the short yaw arc", () => {
  const samples = [
    pose(0, 0),
    pose(2, 2, Math.PI * 0.9),
    pose(6, 6, -Math.PI * 0.9),
  ];
  const middle = sampleAt(samples, 4);
  assert.deepEqual(middle.position, { x: 4, y: 8, z: 2 });
  assert.ok(Math.abs(middle.orientation.yaw - Math.PI) < 1e-12);
  assert.deepEqual(sampleAt(samples, 2), samples[1]);
});

test("seeks long recordings without scanning every pose", () => {
  let reads = 0;
  const samples = new Proxy(
    Array.from({ length: 100000 }, (_, i) => pose(i, i)),
    {
      get(target, key) {
        if (/^\d+$/.test(String(key))) reads++;
        return Reflect.get(target, key);
      },
    },
  );
  assert.equal(sampleAt(samples, 98765.5).position.x, 98765.5);
  assert.ok(reads < 30, `expected logarithmic lookup, got ${reads} reads`);
});

const observed = (samples, duration = 10, threshold = 1) => ({
  samples,
  duration_sec: duration,
  recording: { pose_source: "observed", max_interpolation_gap_sec: threshold },
});

test("only interpolates between close observed samples and preserves exact endpoints", () => {
  const samples = [pose(1, 1), pose(2, 2), pose(5, 5), pose(5.5, 6)];
  const replay = observed(samples);
  for (const sample of samples) {
    assert.deepEqual(poseAt(replay, sample.t), {
      pose: sample, kind: "observed", lastObserved: sample, gap: null,
    });
    assert.equal(poseAt(replay, sample.t).pose, sample);
  }
  assert.deepEqual(poseAt(replay, 0), {
    pose: null, kind: "missing", lastObserved: null, gap: { start: 0, end: 1 },
  });
  const between = poseAt(replay, 1.5);
  assert.equal(between.kind, "interpolated");
  assert.equal(between.pose.position.x, 1.5);
  assert.equal(between.lastObserved, samples[0]);
  assert.deepEqual(poseAt(replay, 3), {
    pose: null, kind: "missing", lastObserved: samples[1], gap: { start: 2, end: 5 },
  });
  for (const time of [5.5001, 10, 11]) {
    assert.deepEqual(poseAt(replay, time), {
      pose: null, kind: "missing", lastObserved: samples[3],
      gap: time <= replay.duration_sec ? { start: 5.5, end: 10 } : null,
    });
  }
  assert.deepEqual(recordingGaps(replay), [
    { start: 0, end: 1 }, { start: 2, end: 5 }, { start: 5.5, end: 10 },
  ]);
});

test("interpolation threshold is inclusive and belongs to each recording", () => {
  const samples = [pose(0, 0), pose(1, 1)];
  const baseline = observed(samples, 1, 1);
  const candidate = observed(samples, 1, 0.9);
  assert.equal(poseAt(baseline, 0.5).kind, "interpolated");
  assert.equal(poseAt(candidate, 0.5).kind, "missing");
  assert.deepEqual(recordingGaps(baseline), []);
  assert.deepEqual(recordingGaps(candidate), [{ start: 0, end: 1 }]);
  assert.deepEqual(trajectorySegments(baseline), [samples]);
  assert.deepEqual(trajectorySegments(candidate), [[samples[0]], [samples[1]]]);
});

test("decimal threshold boundaries agree across poses, gaps and trajectory segments", () => {
  for (const [end, missing] of [[2.003, false], [2.004, true]]) {
    const samples = [pose(1.003, 1), pose(end, 2)];
    const replay = observed(samples, end);
    const state = poseAt(replay, 1.5);
    assert.equal(state.kind, missing ? "missing" : "interpolated");
    assert.deepEqual(state.gap, missing ? { start: 1.003, end } : null);
    assert.deepEqual(recordingGaps(replay), missing
      ? [{ start: 0, end: 1.003 }, { start: 1.003, end }]
      : [{ start: 0, end: 1.003 }]);
    assert.deepEqual(trajectorySegments(replay), missing
      ? [[samples[0]], [samples[1]]] : [samples]);
  }
});

test("gap tolerance is floating-point scale rather than a fixed time allowance", () => {
  const samples = [pose(0, 0), pose(1.000001e-9, 1)];
  const replay = observed(samples, samples[1].t, 1e-9);
  assert.equal(poseAt(replay, 0.5e-9).kind, "missing");
  assert.deepEqual(recordingGaps(replay), [{ start: 0, end: samples[1].t }]);
  assert.deepEqual(trajectorySegments(replay), [[samples[0]], [samples[1]]]);
});

test("closely spaced observed timestamps use their true interval and shortest yaw arc", () => {
  const replay = observed([pose(0, 0, Math.PI * 0.9), pose(0.00001, 2, -Math.PI * 0.9)]);
  const middle = poseAt(replay, 0.000005);
  assert.equal(middle.kind, "interpolated");
  assert.equal(middle.pose.position.x, 1);
  assert.ok(Math.abs(middle.pose.orientation.yaw - Math.PI) < 1e-12);
});

test("empty and singleton observed recordings do not invent poses or a travelled path", () => {
  const empty = observed([]);
  assert.deepEqual(poseAt(empty, 4), {
    pose: null, kind: "missing", lastObserved: null, gap: { start: 0, end: 10 },
  });
  assert.deepEqual(recordingGaps(empty), [{ start: 0, end: 10 }]);
  assert.deepEqual(trajectorySegments(empty), []);
  const sample = pose(4, 2);
  const single = observed([sample]);
  assert.equal(poseAt(single, 3).pose, null);
  assert.equal(poseAt(single, 4).pose, sample);
  assert.equal(poseAt(single, 5).pose, null);
  assert.deepEqual(recordingGaps(single), [{ start: 0, end: 4 }, { start: 4, end: 10 }]);
  assert.deepEqual(trajectorySegments(single), [[sample]]);
});

test("observed seeking remains logarithmic at the end of a large recording", () => {
  let reads = 0;
  const samples = new Proxy(Array.from({ length: 250000 }, (_, i) => pose(i, i)), {
    get(target, key) {
      if (/^\d+$/.test(String(key))) reads++;
      return Reflect.get(target, key);
    },
  });
  assert.equal(poseAt(observed(samples, 250000), 249998.5).pose.position.x, 249998.5);
  assert.ok(reads < 50, `expected logarithmic lookup, got ${reads} reads`);
});

test("legacy playback retains clamping and interpolation without claiming observations", () => {
  const samples = [pose(2, 2), pose(8, 8)];
  const replay = { samples, duration_sec: 10 };
  for (const time of [0, 2, 4, 8, 10]) {
    assert.deepEqual(poseAt(replay, time), {
      pose: sampleAt(samples, time), kind: "legacy", lastObserved: null, gap: null,
    });
  }
  assert.deepEqual(recordingGaps(replay), []);
  assert.deepEqual(trajectorySegments(replay), [samples]);
});

test("thinning preserves gaps and endpoints with a global point budget", () => {
  const samples = Array.from({ length: 100 }, (_, i) => pose(i / 10, i));
  samples.push(...Array.from({ length: 100 }, (_, i) => pose(30 + i / 10, i + 100)));
  const replay = observed(samples, 40);
  const before = JSON.stringify(replay);
  const segments = trajectorySegments(replay, 12);
  assert.equal(segments.length, 2);
  assert.ok(segments.reduce((sum, segment) => sum + segment.length, 0) <= 12);
  assert.equal(segments[0][0], samples[0]);
  assert.equal(segments[0].at(-1), samples[99]);
  assert.equal(segments[1][0], samples[100]);
  assert.equal(segments[1].at(-1), samples[199]);
  assert.ok(segments[0].every((sample) => sample.t < 10));
  assert.ok(segments[1].every((sample) => sample.t >= 30));
  assert.equal(JSON.stringify(replay), before);
});

test("250000 disjoint observations cannot create unbounded display geometry", () => {
  const samples = Array.from({ length: 250000 }, (_, i) => pose(i * 2, i));
  const segments = trajectorySegments(observed(samples, 500000));
  assert.ok(segments.length <= 6000);
  assert.ok(segments.every((segment) => segment.length === 1));
  assert.equal(segments[0][0], samples[0]);
  assert.equal(segments.at(-1)[0], samples.at(-1));
});

test("many short intervals can be omitted without joining unrelated observations", () => {
  const samples = Array.from({ length: 10000 }, (_, i) => pose(Math.floor(i / 2) * 3 + i % 2, i));
  const segments = trajectorySegments(observed(samples, 15000), 24);
  assert.ok(segments.reduce((sum, segment) => sum + segment.length, 0) <= 24);
  assert.ok(segments.every((segment) => segment.length === 2 && segment[1].t - segment[0].t === 1));
  assert.equal(segments[0][0], samples[0]);
  assert.equal(segments.at(-1).at(-1), samples.at(-1));
});
