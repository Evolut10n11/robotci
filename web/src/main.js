import * as THREE from "three";
import "./styles.css";
import { sampleAt } from "./playback.js";

const root = document.querySelector("#root");

const EVENT_SYMBOLS = {
  START: "◆",
  REPLAN: "↻",
  STUCK: "!",
  RECOVERY: "↺",
  GOAL: "●",
  FAIL: "×",
};

const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
const formatSeconds = (value) => `${Number(value || 0).toFixed(1)}s`;
const formatMeters = (value) => `${Number(value || 0).toFixed(2)} m`;

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderLoading(message = "Loading replay…") {
  root.innerHTML = `
    <main class="loading">
      <div class="brand"><span class="brand-symbol">⌁</span><strong>RobotCI</strong></div>
      <h1>${escapeHtml(message)}</h1>
      <p>Reading Replay v1 from the local RobotCI server.</p>
    </main>`;
}

function renderError(error) {
  root.innerHTML = `
    <main class="loading error-state">
      <div class="brand"><span class="brand-symbol">⌁</span><strong>RobotCI</strong></div>
      <h1>Replay could not be loaded</h1>
      <p>${escapeHtml(error?.message || error)}</p>
      <button type="button" id="retry">Retry</button>
    </main>`;
  document.querySelector("#retry")?.addEventListener("click", boot);
}

function shell(replay) {
  const statusClass = replay.status.toLowerCase();
  const metrics = replay.metrics;
  const eventRows = replay.events.length
    ? replay.events
        .map(
          (event, index) => `
          <button class="event-row event-${event.type.toLowerCase()}" data-event-index="${index}" type="button">
            <span class="event-symbol">${EVENT_SYMBOLS[event.type] || "•"}</span>
            <span class="event-copy">
              <strong>${escapeHtml(event.type)}</strong>
              <span>${escapeHtml(event.message || event.type)}</span>
            </span>
            <time>${formatSeconds(event.t)}</time>
          </button>`,
        )
        .join("")
    : '<p class="empty-events">No events in this replay.</p>';

  const eventMarkers = replay.events
    .map((event, index) => {
      const left = replay.duration_sec ? clamp((event.t / replay.duration_sec) * 100, 0, 100) : 0;
      return `<button type="button" class="event-marker event-${event.type.toLowerCase()}" data-event-index="${index}" style="left:${left}%" aria-label="Jump to ${escapeHtml(event.type)} at ${formatSeconds(event.t)}"><span></span></button>`;
    })
    .join("");

  root.innerHTML = `
    <main class="workbench">
      <header class="app-header">
        <div class="brand"><span class="brand-symbol">⌁</span><strong>RobotCI</strong><span>3D Replay</span></div>
        <span class="brand-divider"></span>
        <div class="scenario-heading">
          <span class="breadcrumb">Runs <span>›</span></span>
          <h1 title="${escapeHtml(replay.scenario)}">${escapeHtml(replay.scenario)}</h1>
        </div>
        <div class="run-state">
          <span class="local-label">LOCAL REPLAY</span>
          <span class="status ${statusClass}"><span class="status-dot"></span>${escapeHtml(replay.status)}</span>
        </div>
      </header>

      <section class="workspace">
        <section class="panel viewport" aria-label="3D navigation replay">
          <div id="scene"></div>
          <div class="viewport-toolbar">
            <div class="view-label"><strong>Navigation world</strong><span class="frame-label">frame <span>/</span>${escapeHtml(replay.world.frame)}</span></div>
            <div class="camera-tools">
              <button type="button" data-camera="iso">Iso <span>I</span></button>
              <button type="button" data-camera="top">Top <span>T</span></button>
              <button type="button" data-camera="fit">Fit <span>F</span></button>
            </div>
          </div>
          <div class="scene-event event-start" id="scene-event"><span class="event-dot"></span><span>Navigation started</span></div>
          <div class="viewport-bottom">
            <div class="legend"><span><i class="start-dot"></i>Start</span><span><i class="goal-dot"></i>Goal</span><span><i class="path-dash"></i>Trajectory</span></div>
            <div class="live-distance">Goal distance <strong id="live-distance">—</strong></div>
          </div>
          <div class="camera-hint">Drag to orbit <span>·</span> wheel to zoom <span>·</span> double-click to fit</div>
        </section>

        <aside class="panel sidebar">
          <section class="metrics-section">
            <div class="section-heading"><h2>Run metrics</h2><span class="eyebrow">REPLAY V1</span></div>
            <div class="metric-grid">
              <article class="metric-card"><span class="metric-icon">◷</span><span class="metric-label">Duration</span><strong>${formatSeconds(metrics.duration_sec)}</strong></article>
              <article class="metric-card"><span class="metric-icon">⌁</span><span class="metric-label">Path length</span><strong>${formatMeters(metrics.path_length_m)}</strong></article>
              <article class="metric-card"><span class="metric-icon">◎</span><span class="metric-label">Goal delta</span><strong>${formatMeters(metrics.distance_to_goal_m)}</strong></article>
              <article class="metric-card"><span class="metric-icon">↺</span><span class="metric-label">Recoveries</span><strong>${Number(metrics.recoveries)}</strong></article>
            </div>
            <dl class="metadata">
              <div><dt>Runtime</dt><dd>${escapeHtml(replay.runtime)}</dd></div>
              <div><dt>Robot</dt><dd>${escapeHtml(replay.robot.type)}</dd></div>
              <div><dt>Samples</dt><dd>${replay.samples.length}</dd></div>
              <div><dt>Stuck events</dt><dd>${Number(metrics.stuck_events)}</dd></div>
            </dl>
          </section>

          <section class="events-section">
            <div class="section-heading"><h2>Events <span class="count">${replay.events.length}</span></h2><span class="eyebrow">CLICK TO SEEK</span></div>
            <div class="events-list">${eventRows}</div>
          </section>

          <section class="pose-section">
            <div class="section-heading"><h2>Current pose</h2><span class="eyebrow">MAP FRAME</span></div>
            <output class="pose-values" id="pose-values">x 0.00 <span>/</span> y 0.00 <span>/</span> z 0.00</output>
            <div class="pose-yaw" id="pose-yaw">yaw 0.0°</div>
          </section>
        </aside>

        <section class="panel timeline">
          <div class="transport">
            <button class="round" id="previous-event" type="button" aria-label="Previous event">‹</button>
            <button class="round primary" id="toggle-play" type="button" aria-label="Play replay">▶</button>
            <button class="round" id="next-event" type="button" aria-label="Next event">›</button>
            <label class="speed"><span>Speed</span><select id="speed" aria-label="Playback speed"><option value="0.5">0.5×</option><option value="1" selected>1×</option><option value="2">2×</option><option value="4">4×</option></select></label>
            <span class="playback-state" id="playback-state">Paused</span>
            <div class="timestamp"><output id="time-current">0.0s</output> <span>/ ${formatSeconds(replay.duration_sec)}</span></div>
          </div>
          <input class="seek" id="seek" type="range" min="0" max="${replay.duration_sec}" step="0.01" value="0" style="--progress:0%" aria-label="Replay position" />
          <div class="event-track"><div class="track-line"></div>${eventMarkers}<div class="playhead" id="playhead" style="left:0%"></div></div>
          <div class="time-ruler"><span>0.0s</span><span>${formatSeconds(replay.duration_sec / 2)}</span><span>${formatSeconds(replay.duration_sec)}</span></div>
          <div class="timeline-foot"><span>DETERMINISTIC REPLAY</span><span>Space: play/pause · ←/→: 0.5s · I/T/F: camera</span></div>
        </section>
      </section>

      <footer class="app-footer"><span><span class="status-dot"></span>local viewer</span><span>RobotCI Replay v1 · no cloud required</span></footer>
    </main>`;
}

function makeScene(replay, onFrame) {
  const host = document.querySelector("#scene");
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x031226);
  scene.fog = new THREE.FogExp2(0x031226, 0.027);

  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  host.appendChild(renderer.domElement);

  const camera = new THREE.PerspectiveCamera(45, 1, 0.05, 500);
  camera.up.set(0, 0, 1);
  scene.add(new THREE.HemisphereLight(0xc5d9ff, 0x081326, 2.4));
  const key = new THREE.DirectionalLight(0x9fb7ff, 2.6);
  key.position.set(5, -4, 9);
  scene.add(key);

  const points = replay.samples.map((sample) => new THREE.Vector3(sample.position.x, sample.position.y, 0.055));
  const xs = points.map((point) => point.x).concat(replay.world.goal.x);
  const ys = points.map((point) => point.y).concat(replay.world.goal.y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const span = Math.max(maxX - minX, maxY - minY, 2);
  const center = new THREE.Vector3((minX + maxX) / 2, (minY + maxY) / 2, 0);

  const gridSize = Math.max(12, Math.ceil(span * 2.4));
  const grid = new THREE.GridHelper(gridSize, Math.max(12, Math.round(gridSize * 2)), 0x28507f, 0x102b4d);
  grid.rotation.x = Math.PI / 2;
  grid.position.z = -0.01;
  scene.add(grid);

  const pathGeometry = new THREE.BufferGeometry().setFromPoints(points);
  scene.add(new THREE.Line(pathGeometry, new THREE.LineBasicMaterial({ color: 0x648bff, transparent: true, opacity: 0.95 })));

  function marker(position, color, radius = 0.11) {
    const group = new THREE.Group();
    const ring = new THREE.Mesh(
      new THREE.RingGeometry(radius * 0.58, radius, 40),
      new THREE.MeshBasicMaterial({ color, side: THREE.DoubleSide, transparent: true, opacity: 0.95 }),
    );
    ring.position.z = 0.025;
    group.add(ring);
    const stem = new THREE.Mesh(
      new THREE.CylinderGeometry(radius * 0.08, radius * 0.08, 0.45, 12),
      new THREE.MeshStandardMaterial({ color, roughness: 0.4 }),
    );
    stem.rotation.x = Math.PI / 2;
    stem.position.z = 0.23;
    group.add(stem);
    group.position.set(position.x, position.y, 0);
    scene.add(group);
  }

  marker(replay.samples[0].position, 0x41d6ac, 0.1);
  marker(replay.world.goal, 0xad91ff, 0.14);

  const robot = new THREE.Group();
  const body = new THREE.Mesh(
    new THREE.BoxGeometry(0.42, 0.30, 0.17),
    new THREE.MeshStandardMaterial({ color: 0x7481ff, metalness: 0.2, roughness: 0.38 }),
  );
  body.position.z = 0.16;
  robot.add(body);
  const nose = new THREE.Mesh(
    new THREE.ConeGeometry(0.07, 0.18, 18),
    new THREE.MeshStandardMaterial({ color: 0xe7ecff, roughness: 0.35 }),
  );
  nose.rotation.z = -Math.PI / 2;
  nose.position.set(0.28, 0, 0.18);
  robot.add(nose);
  const wheelMaterial = new THREE.MeshStandardMaterial({ color: 0x091120, roughness: 0.8 });
  for (const y of [-0.18, 0.18]) {
    const wheel = new THREE.Mesh(new THREE.CylinderGeometry(0.09, 0.09, 0.07, 20), wheelMaterial);
    wheel.position.set(-0.03, y, 0.09);
    robot.add(wheel);
  }
  scene.add(robot);

  const orbit = {
    yaw: -0.78,
    pitch: 0.82,
    distance: Math.max(5, span * 1.75),
    target: center.clone(),
  };

  function updateCamera() {
    const horizontal = orbit.distance * Math.cos(orbit.pitch);
    camera.position.set(
      orbit.target.x + horizontal * Math.cos(orbit.yaw),
      orbit.target.y + horizontal * Math.sin(orbit.yaw),
      orbit.target.z + orbit.distance * Math.sin(orbit.pitch),
    );
    camera.lookAt(orbit.target.x, orbit.target.y, 0);
    renderer.render(scene, camera);
  }

  function fit() {
    orbit.target.copy(center);
    orbit.distance = Math.max(5, span * 1.75);
    orbit.yaw = -0.78;
    orbit.pitch = 0.82;
    updateCamera();
  }

  function top() {
    orbit.target.copy(center);
    orbit.distance = Math.max(5, span * 1.8);
    orbit.yaw = -Math.PI / 2;
    orbit.pitch = Math.PI / 2 - 0.025;
    updateCamera();
  }

  function iso() {
    fit();
  }

  let dragging = false;
  let pointerX = 0;
  let pointerY = 0;
  renderer.domElement.addEventListener("pointerdown", (event) => {
    dragging = true;
    pointerX = event.clientX;
    pointerY = event.clientY;
    renderer.domElement.setPointerCapture(event.pointerId);
  });
  renderer.domElement.addEventListener("pointermove", (event) => {
    if (!dragging) return;
    const dx = event.clientX - pointerX;
    const dy = event.clientY - pointerY;
    pointerX = event.clientX;
    pointerY = event.clientY;
    orbit.yaw -= dx * 0.008;
    orbit.pitch = clamp(orbit.pitch + dy * 0.006, 0.12, Math.PI / 2 - 0.02);
    updateCamera();
  });
  renderer.domElement.addEventListener("pointerup", () => { dragging = false; });
  renderer.domElement.addEventListener("pointercancel", () => { dragging = false; });
  renderer.domElement.addEventListener("wheel", (event) => {
    event.preventDefault();
    orbit.distance = clamp(orbit.distance * Math.exp(event.deltaY * 0.001), 1.5, 120);
    updateCamera();
  }, { passive: false });
  renderer.domElement.addEventListener("dblclick", fit);

  const resize = () => {
    const width = Math.max(1, host.clientWidth);
    const height = Math.max(1, host.clientHeight);
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    renderer.render(scene, camera);
  };
  new ResizeObserver(resize).observe(host);
  resize();
  fit();

  function draw(time) {
    const sample = sampleAt(replay.samples, time);
    robot.position.set(sample.position.x, sample.position.y, Math.max(0, sample.position.z));
    robot.rotation.z = sample.orientation.yaw;
    renderer.render(scene, camera);
    onFrame?.(sample);
  }

  return { draw, fit, top, iso };
}

function startReplay(replay) {
  shell(replay);

  const duration = Number(replay.duration_sec);
  const seek = document.querySelector("#seek");
  const playButton = document.querySelector("#toggle-play");
  const speedSelect = document.querySelector("#speed");
  const timeCurrent = document.querySelector("#time-current");
  const playbackState = document.querySelector("#playback-state");
  const playhead = document.querySelector("#playhead");
  const poseValues = document.querySelector("#pose-values");
  const poseYaw = document.querySelector("#pose-yaw");
  const liveDistance = document.querySelector("#live-distance");
  const sceneEvent = document.querySelector("#scene-event");

  let currentTime = 0;
  let playing = false;
  let speed = 1;
  let lastFrame = performance.now();

  const scene = makeScene(replay, (sample) => {
    poseValues.innerHTML = `x ${sample.position.x.toFixed(2)} <span>/</span> y ${sample.position.y.toFixed(2)} <span>/</span> z ${sample.position.z.toFixed(2)}`;
    poseYaw.textContent = `yaw ${THREE.MathUtils.radToDeg(sample.orientation.yaw).toFixed(1)}°`;
    const dx = replay.world.goal.x - sample.position.x;
    const dy = replay.world.goal.y - sample.position.y;
    const dz = replay.world.goal.z - sample.position.z;
    liveDistance.textContent = `${Math.hypot(dx, dy, dz).toFixed(2)} m`;
  });

  function currentEventIndex() {
    let index = -1;
    replay.events.forEach((event, candidate) => {
      if (event.t <= currentTime + 0.001) index = candidate;
    });
    return index;
  }

  function sync() {
    currentTime = clamp(currentTime, 0, duration);
    const progress = duration ? (currentTime / duration) * 100 : 0;
    seek.value = String(currentTime);
    seek.style.setProperty("--progress", `${progress}%`);
    playhead.style.left = `${progress}%`;
    timeCurrent.textContent = formatSeconds(currentTime);
    playButton.textContent = playing ? "❚❚" : "▶";
    playButton.setAttribute("aria-label", playing ? "Pause replay" : "Play replay");
    playbackState.textContent = playing ? `Playing ${speed}×` : currentTime >= duration ? "Finished" : "Paused";

    const activeIndex = currentEventIndex();
    document.querySelectorAll(".event-row").forEach((row, index) => row.classList.toggle("active", index === activeIndex));
    sceneEvent.style.display = activeIndex < 0 ? "none" : "";
    if (activeIndex >= 0) {
      const event = replay.events[activeIndex];
      sceneEvent.className = `scene-event event-${event.type.toLowerCase()}`;
      sceneEvent.innerHTML = `<span class="event-dot"></span><span>${escapeHtml(event.message || event.type)}</span>`;
    }
    scene.draw(currentTime);
  }

  function seekTo(value) {
    currentTime = clamp(Number(value), 0, duration);
    if (currentTime >= duration) playing = false;
    sync();
  }

  function togglePlay() {
    if (currentTime >= duration) currentTime = 0;
    playing = !playing;
    lastFrame = performance.now();
    sync();
  }

  function jumpEvent(direction) {
    if (!replay.events.length) return;
    if (direction > 0) {
      const next = replay.events.find((event) => event.t > currentTime + 0.05) || replay.events[replay.events.length - 1];
      seekTo(next.t);
    } else {
      const previous = [...replay.events].reverse().find((event) => event.t < currentTime - 0.05) || replay.events[0];
      seekTo(previous.t);
    }
  }

  playButton.addEventListener("click", togglePlay);
  seek.addEventListener("input", () => {
    playing = false;
    seekTo(seek.value);
  });
  speedSelect.addEventListener("change", () => {
    speed = Number(speedSelect.value);
    sync();
  });
  document.querySelector("#previous-event").addEventListener("click", () => jumpEvent(-1));
  document.querySelector("#next-event").addEventListener("click", () => jumpEvent(1));
  document.querySelectorAll("[data-event-index]").forEach((node) => {
    node.addEventListener("click", () => {
      const event = replay.events[Number(node.dataset.eventIndex)];
      if (event) {
        playing = false;
        seekTo(event.t);
      }
    });
  });
  document.querySelectorAll("[data-camera]").forEach((button) => {
    button.addEventListener("click", () => scene[button.dataset.camera]?.());
  });

  window.addEventListener("keydown", (event) => {
    if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey) return;
    if (event.target instanceof Element && event.target.closest(
      'input, select, textarea, button, a, [contenteditable="true"], [role="button"]',
    )) return;
    if (event.code === "Space") {
      event.preventDefault();
      togglePlay();
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      playing = false;
      seekTo(currentTime - 0.5);
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      playing = false;
      seekTo(currentTime + 0.5);
    } else if (event.key.toLowerCase() === "i") {
      scene.iso();
    } else if (event.key.toLowerCase() === "t") {
      scene.top();
    } else if (event.key.toLowerCase() === "f") {
      scene.fit();
    }
  });

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      playing = false;
      sync();
    }
    lastFrame = performance.now();
  });

  function frame(now) {
    if (playing) {
      const elapsed = Math.max(0, (now - lastFrame) / 1000);
      currentTime += elapsed * speed;
      if (currentTime >= duration) {
        currentTime = duration;
        playing = false;
      }
      sync();
    }
    lastFrame = now;
    requestAnimationFrame(frame);
  }

  sync();
  requestAnimationFrame(frame);
}

async function boot() {
  renderLoading();
  try {
    const response = await fetch("./api/replay", { cache: "no-store" });
    if (!response.ok) throw new Error(`Replay API returned HTTP ${response.status}`);
    const replay = await response.json();
    startReplay(replay);
  } catch (error) {
    renderError(error);
  }
}

boot();
