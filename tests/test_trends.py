from threading import Barrier

import pytest

from creatoros.services.trend_service import REFRESH_SECONDS, TREND_SOURCES, TrendService, parse_items


@pytest.mark.parametrize("wrap", [lambda rows: {"data": rows}, lambda rows: {"data": {"list": rows}}, lambda rows: {"data": {"data": rows}}])
def test_parse_primary_and_fallback_shapes(wrap):
    rows = [
        {"title": "真实热点", "hot_value_desc": "123万", "link": "https://www.douyin.com/hot/123", "description": "来源摘要"},
        {"word": "第二条", "score": 1234, "mobil_url": "https://example.com/story"},
        {"name": "第三条", "num": 42, "url": "javascript:alert(1)"},
        {"title": "真实热点", "url": "https://example.com/duplicate"},
        {"title": ""}, None, "invalid",
    ]
    items = parse_items(wrap(rows), "douyin")
    assert len(items) == 3
    assert items[0]["hot"] == "123万"
    assert items[0]["summary"] == "来源摘要"
    assert items[1]["hot"] == "1234"
    assert items[1]["url"] == "https://example.com/story"
    assert items[2]["url"].startswith("https://www.douyin.com/search/")
    assert "平台搜索页" in items[2]["summary"]
    assert items[0]["id"] == parse_items({"data": rows[:1]}, "douyin")[0]["id"]
    assert [item["rank"] for item in items] == [1, 2, 3]


def test_parse_limits_and_malformed_responses():
    assert parse_items({"data": {"error": "failed"}}, "weibo") == []
    assert parse_items(None, "weibo") == []
    rows = [{"name": "话题 " + str(index), "hot_value": index} for index in range(40)]
    items = parse_items({"data": rows}, "weibo")
    assert len(items) == 30
    assert items[0]["hot"] == "0"
    assert items[0]["url"].startswith("https://s.weibo.com/weibo?q=")


def test_ttl_force_refresh_and_limit_do_not_truncate_cache():
    now = [0.0]
    calls = []

    def fetch(url):
        calls.append(url)
        return {"data": [{"title": "热榜 " + str(index)} for index in range(20)]}

    service = TrendService(fetcher=fetch, clock=lambda: now[0])
    first = service.get_trends(["douyin"], limit=2)["trends"][0]
    assert first["status"] == "fresh"
    assert len(first["items"]) == 2
    cached = service.get_trends(["douyin"], limit=12)["trends"][0]
    assert len(cached["items"]) == 12
    assert cached["status"] == "cached"
    assert cached["fetched_at"] == first["fetched_at"]
    assert len(calls) == 1
    assert service.get_trends(["douyin"], refresh=True)["trends"][0]["status"] == "fresh"
    assert len(calls) == 2
    now[0] = REFRESH_SECONDS
    assert service.get_trends(["douyin"])["trends"][0]["status"] == "fresh"
    assert len(calls) == 3


def test_fallback_success_records_actual_provider():
    calls = []

    def fetch(url):
        calls.append(url)
        if "60s.viki.moe" in url:
            raise TimeoutError()
        return {"data": {"list": [{"word": "备用热榜", "hot_value": 100, "url": "https://example.com/hot"}]}}

    feed = TrendService(fetcher=fetch).get_trends(["douyin"])["trends"][0]
    assert len(calls) == 2
    assert feed["status"] == "fresh"
    assert feed["source_url"] == TREND_SOURCES["douyin"][1][1][1]
    assert "备用" in feed["source_name"]
    assert feed["items"][0]["title"] == "备用热榜"


def test_failed_refresh_keeps_original_timestamp_and_marks_stale():
    failed = [False]
    now = [0.0]

    def fetch(_url):
        if failed[0]:
            raise OSError("network unavailable")
        return {"data": [{"title": "上次成功的数据"}]}

    service = TrendService(fetcher=fetch, clock=lambda: now[0])
    first = service.get_trends(["weibo"])["trends"][0]
    failed[0] = True
    now[0] = REFRESH_SECONDS + 1
    stale = service.get_trends(["weibo"], refresh=True)["trends"][0]
    assert stale["status"] == "stale"
    assert stale["items"] == first["items"]
    assert stale["fetched_at"] == first["fetched_at"]
    assert stale["source_url"] == first["source_url"]
    assert "上次成功" in stale["error"]
    assert service.get_trends(["weibo"])["trends"][0]["status"] == "stale"


def test_parallel_sources_and_partial_failure():
    barrier = Barrier(2)

    def fetch(url):
        # If requests accidentally become serial this test times out and fails.
        barrier.wait(timeout=3)
        if url.endswith("zhihu"):
            raise TimeoutError()
        return {"data": [{"title": "可用榜单"}]}

    feeds = TrendService(fetcher=fetch).get_trends(["douyin", "zhihu"])["trends"]
    assert feeds[0]["status"] == "fresh"
    assert feeds[1]["status"] == "unavailable"
    assert feeds[1]["items"] == []
    assert feeds[1]["fetched_at"] is None
    assert feeds[1]["source_url"] is None
    assert feeds[1]["error"]


def test_trends_endpoint_schema_and_query_validation(client):
    calls = []

    def fetch(url):
        calls.append(url)
        return {"data": [{"title": "接口热榜", "hot_value": 500}]}

    client.app.state.trend_service = TrendService(fetcher=fetch)
    response = client.get("/api/v1/trends?platforms=douyin,weibo,douyin&limit=1")
    assert response.status_code == 200
    body = response.json()
    assert body["refresh_after_seconds"] == 300
    assert [feed["platform"] for feed in body["trends"]] == ["douyin", "weibo"]
    item = body["trends"][0]["items"][0]
    assert set(item) == {"id", "title", "hot", "url", "rank", "summary"}
    assert len(calls) == 2
    client.get("/api/v1/trends?platforms=douyin,weibo&limit=1")
    assert len(calls) == 2
    assert client.get("/api/v1/trends?platforms=douyin&refresh=true").status_code == 200
    assert len(calls) == 3
    for query in ("platforms=https://example.com", "platforms=", "platforms=douyin,unknown", "limit=0", "limit=31", "refresh=wrong"):
        assert client.get("/api/v1/trends?" + query).status_code == 422
    assert len(calls) == 3


def test_trends_endpoint_unavailable_is_not_an_empty_success(client):
    client.app.state.trend_service = TrendService(fetcher=lambda _: {"data": []})
    response = client.get("/api/v1/trends?platforms=zhihu")
    assert response.status_code == 200
    feed = response.json()["trends"][0]
    assert feed["status"] == "unavailable"
    assert feed["error"]
    assert feed["fetched_at"] is None
