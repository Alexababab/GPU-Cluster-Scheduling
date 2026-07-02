#!/usr/bin/env python3
"""Forensic comparison of V6-safe and hard_p10_slack_light on case036."""

from __future__ import annotations

import argparse
import csv
import math
import statistics
from collections import Counter
from pathlib import Path


def parse_instance(path: Path):
    rows = [list(map(int, line.split())) for line in path.read_text().splitlines() if line.strip()]
    server_count, task_count = rows[0]
    servers = [dict(id=i + 1, gpu=r[0], gpu_memory=r[1], cpu=r[2], ram=r[3]) for i, r in enumerate(rows[1:1 + server_count])]
    tasks = [dict(id=i + 1, release=r[0], duration=r[1], min_gpu=r[2], total_gpu_memory=r[3], cpu=r[4], ram=r[5], weight=r[6]) for i, r in enumerate(rows[1 + server_count:])]
    assert len(tasks) == task_count
    return servers, tasks


def parse_schedule(path: Path):
    return {int(parts[0]): dict(task_id=int(parts[0]), server_id=int(parts[1]), start=int(parts[2]), gpu=int(parts[3]), finish=int(parts[4])) for parts in (line.split() for line in path.read_text().splitlines() if line.strip())}


def q(values, percentile):
    values = sorted(values)
    if not values:
        return 0
    index = (len(values) - 1) * percentile
    low, high = math.floor(index), math.ceil(index)
    if low == high:
        return values[low]
    return values[low] * (high - index) + values[high] * (index - low)


def distribution(values):
    mean = statistics.fmean(values) if values else 0
    std = statistics.pstdev(values) if len(values) > 1 else 0
    return dict(min=min(values), p25=q(values, .25), median=q(values, .5), p75=q(values, .75), p90=q(values, .9), max=max(values), mean=mean, cv=std / mean if mean else 0)


def dist_text(values):
    d = distribution(values)
    return f"min={d['min']:.2f}, p25={d['p25']:.2f}, median={d['median']:.2f}, p75={d['p75']:.2f}, p90={d['p90']:.2f}, max={d['max']:.2f}, mean={d['mean']:.2f}, CV={d['cv']:.3f}"


def feasible_counts(servers, tasks):
    counts = {}
    for task in tasks:
        count = 0
        for server in servers:
            gpu = max(task['min_gpu'], math.ceil(task['total_gpu_memory'] / server['gpu_memory']))
            count += gpu <= server['gpu'] and task['cpu'] <= server['cpu'] and task['ram'] <= server['ram']
        counts[task['id']] = count
    return counts


def task_costs(servers, tasks, schedule):
    server_by_id = {server['id']: server for server in servers}
    result = {}
    for task in tasks:
        assignment = schedule[task['id']]
        server = server_by_id[assignment['server_id']]
        result[task['id']] = dict(
            wait=(assignment['start'] - task['release']) * task['weight'],
            memory=task['duration'] * (assignment['gpu'] * server['gpu_memory'] - task['total_gpu_memory']),
            finish=assignment['finish'],
        )
    return result


def metrics(costs):
    return dict(wait=sum(item['wait'] for item in costs.values()), memory=sum(item['memory'] for item in costs.values()), finish=max(item['finish'] for item in costs.values()))


def profile(path: Path):
    servers, tasks = parse_instance(path)
    feasible = feasible_counts(servers, tasks)
    release_counts = Counter(task['release'] for task in tasks)
    release_burstiness = max(release_counts.values()) / len(tasks)
    return dict(
        servers=servers,
        tasks=tasks,
        feasible=feasible,
        server_count=len(servers),
        task_count=len(tasks),
        gpu=distribution([server['gpu'] for server in servers]),
        gpu_memory=distribution([server['gpu_memory'] for server in servers]),
        weight=distribution([task['weight'] for task in tasks]),
        duration=distribution([task['duration'] for task in tasks]),
        min_gpu=distribution([task['min_gpu'] for task in tasks]),
        total_gpu_memory=distribution([task['total_gpu_memory'] for task in tasks]),
        feasible_modes=distribution(list(feasible.values())),
        release_burstiness=release_burstiness,
        unique_release_ratio=len(release_counts) / len(tasks),
    )


def composite_change(old, new):
    return 100 * ((new['wait'] / max(1, old['wait']) - 1) + (new['memory'] / max(1, old['memory']) - 1) + (new['finish'] / max(1, old['finish']) - 1)) / 3


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    root = args.root
    data_dir = root / '课程设计相关材料' / '课程设计相关材料' / '数据集'
    case_path = data_dir / 'case036.in'
    v6_dir = root / 'tmp' / 'v6-safe-final'
    hard_dir = root / 'tmp' / 'v8-hard_p10_slack_light'
    servers, tasks = parse_instance(case_path)
    task_by_id = {task['id']: task for task in tasks}
    v6_schedule = parse_schedule(v6_dir / 'case036.out')
    hard_schedule = parse_schedule(hard_dir / 'case036.out')
    v6_costs = task_costs(servers, tasks, v6_schedule)
    hard_costs = task_costs(servers, tasks, hard_schedule)
    v6_metrics, hard_metrics = metrics(v6_costs), metrics(hard_costs)
    case_profile = profile(case_path)
    feasible = case_profile['feasible']
    hard_count = max(1, len(tasks) * 10 // 100)

    top_wait = sorted(tasks, key=lambda task: v6_costs[task['id']]['wait'], reverse=True)[:20]
    wait_improvements = {task['id']: v6_costs[task['id']]['wait'] - hard_costs[task['id']]['wait'] for task in tasks}
    positive_improvement = sum(max(0, value) for value in wait_improvements.values())
    baseline_top1_share = v6_costs[top_wait[0]['id']]['wait'] / max(1, v6_metrics['wait'])
    significant = [task for task in top_wait if v6_schedule[task['id']]['start'] - hard_schedule[task['id']]['start'] >= max(10, task['duration'] // 10)]

    memory_increases = sorted(tasks, key=lambda task: hard_costs[task['id']]['memory'] - v6_costs[task['id']]['memory'], reverse=True)[:20]

    blockers = {}
    for task in significant[:10]:
        task_id = task['id']
        target = hard_schedule[task_id]
        interval_start = target['start']
        interval_end = v6_schedule[task_id]['start']
        matches = []
        if interval_end > interval_start:
            for other_id, assignment in v6_schedule.items():
                if other_id == task_id or assignment['server_id'] != target['server_id']:
                    continue
                if assignment['start'] < interval_end and assignment['finish'] > interval_start:
                    other = task_by_id[other_id]
                    matches.append((other_id, assignment['start'], assignment['finish'], assignment['gpu'], other['weight']))
        blockers[task_id] = sorted(matches, key=lambda item: (item[1], item[0]))

    with (v6_dir / 'batch_summary.csv').open(encoding='utf-8-sig', newline='') as source:
        v6_rows = {row['case']: row for row in csv.DictReader(source)}
    with (hard_dir / 'batch_summary.csv').open(encoding='utf-8-sig', newline='') as source:
        hard_rows = {row['case']: row for row in csv.DictReader(source)}
    case_scores = []
    for case, old in v6_rows.items():
        new = hard_rows[case]
        old_metrics = dict(wait=float(old['E_wait']), memory=float(old['E_memory_new']), finish=float(old['E_finish']))
        new_metrics = dict(wait=float(new['E_wait']), memory=float(new['E_memory_new']), finish=float(new['E_finish']))
        case_scores.append((composite_change(old_metrics, new_metrics), case))
    severe_cases = [case for _, case in sorted(case_scores, reverse=True)[:3]]
    severe_profiles = {case: profile(data_dir / case) for case in severe_cases}

    lines = [
        '# Case036 Hard Skeleton Forensic Analysis', '',
        '## 1. Input Profile', '',
        f"- task_count: {len(tasks)}",
        f"- server_count: {len(servers)}",
        f"- server GPU distribution: {dist_text([s['gpu'] for s in servers])}",
        f"- server GPU-memory distribution: {dist_text([s['gpu_memory'] for s in servers])}",
        f"- task weight distribution: {dist_text([t['weight'] for t in tasks])}",
        f"- duration distribution: {dist_text([t['duration'] for t in tasks])}",
        f"- min_gpu distribution: {dist_text([t['min_gpu'] for t in tasks])}",
        f"- total_gpu_memory distribution: {dist_text([t['total_gpu_memory'] for t in tasks])}",
        f"- feasible_mode_count distribution: {dist_text(list(feasible.values()))}",
        f"- release_time burstiness (largest identical-release group / N): {case_profile['release_burstiness']:.4f}",
        f"- unique release-time ratio: {case_profile['unique_release_ratio']:.4f}",
        f"- hard_job_count (top 10%): {hard_count}", '',
        'Server GPU counts: ' + str(dict(sorted(Counter(s['gpu'] for s in servers).items()))) + '.',
        'Server GPU-memory values: ' + str(dict(sorted(Counter(s['gpu_memory'] for s in servers).items()))) + '.', '',
        '## 2. V6-safe vs hard_p10_slack_light', '',
        '| metric | V6-safe | hard_p10_slack_light | delta | change |',
        '|---|---:|---:|---:|---:|',
    ]
    for key, label in [('wait', 'E_wait'), ('memory', 'E_memory_new'), ('finish', 'E_finish')]:
        old, new = v6_metrics[key], hard_metrics[key]
        lines.append(f"| {label} | {old:.0f} | {new:.0f} | {new-old:+.0f} | {(new/old-1)*100 if old else 0:+.4f}% |")
    weighted_proxy_change = 100 * (
        hard_metrics['wait'] / v6_metrics['wait'] - 1.0 +
        1.25 * (hard_metrics['memory'] / v6_metrics['memory'] - 1.0) +
        hard_metrics['finish'] / v6_metrics['finish'] - 1.0
    )
    lines += ['', f"Leaderboard-style weighted proxy change (wait + 1.25*memory + finish): {weighted_proxy_change:+.4f}%.",
              f"Equal-weight averaged relative change: {composite_change(v6_metrics, hard_metrics):+.4f}%.", '',
              '## 3. E_wait Improvement Sources', '',
              '| task | weight | duration | feasible modes | V6 wait_cost | hard wait_cost | wait improvement | start V6->hard | server V6->hard | GPU V6->hard |',
              '|---:|---:|---:|---:|---:|---:|---:|---|---|---|']
    for task in top_wait:
        task_id = task['id']; old = v6_schedule[task_id]; new = hard_schedule[task_id]
        lines.append(f"| {task_id} | {task['weight']} | {task['duration']} | {feasible[task_id]} | {v6_costs[task_id]['wait']:.0f} | {hard_costs[task_id]['wait']:.0f} | {wait_improvements[task_id]:+.0f} | {old['start']}->{new['start']} | {old['server_id']}->{new['server_id']} | {old['gpu']}->{new['gpu']} |")
    top5_share = sum(max(0, wait_improvements[t['id']]) for t in top_wait[:5]) / max(1, positive_improvement)
    top20_share = sum(max(0, wait_improvements[t['id']]) for t in top_wait) / max(1, positive_improvement)
    lines += ['', f"Significantly advanced among V6 top-20 wait tasks: {len(significant)}/20.",
              f"The largest V6 wait task contributes {baseline_top1_share*100:.2f}% of total V6 E_wait.",
              f"Top-5 tasks explain {top5_share*100:.2f}% of all positive wait-cost reduction; top-20 explain {top20_share*100:.2f}%.",
              'The improvement is concentrated if the top-5 share is high; here it is reported directly rather than inferred from the aggregate.', '',
              '## 4. E_memory Regression Sources', '',
              '| task | weight | duration | memory waste V6 | memory waste hard | increase | server V6->hard | GPU V6->hard |',
              '|---:|---:|---:|---:|---:|---:|---|---|']
    for task in memory_increases:
        task_id = task['id']; old = v6_schedule[task_id]; new = hard_schedule[task_id]
        lines.append(f"| {task_id} | {task['weight']} | {task['duration']} | {v6_costs[task_id]['memory']:.0f} | {hard_costs[task_id]['memory']:.0f} | {hard_costs[task_id]['memory']-v6_costs[task_id]['memory']:+.0f} | {old['server_id']}->{new['server_id']} | {old['gpu']}->{new['gpu']} |")
    lines += ['', f"Task 462 memory waste changed from {v6_costs[462]['memory']:.0f} to {hard_costs[462]['memory']:.0f}; most memory regression is collateral remapping, not T462 itself.",
              'Protecting the critical task changed the global assignment topology and displaced unrelated jobs onto poorer memory fits.', '',
              '## 5. Blocker Chains', '']
    for task in significant[:10]:
        task_id = task['id']; target = hard_schedule[task_id]
        lines.append(f"### Task {task_id}: start {v6_schedule[task_id]['start']} -> {target['start']}, target server {target['server_id']}")
        if blockers[task_id]:
            lines.append('V6 tasks occupying the target server inside the advancement window:')
            lines.append(', '.join(f"T{bid}[{start},{finish}),g{gpu},w{weight}" for bid,start,finish,gpu,weight in blockers[task_id]) + '.')
        else:
            lines.append('No direct same-server overlap was found; the delay was likely an indirect capacity/event-order chain.')
        lines.append('')
    lines += ['## 6. Severe Regression Cases', '',
              '| case | tasks | servers | weight CV | duration CV | memory CV | feasible mean | feasible CV | burstiness | E_wait V6->hard | memory delta | finish delta |',
              '|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|']
    score_by_case = {case: score for score, case in case_scores}
    for case in severe_cases:
        p = severe_profiles[case]
        old_row, new_row = v6_rows[case], hard_rows[case]
        lines.append(f"| {case} | {p['task_count']} | {p['server_count']} | {p['weight']['cv']:.3f} | {p['duration']['cv']:.3f} | {p['total_gpu_memory']['cv']:.3f} | {p['feasible_modes']['mean']:.2f} | {p['feasible_modes']['cv']:.3f} | {p['release_burstiness']:.4f} | {float(old_row['E_wait']):.0f}->{float(new_row['E_wait']):.0f} | {float(new_row['E_memory_new'])-float(old_row['E_memory_new']):+.0f} | {float(new_row['E_finish'])-float(old_row['E_finish']):+.0f} |")
    lines += ['', 'Case036 reference: '
              f"weight CV={case_profile['weight']['cv']:.3f}, duration CV={case_profile['duration']['cv']:.3f}, memory CV={case_profile['total_gpu_memory']['cv']:.3f}, feasible mean={case_profile['feasible_modes']['mean']:.2f}, feasible CV={case_profile['feasible_modes']['cv']:.3f}, burstiness={case_profile['release_burstiness']:.4f}.", '',
              '## 7. Conclusions', '',
              '- Case036 is a single-critical-job priority-inversion / blocker-chain case: T462 alone contributes 86.88% of V6 E_wait, has weight 19, and only 4 feasible servers.',
              '- The hard skeleton helps by reserving ordering priority for top hard jobs before soft jobs establish the original blocker chain. It does not improve makespan; it trades some memory fit for sharply lower weighted wait.',
              '- A detector is plausible, but it should route only cases with a predicted concentrated wait tail. Input features alone are insufficient; run a cheap baseline and inspect the schedule.',
              '- Recommended detector: require baseline E_wait > 0; top-1 wait_cost share >= 70% or top-5 share >= 90%; the dominant wait task has weight >= p90 and feasible-mode count <= p25; then accept the cheap hard candidate only when E_wait drops >= 50%, E_memory_new <= 1.05 * baseline, and E_finish <= 1.005 * baseline.',
              '- Immediate disable condition: baseline E_wait == 0. All three severe controls had zero V6 wait and the hard skeleton manufactured positive wait. Also disable for a diffuse wait tail or projected memory regression above 5%.',
              '']
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text('\n'.join(lines), encoding='utf-8', newline='\n')
    print(f"wrote {args.report}")
    print(f"case036 weighted_proxy={weighted_proxy_change:+.4f}% equal_composite={composite_change(v6_metrics, hard_metrics):+.4f}% top1_share={baseline_top1_share:.4f} top5_improvement_share={top5_share:.4f} significant={len(significant)}")
    print('severe regressions:', ', '.join(severe_cases))


if __name__ == '__main__':
    main()
