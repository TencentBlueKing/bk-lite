"""GitHub commits 工具单元测试 (github/commits)。

覆盖 URL/日期校验、commits 数据分组排序、HTTP 抓取的错误映射 (mock requests),
以及 @tool 入口的参数校验、分页终止逻辑、批量容错。仅 mock HTTP 边界。
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from apps.opspilot.metis.llm.tools.github import commits as gh


class TestValidateGithubUrl:
    def test_valid_https_official(self):
        assert gh._validate_github_url("https://api.github.com/repos/o/r/commits") is True

    def test_http_rejected(self):
        with pytest.raises(ValueError, match="HTTPS"):
            gh._validate_github_url("http://api.github.com/x")

    def test_other_domain_rejected(self):
        with pytest.raises(ValueError, match="官方API域名"):
            gh._validate_github_url("https://evil.com/repos")


class TestValidateDatetimeFormat:
    def test_z_suffix_ok(self):
        assert gh._validate_datetime_format("2025-09-08T00:00:00Z") is True

    def test_offset_ok(self):
        assert gh._validate_datetime_format("2025-09-08T00:00:00+08:00") is True

    def test_bad_format_raises(self):
        with pytest.raises(ValueError, match="ISO 8601"):
            gh._validate_datetime_format("2025/09/08")


class TestProcessCommitsData:
    def test_empty_returns_empty_dict(self):
        assert gh._process_commits_data([]) == {}

    def test_group_by_author_and_sort_desc(self):
        commits = [
            {"commit": {"author": {"name": "alice", "date": "2025-01-01T00:00:00Z"}, "message": "old"}},
            {"commit": {"author": {"name": "alice", "date": "2025-01-03T00:00:00Z"}, "message": "new"}},
            {"commit": {"author": {"name": "bob", "date": "2025-01-02T00:00:00Z"}, "message": "b1"}},
        ]
        out = gh._process_commits_data(commits)
        assert set(out.keys()) == {"alice", "bob"}
        # alice 按日期降序
        assert [c["message"] for c in out["alice"]] == ["new", "old"]
        assert out["bob"][0]["message"] == "b1"

    def test_missing_author_defaults_unknown(self):
        out = gh._process_commits_data([{"commit": {"message": "m"}}])
        assert "Unknown" in out


class TestFetchGithubCommits:
    def _resp(self, status, payload=None, text=""):
        r = MagicMock()
        r.status_code = status
        r.json.return_value = payload if payload is not None else []
        r.text = text
        return r

    def test_success_returns_payload(self):
        with patch.object(gh.requests, "get", return_value=self._resp(200, [{"sha": "x"}])):
            out = gh._fetch_github_commits("https://api.github.com/x", {})
        assert out == [{"sha": "x"}]

    def test_401_maps_to_auth_error(self):
        with patch.object(gh.requests, "get", return_value=self._resp(401)):
            with pytest.raises(ValueError, match="认证失败"):
                gh._fetch_github_commits("https://api.github.com/x", {})

    def test_404_maps_to_repo_not_found(self):
        with patch.object(gh.requests, "get", return_value=self._resp(404)):
            with pytest.raises(ValueError, match="仓库不存在"):
                gh._fetch_github_commits("https://api.github.com/x", {})

    def test_403_rate_limit(self):
        with patch.object(gh.requests, "get", return_value=self._resp(403)):
            with pytest.raises(ValueError, match="速率限制"):
                gh._fetch_github_commits("https://api.github.com/x", {})

    def test_500_generic_error(self):
        with patch.object(gh.requests, "get", return_value=self._resp(500, text="boom")):
            with pytest.raises(ValueError, match="状态码"):
                gh._fetch_github_commits("https://api.github.com/x", {})

    def test_timeout_mapped(self):
        with patch.object(gh.requests, "get", side_effect=gh.requests.exceptions.Timeout()):
            with pytest.raises(ValueError, match="请求超时"):
                gh._fetch_github_commits("https://api.github.com/x", {})


class TestGetGithubCommitsTool:
    def _invoke(self, **kwargs):
        return gh.get_github_commits.invoke(kwargs)

    def test_empty_owner_rejected(self):
        with pytest.raises(ValueError, match="owner"):
            self._invoke(owner="", repo="r", since="2025-01-01T00:00:00Z", until="2025-01-02T00:00:00Z")

    def test_bad_date_rejected(self):
        with pytest.raises(ValueError, match="ISO 8601"):
            self._invoke(owner="o", repo="r", since="bad", until="2025-01-02T00:00:00Z")

    def test_happy_path_returns_grouped_json(self):
        fake = [{"commit": {"author": {"name": "alice", "date": "2025-01-01T00:00:00Z"}, "message": "m"}}]
        with patch.object(gh, "_fetch_github_commits", return_value=fake):
            out = self._invoke(owner="o", repo="r", since="2025-01-01T00:00:00Z", until="2025-01-02T00:00:00Z")
        data = json.loads(out)
        assert data["alice"][0]["message"] == "m"

    def test_token_adds_auth_header(self):
        captured = {}

        def _fake(url, headers):
            captured["headers"] = headers
            return []

        with patch.object(gh, "_fetch_github_commits", side_effect=_fake):
            self._invoke(owner="o", repo="r", since="2025-01-01T00:00:00Z", until="2025-01-02T00:00:00Z", token="abc")
        assert captured["headers"]["Authorization"] == "token abc"


class TestGetGithubCommitsPagination:
    def _invoke(self, **kwargs):
        return gh.get_github_commits_with_pagination.invoke(kwargs)

    def test_invalid_max_pages_rejected(self):
        with pytest.raises(ValueError, match="max_pages"):
            self._invoke(owner="o", repo="r", since="2025-01-01T00:00:00Z", until="2025-01-02T00:00:00Z", max_pages=0)

    def test_stops_when_page_under_100(self):
        page1 = [{"commit": {"author": {"name": "a", "date": "2025-01-01T00:00:00Z"}, "message": "x"}}]
        calls = []

        def _fake(url, headers):
            calls.append(url)
            return page1  # 仅1条 < 100 -> 应在第一页后停止

        with patch.object(gh, "_fetch_github_commits", side_effect=_fake):
            out = self._invoke(owner="o", repo="r", since="2025-01-01T00:00:00Z", until="2025-01-02T00:00:00Z", max_pages=5)
        assert len(calls) == 1
        assert "a" in json.loads(out)

    def test_stops_on_empty_page(self):
        seq = [[{"commit": {"author": {"name": "a", "date": "2025-01-01T00:00:00Z"}, "message": "x"}} for _ in range(100)], []]
        idx = {"i": 0}

        def _fake(url, headers):
            r = seq[idx["i"]]
            idx["i"] += 1
            return r

        with patch.object(gh, "_fetch_github_commits", side_effect=_fake):
            out = self._invoke(owner="o", repo="r", since="2025-01-01T00:00:00Z", until="2025-01-02T00:00:00Z", max_pages=5)
        # 第一页满100,第二页空 -> 停止;共调用2次
        assert idx["i"] == 2
        assert json.loads(out)["a"]


class TestGetGithubCommitsBatch:
    def _invoke(self, **kwargs):
        return gh.get_github_commits_batch.invoke(kwargs)

    def test_partial_failure_does_not_abort(self):
        def _fake(url, headers):
            if "/bad/" in url:
                raise ValueError("repo missing")
            return [{"commit": {"author": {"name": "a", "date": "2025-01-01T00:00:00Z"}, "message": "m"}}]

        with patch.object(gh, "_fetch_github_commits", side_effect=_fake):
            out = self._invoke(
                repos=[{"owner": "o", "repo": "good"}, {"owner": "o", "repo": "bad"}],
                since="2025-01-01T00:00:00Z",
                until="2025-01-02T00:00:00Z",
            )
        data = json.loads(out)
        assert data["total"] == 2
        assert data["succeeded"] == 1
        assert data["failed"] == 1
        results = {r["input"]: r for r in data["results"]}
        assert results["o/good"]["ok"] is True
        assert results["o/bad"]["ok"] is False
        assert "repo missing" in results["o/bad"]["error"]
