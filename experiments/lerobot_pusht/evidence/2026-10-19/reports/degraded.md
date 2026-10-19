# LeRobot PushT comparison

Verdict: **REGRESSION**

| Metric | Baseline | Candidate | Drop | Allowed drop | Verdict |
| --- | ---: | ---: | ---: | ---: | --- |
| success_rate | 1 | 0 | 1 | 0 | REGRESSION |
| mean_max_reward | 1 | 0.0854993108637 | 0.914500689136 | 0.05 | REGRESSION |

## Findings

- success\_rate\_regression: success\_rate dropped by 1; allowed 0.
- mean\_max\_reward\_regression: mean\_max\_reward dropped by 0.914500689136; allowed 0.05.

## Evaluations

- Baseline: lerobot/diffusion\_pusht, revision 84a7c23178445c6bbf7e1a884ff497017910f653; 3/3 successful episodes; 163.044 s wall time.
- Candidate: lerobot/diffusion\_pusht, revision 84a7c23178445c6bbf7e1a884ff497017910f653; 0/3 successful episodes; 255.472 s wall time.

Drops are absolute metric differences; equality at the threshold passes.
Wall-clock timing is diagnostic and does not affect the verdict.
This gate checks simulation artifacts; trajectory files and producer authenticity are not verified by offline comparison.
