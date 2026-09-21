const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
const lerp = (a, b, alpha) => a + (b - a) * alpha;

function interpolateAngle(a, b, alpha) {
  const delta = Math.atan2(Math.sin(b - a), Math.cos(b - a));
  return a + delta * alpha;
}

export function sampleAt(samples, time) {
  if (time <= samples[0].t) return samples[0];
  const last = samples[samples.length - 1];
  if (time >= last.t) return last;

  let left = 1;
  let right = samples.length - 1;
  while (left < right) {
    const middle = Math.floor((left + right) / 2);
    if (samples[middle].t < time) left = middle + 1;
    else right = middle;
  }
  const high = left;
  const low = high - 1;
  const a = samples[low];
  const b = samples[high];
  const span = Math.max(0.0001, b.t - a.t);
  const alpha = clamp((time - a.t) / span, 0, 1);

  return {
    t: time,
    position: {
      x: lerp(a.position.x, b.position.x, alpha),
      y: lerp(a.position.y, b.position.y, alpha),
      z: lerp(a.position.z, b.position.z, alpha),
    },
    orientation: {
      yaw: interpolateAngle(a.orientation.yaw, b.orientation.yaw, alpha),
    },
  };
}
