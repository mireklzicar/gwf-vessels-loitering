from unittest.mock import Mock

import pytest
import requests

from gfw_anomaly.gfw import GFWClient


def response(code, body=None):
    return Mock(status_code=code, ok=code < 400, json=Mock(return_value=body or {}))


def test_event_page_retries_do_not_duplicate_or_skip(monkeypatch):
    post = Mock(side_effect=[requests.ReadTimeout(), response(503),
        response(200, {'entries': [{'id': 'a'}], 'nextOffset': 1}),
        requests.ConnectionError(), response(200, {'entries': [{'id': 'b'}]})])
    monkeypatch.setattr('gfw_anomaly.gfw.requests.post', post)
    monkeypatch.setattr('gfw_anomaly.gfw.time.sleep', lambda _: None)
    rows = GFWClient('test').event_pages({}, '2022-01-01', '2022-02-01', 'test')
    assert rows == [{'id': 'a'}, {'id': 'b'}]
    assert [c.kwargs['params']['offset'] for c in post.call_args_list] == [0, 0, 0, 1, 1]


def test_retry_limit_and_non_transient_errors(monkeypatch):
    post = Mock(side_effect=requests.ReadTimeout())
    monkeypatch.setattr('gfw_anomaly.gfw.requests.post', post)
    monkeypatch.setattr('gfw_anomaly.gfw.time.sleep', lambda _: None)
    with pytest.raises(requests.ReadTimeout):
        GFWClient('test').event_pages({}, 'a', 'b', 'test')
    assert post.call_count == 5
    post = Mock(return_value=response(401))
    monkeypatch.setattr('gfw_anomaly.gfw.requests.post', post)
    with pytest.raises(RuntimeError, match='401'):
        GFWClient('test').event_pages({}, 'a', 'b', 'test')
    assert post.call_count == 1
