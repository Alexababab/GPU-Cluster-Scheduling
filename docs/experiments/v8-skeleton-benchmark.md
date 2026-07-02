# V8 Skeleton Benchmark

| candidate | source | legal | selected | avg E_wait | avg E_memory_new | avg E_finish | composite vs V6 | strict I/R/M | max runtime | case100 |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| hard_p5_slack0 | hard_job_skeleton | 100/100 | 3 | 132145354.56 | 20163060.78 | 22347.06 | +1.370608% | 3/63/34 | 3.058374 | 3.058374 |
<!-- best hard_p5_slack0: case059.in (-1.9696%), case030.in (-0.8076%), case084.in (-0.4287%) -->
| hard_p10_slack0 | hard_job_skeleton | 100/100 | 0 | 136569192.52 | 20075988.42 | 22397.45 | +2.452779% | 3/62/35 | 3.005905 | 3.005905 |
<!-- best hard_p10_slack0: case059.in (-1.9696%), case006.in (-0.8088%), case030.in (-0.8076%) -->
| hard_p15_slack0 | hard_job_skeleton | 100/100 | 1 | 141432444.20 | 20123765.50 | 22378.06 | +3.769581% | 2/67/31 | 2.756865 | 2.299224 |
<!-- best hard_p15_slack0: case014.in (-5.5174%), case030.in (-0.8076%), case084.in (-0.4287%) -->
| hard_p10_slack_light | hard_job_skeleton | 100/100 | 1 | 136444287.70 | 20212852.12 | 22384.85 | +2.629284% | 1/68/31 | 2.713846 | 2.713846 |
<!-- best hard_p10_slack_light: case036.in (-84.6469%), case016.in (-2.7649%), case006.in (-0.8088%) -->
| hard_p15_slack_light | hard_job_skeleton | 100/100 | 1 | 141419893.70 | 20119838.22 | 22401.82 | +3.795283% | 1/65/34 | 3.072427 | 2.875680 |
<!-- best hard_p15_slack_light: case036.in (-84.6469%), case016.in (-7.7031%), case029.in (-0.1842%) -->
| reservation_top3_strict | reservation_profile | 100/100 | 6 | 128137948.47 | 20148959.68 | 22395.06 | +0.375462% | 4/68/28 | 2.111513 | 1.774477 |
<!-- best reservation_top3_strict: case078.in (-2.9719%), case045.in (-2.6757%), case039.in (-2.2442%) -->
| reservation_top5_slack | reservation_profile | 100/100 | 3 | 128149245.27 | 20174077.80 | 22387.60 | +0.409072% | 3/64/33 | 2.548054 | 1.969099 |
<!-- best reservation_top5_slack: case086.in (-3.8129%), case059.in (-1.9696%), case049.in (-0.9596%) -->
| reservation_top10_slack | reservation_profile | 100/100 | 3 | 128258241.31 | 20190406.60 | 22407.64 | +0.494585% | 3/67/30 | 2.628662 | 2.628662 |
<!-- best reservation_top10_slack: case014.in (-5.5174%), case049.in (-5.2274%), case066.in (-3.5062%) -->
| regret2_all | regret_constructor | 100/100 | 1 | 140332634.88 | 20278276.02 | 22439.62 | +3.832457% | 2/70/28 | 2.121838 | 1.648359 |
<!-- best regret2_all: case025.in (-1.0349%), case030.in (-0.8076%), case076.in (-0.2968%) -->
| regret3_all | regret_constructor | 100/100 | 0 | 145685142.75 | 20205484.76 | 22420.39 | +5.076158% | 1/71/28 | 2.007272 | 1.469088 |
<!-- best regret3_all: case030.in (-0.8076%), case001.in (+0.0000%), case005.in (+0.0000%) -->
| regret2_hard_first | regret_constructor | 100/100 | 1 | 143266413.84 | 20070245.22 | 22382.59 | +4.164756% | 2/63/35 | 2.265648 | 1.524569 |
<!-- best regret2_hard_first: case012.in (-9.6455%), case030.in (-0.8076%), case001.in (+0.0000%) -->
| window_memory_hotspot | window_repacking | 100/100 | 5 | 128023648.83 | 20020373.04 | 22305.21 | -0.002648% | 8/0/92 | 50.779929 | 46.543595 |
<!-- best window_memory_hotspot: case021.in (-39.4737%), case035.in (-4.2851%), case026.in (-2.0223%) -->
| window_wait_hotspot | window_repacking | 100/100 | 2 | 128023553.72 | 20020601.38 | 22305.21 | -0.002292% | 5/0/95 | 52.736675 | 50.407257 |
<!-- best window_wait_hotspot: case004.in (-10.3727%), case031.in (-5.7347%), case053.in (-0.6449%) -->
| window_tail_hotspot | window_repacking | 100/100 | 13 | 128023623.94 | 20018479.98 | 22305.21 | -0.005806% | 15/0/85 | 53.440439 | 47.567728 |
<!-- best window_tail_hotspot: case035.in (-5.6724%), case025.in (-3.6802%), case042.in (-3.6073%) -->

Promising skeletons: none.
Combined per-case skeleton oracle composite vs V6: -0.037443%.

## Oracle Selection Counts

- v6_safe: 60
- window_tail_hotspot: 13
- reservation_top3_strict: 6
- window_memory_hotspot: 5
- hard_p5_slack0: 3
- reservation_top10_slack: 3
- reservation_top5_slack: 3
- window_wait_hotspot: 2
- regret2_hard_first: 1
- hard_p15_slack0: 1
- hard_p15_slack_light: 1
- hard_p10_slack_light: 1
- regret2_all: 1

## Winner Profiles

- window_repacking: {'balanced': 16, 'memory_dominated': 4}
- regret_constructor: {'memory_dominated': 1, 'large_dense': 1}
- hard_job_skeleton: {'memory_dominated': 2, 'balanced': 3, 'large_dense': 1}
- reservation_profile: {'balanced': 4, 'memory_dominated': 2, 'large_dense': 6}

## Loser Profiles

- hard_job_skeleton: {'balanced': 200, 'heterogeneous_tight': 5, 'memory_dominated': 114, 'large_dense': 71}
- reservation_profile: {'balanced': 114, 'heterogeneous_tight': 3, 'memory_dominated': 52, 'large_dense': 19}
- regret_constructor: {'balanced': 129, 'heterogeneous_tight': 3, 'memory_dominated': 71, 'large_dense': 46}
