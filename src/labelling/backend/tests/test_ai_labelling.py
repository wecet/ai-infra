import json

import httpx
import pytest
from fastapi import HTTPException
from PIL import Image

import ai_labelling as ai


@pytest.fixture
def config(tmp_path, monkeypatch):
    env = tmp_path / 'gpt.env'
    env.write_text('OPENAI_API_KEY="test-secret"\nOPENAI_MODEL=test-model\nOPENAI_PROJECT=project\n')
    monkeypatch.setenv('GPT_ENV_FILE', str(env))
    return env


def mock_response(monkeypatch, status, body):
    requests = []
    real_client = httpx.Client
    def handle(request):
        requests.append(request)
        return httpx.Response(status, json=body)
    monkeypatch.setattr(ai.httpx, 'Client', lambda **kwargs: real_client(
        transport=httpx.MockTransport(handle), **kwargs))
    return requests


def completed(boxes):
    return {'status': 'completed', 'output': [{'type': 'message', 'content': [
        {'type': 'output_text', 'text': json.dumps({'boxes': boxes})}]}]}


def test_validate_uses_image_model_and_does_not_store(config, monkeypatch):
    requests = mock_response(monkeypatch, 200, completed([]))
    ai.validate_credentials()
    req = requests[0]
    body = json.loads(req.content)
    assert req.headers['authorization'] == 'Bearer test-secret'
    assert req.headers['OpenAI-Project'] == 'project'
    assert body['model'] == 'test-model' and body['store'] is False
    assert body['input'][0]['content'][1]['image_url'].startswith('data:image/png;base64,')
    assert body['text']['format']['strict'] is True


@pytest.mark.parametrize('status,expected', [(401,401), (403,401), (404,401), (429,429), (400,422), (500,502)])
def test_provider_errors_never_leak_credentials(config, monkeypatch, status, expected):
    mock_response(monkeypatch, status, {'error': 'test-secret'})
    with pytest.raises(HTTPException) as caught:
        ai.validate_credentials()
    assert caught.value.status_code == expected
    assert 'test-secret' not in caught.value.detail
    if expected == 401:
        assert caught.value.detail == 'Invalid Credentials Provided'


@pytest.mark.parametrize('box', [
    {'category_id': 99, 'x': 0, 'y': 0, 'width': .5, 'height': .5},
    {'category_id': 1, 'x': .9, 'y': 0, 'width': .5, 'height': .5},
    {'category_id': 1, 'x': 0, 'y': 0, 'width': 0, 'height': .5},
    {'category_id': 1, 'x': float('nan'), 'y': 0, 'width': .5, 'height': .5},
    {'category_id': 1, 'x': 1, 'y': 0, 'width': 0.0000001, 'height': .5},
])
def test_reject_invalid_model_boxes(config, monkeypatch, tmp_path, box):
    path = tmp_path / 'image.png'
    Image.new('RGB', (100, 80)).save(path)
    mock_response(monkeypatch, 200, completed([box]))
    with pytest.raises(HTTPException) as caught:
        ai.detect(path, [{'id':1, 'name':'A'}], 100, 80)
    assert caught.value.status_code == 502


def test_normalized_coordinates_scale_to_original(config, monkeypatch, tmp_path):
    path = tmp_path / 'image.png'
    Image.new('RGB', (3000, 2000)).save(path)
    mock_response(monkeypatch, 200, completed([
        {'category_id':1, 'x': .1, 'y': .2, 'width': .3, 'height': .4}]))
    assert ai.detect(path, [{'id':1, 'name':'A'}], 3000, 2000) == [
        {'category_id':1, 'x':300, 'y':400, 'width':900, 'height':800}]


def test_project_instructions_are_sent_as_annotation_criteria(config, monkeypatch, tmp_path):
    path = tmp_path / 'image.png'
    Image.new('RGB', (100, 80)).save(path)
    requests = mock_response(monkeypatch, 200, completed([]))
    ai.detect(path, [{'id': 1, 'name': 'A'}], 100, 80, 'Label partially obscured objects')
    prompt = json.loads(requests[0].content)['input'][0]['content'][0]['text']
    assert 'Project-specific labelling guidance' in prompt
    assert 'Label partially obscured objects' in prompt


def test_refused_or_incomplete_output(config, monkeypatch):
    mock_response(monkeypatch, 200, {'status':'incomplete','output':[]})
    with pytest.raises(HTTPException) as caught:
        ai.validate_credentials()
    assert caught.value.status_code == 502
