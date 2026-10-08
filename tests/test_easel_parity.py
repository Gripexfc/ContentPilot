"""Parity boundary tests: no real models, logins or publication are invoked."""
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from creatoros.services.workflow_service import FINAL_ARTIFACTS, WorkflowService
from creatoros.api.easel_bridge import _module as upstream
from creatoros.api.app import app


def wait_job(service, job_id):
    end = time.monotonic() + 3
    while time.monotonic() < end:
        job = service.get(job_id)
        if job['status'] not in {'running', 'queued'} and job_id not in service.active:
            return job
        time.sleep(.01)
    pytest.fail('workflow did not settle')


def test_workflow_blocks_without_output(tmp_path):
    called = []
    service = WorkflowService(tmp_path, lambda: False, lambda prompt: called.append(prompt))
    job = wait_job(service, service.start('topic', ['wechat-oa'])['id'])
    assert job['status'] == 'blocked' and not called
    assert job['stages']['discovery']['status'] == 'blocked'
    assert job['stages']['archive']['status'] == 'pending'
    assert not list(tmp_path.glob('workflow-*'))
    service.executor.shutdown()


def test_workflow_real_sequence_and_retry_preserves_prior_artifacts(tmp_path):
    calls = []
    job_ref = {}

    def runner(prompt):
        calls.append(prompt)
        if len(calls) == 3:
            raise RuntimeError('injected model failure')
        if '阶段：平台适配' in prompt:
            folder = tmp_path / f"workflow-{job_ref['id']}"
            folder.mkdir(parents=True, exist_ok=True)
            for filename in FINAL_ARTIFACTS.values():
                (folder / filename).write_text('adapted final', encoding='utf-8')
        return f'Injected test runner output {len(calls)}'
    service = WorkflowService(tmp_path, lambda: True, runner)
    job_id = service.start('topic', ['xiaohongshu', 'douyin', 'wechat-oa'], profile='画像测试', skill='social-content')['id']
    job_ref['id'] = job_id
    failed = wait_job(service, job_id)
    assert failed['status'] == 'failed'
    first = tmp_path / failed['stages']['discovery']['artifact']
    before = first.read_bytes()
    service.retry(job_id)
    done = wait_job(service, job_id)
    assert done['status'] == 'completed'
    assert done['content_status'] == 'draft' and done['published'] is False
    assert done['skill'] == 'social-content'
    assert done['attempt'] == 2 and len(done['attempts']) == 1
    assert len(calls) == 6 and first.read_bytes() == before
    assert 'workspace/AGENTS.md' in calls[0] and '/skill-trending-topics' in calls[0]
    assert done['stages']['discovery']['skills'] == ['skill-trending-topics', 'skill-news-intelligence']
    assert done['stages']['topic']['skills'] == ['skill-trend-rider', 'skill-topic-evaluator', 'skill-article-outline']
    assert done['stages']['master']['skills'] == ['social-content', 'xhs-note-creator', 'video-script']
    assert done['stages']['quality']['skills'] == ['skill-quality-gate', 'skill-persona-check']
    assert done['stages']['archive']['skills'] == ['asset-manager', 'skill-publish-checklist']
    assert all(x['status'] == 'completed' for x in done['stages'].values())
    assert all((tmp_path / x['artifact']).is_file() for x in done['stages'].values())
    manifest_path = tmp_path / f"workflow-{job_id}" / ".creatoros.json"
    manifest = json.loads(manifest_path.read_text())
    assert "06-archive.md" in manifest["deliverables"]
    archive = json.loads((tmp_path / done['stages']['archive']['artifact']).read_text())
    assert archive["stages"]["archive"]["status"] == "completed"
    assert archive["stages"]["archive"]["artifact"] == done['stages']['archive']['artifact']
    with pytest.raises(ValueError): service.retry(job_id)
    service.executor.shutdown()


def test_workflow_explicit_blocked_runner_result_does_not_complete(tmp_path):
    calls = []

    def runner(prompt):
        calls.append(prompt)
        return "BLOCKED：原始来源不可访问，不能继续正文生成。"

    service = WorkflowService(tmp_path, lambda: True, runner)
    job_id = service.start('topic', ['wechat-oa'])['id']
    blocked = wait_job(service, job_id)
    assert blocked['status'] == 'blocked'
    assert blocked['stages']['discovery']['status'] == 'blocked'
    assert blocked['stages']['discovery']['reason'].startswith('BLOCKED')
    assert len(calls) == 1
    folders = list(tmp_path.glob('workflow-*'))
    assert folders and not list(folders[0].glob('*.md'))
    service.executor.shutdown()


def test_workflow_blocked_marker_after_preamble_does_not_complete(tmp_path):
    def runner(_prompt):
        return "发现与核验阶段已完成并落盘。\n结论：主题事实核验 BLOCKED。\n缺少当前一手来源。"

    service = WorkflowService(tmp_path, lambda: True, runner)
    job_id = service.start('topic', ['wechat-oa'])['id']
    blocked = wait_job(service, job_id)
    assert blocked['status'] == 'blocked'
    assert blocked['stages']['discovery']['status'] == 'blocked'
    assert '主题事实核验 BLOCKED' in blocked['stages']['discovery']['reason']
    assert len(list((tmp_path / f'workflow-{job_id}').glob('*.md'))) == 0
    service.executor.shutdown()


def test_workflow_markdown_blocked_status_does_not_complete(tmp_path):
    def runner(_prompt):
        return "**整体状态为 BLOCKED**\n当前来源不可核验。"

    service = WorkflowService(tmp_path, lambda: True, runner)
    job_id = service.start('topic', ['wechat-oa'])['id']
    blocked = wait_job(service, job_id)
    assert blocked['status'] == 'blocked'
    assert blocked['stages']['discovery']['status'] == 'blocked'
    assert '整体状态为 BLOCKED' in blocked['stages']['discovery']['reason']
    service.executor.shutdown()


def test_workflow_billing_failure_keeps_actionable_reason(tmp_path):
    def runner(_prompt):
        raise RuntimeError('openai returned a billing error: 402 Insufficient Balance')

    service = WorkflowService(tmp_path, lambda: True, runner)
    failed = wait_job(service, service.start('topic', ['wechat-oa'])['id'])
    assert failed['status'] == 'failed'
    assert failed['stages']['discovery']['reason'] == (
        '模型账户余额或额度不足；请到服务商控制台充值，或在连接与设置更换可用 API Key 后重试。'
    )
    service.executor.shutdown()


def test_workflow_arrearage_failure_keeps_actionable_reason(tmp_path):
    def runner(_prompt):
        raise RuntimeError('HTTP 400 code=Arrearage message=account overdue-payment')

    service = WorkflowService(tmp_path, lambda: True, runner)
    failed = wait_job(service, service.start('topic', ['wechat-oa'])['id'])
    assert failed['status'] == 'failed'
    assert failed['stages']['discovery']['reason'] == (
        '模型账户欠费或账户状态异常；请到服务商控制台处理欠费并开启可用额度，或在连接与设置更换可用 API Key 后重试。'
    )
    service.executor.shutdown()


def test_workflow_model_permission_failure_keeps_actionable_reason(tmp_path):
    def runner(_prompt):
        raise RuntimeError('HTTP 403 Forbidden: model not found or not enabled')

    service = WorkflowService(tmp_path, lambda: True, runner)
    failed = wait_job(service, service.start('topic', ['wechat-oa'])['id'])
    assert failed['status'] == 'failed'
    assert failed['stages']['discovery']['reason'] == (
        '当前模型未开通或没有调用权限；请在服务商控制台开启该模型，或在连接与设置更换可用模型。'
    )
    service.executor.shutdown()


def test_workflow_does_not_archive_when_a_prior_artifact_is_missing(tmp_path):
    service = WorkflowService(tmp_path, lambda: True, lambda _prompt: 'stage output')
    original_save = service._save
    sabotaged = {'done': False}

    def save_and_remove_prior_artifact(job):
        original_save(job)
        if job.get('current') == 'archive' and job['stages']['archive']['status'] == 'running' and not sabotaged['done']:
            artifact = job['stages']['discovery'].get('artifact')
            if artifact:
                (tmp_path / artifact).unlink()
                sabotaged['done'] = True

    service._save = save_and_remove_prior_artifact
    failed = wait_job(service, service.start('topic', ['wechat-oa'])['id'])
    assert failed['status'] == 'failed'
    assert failed['stages']['archive']['status'] == 'failed'
    assert '阶段产物缺失' in failed['stages']['archive']['reason']
    assert not (tmp_path / f"workflow-{failed['id']}" / '.creatoros.json').exists()
    service.executor.shutdown()


def test_workflow_uses_isolated_stage_sessions_and_fresh_retry(tmp_path):
    calls = []
    job_ref = {}

    def session_runner(prompt, session_id):
        calls.append((prompt, session_id))
        if len(calls) == 3:
            raise RuntimeError('injected model failure')
        if '阶段：平台适配' in prompt:
            folder = tmp_path / f"workflow-{job_ref['id']}"
            folder.mkdir(parents=True, exist_ok=True)
            (folder / FINAL_ARTIFACTS['wechat-oa']).write_text('adapted final', encoding='utf-8')
        return f'session output {len(calls)}'

    service = WorkflowService(tmp_path, lambda: True, lambda _: 'unused', session_runner=session_runner)
    job_id = service.start('topic', ['wechat-oa'])['id']
    job_ref['id'] = job_id
    failed = wait_job(service, job_id)
    assert failed['status'] == 'failed'
    assert [session_id for _, session_id in calls] == [
        f'workflow-{job_id}-discovery-attempt-1',
        f'workflow-{job_id}-topic-attempt-1',
        f'workflow-{job_id}-master-attempt-1',
    ]
    # Stage artifacts, rather than the OpenClaw transcript, carry the prior
    # work forward into the next stage.
    assert 'session output 1' in calls[1][0]
    assert 'session output 2' in calls[2][0]

    service.retry(job_id)
    done = wait_job(service, job_id)
    assert done['status'] == 'completed'
    assert [session_id for _, session_id in calls] == [
        f'workflow-{job_id}-discovery-attempt-1',
        f'workflow-{job_id}-topic-attempt-1',
        f'workflow-{job_id}-master-attempt-1',
        f'workflow-{job_id}-master-attempt-2',
        f'workflow-{job_id}-adaptation-attempt-2',
        f'workflow-{job_id}-quality-attempt-2',
    ]
    assert len({session_id for _, session_id in calls}) == len(calls)
    assert all('目标平台（仅限这些，不得新增）：公众号' in prompt for prompt, _ in calls)
    assert all('不得默认输出三平台版本' in prompt for prompt, _ in calls)
    service.executor.shutdown()


def test_workflow_restart_marks_interrupted_and_recovers(tmp_path):
    folder = tmp_path / '_workflow'
    folder.mkdir()
    job = {'id': '123456789abc', 'topic': 'topic', 'platforms': ['wechat-oa'], 'profile': '',
           'status': 'running', 'created': 1, 'current': 'discovery', 'attempt': 1,
           'stages': {k: {'label': k, 'status': 'running' if k == 'discovery' else 'pending', 'artifact': None} for k in ['discovery','topic','master','adaptation','quality','archive']}}
    (folder / '123456789abc.json').write_text(json.dumps(job))
    service = WorkflowService(tmp_path, lambda: False, lambda _: '')
    assert service.get(job['id'])['status'] == 'interrupted'
    assert wait_job(service, service.retry(job['id'])['id'])['status'] == 'blocked'
    with pytest.raises(KeyError): service.get('../secret')
    with pytest.raises(ValueError): service.start('topic', ['weibo'])
    service.executor.shutdown()


@pytest.fixture
def parity_client():
    with TestClient(app, base_url='http://127.0.0.1:8000', headers={'Origin': 'http://127.0.0.1:8000'}) as c:
        yield c


def test_three_targets_legacy_and_gate(parity_client, monkeypatch):
    c = parity_client
    monkeypatch.setattr(upstream, 'check_gateway', lambda: False)
    assert c.get('/api/v1/status').status_code == 200
    assert c.get('/api/v1/connectors').status_code == 200
    assert c.get('/legacy.html').status_code == 200
    assert {x['platform'] for x in c.get('/api/accounts').json()} == {'xiaohongshu', 'douyin', 'wechat-oa'}
    assert c.post('/api/publish/weibo', json={'title': 'x', 'body': 'x'}).status_code == 404
    assert c.post('/api/publish/xiaohongshu', json={'title': 'x'*21, 'body': 'x'}).status_code == 422
    assert c.post('/api/schedule', json={'title': 'x', 'date': '2026-10-01', 'platform': '微博'}).status_code == 422
    assert c.post('/api/chat/stream', json={'message': 'test'}).status_code == 503
    assert c.post('/api/skill', json={'skill': 'copywriting', 'input': 'test'}).status_code == 503


def test_outputs_tree_media_and_traversal(parity_client, monkeypatch, tmp_path):
    monkeypatch.setattr(upstream, 'OUTPUTS_DIR', tmp_path)
    folder = tmp_path / 'test-project'
    folder.mkdir()
    (folder/'draft.md').write_text('fixture draft')
    (folder/'clip.mp4').write_bytes(b'fixture-video')
    (folder/'outside').symlink_to('/etc')
    c = parity_client
    nodes = c.get('/api/outputs').json()
    assert nodes[0]['name'] == 'test-project'
    assert {x['name'] for x in nodes[0]['children']} == {'draft.md', 'clip.mp4'}
    assert c.get('/api/output/test-project/draft.md').json()['content'] == 'fixture draft'
    assert c.get('/api/output/%2e%2e%2fsecret').status_code == 403
    assert c.get('/api/media/test-project/clip.mp4').content == b'fixture-video'
