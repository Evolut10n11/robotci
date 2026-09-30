import test from "node:test";
import assert from "node:assert/strict";
import * as THREE from "three";
import { createRobotModel } from "../src/robot-models.js";
import { SceneView } from "../src/scene-view.js";

const profiles = ["rover", "quadruped", "humanoid"];
const boundsOf = (model) => new THREE.Box3().setFromObject(model);

test("visual profiles produce finite, grounded geometry with distinct silhouettes", () => {
  const sizes = {};
  for (const profile of profiles) {
    const model = createRobotModel(profile);
    const bounds = boundsOf(model);
    sizes[profile] = bounds.getSize(new THREE.Vector3());
    assert.equal(model.userData.visualProfile, profile);
    assert.equal(model.userData.visualOnly, true);
    assert.ok(Math.abs(bounds.min.z) < 1e-6, `${profile} must stand on the pose origin`);
    assert.ok(bounds.max.z > 0.5 && bounds.max.z < 1.5);
    let triangles = 0;
    model.traverse((item) => {
      assert.ok(item.matrixWorld.elements.every(Number.isFinite));
      if (!item.isMesh) return;
      const positions = item.geometry.getAttribute("position");
      assert.ok(positions.array.every(Number.isFinite));
      triangles += (item.geometry.index?.count ?? positions.count) / 3 * (item.isInstancedMesh ? item.count : 1);
    });
    assert.ok(triangles < 100_000, `${profile} exceeds the small replay-model budget`);
  }
  assert.ok(sizes.rover.x > sizes.rover.z);
  assert.ok(sizes.quadruped.y < sizes.rover.y);
  assert.ok(sizes.humanoid.z > sizes.humanoid.y * 1.8);
  assert.ok(sizes.humanoid.z > sizes.rover.z * 1.4);
});

test("unknown and absent visual profiles retain the rover fallback", () => {
  const expected = boundsOf(createRobotModel("rover"));
  for (const profile of [undefined, null, "unknown", "__proto__"]) {
    const model = createRobotModel(profile);
    assert.equal(model.userData.visualProfile, "rover");
    assert.deepEqual(boundsOf(model), expected);
  }
});

test("baseline ghosts preserve geometry and never occlude candidate depth", () => {
  for (const profile of profiles) {
    const model = createRobotModel(profile);
    const ghost = createRobotModel(profile, { ghost: true });
    assert.deepEqual(boundsOf(ghost), boundsOf(model));
    ghost.traverse((item) => {
      if (!item.isMesh) return;
      assert.equal(item.material.transparent, true);
      assert.equal(item.material.depthWrite, false);
      assert.ok(item.material.opacity > 0 && item.material.opacity < 0.5);
      assert.equal(item.castShadow, false);
    });
  }
});

test("scene cleanup tolerates partial initialization and releases shared resources once", () => {
  assert.doesNotThrow(() => SceneView.prototype.dispose.call({}));
  const scene = new THREE.Scene();
  const geometry = new THREE.BoxGeometry();
  const texture = new THREE.Texture();
  const material = new THREE.MeshBasicMaterial({ map: texture });
  const disposed = { geometry: 0, material: 0, texture: 0 };
  for (const [name, resource] of Object.entries({ geometry, material, texture })) {
    resource.addEventListener("dispose", () => disposed[name]++);
  }
  scene.add(new THREE.Mesh(geometry, material), new THREE.Mesh(geometry, material));
  SceneView.prototype.dispose.call({ scene });
  assert.deepEqual(disposed, { geometry: 1, material: 1, texture: 1 });
});
