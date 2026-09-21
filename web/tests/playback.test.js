import test from "node:test";
import assert from "node:assert/strict";
import { sampleAt } from "../src/playback.js";

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
