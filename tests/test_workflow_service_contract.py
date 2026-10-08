"""Workflow output contracts without importing the application module."""
import time
import json
import re

import pytest

from creatoros.services.workflow_service import FINAL_ARTIFACTS, WorkflowService


def output_folder(tmp_path, prompt):
    project = re.search(r'工作流项目目录：outputs/(workflow-[a-f0-9]{12})', prompt).group(1)
    return tmp_path / project


def wait_job(service, job_id):
    end = time.monotonic() + 5
    while time.monotonic() < end:
        job = service.get(job_id)
        if job['status'] not in {'running', 'queued'} and job_id not in service.active:
            return job
        time.sleep(.01)
    pytest.fail('workflow did not settle')


def test_adaptation_writes_selected_platform_final_contract(tmp_path):
    calls = []
    job_ref = {}

    def runner(prompt):
        calls.append(prompt)
        if '阶段：平台适配' in prompt:
            folder = output_folder(tmp_path, prompt)
            folder.mkdir(parents=True, exist_ok=True)
            (folder / FINAL_ARTIFACTS['xiaohongshu']).write_text('小红书可编辑终稿', encoding='utf-8')
        return 'stage output'

    service = WorkflowService(tmp_path, lambda: True, runner)
    job_ref['id'] = service.start('topic', ['xiaohongshu'])['id']
    done = wait_job(service, job_ref['id'])
    assert done['status'] == 'completed'
    final = tmp_path / f"workflow-{job_ref['id']}" / FINAL_ARTIFACTS['xiaohongshu']
    assert final.is_file() and final.read_text(encoding='utf-8')
    adaptation_prompt = next(prompt for prompt in calls if '阶段：平台适配' in prompt)
    assert 'outputs/workflow-' in adaptation_prompt
    assert '09-xhs-final.md' in adaptation_prompt
    assert '不得默认输出三平台版本' in adaptation_prompt
    manifest = json.loads((tmp_path / f"workflow-{job_ref['id']}" / '.creatoros.json').read_text(encoding='utf-8'))
    assert '09-xhs-final.md' in manifest['deliverables']
    service.executor.shutdown()


def test_missing_final_marks_adaptation_and_retry_recovers(tmp_path):
    adaptation_attempts = 0
    calls = []
    job_ref = {}

    def runner(prompt):
        nonlocal adaptation_attempts
        calls.append(prompt)
        if '阶段：平台适配' in prompt:
            adaptation_attempts += 1
            if adaptation_attempts > 1:
                folder = output_folder(tmp_path, prompt)
                folder.mkdir(parents=True, exist_ok=True)
                (folder / FINAL_ARTIFACTS['xiaohongshu']).write_text('恢复后的终稿', encoding='utf-8')
        return 'stage output'

    service = WorkflowService(tmp_path, lambda: True, runner)
    job_ref['id'] = service.start('topic', ['xiaohongshu'])['id']
    failed = wait_job(service, job_ref['id'])
    assert failed['status'] == 'failed'
    assert failed['stages']['archive']['status'] == 'failed'
    assert failed['stages']['adaptation']['status'] == 'failed'
    assert '平台终稿未生成' in failed['stages']['archive']['reason']

    service.retry(job_ref['id'])
    done = wait_job(service, job_ref['id'])
    assert done['status'] == 'completed'
    assert adaptation_attempts == 2
    assert sum('阶段：质量检查' in prompt for prompt in calls) == 2
    assert sum('阶段：发现与核验' in prompt for prompt in calls) == 1
    final = tmp_path / f"workflow-{job_ref['id']}" / FINAL_ARTIFACTS['xiaohongshu']
    assert final.read_text(encoding='utf-8') == '恢复后的终稿'
    service.executor.shutdown()


@pytest.mark.parametrize('invalid_content', [None, '', ' \n\t'])
def test_completed_legacy_job_without_final_restarts_at_adaptation(tmp_path, invalid_content):
    calls = []

    def runner(prompt):
        calls.append(prompt)
        if '阶段：平台适配' in prompt:
            (output_folder(tmp_path, prompt) / FINAL_ARTIFACTS['xiaohongshu']).write_text('完整终稿', encoding='utf-8')
        return f'stage output {len(calls)}'

    service = WorkflowService(tmp_path, lambda: True, runner)
    job_id = service.start('topic', ['xiaohongshu'])['id']
    completed = wait_job(service, job_id)
    assert completed['status'] == 'completed'
    first = tmp_path / completed['stages']['discovery']['artifact']
    first_bytes = first.read_bytes()
    final = tmp_path / f'workflow-{job_id}' / FINAL_ARTIFACTS['xiaohongshu']
    if invalid_content is None:
        final.unlink()
    else:
        final.write_text(invalid_content, encoding='utf-8')

    service.retry(job_id)
    recovered = wait_job(service, job_id)
    assert recovered['status'] == 'completed'
    assert recovered['attempt'] == 2
    assert len(calls) == 7
    assert '阶段：平台适配' in calls[5]
    assert '阶段：质量检查' in calls[6]
    assert first.read_bytes() == first_bytes
    assert final.read_text(encoding='utf-8') == '完整终稿'
    with pytest.raises(ValueError):
        service.retry(job_id)
    service.executor.shutdown()
