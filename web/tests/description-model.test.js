import test from "node:test";
import assert from "node:assert/strict";
import * as THREE from "three";
import { createDescribedRobot, cloneReferenceModel, disposeModel, normalizeLocalPath, resolveLocalMesh } from "../src/description-model.js";
const description = () => ({ schema_version: 1, visual_only: true, name: "test", nodes: [
  { name: "base", parent: null, pos: [0, 0, 0], quat: [0, 0, 0, 1], joints: [], visuals: [
    { type: "box", size: [.4, .2, .1], pos: [0, 0, 0], quat: [0, 0, 0, 1], rgba: [.7, .7, .7, 1] },
  ] },
  { name: "arm", parent: "base", pos: [0, 0, .1], quat: [0, 0, 0, 1], joints: [
    { name: "axis", axis: [0, 1, 0], pos: [0, 0, 0], type: "revolute", value: Math.PI / 2, ref: 0, range: [-Math.PI, Math.PI] },
  ], visuals: [{ type: "box", size: [.05, .05, .3], pos: [0, 0, .15], quat: [0, 0, 0, 1], rgba: [.3, .5, .8, 1] }] },
] });

test("reference model keeps real geometry dimensions and joint reference transform", async () => {
  const d = description(), before = JSON.stringify(d), robot = await createDescribedRobot(d);
  const bounds = new THREE.Box3().setFromObject(robot);
  assert.ok(Math.abs(bounds.min.z) < 1e-9);
  assert.ok(Math.abs(bounds.max.x - .3) < 1e-6);
  assert.equal(JSON.stringify(d), before);
  assert.equal(robot.userData.visualOnly, true);
  disposeModel(robot);
});
test("missing meshes are explicit and cannot turn into a guessed branded robot", async () => {
  const d = description(); d.nodes[0].visuals[0] = { type: "mesh", file: "missing.obj", scale: [1, 1, 1], pos: [0, 0, 0], quat: [0, 0, 0, 1], rgba: [1, 1, 1, 1] };
  const robot = await createDescribedRobot(d);
  assert.deepEqual(robot.userData.missingMeshes, ["missing.obj"]);
  assert.equal(robot.userData.modelId, undefined); disposeModel(robot);
});
test("local OBJ geometry loads from explicit files without fetch", async () => {
  const old = globalThis.fetch; globalThis.fetch = () => { throw new Error("Network forbidden"); };
  try {
    const d = description(); d.nodes[0].visuals[0] = { type: "mesh", file: "package://myrobot/meshes/body.obj", scale: [1, 1, 1], pos: [0, 0, 0], quat: [0, 0, 0, 1], rgba: [1, 1, 1, 1] };
    const robot = await createDescribedRobot(d, { files: new Map([["upload/meshes/body.obj", { size: 50, text: async () => "v 0 0 0\nv .1 0 0\nv 0 .1 0\nf 1 2 3" }]]) });
    assert.deepEqual(robot.userData.missingMeshes, []); disposeModel(robot);
  } finally { globalThis.fetch = old; }
});
test("clones do not dispose cached template geometry or materials", async () => {
  const robot = await createDescribedRobot(description()), copy = cloneReferenceModel(robot, true);
  const materials = new Set(); robot.traverse((n) => { if (n.material) materials.add(n.material); });
  copy.traverse((n) => { if (n.isMesh) { assert.equal(n.material.depthWrite, false); assert.ok(!materials.has(n.material)); } });
  const before = new THREE.Box3().setFromObject(robot);
  disposeModel(copy); assert.deepEqual(new THREE.Box3().setFromObject(robot), before); disposeModel(robot);
});
test("path resolution does not guess between duplicate mesh names", () => {
  const files = new Map([["one/meshes/x.obj", {}], ["two/meshes/x.obj", {}]]);
  assert.equal(resolveLocalMesh("package://robot/meshes/x.obj", files), null);
  assert.equal(resolveLocalMesh("meshes/x.obj", files, "one"), files.get("one/meshes/x.obj"));
});
for (const path of ["https://evil/x.obj", "file:///x.obj", "../../x.obj", "C:\\x.obj", "/x.obj", "x\u0000.obj"])
  test(`unsafe path rejected: ${JSON.stringify(path)}`, () => assert.throws(() => normalizeLocalPath(path)));
