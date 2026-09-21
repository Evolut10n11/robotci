import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { sampleAt } from "./playback.js";
import { trajectoryBounds, displaySamples } from "./model.js";
import { COLORS } from "./top-view.js";

export class SceneView {
  constructor(host, recordings) {
    this.host = host;
    this.recordings = Object.entries(recordings).filter(([, replay]) => replay);
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color("#fbfaf7");
    this.camera = new THREE.PerspectiveCamera(40, 1, 0.01, 10000);
    this.camera.up.set(0, 0, 1);
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.domElement.setAttribute(
      "aria-label",
      "Траектории в 3D. Перетаскивание поворачивает камеру, колесо меняет масштаб.",
    );
    this.renderer.domElement.setAttribute("role", "img");
    host.append(this.renderer.domElement);
    this.controls = new OrbitControls(this.camera, this.renderer.domElement);
    this.controls.addEventListener("change", () => this.render());
    const bounds = trajectoryBounds(
      this.recordings.map(([, replay]) => replay),
    );
    this.center = new THREE.Vector3(
      (bounds.minX + bounds.maxX) / 2,
      (bounds.minY + bounds.maxY) / 2,
      0,
    );
    this.span = Math.max(
      bounds.maxX - bounds.minX,
      bounds.maxY - bounds.minY,
      2,
    );
    this.robots = [];
    this.scene.add(new THREE.AmbientLight(0xffffff, 2));
    const light = new THREE.DirectionalLight(0xffffff, 3);
    light.position.set(2, -3, 8);
    this.scene.add(light);
    const grid = new THREE.GridHelper(this.span * 2, 20, "#c8cfca", "#e5e8e3");
    grid.rotation.x = Math.PI / 2;
    grid.position.copy(this.center);
    grid.position.z = -0.02;
    this.scene.add(grid);
    for (const [source, replay] of this.recordings) {
      const points = displaySamples(replay.samples).map(
        ({ position: p }) => new THREE.Vector3(p.x, p.y, p.z + 0.03),
      );
      const geometry = new THREE.BufferGeometry().setFromPoints(points);
      const material =
        source === "baseline"
          ? new THREE.LineDashedMaterial({
              color: COLORS[source],
              dashSize: this.span / 80,
              gapSize: this.span / 120,
            })
          : new THREE.LineBasicMaterial({ color: COLORS[source] });
      const line = new THREE.Line(geometry, material);
      line.computeLineDistances();
      this.scene.add(line);
      const robot = new THREE.Group();
      const body = new THREE.Mesh(
        new THREE.BoxGeometry(0.24, 0.18, 0.12),
        new THREE.MeshStandardMaterial({
          color: COLORS[source],
          roughness: 0.7,
        }),
      );
      body.position.z = 0.09;
      robot.add(body);
      const nose = new THREE.Mesh(
        new THREE.ConeGeometry(0.05, 0.1, 3),
        new THREE.MeshBasicMaterial({ color: "#ffffff" }),
      );
      nose.rotation.z = -Math.PI / 2;
      nose.position.set(0.12, 0, 0.13);
      robot.add(nose);
      this.scene.add(robot);
      this.robots.push({ replay, robot });
      if (source === "candidate") {
        const goal = new THREE.Mesh(
          new THREE.RingGeometry(0.12, 0.16, 32),
          new THREE.MeshBasicMaterial({
            color: "#567a55",
            side: THREE.DoubleSide,
          }),
        );
        goal.position.set(
          replay.world.goal.x,
          replay.world.goal.y,
          replay.world.goal.z + 0.02,
        );
        this.scene.add(goal);
      }
    }
    this.observer = new ResizeObserver(() => {
      const width = Math.max(1, host.clientWidth),
        height = Math.max(1, host.clientHeight);
      this.renderer.setSize(width, height);
      this.camera.aspect = width / height;
      this.camera.updateProjectionMatrix();
      this.render();
    });
    this.observer.observe(host);
    this.fit();
    this.setTime(0);
  }
  render() {
    this.renderer.render(this.scene, this.camera);
  }
  fit() {
    this.camera.position
      .copy(this.center)
      .add(new THREE.Vector3(this.span * 0.6, -this.span, this.span * 1.3));
    this.camera.far = Math.max(1000, this.span * 100);
    this.camera.updateProjectionMatrix();
    this.controls.target.copy(this.center);
    this.controls.update();
    this.render();
  }
  setTime(time) {
    for (const { replay, robot } of this.robots) {
      const pose = sampleAt(replay.samples, time);
      robot.position.set(pose.position.x, pose.position.y, pose.position.z);
      robot.rotation.z = pose.orientation.yaw;
    }
    this.render();
  }
  dispose() {
    this.observer.disconnect();
    this.controls.dispose();
    this.scene.traverse((item) => {
      item.geometry?.dispose();
      if (Array.isArray(item.material))
        item.material.forEach((material) => material.dispose());
      else item.material?.dispose();
    });
    this.renderer.dispose();
    this.renderer.forceContextLoss();
    this.renderer.domElement.remove();
  }
}
