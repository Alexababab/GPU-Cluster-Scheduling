# Case036 Hard Skeleton Forensic Analysis

## 1. Input Profile

- task_count: 490
- server_count: 23
- server GPU distribution: min=2.00, p25=4.00, median=6.00, p75=7.00, p90=8.00, max=8.00, mean=5.61, CV=0.336
- server GPU-memory distribution: min=24.00, p25=32.00, median=48.00, p75=72.00, p90=80.00, max=80.00, mean=51.83, CV=0.414
- task weight distribution: min=1.00, p25=6.00, median=11.00, p75=16.00, p90=19.00, max=20.00, mean=10.63, CV=0.550
- duration distribution: min=10.00, p25=162.00, median=300.50, p75=487.00, p90=591.00, max=650.00, mean=319.98, CV=0.587
- min_gpu distribution: min=1.00, p25=1.00, median=2.00, p75=3.00, p90=4.00, max=8.00, mean=2.18, CV=0.652
- total_gpu_memory distribution: min=9.00, p25=41.00, median=77.00, p75=143.00, p90=212.10, max=467.00, mean=101.26, CV=0.795
- feasible_mode_count distribution: min=1.00, p25=10.00, median=13.00, p75=16.00, p90=20.00, max=23.00, mean=13.19, CV=0.374
- release_time burstiness (largest identical-release group / N): 0.0041
- unique release-time ratio: 0.9714
- hard_job_count (top 10%): 49

Server GPU counts: {2: 2, 3: 2, 4: 3, 5: 2, 6: 5, 7: 5, 8: 4}.
Server GPU-memory values: {24: 4, 32: 4, 40: 3, 48: 1, 64: 5, 80: 6}.

## 2. V6-safe vs hard_p10_slack_light

| metric | V6-safe | hard_p10_slack_light | delta | change |
|---|---:|---:|---:|---:|
| E_wait | 2165 | 224 | -1941 | -89.6536% |
| E_memory_new | 4191862 | 4359758 | +167896 | +4.0053% |
| E_finish | 12392 | 12392 | +0 | +0.0000% |

Leaderboard-style weighted proxy change (wait + 1.25*memory + finish): -84.6470%.
Equal-weight averaged relative change: -28.5494%.

## 3. E_wait Improvement Sources

| task | weight | duration | feasible modes | V6 wait_cost | hard wait_cost | wait improvement | start V6->hard | server V6->hard | GPU V6->hard |
|---:|---:|---:|---:|---:|---:|---:|---|---|---|
| 462 | 19 | 248 | 4 | 1881 | 0 | +1881 | 5697->5598 | 21->7 | 5->5 |
| 390 | 2 | 562 | 4 | 136 | 136 | +0 | 5595->5595 | 15->15 | 5->5 |
| 325 | 11 | 96 | 6 | 88 | 88 | +0 | 5746->5746 | 7->21 | 3->3 |
| 66 | 4 | 508 | 5 | 60 | 0 | +60 | 11326->11311 | 21->12 | 3->3 |
| 1 | 10 | 599 | 13 | 0 | 0 | +0 | 4307->4307 | 3->3 | 7->7 |
| 2 | 19 | 389 | 17 | 0 | 0 | +0 | 10418->10418 | 20->4 | 1->2 |
| 3 | 17 | 421 | 12 | 0 | 0 | +0 | 7842->7842 | 1->1 | 1->1 |
| 4 | 6 | 474 | 16 | 0 | 0 | +0 | 4434->4434 | 8->8 | 5->5 |
| 5 | 7 | 302 | 17 | 0 | 0 | +0 | 8304->8304 | 3->3 | 2->2 |
| 6 | 9 | 546 | 13 | 0 | 0 | +0 | 640->640 | 1->8 | 1->1 |
| 7 | 1 | 232 | 12 | 0 | 0 | +0 | 4691->4691 | 1->1 | 4->4 |
| 8 | 12 | 317 | 12 | 0 | 0 | +0 | 2155->2155 | 6->6 | 4->4 |
| 9 | 14 | 502 | 23 | 0 | 0 | +0 | 5277->5277 | 14->17 | 1->1 |
| 10 | 15 | 238 | 14 | 0 | 0 | +0 | 11648->11648 | 8->10 | 3->3 |
| 11 | 5 | 470 | 17 | 0 | 0 | +0 | 10757->10757 | 10->10 | 1->1 |
| 12 | 16 | 170 | 13 | 0 | 0 | +0 | 7868->7868 | 1->1 | 5->5 |
| 13 | 8 | 607 | 14 | 0 | 0 | +0 | 5544->5544 | 4->10 | 2->2 |
| 14 | 11 | 451 | 10 | 0 | 0 | +0 | 5766->5766 | 20->20 | 3->3 |
| 15 | 7 | 162 | 14 | 0 | 0 | +0 | 7705->7705 | 16->6 | 3->7 |
| 16 | 18 | 198 | 14 | 0 | 0 | +0 | 3172->3172 | 4->23 | 2->2 |

Significantly advanced among V6 top-20 wait tasks: 1/20.
The largest V6 wait task contributes 86.88% of total V6 E_wait.
Top-5 tasks explain 100.00% of all positive wait-cost reduction; top-20 explain 100.00%.
The improvement is concentrated if the top-5 share is high; here it is reported directly rather than inferred from the aggregate.

## 4. E_memory Regression Sources

| task | weight | duration | memory waste V6 | memory waste hard | increase | server V6->hard | GPU V6->hard |
|---:|---:|---:|---:|---:|---:|---|---|
| 255 | 7 | 466 | 5126 | 79686 | +74560 | 3->5 | 4->4 |
| 130 | 8 | 292 | 37668 | 103076 | +65408 | 13->5 | 7->7 |
| 233 | 19 | 595 | 2975 | 60095 | +57120 | 3->9 | 6->3 |
| 279 | 17 | 630 | 1260 | 41580 | +40320 | 13->9 | 8->4 |
| 272 | 15 | 180 | 2520 | 38520 | +36000 | 3->5 | 5->5 |
| 350 | 2 | 200 | 11600 | 43600 | +32000 | 6->5 | 5->5 |
| 165 | 8 | 613 | 10421 | 39845 | +29424 | 1->9 | 1->1 |
| 270 | 10 | 303 | 6060 | 35148 | +29088 | 1->22 | 3->3 |
| 414 | 18 | 547 | 5470 | 31726 | +26256 | 8->23 | 6->3 |
| 136 | 15 | 546 | 12558 | 38766 | +26208 | 22->9 | 3->3 |
| 261 | 15 | 442 | 1768 | 22984 | +21216 | 3->23 | 6->3 |
| 56 | 16 | 104 | 4888 | 24856 | +19968 | 6->5 | 6->6 |
| 57 | 12 | 515 | 7725 | 24205 | +16480 | 18->21 | 1->1 |
| 247 | 9 | 170 | 9690 | 26010 | +16320 | 1->23 | 3->3 |
| 438 | 4 | 332 | 4648 | 20584 | +15936 | 8->22 | 6->3 |
| 252 | 17 | 625 | 5000 | 20000 | +15000 | 8->14 | 4->3 |
| 369 | 3 | 286 | 2574 | 16302 | +13728 | 6->18 | 3->3 |
| 16 | 18 | 198 | 594 | 13266 | +12672 | 4->23 | 2->2 |
| 302 | 2 | 628 | 13188 | 23236 | +10048 | 8->23 | 2->1 |
| 405 | 15 | 573 | 573 | 9741 | +9168 | 18->1 | 3->5 |

Task 462 memory waste changed from 12648 to 12648; most memory regression is collateral remapping, not T462 itself.
Protecting the critical task changed the global assignment topology and displaced unrelated jobs onto poorer memory fits.

## 5. Blocker Chains

### Task 462: start 5697 -> 5598, target server 7
V6 tasks occupying the target server inside the advancement window:
T20[5458,5746),g5,w11.

## 6. Severe Regression Cases

| case | tasks | servers | weight CV | duration CV | memory CV | feasible mean | feasible CV | burstiness | E_wait V6->hard | memory delta | finish delta |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|
| case035.in | 461 | 28 | 0.841 | 0.592 | 0.973 | 15.42 | 0.430 | 0.0043 | 0->9299 | +122200 | +0 |
| case038.in | 574 | 25 | 0.816 | 0.566 | 0.778 | 15.00 | 0.349 | 0.0035 | 0->2977 | +346630 | +0 |
| case080.in | 3934 | 80 | 0.840 | 0.558 | 0.823 | 44.13 | 0.430 | 0.0010 | 0->558 | -134500 | +0 |

Case036 reference: weight CV=0.550, duration CV=0.587, memory CV=0.795, feasible mean=13.19, feasible CV=0.374, burstiness=0.0041.

## 7. Conclusions

- Case036 is a single-critical-job priority-inversion / blocker-chain case: T462 alone contributes 86.88% of V6 E_wait, has weight 19, and only 4 feasible servers.
- The hard skeleton helps by reserving ordering priority for top hard jobs before soft jobs establish the original blocker chain. It does not improve makespan; it trades some memory fit for sharply lower weighted wait.
- A detector is plausible, but it should route only cases with a predicted concentrated wait tail. Input features alone are insufficient; run a cheap baseline and inspect the schedule.
- Recommended detector: require baseline E_wait > 0; top-1 wait_cost share >= 70% or top-5 share >= 90%; the dominant wait task has weight >= p90 and feasible-mode count <= p25; then accept the cheap hard candidate only when E_wait drops >= 50%, E_memory_new <= 1.05 * baseline, and E_finish <= 1.005 * baseline.
- Immediate disable condition: baseline E_wait == 0. All three severe controls had zero V6 wait and the hard skeleton manufactured positive wait. Also disable for a diffuse wait tail or projected memory regression above 5%.
