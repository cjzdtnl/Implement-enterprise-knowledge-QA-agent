"""Reproducible acceptance evidence; fixtures never count as live behavior.

Creates a new directory on every invocation. Configuration values are never
printed. Run baseline before edits, then run again with --clean-env after edits.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid
import venv

from kb_agent.config import ENV_KEYS, load_env_file
from kb_agent.evaluation import assess, load_events
from kb_agent.model import LiveClient
from kb_agent.retrieval import KnowledgeBase
from kb_agent.runner import run_agent, write_json
from kb_agent.schema import AgentInput, FinalAnswer
from kb_agent.tools import ToolExecutor
from kb_agent.validation import validate_answer


ROOT = Path(__file__).resolve().parents[1]


def now():
    return datetime.now(timezone.utc).isoformat()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=['baseline', 'after'], required=True)
    parser.add_argument('--clean-env', action='store_true')
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    directory = ROOT / 'examples/audit' / ('review_' + args.phase + '_' + uuid.uuid4().hex[:12])
    directory.mkdir(parents=True)
    print(directory.relative_to(ROOT).as_posix(), flush=True)
    records = []
    offline_env = {k: v for k, v in os.environ.items() if k not in ENV_KEYS}
    offline_env.update(PYTHONIOENCODING='utf-8', PYTHONUTF8='1')
    offline_env.pop('PYTHONPATH', None)

    def command(name, arguments, *, cwd=ROOT, env=None, interpreter=sys.executable):
        started = time.perf_counter()
        started_at = now()
        process = subprocess.run([str(interpreter), *map(str, arguments)], cwd=cwd,
                                 env=env or offline_env, capture_output=True, text=True, encoding='utf-8')
        (directory / (name + '.stdout.txt')).write_text(process.stdout, encoding='utf-8')
        (directory / (name + '.stderr.txt')).write_text(process.stderr, encoding='utf-8')
        records.append({'name': name, 'command': [str(interpreter), *map(str, arguments)],
                        'cwd': str(cwd), 'started_at': started_at, 'ended_at': now(),
                        'duration_seconds': round(time.perf_counter() - started, 6), 'exit_code': process.returncode})
        write_json(directory / 'commands.json', records)
        print(f'{name}: exit={process.returncode}', flush=True)
        return process

    command('pip-check', ['-m', 'pip', 'check'])
    command('offline-tests', ['-m', 'pytest', '-q', '-m', 'not live', '--tb=short'])
    command('mock-evaluation', ['-m', 'kb_agent', 'evaluate', '--mode', 'mock'])
    command('retrieval-evaluation', ['-m', 'kb_agent', 'retrieval-eval'])
    command('independent-negative-audit', ['scripts/offline_requirements_audit.py'])

    # Reproduce two independently constructed gaps before/after fixing them.
    corpus = KnowledgeBase(ROOT / 'data/no_conflict.json')
    executor = ToolExecutor(corpus)
    executor.execute('read_excerpt', json.dumps({'doc_id': 'D01', 'section_id': 'S01', 'purpose': '独立单位负例'}))
    source = corpus.sections[('D01', 'S01')]
    value = FinalAnswer(status='answered', answer='报销材料须在费用发生后 30 年内提交。',
                        claims=[{'text': '报销材料须在费用发生后 30 年内提交。', 'citation_ids': ['C1']}],
                        citations=[{'citation_id': 'C1', 'doc_id': 'D01', 'section_id': 'S01',
                                    'version_date': source['version_date'], 'quote': source['text']}],
                        conflicts=[], knowledge_gaps=[], clarification_question=None,
                        stop_reason='explicit_offline_negative_fixture', run_id='unit-negative')
    errors = validate_answer(value, executor, value.run_id)
    probes = [{'id': 'B01', 'name': '数字相同但单位从天改成年', 'verdict': 'PASS' if errors else 'FAIL',
               'fixture_output': value.model_dump(), 'runtime_errors': errors}]

    class NoAttempt:
        model_name = 'explicit-offline-no-attempt-fixture'

        def complete(self, messages, tools, timeout):
            from kb_agent.model import ModelReply
            run_id = messages[0]['content'].split('run_id 必须是 ')[1].split('。')[0]
            return ModelReply({'role': 'assistant', 'content': json.dumps({
                'status': 'tool_failed', 'answer': '检索服务持续失败，未取得依据。', 'claims': [], 'citations': [],
                'conflicts': [], 'knowledge_gaps': ['无可用检索'], 'clarification_question': None,
                'stop_reason': 'explicit_offline_no_attempt', 'run_id': run_id}, ensure_ascii=False)})

    normal = AgentInput.model_validate_json((ROOT / 'examples/inputs/normal.json').read_text(encoding='utf-8'))
    result, no_attempt_dir = run_agent(normal, ROOT / 'data/no_conflict.json', directory / 'B02',
                                       mode='mock', client=NoAttempt(), fault='always_search')
    cases = json.loads((ROOT / 'data/evaluation_cases.json').read_text(encoding='utf-8'))['cases']
    case = next(c for c in cases if c['id'] == 'E07')
    errors = assess(case, result, no_attempt_dir)
    probes.append({'id': 'B02', 'name': '没有执行工具就谎报持续失败', 'verdict': 'PASS' if errors else 'FAIL',
                   'directory': no_attempt_dir.relative_to(ROOT).as_posix(), 'assessment_errors': errors})
    write_json(directory / 'independent-probes.json', {'notice': '显式离线负例，不是真实模型结果。', 'probes': probes})

    # Create new corpus copies; never mutate data/ or use pre-built replaced_45.
    fixtures = directory / 'fixtures'
    fixtures.mkdir()
    original = json.loads((ROOT / 'data/no_conflict.json').read_text(encoding='utf-8'))
    changed = copy.deepcopy(original)
    document = next(d for d in changed['documents'] if d['doc_id'] == 'D01')
    document['sections'][0]['text'] = document['sections'][0]['text'].replace('30', '45')
    added = copy.deepcopy(original)
    conflict = json.loads((ROOT / 'data/conflict.json').read_text(encoding='utf-8'))
    added['documents'].append(copy.deepcopy(next(d for d in conflict['documents'] if d['doc_id'] == 'D02')))
    mutations = []
    for name, data, expectation in [('original', original, 'E01'), ('changed45', changed, 'E09'), ('added-conflict', added, 'E10')]:
        path = fixtures / (name + '.json')
        write_json(path, data)
        output, run_dir = run_agent(normal, path, directory / name, mode='mock')
        failures = assess(next(c for c in cases if c['id'] == expectation), output, run_dir)
        mutations.append({'name': name, 'mode': 'mock', 'verdict': 'FAIL' if failures else 'PASS',
                          'errors': failures, 'directory': run_dir.relative_to(ROOT).as_posix(),
                          'fixture': path.relative_to(ROOT).as_posix(), 'status': output.status,
                          'corpus_sha256': KnowledgeBase(path).sha256,
                          'path': [e.get('tool_name', e.get('status')) for e in load_events(run_dir)
                                   if e['event'] in {'tool_call', 'final'}]})
    write_json(directory / 'mutations.json', {'notice': 'Mock 验证重新加载及执行机制，真实模型响应变化另列。', 'runs': mutations})

    # Only inspect this project's explicitly authorized .env and process config.
    live_config = {'env_file_exists': (ROOT / '.env').is_file(), 'config_error': None}
    key = ''
    try:
        if live_config['env_file_exists']:
            load_env_file(ROOT / '.env')
        key = os.getenv('LLM_API_KEY') or os.getenv('DEEPSEEK_API_KEY') or ''
        placeholder = any(token in key.lower() for token in ('replace-with', 'your-key', 'fixture', '你的', '实际密钥'))
        live_config['key_available'] = bool(key.strip()) and not placeholder
    except (OSError, ValueError) as exc:
        live_config.update(config_error=type(exc).__name__, key_available=False)
    live_env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1')
    # Without a usable key, remove placeholders and obtain actual CONFIG_MISSING artifacts.
    if not live_config['key_available']:
        live_env = dict(offline_env)
    live_env.setdefault('LLM_TIMEOUT_SECONDS', '60')
    live_env.setdefault('RUN_TIMEOUT_SECONDS', '300')
    command('live-evaluation', ['-m', 'kb_agent', 'evaluate', '--mode', 'live', '--provider', 'deepseek'], env=live_env)
    live_config['verdict'] = 'ATTEMPTED' if live_config['key_available'] else 'BLOCKED'
    live_config['reason'] = None if live_config['key_available'] else '当前项目无可用密钥；配置失败不是模型行为证据。'
    write_json(directory / 'live-configuration.json', live_config)

    # Audit existing user-run web live evidence as well as this batch. Do not
    # confuse zero requests in the new batch with absence of historical live.
    history = []
    for path in ROOT.glob('examples/live/web/*/*/meta.json'):
        meta = json.loads(path.read_text(encoding='utf-8'))
        if not meta['steps']:
            continue
        events = load_events(path.parent)
        observations, actions, failures = {}, {}, []
        for event in events:
            if event['event'] == 'action':
                for call in event['action'].get('tool_calls', []):
                    actions[call['id']] = call['function']
            elif event['event'] == 'tool_call':
                function = actions.get(event['tool_call_id'])
                if not function or function['name'] != event['tool_name'] or json.loads(function['arguments']) != event['arguments']:
                    failures.append('executed tool differs from model action')
            elif event['event'] == 'tool_result':
                observations[event['tool_call_id']] = event['result']
            elif event['event'] == 'model_request':
                context = {m['tool_call_id']: json.loads(m['content']) for m in event['messages'] if m['role'] == 'tool'}
                if any(context.get(call_id) != value for call_id, value in observations.items()):
                    failures.append('tool observation omitted or altered in next request')
        history.append({'directory': path.parent.relative_to(ROOT).as_posix(), 'status': meta['status'],
                        'steps': meta['steps'], 'tool_calls': meta['tool_calls'], 'transport_retries': meta['transport_retries'],
                        'usage_present': all(item.get('usage') is not None for item in meta['model_requests']),
                        'measured_latency_present': all(item.get('latency_ms') is not None for item in meta['model_requests']),
                        'trace_chain_errors': failures,
                        'sequence': [e.get('tool_name', e.get('status')) for e in events if e['event'] in {'tool_call', 'final'}]})
    write_json(directory / 'existing-live-evidence.json', {'records': history,
               'notice': '依据已有本机 HTTP 运行产物及代码核验，不冒称为本轮重新请求；仍需第二种真实路径。'})

    names = subprocess.check_output(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'], cwd=ROOT).decode('utf-8').split('\0')
    eligible = sorted(set(filter(None, names)))
    sensitive_paths = [name for name in eligible if Path(name).name == '.env' or Path(name).suffix.lower() in {'.pem', '.key'}]
    import re
    secret_hits = []
    patterns = (r'sk-[A-Za-z0-9_-]{24,}', r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')
    for name in eligible:
        path = ROOT / name
        if path.is_file():
            text = path.read_bytes().decode('utf-8', errors='replace')
            if any(re.search(pattern, text) for pattern in patterns) or (key and len(key) >= 12 and key in text):
                secret_hits.append(name)  # Never echo matching values.
    statuses = subprocess.run(['git', 'status', '--short'], cwd=ROOT, capture_output=True, text=True).stdout
    remotes = subprocess.run(['git', 'remote', '-v'], cwd=ROOT, capture_output=True, text=True).stdout
    head = subprocess.run(['git', 'rev-parse', '--verify', 'HEAD'], cwd=ROOT, capture_output=True, text=True)
    write_json(directory / 'git-and-secrets.json', {'status': statuses, 'remotes': remotes, 'head': head.stdout.strip() if head.returncode == 0 else None,
               'eligible_files': len(eligible), 'sensitive_paths': sensitive_paths, 'possible_secret_files': secret_hits,
               'scan_scope': 'Git 跟踪及未忽略文件；常见密钥模式与本次已知密钥精确匹配，不是全面泄密证明。'})

    if args.clean_env:
        clean = ROOT / 'work' / directory.name
        project = clean / 'repository'
        project.mkdir(parents=True)
        for name in eligible:
            source = ROOT / name
            if source.is_file() and name not in sensitive_paths:
                target = project / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        clean_python = clean / '.venv/Scripts/python.exe'
        started_at = now()
        venv.EnvBuilder(with_pip=True).create(clean / '.venv')
        write_json(directory / 'clean-environment.json', {'project_copy': str(project), 'venv': str(clean / '.venv'),
                   'created_at': started_at, 'source_files_copied': len(eligible), 'inherits_system_packages': False,
                   'pythonpath_removed': True, 'secret_config_copied': False})
        install = command('clean-install', ['-m', 'pip', 'install', '-e', '.[test]'], cwd=project, interpreter=clean_python)
        if install.returncode == 0:
            command('clean-pip-check', ['-m', 'pip', 'check'], cwd=project, interpreter=clean_python)
            command('clean-offline-run', ['-m', 'kb_agent', 'run', '--mode', 'mock', '--input', 'examples/inputs/normal.json',
                    '--output-dir', 'work/acceptance-normal'], cwd=project, interpreter=clean_python)
            command('clean-offline-tests', ['-m', 'pytest', '-q', '-m', 'not live', '--tb=short'], cwd=project, interpreter=clean_python)
            command('clean-build-wheel', ['-m', 'pip', 'wheel', '--no-deps', '.', '-w', str(clean / 'wheels')], cwd=project, interpreter=clean_python)
            command('clean-package-assets', ['-c', "from importlib.resources import files; import json; print(json.dumps({n: files('kb_agent').joinpath('web_static', n).is_file() for n in ['index.html','style.css','app.js']}))"], cwd=clean, interpreter=clean_python)

    write_json(directory / 'summary.json', {'phase': args.phase, 'ended_at': now(), 'commands': records,
               'probes': [{'id': p['id'], 'verdict': p['verdict']} for p in probes], 'mutations': mutations,
               'live': live_config, 'semantic_scope_gap': 'A05 remains a documented production limitation; inspect independent audit and semantic review.',
               'source_sha256': {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in (ROOT / 'src/kb_agent').glob('*.py')}})
    print('Evidence: ' + directory.relative_to(ROOT).as_posix(), flush=True)
    # An unresolved negative audit must never become a successful CI result.
    if any(p['verdict'] == 'FAIL' for p in probes) or any(r['exit_code'] != 0 and r['name'] != 'live-evaluation' for r in records):
        return 1
    return 2 if live_config['verdict'] == 'BLOCKED' or any(r['exit_code'] != 0 for r in records) else 0


if __name__ == '__main__':
    raise SystemExit(main())
