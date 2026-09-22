const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
const lerp = (a, b, alpha) => a + (b - a) * alpha;

function interpolateAngle(a, b, alpha) {
  const delta = Math.atan2(Math.sin(b - a), Math.cos(b - a));
  return a + delta * alpha;
}

function interpolatePose(a, b, time, alpha) {
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

export function sampleAt(samples, time) {
  if (!samples.length) return null;
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

  return interpolatePose(a, b, time, alpha);
}

// First sample at or after time. Seeking remains logarithmic for long recordings.
function sampleIndex(samples, time) {
  let left = 0;
  let right = samples.length;
  while (left < right) {
    const middle = Math.floor((left + right) / 2);
    if (samples[middle].t < time) left = middle + 1;
    else right = middle;
  }
  return left;
}

function exceedsGap(start, end, threshold) {
  // Decimal timestamps can round on opposite sides of their inclusive boundary.
  // Allow only floating-point representation error, scaled to the input clocks.
  const tolerance = Number.EPSILON * Math.max(Math.abs(start), Math.abs(end), threshold) * 2;
  return end - start - threshold > tolerance;
}

export function poseAt(replay, time) {
  const samples = replay.samples;
  if (!replay.recording) {
    return { pose: sampleAt(samples, time), kind: "legacy", lastObserved: null, gap: null };
  }
  const index = sampleIndex(samples, time);
  const next = samples[index];
  if (next?.t === time) {
    return { pose: next, kind: "observed", lastObserved: next, gap: null };
  }
  const previous = samples[index - 1] ?? null;
  if (!previous || !next ||
      exceedsGap(previous.t, next.t, replay.recording.max_interpolation_gap_sec)) {
    return {
      pose: null,
      kind: "missing",
      lastObserved: previous,
      gap: time < 0 || time > replay.duration_sec ? null : {
        start: previous?.t ?? 0,
        end: next?.t ?? replay.duration_sec,
      },
    };
  }
  return {
    pose: interpolatePose(previous, next, time, (time - previous.t) / (next.t - previous.t)),
    kind: "interpolated",
    lastObserved: previous,
    gap: null,
  };
}

export function recordingGaps(replay) {
  if (!replay.recording) return [];
  const samples = replay.samples;
  if (!samples.length) return [{ start: 0, end: replay.duration_sec }];
  const gaps = [];
  if (samples[0].t > 0) gaps.push({ start: 0, end: samples[0].t });
  for (let index = 1; index < samples.length; index++) {
    if (exceedsGap(samples[index - 1].t, samples[index].t,
        replay.recording.max_interpolation_gap_sec)) {
      gaps.push({ start: samples[index - 1].t, end: samples[index].t });
    }
  }
  const last = samples.at(-1);
  if (last.t < replay.duration_sec) {
    gaps.push({ start: last.t, end: replay.duration_sec });
  }
  return gaps;
}

/** Split before thinning so a display budget can never reconnect a missing interval. */
export function trajectorySegments(replay, limit = 6000) {
  const samples = replay.samples;
  const budget = Math.floor(limit);
  if (!Number.isFinite(budget) || budget < 2 || !samples.length) return [];
  const ranges = [];
  const threshold = replay.recording?.max_interpolation_gap_sec ?? Infinity;
  let start = 0;
  for (let index = 1; index < samples.length; index++) {
    if (exceedsGap(samples[index - 1].t, samples[index].t, threshold)) {
      ranges.push({ start, length: index - start });
      start = index;
    }
  }
  ranges.push({ start, length: samples.length - start });
  if (samples.length <= budget) {
    return ranges.map(({ start, length }) => samples.slice(start, start + length));
  }

  // If there are too many disjoint intervals, omit entire intervals evenly.
  // Each retained interval keeps its own endpoints; omitted intervals are never joined.
  const minimum = ranges.reduce((sum, range) => sum + Math.min(2, range.length), 0);
  let selected = ranges;
  if (minimum > budget) {
    const count = Math.floor(budget / 2);
    selected = Array.from({ length: count }, (_, index) =>
      ranges[count === 1 ? 0 : Math.floor(index * (ranges.length - 1) / (count - 1))]);
  }
  const counts = selected.map(({ length }) => Math.min(2, length));
  const available = budget - counts.reduce((sum, count) => sum + count, 0);
  const capacity = selected.reduce((sum, range, index) => sum + range.length - counts[index], 0);
  let remaining = available;
  if (capacity > 0) {
    selected.forEach((range, index) => {
      const extra = Math.min(range.length - counts[index],
        Math.floor(available * (range.length - counts[index]) / capacity));
      counts[index] += extra;
      remaining -= extra;
    });
    for (let index = 0; remaining > 0 && index < selected.length; index++) {
      if (counts[index] < selected[index].length) {
        counts[index]++;
        remaining--;
      }
    }
  }
  return selected.map(({ start, length }, index) =>
    Array.from({ length: counts[index] }, (_, point) => samples[start +
      (counts[index] === 1 ? 0 : Math.floor(point * (length - 1) / (counts[index] - 1)))]));
}
