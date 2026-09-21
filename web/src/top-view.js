import { eventTitle, formatTime } from "./ru.js";
import { sampleAt } from "./playback.js";
import { trajectoryBounds, displaySamples, formatNumber } from "./model.js";
const NS = "http://www.w3.org/2000/svg";
const node = (tag, attrs = {}, label) => {
  const element = document.createElementNS(NS, tag);
  for (const [key, value] of Object.entries(attrs))
    element.setAttribute(key, value);
  if (label != null) element.textContent = label;
  return element;
};
export const COLORS = { candidate: "#bd602d", baseline: "#287c79" };

export class TopView {
  constructor(host, recordings) {
    this.host = host;
    this.recordings = Object.entries(recordings).filter(([, value]) => value);
    this.bounds = trajectoryBounds(this.recordings.map(([, replay]) => replay));
    this.svg = node("svg", {
      role: "img",
      "aria-label":
        "Записанные траектории в системе координат мира. Перетаскивание сдвигает вид, колесо меняет масштаб.",
      class: "trajectory-svg",
    });
    host.append(this.svg);
    this.time = 0;
    this.zoom = 1;
    this.pan = { x: 0, y: 0 };
    this.drag = null;
    this.svg.addEventListener("pointerdown", (event) => {
      if (event.button !== 0) return;
      this.drag = { x: event.clientX, y: event.clientY, pan: { ...this.pan } };
      this.svg.setPointerCapture(event.pointerId);
    });
    this.svg.addEventListener("pointermove", (event) => {
      if (!this.drag) return;
      this.pan.x = this.drag.pan.x + event.clientX - this.drag.x;
      this.pan.y = this.drag.pan.y + event.clientY - this.drag.y;
      this.draw();
    });
    this.svg.addEventListener("pointerup", () => {
      this.drag = null;
    });
    this.svg.addEventListener("pointercancel", () => {
      this.drag = null;
    });
    this.svg.addEventListener(
      "wheel",
      (event) => {
        event.preventDefault();
        const factor = Math.exp(-event.deltaY * 0.0015);
        this.zoom = Math.max(0.2, Math.min(20, this.zoom * factor));
        this.draw();
      },
      { passive: false },
    );
    this.observer = new ResizeObserver(() => this.draw());
    this.observer.observe(host);
    this.draw();
  }
  fit() {
    this.zoom = 1;
    this.pan = { x: 0, y: 0 };
    this.draw();
  }
  draw() {
    const width = Math.max(100, this.host.clientWidth),
      height = Math.max(100, this.host.clientHeight);
    this.svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    const b = this.bounds;
    const scale =
      Math.min(
        (width - 60) / (b.maxX - b.minX),
        (height - 45) / (b.maxY - b.minY),
      ) * this.zoom;
    const cx = (b.minX + b.maxX) / 2,
      cy = (b.minY + b.maxY) / 2;
    this.xy = (p) => [
      width / 2 + (p.x - cx) * scale + this.pan.x,
      height / 2 - (p.y - cy) * scale + this.pan.y,
    ];
    this.svg.replaceChildren();
    const grid = node("g", { class: "plot-grid" });
    const rawStep = 60 / scale;
    const magnitude = 10 ** Math.floor(Math.log10(rawStep));
    const step =
      [1, 2, 5, 10].find((factor) => factor * magnitude >= rawStep) * magnitude;
    const xMin = cx - (width / 2 + this.pan.x) / scale,
      xMax = xMin + width / scale;
    const yMax = cy + (height / 2 + this.pan.y) / scale,
      yMin = yMax - height / scale;
    for (let x = Math.ceil(xMin / step) * step; x < xMax; x += step) {
      const [px] = this.xy({ x, y: 0 });
      grid.append(node("line", { x1: px, x2: px, y1: 0, y2: height }));
      grid.append(
        node(
          "text",
          { x: px + 5, y: height - 12 },
          formatNumber(Math.abs(x) < step * 1e-9 ? 0 : x),
        ),
      );
    }
    for (let y = Math.ceil(yMin / step) * step; y < yMax; y += step) {
      const [, py] = this.xy({ x: 0, y });
      grid.append(node("line", { x1: 0, x2: width, y1: py, y2: py }));
      if (py < height - 28)
        grid.append(
          node(
            "text",
            { x: 12, y: py - 5 },
            formatNumber(Math.abs(y) < step * 1e-9 ? 0 : y),
          ),
        );
    }
    this.svg.append(grid);
    this.robots = [];
    for (const [source, replay] of this.recordings) {
      const color = COLORS[source];
      const points = displaySamples(replay.samples)
        .map(({ position }) => this.xy(position).join(","))
        .join(" ");
      this.svg.append(
        node("polyline", {
          points,
          fill: "none",
          stroke: color,
          "stroke-width": source === "candidate" ? 3 : 2.5,
          "stroke-dasharray": source === "baseline" ? "7 5" : "none",
          "stroke-linecap": "round",
          "stroke-linejoin": "round",
          opacity: 0.83,
        }),
      );
      if (source === "candidate") {
        const [sx, sy] = this.xy(replay.samples[0].position),
          [gx, gy] = this.xy(replay.world.goal);
        this.svg.append(
          node("circle", {
            cx: sx,
            cy: sy,
            r: 5,
            fill: "#fff",
            stroke: "#4c5554",
            "stroke-width": 2,
          }),
        );
        this.svg.append(
          node("text", { x: sx - 9, y: sy + 24, class: "plot-label" }, "Старт"),
        );
        this.svg.append(
          node("circle", {
            cx: gx,
            cy: gy,
            r: 13,
            fill: "none",
            stroke: "#567a55",
            "stroke-width": 1.5,
            "stroke-dasharray": "3 3",
          }),
        );
        this.svg.append(
          node("circle", { cx: gx, cy: gy, r: 5, fill: "#567a55" }),
        );
        this.svg.append(
          node("text", { x: gx + 20, y: gy + 4, class: "plot-label" }, "Цель"),
        );
        for (const event of replay.events.filter(
          (e) => !["START", "GOAL"].includes(e.type),
        )) {
          const [ex, ey] = this.xy(sampleAt(replay.samples, event.t).position);
          const mark = node("circle", {
            cx: ex,
            cy: ey,
            r: 5,
            fill: "#fff9ed",
            stroke: color,
            "stroke-width": 2,
          });
          mark.append(node("title", {}, `${eventTitle(event)} · ${formatTime(event.t)} с`));
          this.svg.append(mark);
        }
      }
      const marker = node("g");
      marker.append(node("circle", { r: 13, fill: color, opacity: 0.13 }));
      marker.append(
        node("path", {
          d: "M 10 0 L -6 -6 L -3 0 L -6 6 Z",
          fill: color,
          stroke: "white",
          "stroke-width": 1.5,
        }),
      );
      this.svg.append(marker);
      this.robots.push({ replay, marker });
    }
    this.setTime(this.time);
  }
  setTime(time) {
    this.time = time;
    for (const { replay, marker } of this.robots ?? []) {
      const pose = sampleAt(replay.samples, time),
        [x, y] = this.xy(pose.position);
      marker.setAttribute(
        "transform",
        `translate(${x} ${y}) rotate(${(-pose.orientation.yaw * 180) / Math.PI})`,
      );
    }
  }
  dispose() {
    this.observer.disconnect();
    this.svg.remove();
  }
}
