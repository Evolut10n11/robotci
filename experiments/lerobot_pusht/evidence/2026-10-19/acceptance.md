# LeRobot PushT acceptance

Verdict: **PASS**

| Run | Verified trajectories | Success rate | Mean max reward |
| --- | ---: | ---: | ---: |
| baseline | 3 | 1.000000 | 1.000000 |
| unchanged | 3 | 1.000000 | 1.000000 |
| degraded | 3 | 0.000000 | 0.085499 |

Checks include all trajectory SHA-256 values, action scaling, step order,
terminal flags, episode metrics, repeated traces and expected comparison gates.

## Repeated-run evidence

Actions, positions, pixel hashes and flags must match exactly.
Only per-step rewards allow absolute error 1e-12; relative tolerance is zero.
Original trajectory hashes are verified individually and remain unchanged.

| Seed | Bytes identical | Other fields identical | Max reward difference |
| ---: | --- | --- | ---: |
| 1000 | True | True | 0 |
| 1001 | False | True | 4.440892098500626e-16 |
| 1002 | False | True | 4.440892098500626e-16 |
