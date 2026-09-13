# RobotCI replay viewer source

This directory is the maintainable source for the browser UI bundled in `robotci/viewer_assets/`.
The Python package serves the built files locally with `robotci view`; the viewer itself has no cloud dependency.

## Development

Requirements: Node.js 20+ and npm.

For normal end-to-end development, start RobotCI on the default viewer port in one terminal:

```bash
robotci view --demo --no-open
```

Then start Vite in another terminal:

```bash
cd web
npm install
npm run dev
```

Vite proxies `/api/*` to `http://127.0.0.1:8765`, so the development UI receives the same Replay v1 payload as the bundled viewer.

## Production build

```bash
cd web
npm install
npm run build
```

`npm run build` writes directly to `robotci/viewer_assets/` and replaces the previous generated frontend bundle. Never commit `node_modules/`, `web/dist/`, Playwright output, or Vite caches.

## Responsibilities

- `src/main.js`: Replay v1 loading, deterministic playback, event seeking, Three.js scene, camera controls, and live pose state.
- `src/styles.css`: the 12ui-derived RobotCI dark workbench visual system and responsive layouts.
- `vite.config.js`: development API proxy and production output into the Python package.

The source intentionally consumes Replay v1 only. Contract changes should be coordinated with `robotci/viewer.py`, `robotci/replay.py`, and their tests.
