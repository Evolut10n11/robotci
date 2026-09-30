import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { LineSegments2 } from "three/addons/lines/LineSegments2.js";
import { LineSegmentsGeometry } from "three/addons/lines/LineSegmentsGeometry.js";
import { LineMaterial } from "three/addons/lines/LineMaterial.js";
import { poseAt, trajectorySegments } from "./playback.js";
import { trajectoryBounds } from "./model.js";
import { COLORS } from "./top-view.js";
import { createRobotModel } from "./robot-models.js";

export class SceneView {
  constructor(host, recordings, { visualProfile = null } = {}) {
    this.host = host;
    try {
      this.recordings = Object.entries(recordings).filter(([, replay]) => replay);
      this.scene = new THREE.Scene();
      this.scene.background = new THREE.Color("#1a242e");
      this.camera = new THREE.PerspectiveCamera(38, 1, 0.01, 10000);
      this.camera.up.set(0, 0, 1);
      this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
      this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
      this.renderer.outputColorSpace = THREE.SRGBColorSpace;
      this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
      this.renderer.toneMappingExposure = 1.3;
      this.renderer.shadowMap.enabled = true;
      this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
      this.renderer.domElement.setAttribute("aria-label", "Модель робота и записанные траектории в 3D. Модель условная; движения суставов не записаны. Перетаскивание поворачивает камеру, колесо меняет масштаб.");
      this.renderer.domElement.setAttribute("role", "img");
      host.append(this.renderer.domElement);
      this.controls = new OrbitControls(this.camera, this.renderer.domElement);
      this.controls.minDistance = 0.55;
      this.controls.maxPolarAngle = Math.PI / 2 - 0.015;
      this.controls.addEventListener("change", () => this.render());
      const bounds = trajectoryBounds(this.recordings.map(([, replay]) => replay));
      this.center = new THREE.Vector3((bounds.minX + bounds.maxX) / 2, (bounds.minY + bounds.maxY) / 2, 0);
      this.span = Math.max(bounds.maxX - bounds.minX, bounds.maxY - bounds.minY, 2);
      this.robots = [];
      this.lineMaterials = [];
      this.scene.fog = new THREE.Fog("#1a242e", this.span * 2.5, this.span * 7);
      const fill = new THREE.HemisphereLight("#d4e4ff", "#34302c", 2.3);
      fill.position.set(0, 0, 1);
      this.scene.add(fill);
      this.keyLight = new THREE.DirectionalLight("#fff0d8", 3.6);
      this.keyLight.castShadow = true;
      this.keyLight.shadow.mapSize.set(2048, 2048);
      this.keyLight.shadow.bias = -0.00015;
      this.keyLight.shadow.normalBias = 0.025;
      this.keyLight.shadow.radius = 3;
      this.scene.add(this.keyLight, this.keyLight.target);
      for (const [color, intensity, position] of [
        ["#8badff", 2.6, [-4, 6, 5]], ["#ffffff", 0.7, [4, -6, 2]],
      ]) {
        const light = new THREE.DirectionalLight(color, intensity);
        light.position.copy(this.center).add(new THREE.Vector3(...position));
        light.target.position.copy(this.center);
        this.scene.add(light, light.target);
      }
      this.positionLight(this.center, this.span);
      // A coordinate plane, not an imported map or inferred terrain.
      const ground = new THREE.Mesh(
        new THREE.PlaneGeometry(this.span * 16, this.span * 16),
        new THREE.MeshStandardMaterial({ color: "#202b35", roughness: 0.92, metalness: 0.12 }),
      );
      ground.name = "coordinate-plane";
      ground.position.copy(this.center);
      ground.position.z = -0.003;
      ground.receiveShadow = true;
      this.scene.add(ground);
      const magnitude = 10 ** Math.floor(Math.log10(this.span / 12));
      const step = [1, 2, 5, 10].find((n) => n * magnitude >= this.span / 12) * magnitude;
      this.gridStep = step;
      const divisions = Math.ceil(this.span * 6 / step);
      const grid = new THREE.GridHelper(divisions * step, divisions, "#566673", "#374651");
      grid.rotation.x = Math.PI / 2;
      grid.position.set(Math.round(this.center.x / step) * step, Math.round(this.center.y / step) * step, -0.001);
      grid.material.transparent = true;
      grid.material.opacity = 0.48;
      grid.material.depthWrite = false;
      this.scene.add(grid);
      for (const [source, replay] of this.recordings) {
        const points = trajectorySegments(replay).flatMap((segment) => segment.slice(1).flatMap((sample, index) =>
          [segment[index], sample].flatMap(({ position: p }) => [p.x, p.y, p.z + 0.012]),
        ));
        // A stationary recording is valid; a single point has no segment.
        if (points.length >= 6) {
          const geometry = new LineSegmentsGeometry();
          geometry.setPositions(points);
          const material = new LineMaterial({
            color: COLORS[source], linewidth: source === "baseline" ? 2.2 : 3,
            dashed: source === "baseline", dashSize: 0.13, gapSize: 0.10,
            transparent: true, opacity: source === "baseline" ? 0.7 : 0.95, depthWrite: false,
          });
          const line = new LineSegments2(geometry, material);
          line.name = `${source}-recorded-trajectory`;
          line.computeLineDistances();
          this.lineMaterials.push(material);
          this.scene.add(line);
        }
        const robot = createRobotModel(visualProfile ?? replay.robot.visual_profile ?? "rover", {
          color: COLORS[source], ghost: source === "baseline",
        });
        this.scene.add(robot);
        this.robots.push({ source, replay, robot });
      }
      const primary = recordings.candidate ?? recordings.baseline;
      if (primary) {
        this.addMarker(primary.recording ? primary.world.start : primary.samples[0].position,
          primary.recording ? "ЗАДАННЫЙ СТАРТ" : "СТАРТ", COLORS.candidate, 0.074);
        this.addMarker(primary.world.goal, "ЦЕЛЬ", "#45cfb5", 0.1);
      }
      this.observer = new ResizeObserver(() => this.resize());
      this.observer.observe(host);
      this.resize();
      this.fit();
      this.setTime(0);
    } catch (error) {
      // WebGL can fail after allocating a context or uploading part of a scene.
      // Release whatever exists before the caller switches to the 2D view.
      try { this.dispose(); } catch { /* Preserve the original rendering error. */ }
      throw error;
    }
  }

  addMarker(position, label, color, radius) {
    const marker = new THREE.Mesh(
      new THREE.RingGeometry(radius, radius + 0.025, 48),
      new THREE.MeshBasicMaterial({ color, side: THREE.DoubleSide, depthWrite: false }),
    );
    marker.position.set(position.x, position.y, position.z + 0.023);
    this.scene.add(marker);
    const inner = new THREE.Mesh(
      new THREE.CircleGeometry(radius * 0.4, 32),
      new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.75, depthWrite: false }),
    );
    inner.position.copy(marker.position);
    this.scene.add(inner);
    const canvas = document.createElement("canvas");
    canvas.width = 256;
    canvas.height = 80;
    const context = canvas.getContext("2d");
    if (!context) return;
    context.fillStyle = "rgba(18, 27, 36, 0.8)";
    context.beginPath();
    context.roundRect(10, 10, 236, 60, 15);
    context.fill();
    context.font = "600 29px system-ui, sans-serif";
    context.textAlign = "center";
    context.textBaseline = "middle";
    context.fillStyle = "#e8eef4";
    context.fillText(label, 128, 42);
    const texture = new THREE.CanvasTexture(canvas);
    texture.colorSpace = THREE.SRGBColorSpace;
    const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: texture, transparent: true, depthWrite: false }));
    const size = Math.max(0.43, this.span * 0.07);
    sprite.scale.set(size, size * 80 / 256, 1);
    sprite.position.set(position.x, position.y, position.z + 0.28);
    this.scene.add(sprite);
  }

  resize() {
    const width = Math.max(1, this.host.clientWidth), height = Math.max(1, this.host.clientHeight);
    this.renderer.setSize(width, height);
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    for (const material of this.lineMaterials) material.resolution.set(width, height);
    this.render();
  }

  positionLight(target, span) {
    this.keyLight.position.copy(target).add(new THREE.Vector3(3, -4, 7).multiplyScalar(Math.max(1, span / 6)));
    this.keyLight.target.position.copy(target);
    const camera = this.keyLight.shadow.camera;
    const extent = Math.max(1.5, span * 0.8);
    camera.left = camera.bottom = -extent;
    camera.right = camera.top = extent;
    camera.near = 0.1;
    camera.far = Math.max(25, span * 6);
    camera.updateProjectionMatrix();
  }

  render() { this.renderer.render(this.scene, this.camera); }

  fit() {
    this.focused = false;
    const aspectCorrection = Math.max(1, 1 / this.camera.aspect);
    this.camera.position.copy(this.center).add(new THREE.Vector3(
      this.span * 0.7, -this.span * 0.9, this.span * 0.85,
    ).multiplyScalar(aspectCorrection));
    this.camera.far = Math.max(1000, this.span * 100);
    this.camera.updateProjectionMatrix();
    this.controls.target.copy(this.center);
    this.controls.maxDistance = this.span * 12;
    this.positionLight(this.center, this.span);
    this.controls.update();
    this.render();
  }

  focusRobot() {
    const entry = this.robots.find(({ source }) => source === "candidate") ?? this.robots[0];
    if (!entry || !entry.robot.visible) return;
    const { robot } = entry;
    const target = robot.position.clone().add(new THREE.Vector3(0, 0, robot.userData.height * 0.43));
    const distance = Math.max(robot.userData.height, 0.8) * Math.max(1, 1 / this.camera.aspect);
    const offset = new THREE.Vector3(1.55, -2.1, 1.1).multiplyScalar(distance);
    offset.applyAxisAngle(new THREE.Vector3(0, 0, 1), robot.rotation.z);
    this.camera.position.copy(target).add(offset);
    this.controls.target.copy(target);
    this.positionLight(target, 2.5);
    this.focused = true;
    this.focusedRobot = robot;
    this.controls.update();
    this.render();
  }

  setTime(time) {
    const before = this.focused ? this.focusedRobot.position.clone() : null;
    for (const { replay, robot } of this.robots) {
      const { pose } = poseAt(replay, time);
      robot.visible = !!pose;
      if (!pose) continue;
      robot.position.set(pose.position.x, pose.position.y, pose.position.z);
      robot.rotation.z = pose.orientation.yaw;
    }
    if (before) {
      // Follow translation only; the user controls the camera's orbit angle.
      const delta = this.focusedRobot.position.clone().sub(before);
      this.camera.position.add(delta);
      this.controls.target.add(delta);
      this.positionLight(this.controls.target, 2.5);
      this.controls.update();
    }
    this.render();
  }

  dispose() {
    this.observer?.disconnect();
    this.controls?.dispose();
    const geometries = new Set(), materials = new Set(), textures = new Set();
    this.scene?.traverse((item) => {
      if (item.geometry) geometries.add(item.geometry);
      for (const material of Array.isArray(item.material) ? item.material : [item.material]) {
        if (!material) continue;
        materials.add(material);
        for (const value of Object.values(material)) if (value?.isTexture) textures.add(value);
      }
      if (item.isInstancedMesh) item.dispose();
      if (item.isLight && item.shadow) item.shadow.dispose();
    });
    textures.forEach((texture) => texture.dispose());
    geometries.forEach((geometry) => geometry.dispose());
    materials.forEach((material) => material.dispose());
    this.renderer?.dispose();
    this.renderer?.forceContextLoss();
    this.renderer?.domElement.remove();
  }
}
