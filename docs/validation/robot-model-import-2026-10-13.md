# Robot-description import acceptance, 2026-10-13

This is presentation/import acceptance, not a robot-control adapter or completion
of the separate Nav2 controller experiment and M8 goals in issue #99.

## Scope

The Russian local viewer accepts pasted URDF/MJCF or YAML with an explicit
`robot.model`, a description file, or a selected folder with local OBJ/STL meshes.
It distinguishes conservative structural classification from exact catalog
identity. A manufacturer's name alone never selects a branded reference model.
Unsupported or missing geometry remains explicit. No uploaded code, Xacro, DTD,
plugin, remote mesh URL or arbitrary host-file lookup is executed.

Three self-contained catalog models use MuJoCo Menagerie revision
`0059d4335f8156206f63a35662313385f7ad6d74`: Unitree Go2, Unitree G1 and Franka Emika
Panda. Original model licenses are distributed alongside their compressed GLBs.
The package gains approximately 22 MB of compressed model assets; core runtime
dependencies are unchanged. MuJoCo and Playwright are isolated verification tools.

`robot.model` in RobotCI YAML is recorded as replay presentation metadata. It does
not replace the Nav2 simulator, controller, task, measured trajectory or official
gate. Imported joints stay in their reference pose; joint motion is not inferred
from root motion. A 2D view still uses a conditional marker.

## Executed verification

Development verification runs:

- https://github.com/Evolut10n11/robotci/actions/runs/38381055955
- https://github.com/Evolut10n11/robotci/actions/runs/38381733512

The second run additionally checks that a real imported model does not leave a
misleading generic profile card selected. Source was published on the feature
branch only after all checks passed. Verified published source is commit
`ed9cf5fe76819fb8a10ca0b0d9970e7321181bb2`; the temporary write-enabled development
workflow is removed before the final PR. The permanent acceptance workflow has
read-only permissions.

Both runs passed Ruff, the targeted 262 Python checks, all 47 frontend tests,
actual Chromium import interactions, and wheel inclusion checks for each model's
manifest, compressed geometry and LICENSE. These are not the full repository's
PR checks; their results must be reviewed separately.

The renderer's raw reference-frame transforms were compared with MuJoCo 3.3.7
forward kinematics on the original pinned robot XML and its home/stand keyframe:

| Model | Compared body frames | Largest component difference |
| --- | ---: | ---: |
| Unitree Go2 | 13 | 1.11e-16 |
| Unitree G1 | 30 | 3.33e-16 |
| Franka Emika Panda | 11 | 5.55e-16 |

Position and quaternion comparisons both used an absolute tolerance of 1e-6,
with quaternion sign equivalence accounted for. This verifies assembly of 54
reference frames, not collision/dynamics accuracy or a walking policy.

Browser checks cover automatic selection from recording metadata, all three
pasted catalog identifiers, exact Go2 MJCF file recognition, misleading-name
rejection, unsafe XML rejection without replacing the previous model, custom
URDF primitives, an explicitly selected OBJ folder, unchanged source replay,
960px dialog layout, and no external requests or uncaught JavaScript errors.
Screenshots were inspected. The browser uses software WebGL and a synthetic
replay to verify presentation; it does not establish physical GPU performance.

## Limits

URDF support is a bounded tree subset. MJCF requires an expanded robot XML rather
than a scene containing includes. Xacro, mimic, MJCF ball joints/frame/attach and
other unsupported constructs are rejected rather than silently interpreted.
Local mesh support is OBJ/STL; DAE, external textures and MTL are not imported.
Structural confidence is a qualitative heuristic, not a calibrated probability.
A controller-only YAML cannot supply missing robot geometry.

The existing forced-MCP-shutdown test synchronization issue #103 and the measured
Nav2 controller-pair acceptance are not changed or claimed fixed by this feature.
