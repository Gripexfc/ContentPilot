"""Compact-v2 workflow tests; no real model, network, or publisher is used."""
import time

from creatoros.services.workflow_service import FINAL_ARTIFACTS, WorkflowService


def wait_job(service, job_id):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        job = service.get(job_id)
        if job['status'] not in {'queued', 'running'} and job_id not in service.active:
            return job
        time.sleep(0.01)
    raise AssertionError('compact workflow did not settle')


def test_compact_uses_one_research_and_one_compose_call(tmp_path):
    calls = []

    def research(prompt, session_id):
        calls.append((session_id, prompt))
        return '事实：官方公告；来源：https://example.com；待核验：热度。'

    def compose(prompt, session_id):
        calls.append((session_id, prompt))
        return {'platform': 'xiaohongshu', 'content': '小红书终稿\n事实边界已保留。'}

    service = WorkflowService(tmp_path, lambda: True, research, compose_runner=compose)
    try:
        job_id = service.start('主题', ['xiaohongshu'])['id']
        job = wait_job(service, job_id)
        assert job['status'] == 'completed'
        assert job['execution_mode'] == 'compact-v2'
        assert [item[0] for item in calls] == [
            f'workflow-{job_id}-compact-research-attempt-1',
            f'workflow-{job_id}-compact-compose-xiaohongshu-attempt-1',
        ]
        final = tmp_path / f'workflow-{job_id}' / FINAL_ARTIFACTS['xiaohongshu']
        assert final.read_text(encoding='utf-8').startswith('小红书终稿')
        assert job['stages']['quality']['status'] == 'completed'
        assert '需人工复核' in (tmp_path / job['stages']['quality']['artifact']).read_text(encoding='utf-8')
    finally:
        service.executor.shutdown()


def test_compact_retry_preserves_research_and_only_retries_failed_platform(tmp_path):
    research_calls = 0
    compose_calls = []

    def research(_prompt, _session_id):
        nonlocal research_calls
        research_calls += 1
        return '共享研究\n来源：https://example.com'

    def compose(_prompt, session_id):
        compose_calls.append(session_id)
        if 'douyin' in session_id and 'attempt-1' in session_id:
            raise RuntimeError('模型请求超时')
        platform = 'xiaohongshu' if 'xiaohongshu' in session_id else 'douyin'
        return {'platform': platform, 'content': f'{platform} 终稿'}

    service = WorkflowService(tmp_path, lambda: True, research, compose_runner=compose)
    try:
        job_id = service.start('主题', ['xiaohongshu', 'douyin'])['id']
        failed = wait_job(service, job_id)
        assert failed['status'] == 'failed'
        assert research_calls == 1
        assert (tmp_path / f'workflow-{job_id}' / FINAL_ARTIFACTS['xiaohongshu']).is_file()

        service.retry(job_id)
        done = wait_job(service, job_id)
        assert done['status'] == 'completed'
        assert research_calls == 1
        assert len([x for x in compose_calls if 'xiaohongshu' in x]) == 1
        assert len([x for x in compose_calls if 'douyin' in x]) == 2
    finally:
        service.executor.shutdown()


def test_explicit_retry_migrates_failed_legacy_job_when_compose_is_available(tmp_path):
    legacy_calls = []

    def legacy(prompt):
        legacy_calls.append(prompt)
        if '阶段：主稿' in prompt:
            raise RuntimeError('模型请求超时')
        return '旧研究产物'

    def compose(_prompt, _session_id):
        return {'platform': 'wechat-oa', 'content': '恢复后的公众号终稿'}

    service = WorkflowService(tmp_path, lambda: True, legacy)
    try:
        job_id = service.start('主题', ['wechat-oa'])['id']
        failed = wait_job(service, job_id)
        assert failed['status'] == 'failed'
        discovery = tmp_path / failed['stages']['discovery']['artifact']
        service.compose_runner = compose
        service.retry(job_id)
        done = wait_job(service, job_id)
        assert done['status'] == 'completed'
        assert done['execution_mode'] == 'compact-v2'
        assert done['migrated_from'] == 'legacy-v1'
        assert discovery.read_text(encoding='utf-8') == '旧研究产物'
    finally:
        service.executor.shutdown()


def test_compact_streaming_preview_is_checkpointed_and_completed(tmp_path):
    def research(_prompt, _session_id):
        return '共享研究\n来源：https://example.com'

    def compose(_prompt, _session_id):
        return {'platform': 'xiaohongshu', 'content': '完整终稿'}

    def stream_compose(_prompt, _session_id, on_delta):
        on_delta('实时')
        on_delta('预览')
        return {'platform': 'xiaohongshu', 'content': '完整终稿'}

    service = WorkflowService(
        tmp_path, lambda: True, research,
        compose_runner=compose, compose_stream_runner=stream_compose,
    )
    try:
        job_id = service.start('主题', ['xiaohongshu'])['id']
        job = wait_job(service, job_id)
        assert job['status'] == 'completed'
        preview = job['streaming_outputs']['xiaohongshu']
        assert preview['text'] == '完整终稿'
        assert preview['complete'] is True
        assert preview['chars'] == len('完整终稿')
    finally:
        service.executor.shutdown()
