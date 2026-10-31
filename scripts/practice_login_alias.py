"""Candidate's small retrieval exercise; never supplies Agent decisions/answers.

Run --phase before, make a short phrase normalization change yourself, then run
--phase after. Each invocation preserves actual results in a new directory.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import uuid

from kb_agent.retrieval import KnowledgeBase, tokenize


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=['before', 'after'], required=True)
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    root = Path(__file__).resolve().parents[1]
    kb = KnowledgeBase(root / 'data/conflict.json')
    rows = []
    # Exercise labels, isolated from the existing fixed 10-query benchmark.
    for role, query, relevant in [
        ('development', '忘了登录暗号怎么办', {'D04'}),
        ('transfer_check', '登录暗号忘记了去哪里重设', {'D04'}),
        ('negative_control', '活动接头暗号是什么', set()),
    ]:
        hits = kb.search(query, 3)
        found = {hit['doc_id'] for hit in hits}
        passed = relevant.issubset(found) if relevant else not hits
        rows.append({'role': role, 'query': query, 'tokens': tokenize(query),
                     'expected_doc_ids': sorted(relevant), 'hits': hits,
                     'verdict': 'PASS' if passed else 'FAIL'})
    directory = root / 'examples/practice' / ('login_alias_' + args.phase + '_' + uuid.uuid4().hex[:12])
    directory.mkdir(parents=True)
    report = {'phase': args.phase, 'created_at': datetime.now(timezone.utc).isoformat(),
              'corpus_sha256': kb.sha256,
              'retrieval_source_sha256': hashlib.sha256((root / 'src/kb_agent/retrieval.py').read_bytes()).hexdigest(),
              'rows': rows, 'counts': {v: sum(r['verdict'] == v for r in rows) for v in ['PASS', 'FAIL']},
              'notice': '仅检索词面练习，不是Live模型效果；个人是否亲手完成须本人确认。新增词表后此transfer_check不能再称为独立盲测。'}
    path = directory / 'report.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'report': path.relative_to(root).as_posix(), 'counts': report['counts']}, ensure_ascii=False, indent=2))
    return 1 if report['counts']['FAIL'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
