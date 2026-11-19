"""Verify complete shard coverage from collected IDs, phase logs and JUnit."""
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent


def main():
    selected = []; collections = []; runs = []; phases = defaultdict(float)
    sql_seconds = defaultdict(float); slow = []; issues = []; remaining = []
    for index in range(4):
        pointer = ROOT / f'FINAL_RELEASE_SHARD_{index}.json'
        if not pointer.exists():
            issues.append(f'Shard {index} not started'); continue
        directory = Path(json.loads(pointer.read_text())['directory'])
        if not (directory / 'collected.json').exists():
            issues.append(f'Shard {index} not collected'); continue
        collected = json.loads((directory / 'collected.json').read_text())
        assigned = json.loads((directory / 'selected.json').read_text())
        collections.append(collected); selected.extend(assigned)
        rows = [json.loads(line) for line in (directory / 'progress.jsonl').read_text().splitlines()]
        completed = {row['nodeid'] for row in rows if row.get('phase') == 'teardown'}
        remaining.extend(nodeid for nodeid in assigned if nodeid not in completed)
        for row in rows:
            if row.get('event') != 'phase': continue
            phases[row['phase']] += row['seconds']
            slow.append({key: row[key] for key in ('nodeid', 'phase', 'seconds', 'outcome')})
            if row['phase'] == 'teardown':
                for operation, duration in row['sql_seconds'].items(): sql_seconds[operation] += duration
        summary = json.loads((directory / 'summary.json').read_text()) if (directory / 'summary.json').exists() else {}
        junit = directory / 'results.xml'
        cases = list(ET.parse(junit).iter('testcase')) if junit.exists() else []
        failures = sum(case.find('failure') is not None or case.find('error') is not None for case in cases)
        skipped = sum(case.find('skipped') is not None for case in cases)
        runs.append({'index': index, 'directory': str(directory), 'assigned': len(assigned), 'completed': len(completed),
            'junit_cases': len(cases), 'failures_or_errors': failures, 'skipped': skipped, **summary,
            'last_phase': next((row['nodeid']+':'+row['phase'] for row in reversed(rows) if row.get('event') == 'phase'), None),
            'stack_dumps': (directory / 'pytest.log').read_text().count('Timeout (')})
        if summary.get('pytest_exit') != 0 or summary.get('timeout') or len(cases) != len(assigned):
            issues.append(f'Shard {index} lacks a successful complete JUnit result')
    if collections and any(items != collections[0] for items in collections): issues.append('Collection changed between shards')
    expected = collections[0] if collections else []
    if Counter(selected) != Counter(expected): issues.append('Selected shard union differs from full collection')
    if len(set(selected)) != len(selected): issues.append('Duplicate shard test IDs')
    source = json.loads((ROOT / 'FINAL_RELEASE_SUITE_SOURCE.json').read_text())
    changed = [name for name, digest in source.items() if not (ROOT/'backend'/name).exists()
        or hashlib.sha256((ROOT/'backend'/name).read_bytes()).hexdigest() != digest]
    if changed: issues.append('Backend source changed during run')
    result = {'full_suite_passed': not issues and len(runs) == 4 and not remaining,
        'collected': len(expected), 'executed_junit_cases': sum(run['junit_cases'] for run in runs),
        'issues': issues, 'remaining': remaining, 'runs': runs, 'phase_seconds': dict(phases),
        'sql_seconds_cumulative': dict(sql_seconds), 'slowest_phases': sorted(slow,key=lambda row:row['seconds'],reverse=True)[:30],
        'source_changes': changed}
    (ROOT/'FINAL_RELEASE_SUITE_SUMMARY.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({key:result[key] for key in ('full_suite_passed','collected','executed_junit_cases','issues','phase_seconds')},indent=2))


if __name__ == '__main__': main()