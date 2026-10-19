# LeRobot PushT comparison

Verdict: **PASS**

| Metric | Baseline | Candidate | Drop | Allowed drop | Verdict |
| --- | ---: | ---: | ---: | ---: | --- |
| success_rate | 1 | 1 | 0 | 0 | PASS |
| mean_max_reward | 1 | 1 | 0 | 0.05 | PASS |

## Evaluations

- Baseline: lerobot/diffusion\_pusht, revision 84a7c23178445c6bbf7e1a884ff497017910f653; 3/3 successful episodes; 163.044 s wall time.
- Candidate: lerobot/diffusion\_pusht, revision 84a7c23178445c6bbf7e1a884ff497017910f653; 3/3 successful episodes; 151.671 s wall time.

Drops are absolute metric differences; equality at the threshold passes.
Wall-clock timing is diagnostic and does not affect the verdict.
This gate checks simulation artifacts; trajectory files and producer authenticity are not verified by offline comparison.
