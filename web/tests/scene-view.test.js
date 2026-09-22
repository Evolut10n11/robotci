import test from "node:test";
import assert from "node:assert/strict";
import * as THREE from "three";
import { SceneView } from "../src/scene-view.js";

const sample = (t, x) => ({ t, position: { x, y: 0, z: 0 }, orientation: { yaw: 0 } });
const recording = (samples, threshold = 1) => ({
  duration_sec: 12, samples,
  recording: { pose_source: "observed", max_interpolation_gap_sec: threshold },
});

test("3D hides only the robot without observations and resumes at the actual next pose", () => {
  const samples = [sample(1, 1), sample(2, 2), sample(8, 8), sample(9, 9)];
  const candidate = new THREE.Group(), baseline = new THREE.Group();
  const view = {
    robots: [
      { replay: recording(samples), robot: candidate },
      { replay: recording(samples, 10), robot: baseline },
    ],
    render() {},
  };
  SceneView.prototype.setTime.call(view, 1.5);
  assert.equal(candidate.visible, true);
  assert.equal(candidate.position.x, 1.5);
  SceneView.prototype.setTime.call(view, 5);
  assert.equal(candidate.visible, false);
  assert.equal(candidate.position.x, 1.5); // Never move to a fabricated position.
  assert.equal(baseline.visible, true);
  assert.equal(baseline.position.x, 5);
  SceneView.prototype.setTime.call(view, 8);
  assert.equal(candidate.visible, true);
  assert.equal(candidate.position.x, 8);
  SceneView.prototype.setTime.call(view, 12);
  assert.equal(candidate.visible, false);
  assert.equal(baseline.visible, false);
});

test("empty 3D recording has no robot to focus or move", () => {
  const robot = new THREE.Group();
  const view = { robots: [{ source: "candidate", replay: recording([]), robot }], render() {} };
  SceneView.prototype.setTime.call(view, 0);
  assert.equal(robot.visible, false);
  // No camera is required: focusing an unknown position is deliberately a no-op.
  SceneView.prototype.focusRobot.call(view);
  SceneView.prototype.setTime.call(view, 12);
  assert.equal(robot.visible, false);
});
