import * as THREE from "three";
import { RoundedBoxGeometry } from "three/addons/geometries/RoundedBoxGeometry.js";

// Presentation models, in metres: +X forward, +Z up, contact points at z = 0.
// These silhouettes describe a visual profile, never a robot's collision model
// or recorded joint state. Their parts remain static during pose playback.
const PROFILES = new Set(["rover", "quadruped", "humanoid"]);
const UP = new THREE.Vector3(0, 1, 0);

export function createRobotModel(profile, { color = "#426cff", ghost = false } = {}) {
  const visualProfile = PROFILES.has(profile) ? profile : "rover";
  const root = new THREE.Group();
  root.name = `robot-${visualProfile}${ghost ? "-baseline" : ""}`;
  root.userData.visualProfile = visualProfile;
  root.userData.visualOnly = true;
  const materials = {};
  const material = (name, hex, metalness = 0, roughness = 0.4) => {
    materials[name] = new THREE.MeshStandardMaterial({
      color: ghost ? "#93a4b9" : hex,
      metalness: ghost ? 0.12 : metalness,
      roughness: ghost ? 0.7 : roughness,
      transparent: ghost,
      opacity: ghost ? 0.25 : 1,
      depthWrite: !ghost,
    });
    return materials[name];
  };
  material("shell", "#eceee9", 0.26, 0.31);
  material("edge", "#c7cdd0", 0.62, 0.3);
  material("frame", "#333d47", 0.6, 0.35);
  material("rubber", "#151d24", 0.02, 0.88);
  material("glass", "#0c222f", 0.64, 0.17);
  material("accent", color, 0.42, 0.26);
  material("light", "#b6e4ff", 0.1, 0.23);
  if (!ghost) {
    materials.accent.emissive.set(color);
    materials.accent.emissiveIntensity = 0.16;
    materials.light.emissive.set("#81c9ff");
    materials.light.emissiveIntensity = 0.7;
  }
  const geometryCache = new Map();
  const geometry = (key, build) => {
    if (!geometryCache.has(key)) geometryCache.set(key, build());
    return geometryCache.get(key);
  };
  const mesh = (name, shape, surface, position, parent = root) => {
    const item = new THREE.Mesh(shape, materials[surface]);
    item.name = name;
    item.position.set(...position);
    item.castShadow = !ghost;
    item.receiveShadow = !ghost;
    parent.add(item);
    return item;
  };
  const box = (name, size, position, surface = "shell", radius = 0.015) =>
    mesh(name, geometry(`box:${size}:${radius}`, () => new RoundedBoxGeometry(
      ...size, 2, Math.min(radius, ...size.map((v) => v / 3)),
    )), surface, position);
  const cylinder = (name, radius, length, position, surface = "frame", axis = "y", segments = 20) => {
    const item = mesh(name, geometry(`cylinder:${radius}:${length}:${segments}`, () =>
      new THREE.CylinderGeometry(radius, radius, length, segments)), surface, position);
    if (axis === "x") item.rotation.z = -Math.PI / 2;
    if (axis === "z") item.rotation.x = Math.PI / 2;
    return item;
  };
  const link = (name, from, to, radius, surface = "frame") => {
    const a = new THREE.Vector3(...from), b = new THREE.Vector3(...to);
    const length = a.distanceTo(b);
    const item = cylinder(name, radius, length, a.clone().add(b).multiplyScalar(0.5).toArray(), surface);
    item.quaternion.setFromUnitVectors(UP, b.sub(a).normalize());
    return item;
  };
  const panelLink = (name, from, to, width, depth, surface = "shell") => {
    const a = new THREE.Vector3(...from), b = new THREE.Vector3(...to);
    const item = box(name, [depth, width, a.distanceTo(b)], a.clone().add(b).multiplyScalar(0.5).toArray(), surface);
    item.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), b.sub(a).normalize());
    return item;
  };
  const lens = (name, x, y, z, radius = 0.026) => {
    cylinder(`${name}-rim`, radius * 1.3, 0.017, [x, y, z], "edge", "x");
    cylinder(name, radius, 0.019, [x + 0.003, y, z], "glass", "x");
    cylinder(`${name}-optic`, radius * 0.38, 0.020, [x + 0.005, y, z], "accent", "x", 16);
  };
  const lidar = (x, z, radius = 0.07) => {
    cylinder("lidar-pedestal", radius * 0.42, 0.065, [x, 0, z - 0.075], "frame", "z");
    cylinder("lidar-base", radius * 1.05, 0.025, [x, 0, z - 0.034], "edge", "z");
    cylinder("lidar-optical-band", radius, 0.055, [x, 0, z], "glass", "z", 32);
    cylinder("lidar-signal-ring", radius * 1.005, 0.006, [x, 0, z + 0.019], "accent", "z", 32);
    cylinder("lidar-cap", radius * 1.04, 0.022, [x, 0, z + 0.036], "shell", "z", 32);
  };

  if (visualProfile === "rover") {
    box("underbody", [0.66, 0.35, 0.12], [0, 0, 0.25], "frame", 0.025);
    box("armored-chassis", [0.69, 0.42, 0.24], [0, 0, 0.405], "shell", 0.04);
    box("top-service-panel", [0.43, 0.34, 0.025], [-0.04, 0, 0.532], "edge");
    box("deck-inset", [0.35, 0.27, 0.016], [-0.04, 0, 0.546], "frame");
    box("sensor-face", [0.04, 0.325, 0.112], [0.356, 0, 0.432], "rubber", 0.012);
    lens("left-stereo-camera", 0.385, -0.094, 0.439);
    lens("right-stereo-camera", 0.385, 0.094, 0.439);
    box("front-status-light", [0.016, 0.064, 0.011], [0.384, 0, 0.444], "light", 0.003);
    box("front-skid-plate", [0.042, 0.28, 0.10], [0.36, 0, 0.313], "edge");
    for (const side of [-1, 1]) {
      box("side-armor", [0.38, 0.025, 0.15], [-0.04, side * 0.218, 0.408], "shell");
      box("side-status-strip", [0.24, 0.010, 0.014], [-0.015, side * 0.234, 0.453], "accent", 0.004);
      for (const x of [-0.18, 0.18]) {
        cylinder("panel-fastener", 0.008, 0.028, [x, side * 0.224, 0.369], "frame", "y", 8);
      }
      link("side-protection-rail", [-0.28, side * 0.253, 0.293], [0.29, side * 0.253, 0.293], 0.012);
    }
    for (const x of [-0.29, 0.29]) {
      link("axle", [x, -0.3, 0.171], [x, 0.3, 0.171], 0.023);
      for (const side of [-1, 1]) {
        const y = side * 0.296;
        cylinder("all-terrain-tire", 0.151, 0.124, [x, y, 0.163], "rubber", "y", 32);
        cylinder("wheel-rim", 0.086, 0.009, [x, y + side * 0.065, 0.163], "edge");
        cylinder("wheel-hub", 0.061, 0.012, [x, y + side * 0.071, 0.163], "frame");
        cylinder("hub-cap", 0.023, 0.016, [x, y + side * 0.079, 0.163], "accent");
        link("suspension-arm", [x * 0.57, side * 0.16, 0.278], [x, y, 0.163], 0.024, "frame");
        link("suspension-piston", [x * 0.75, side * 0.218, 0.348], [x, side * 0.253, 0.178], 0.012, "edge");
        box("wheel-arch", [0.23, 0.145, 0.027], [x, side * 0.266, 0.347], "frame");
      }
    }
    // Instanced treads retain the silhouette without hundreds of draw calls.
    const treadGeometry = geometry("treads", () => new THREE.BoxGeometry(0.047, 0.126, 0.019));
    const treads = new THREE.InstancedMesh(treadGeometry, materials.rubber, 4 * 24);
    treads.name = "tire-tread-blocks";
    treads.castShadow = !ghost;
    const matrix = new THREE.Object3D();
    let index = 0;
    for (const x of [-0.29, 0.29]) for (const y of [-0.296, 0.296]) {
      for (let i = 0; i < 24; i++) {
        const angle = i / 24 * Math.PI * 2;
        matrix.position.set(x + Math.sin(angle) * 0.153, y, 0.163 + Math.cos(angle) * 0.153);
        matrix.rotation.set(0, angle, 0);
        matrix.updateMatrix();
        treads.setMatrixAt(index++, matrix.matrix);
      }
    }
    root.add(treads);
    for (const x of [-0.40, 0.41]) {
      link("bumper", [x, -0.185, 0.275], [x, 0.185, 0.275], 0.016);
      for (const y of [-0.185, 0.185]) {
        link("bumper-mount", [x * 0.8, y, 0.245], [x, y, 0.275], 0.014);
      }
    }
    lidar(-0.11, 0.661, 0.072);
    box("roof-camera-mount", [0.085, 0.105, 0.055], [0.17, 0, 0.569], "frame");
    lens("roof-camera", 0.218, 0, 0.573, 0.017);
    cylinder("antenna-base", 0.023, 0.035, [-0.26, 0.142, 0.555], "rubber", "z");
    cylinder("antenna", 0.006, 0.15, [-0.26, 0.142, 0.643], "frame", "z", 10);
  } else if (visualProfile === "quadruped") {
    box("body-core", [0.55, 0.24, 0.125], [0, 0, 0.465], "frame", 0.035);
    box("dorsal-shell", [0.61, 0.245, 0.145], [0, 0, 0.501], "shell", 0.04);
    box("battery-panel", [0.39, 0.175, 0.026], [-0.025, 0, 0.581], "frame");
    box("front-visor", [0.038, 0.207, 0.072], [0.306, 0, 0.511], "glass", 0.016);
    lens("left-camera", 0.33, -0.062, 0.51, 0.018);
    lens("right-camera", 0.33, 0.062, 0.51, 0.018);
    box("front-light", [0.015, 0.12, 0.008], [0.328, 0, 0.553], "accent", 0.002);
    lidar(-0.125, 0.65, 0.047);
    for (const side of [-1, 1]) {
      box("flank-accent", [0.24, 0.011, 0.019], [0, side * 0.127, 0.517], "accent", 0.004);
      for (const front of [-1, 1]) {
        const hip = [front * 0.223, side * 0.168, 0.463];
        const knee = [front * 0.327, side * 0.216, 0.262];
        const ankle = [front * 0.212, side * 0.224, 0.053];
        cylinder("hip-motor", 0.055, 0.089, hip, "frame");
        cylinder("hip-cover", 0.039, 0.010, [hip[0], hip[1] + side * 0.048, hip[2]], "shell");
        cylinder("hip-badge", 0.021, 0.012, [hip[0], hip[1] + side * 0.054, hip[2]], "accent");
        panelLink("upper-leg-shell", hip, knee, 0.047, 0.062);
        cylinder("knee-joint", 0.035, 0.066, knee, "frame");
        cylinder("knee-cap", 0.024, 0.012, [knee[0], knee[1] + side * 0.039, knee[2]], "edge");
        link("lower-leg-strut", knee, ankle, 0.016, "frame");
        const lowerStart = new THREE.Vector3(...knee).lerp(new THREE.Vector3(...ankle), 0.1).toArray();
        const lowerEnd = new THREE.Vector3(...knee).lerp(new THREE.Vector3(...ankle), 0.65).toArray();
        panelLink("shin-shell", lowerStart, lowerEnd, 0.036, 0.039, "edge");
        box("foot", [0.081, 0.061, 0.045], [ankle[0] + 0.007, ankle[1], 0.0225], "rubber", 0.017);
        cylinder("ankle", 0.024, 0.052, [ankle[0], ankle[1], 0.052], "frame");
      }
    }
  } else {
    box("pelvis-frame", [0.145, 0.23, 0.09], [0, 0, 0.535], "frame", 0.025);
    box("pelvis-armor", [0.026, 0.175, 0.085], [0.079, 0, 0.544], "shell");
    cylinder("waist-joint", 0.074, 0.08, [0, 0, 0.612], "frame", "z");
    box("torso-shell", [0.18, 0.29, 0.247], [0, 0, 0.755], "shell", 0.044);
    box("upper-back-panel", [0.023, 0.2, 0.153], [-0.096, 0, 0.762], "frame");
    box("chest-inset", [0.012, 0.163, 0.071], [0.094, 0, 0.781], "frame");
    box("chest-status-light", [0.014, 0.102, 0.014], [0.099, 0, 0.792], "accent", 0.004);
    lens("depth-sensor", 0.103, 0, 0.756, 0.012);
    cylinder("neck", 0.039, 0.076, [0, 0, 0.908], "edge", "z");
    box("head", [0.151, 0.155, 0.162], [0.005, 0, 1.001], "shell", 0.035);
    box("face-visor", [0.026, 0.137, 0.079], [0.081, 0, 1.016], "glass", 0.014);
    box("eye-light", [0.009, 0.088, 0.009], [0.097, 0, 1.024], "accent", 0.003);
    for (const side of [-1, 1]) {
      cylinder("head-hinge", 0.029, 0.013, [0, side * 0.079, 0.983], "edge");
      const hip = [0, side * 0.075, 0.519];
      const knee = [0.031, side * 0.084, 0.301];
      const ankle = [-0.012, side * 0.086, 0.102];
      cylinder("hip-motor", 0.049, 0.070, hip, "frame");
      panelLink("thigh-shell", [0, hip[1], 0.481], [0.026, knee[1], 0.331], 0.083, 0.105);
      link("thigh-core", hip, knee, 0.029);
      cylinder("knee-motor", 0.039, 0.083, knee, "frame");
      cylinder("knee-cap", 0.025, 0.012, [knee[0], knee[1] + side * 0.046, knee[2]], "accent");
      link("calf-core", knee, ankle, 0.024, "frame");
      panelLink("shin-armor", [0.025, knee[1], 0.268], [-0.002, ankle[1], 0.13], 0.062, 0.073);
      cylinder("ankle-motor", 0.028, 0.070, ankle, "edge");
      box("foot-sole", [0.174, 0.088, 0.032], [0.038, side * 0.086, 0.016], "rubber", 0.01);
      box("foot-armor", [0.142, 0.079, 0.035], [0.025, side * 0.086, 0.048], "shell");
      const shoulder = [0, side * 0.172, 0.836];
      const elbow = [-0.008, side * 0.228, 0.686];
      const wrist = [0.024, side * 0.229, 0.546];
      cylinder("shoulder-motor", 0.051, 0.080, shoulder, "frame");
      cylinder("shoulder-cap", 0.04, 0.022, [0, side * 0.221, 0.836], "shell");
      cylinder("shoulder-ring", 0.024, 0.026, [0, side * 0.232, 0.836], "accent");
      link("upper-arm-core", shoulder, elbow, 0.019);
      panelLink("upper-arm-shell", [0, side * 0.191, 0.796], [-0.005, side * 0.221, 0.717], 0.048, 0.058);
      cylinder("elbow-joint", 0.029, 0.060, elbow, "frame");
      link("forearm-core", elbow, wrist, 0.018);
      panelLink("forearm-shell", [0, side * 0.229, 0.654], [0.019, side * 0.229, 0.565], 0.046, 0.052);
      box("hand", [0.055, 0.046, 0.072], [0.026, side * 0.229, 0.506], "frame", 0.012);
      box("hand-plate", [0.01, 0.04, 0.05], [0.058, side * 0.229, 0.513], "shell", 0.003);
    }
  }
  // Bounds are useful for camera framing without rescaling a robot to its route.
  root.updateMatrixWorld(true);
  const bounds = new THREE.Box3().setFromObject(root);
  for (const child of root.children) child.position.z -= bounds.min.z;
  root.userData.height = bounds.max.z - bounds.min.z;
  return root;
}
