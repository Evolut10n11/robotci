/** Offline reference-pose rendering. No code execution, URL loading or simulated motion. */
import * as THREE from "three";
import { OBJLoader } from "three/addons/loaders/OBJLoader.js";
import { STLLoader } from "three/addons/loaders/STLLoader.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";

export const MAX_MESH_BYTES = 24 * 1024 * 1024;
export const MAX_MESH_TRIANGLES = 2_000_000;
const vector = (a) => new THREE.Vector3(...a);

export function normalizeLocalPath(path) {
  if (typeof path !== "string" || !path || path.includes("\\") || path.startsWith("/") || /[\x00-\x1f]/.test(path))
    throw new Error("Нужен относительный путь к локальному файлу.");
  if (path.startsWith("package://")) path = path.slice(10);
  if (path.includes(":")) throw new Error("Загрузка сетевых файлов запрещена.");
  const parts = [];
  for (const part of path.split("/")) {
    if (!part || part === ".") continue;
    if (part === "..") {
      if (!parts.length) throw new Error("Путь выходит за пределы выбранного набора файлов.");
      parts.pop();
    } else parts.push(part);
  }
  return parts.join("/");
}

export function resolveLocalMesh(path, files, base = "") {
  const packagePath = path.startsWith("package://");
  const target = normalizeLocalPath(packagePath ? path : `${base}${base ? "/" : ""}${path}`);
  if (files.has(target)) return files.get(target);
  // A selected folder may contain a ROS package under a different top-level name.
  // Never choose one of several identically named candidates by accident.
  const suffix = packagePath ? normalizeLocalPath(path).split("/").slice(1).join("/") : target;
  const matches = [...files].filter(([key]) => key === suffix || key.endsWith(`/${suffix}`));
  return matches.length === 1 ? matches[0][1] : null;
}

export function disposeModel(root) {
  const geometries = new Set(), materials = new Set();
  root?.traverse((node) => {
    if (node.geometry) geometries.add(node.geometry);
    const ms = Array.isArray(node.material) ? node.material : [node.material];
    ms.filter(Boolean).forEach((m) => materials.add(m));
  });
  geometries.forEach((g) => g.dispose());
  materials.forEach((m) => m.dispose());
}

export function cloneReferenceModel(template, ghost = false) {
  const root = template.clone(true);
  root.traverse((node) => {
    if (node.geometry) node.geometry = node.geometry.clone();
    if (node.material) {
      const clone = (m) => {
        const result = m.clone();
        if (ghost) { result.transparent = true; result.opacity = 0.24; result.depthWrite = false; }
        return result;
      };
      node.material = Array.isArray(node.material) ? node.material.map(clone) : clone(node.material);
    }
    if (node.isMesh) { node.castShadow = !ghost; node.receiveShadow = !ghost; }
  });
  return root;
}

function geometry(shape) {
  const size = shape.size;
  switch (shape.type) {
    case "box": return new THREE.BoxGeometry(...size);
    case "sphere": return new THREE.SphereGeometry(size[0], 20, 12);
    case "ellipsoid": {
      const g = new THREE.SphereGeometry(1, 20, 12); g.scale(...size.map((v) => v / 2)); return g;
    }
    case "cylinder": {
      const g = new THREE.CylinderGeometry(size[0], size[0], size[1], 24); g.rotateX(Math.PI / 2); return g;
    }
    case "capsule": {
      const g = new THREE.CapsuleGeometry(size[0], size[1], 6, 16); g.rotateX(Math.PI / 2); return g;
    }
    default: throw new Error("Неизвестная геометрия.");
  }
}

function checkGeometry(object) {
  let triangles = 0;
  object.traverse((node) => {
    if (!node.geometry) return;
    const positions = node.geometry.attributes.position;
    if (!positions || !positions.array.every(Number.isFinite)) throw new Error("Меш содержит неверные координаты.");
    triangles += (node.geometry.index?.count ?? positions.count) / 3;
  });
  if (triangles > MAX_MESH_TRIANGLES) throw new Error("Меш превышает лимит сложности.");
  return triangles;
}

/** Caller-supplied files are in-memory File-like objects, not filesystem paths. */
export async function createDescribedRobot(description, { files = new Map(), base = "", useCatalog = true } = {}) {
  if (description?.schema_version !== 1 || description.visual_only !== true || !Array.isArray(description.nodes))
    throw new Error("Неподдерживаемое описание модели.");
  if (useCatalog && description.catalog_asset && description.model_id) {
    if (!/^(unitree_go2|unitree_g1|franka_emika_panda)$/.test(description.model_id))
      throw new Error("Неизвестная встроенная модель.");
    const response = await fetch(`/api/robot-model/asset/${description.model_id}`);
    if (!response.ok) throw new Error("Встроенная геометрия не установлена.");
    const bytes = await response.arrayBuffer();
    if (bytes.byteLength > 64 * 1024 * 1024) throw new Error("Слишком большой файл модели.");
    const data = await new GLTFLoader().parseAsync(bytes, "");
    const root = data.scene;
    const bounds = new THREE.Box3().setFromObject(root);
    root.userData = { ...root.userData, height: bounds.max.z - bounds.min.z, visualOnly: true,
      source: "catalog", missingMeshes: [], modelId: description.model_id };
    return root;
  }
  const root = new THREE.Group(), hierarchy = new THREE.Group();
  root.add(hierarchy);
  root.name = `description-${description.name}`;
  root.userData = { visualOnly: true, source: "description", missingMeshes: [], triangles: 0 };
  const nodes = new Map(), attachment = new Map(), cache = new Map();
  try {
    for (const node of description.nodes) {
      const group = new THREE.Group(); group.name = node.name;
      group.position.fromArray(node.pos); group.quaternion.fromArray(node.quat);
      nodes.set(node.name, group);
      let tail = group;
      for (const joint of node.joints) {
        const pivot = new THREE.Group(), rotation = new THREE.Group(), unpivot = new THREE.Group();
        pivot.position.fromArray(joint.pos); unpivot.position.copy(pivot.position).negate();
        const q = joint.value - joint.ref;
        if (joint.type === "prismatic") rotation.position.copy(vector(joint.axis)).multiplyScalar(q);
        else rotation.quaternion.setFromAxisAngle(vector(joint.axis), q);
        rotation.name = `joint:${joint.name}`;
        rotation.userData = { joint: joint.name, value: joint.value, limits: joint.range };
        tail.add(pivot); pivot.add(rotation); rotation.add(unpivot); tail = unpivot;
      }
      tail.userData.linkFrame = node.name;
      attachment.set(node.name, tail);
    }
    for (const node of description.nodes) {
      const group = nodes.get(node.name), tail = attachment.get(node.name);
      (node.parent === null ? hierarchy : attachment.get(node.parent)).add(group);
      const preferred = node.visuals.filter((shape) => !shape.collision);
      const shapes = preferred.length ? preferred : node.visuals;
      let missing = false, shown = false;
      for (const shape of shapes) {
        let object;
        if (shape.type === "mesh") {
          const file = resolveLocalMesh(shape.file, files, base);
          if (!file) { root.userData.missingMeshes.push(shape.file); missing = true; continue; }
          if (file.size > MAX_MESH_BYTES) throw new Error("Файл меша превышает 24 МиБ.");
          let template = cache.get(file);
          if (!template) {
            const extension = shape.file.split(".").pop().toLowerCase();
            if (extension === "obj") template = new OBJLoader().parse(await file.text());
            else if (extension === "stl") template = new THREE.Mesh(new STLLoader().parse(await file.arrayBuffer()));
            else { root.userData.missingMeshes.push(shape.file); missing = true; continue; }
            checkGeometry(template); cache.set(file, template);
          }
          object = template.clone(true);
          object.traverse((n) => { if (n.geometry) n.geometry = n.geometry.clone(); });
          object.scale.fromArray(shape.scale);
        } else object = new THREE.Mesh(geometry(shape));
        object.position.fromArray(shape.pos); object.quaternion.fromArray(shape.quat);
        const [r, g, b, alpha] = shape.rgba;
        const material = new THREE.MeshStandardMaterial({
          color: new THREE.Color().setRGB(r, g, b, THREE.SRGBColorSpace),
          roughness: 0.48, metalness: 0.25, transparent: alpha < 1, opacity: alpha,
        });
        object.traverse((n) => { if (n.isMesh) { n.material = material; n.castShadow = true; n.receiveShadow = true; } });
        tail.add(object); shown = true;
      }
      if (missing) {
        const fallback = node.visuals.filter((s) => s.collision && s.type !== "mesh");
        for (const shape of fallback) {
          const object = new THREE.Mesh(geometry(shape), new THREE.MeshStandardMaterial({ color: "#daa350", wireframe: true }));
          object.position.fromArray(shape.pos); object.quaternion.fromArray(shape.quat);
          tail.add(object); shown = true;
        }
      }
      if (!shown) {
        const marker = new THREE.Mesh(new THREE.SphereGeometry(0.018, 12, 8), new THREE.MeshStandardMaterial({ color: "#daa350" }));
        tail.add(marker);
      }
    }
    if (root.userData.missingMeshes.length) {
      for (const node of description.nodes.filter((n) => n.parent !== null)) {
        const p = vector(node.pos), length = p.length();
        if (length < 1e-6) continue;
        const rod = new THREE.Mesh(new THREE.CylinderGeometry(0.006, 0.006, length, 8),
          new THREE.MeshStandardMaterial({ color: "#daa350", transparent: true, opacity: 0.5 }));
        rod.position.copy(p).multiplyScalar(0.5);
        rod.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), p.normalize());
        attachment.get(node.parent).add(rod);
      }
    }
    root.updateMatrixWorld(true);
    root.userData.referenceFrames = {};
    for (const [name, frame] of attachment) {
      const pos = new THREE.Vector3(), quat = new THREE.Quaternion(), scale = new THREE.Vector3();
      frame.matrixWorld.decompose(pos, quat, scale);
      root.userData.referenceFrames[name] = { position: pos.toArray(), quaternion_xyzw: quat.toArray() };
    }
    root.userData.triangles = checkGeometry(root);
    const bounds = new THREE.Box3().setFromObject(root);
    if (bounds.isEmpty() || ![...bounds.min, ...bounds.max].every(Number.isFinite)) throw new Error("Геометрия пуста или не конечна.");
    const size = bounds.getSize(new THREE.Vector3());
    if (Math.max(...size) > 100 || size.length() < 0.001) throw new Error("Проверьте единицы и размеры модели.");
    // Replay z is a visual anchor. Reference model is grounded, not identified as measured joint pose.
    hierarchy.position.z -= bounds.min.z;
    root.userData.height = size.z;
    root.userData.dimensions = size.toArray();
    root.userData.missingMeshes = [...new Set(root.userData.missingMeshes)];
    root.updateMatrixWorld(true);
    return root;
  } catch (error) { disposeModel(root); throw error; }
  finally { cache.forEach(disposeModel); }
}
