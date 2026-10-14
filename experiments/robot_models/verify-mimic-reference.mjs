/** Verify the existing Three.js renderer uses the solved scalar joint values. */
import assert from "node:assert/strict";
import fs from "node:fs/promises";
import { createDescribedRobot, disposeModel } from "../../web/src/description-model.js";

const description = JSON.parse(await fs.readFile(process.argv[2], "utf8"));
const model = await createDescribedRobot(description, { useCatalog: false });
try {
  const expected = {
    base: [0, 0, 0],
    left_finger: [0, 0.020, 0.06],
    right_finger: [0, -0.020, 0.06],
  };
  const frames = model.userData.referenceFrames;
  for (const [name, position] of Object.entries(expected)) {
    assert.ok(frames[name], `Missing frame: ${name}`);
    frames[name].position.forEach((value, i) => {
      assert.ok(Math.abs(value - position[i]) <= 1e-12, `${name} coordinate ${i}`);
    });
    frames[name].quaternion_xyzw.forEach((value, i) => {
      assert.ok(Math.abs(value - [0, 0, 0, 1][i]) <= 1e-12, `${name} rotation ${i}`);
    });
  }
  assert.equal(model.userData.visualOnly, true);
  assert.deepEqual(model.userData.missingMeshes, []);
  console.log(JSON.stringify({ status: "PASS", frames, expected,
    note: "Actual Three.js reference transforms; static geometry, not a simulated grasp" }));
} finally { disposeModel(model); }
