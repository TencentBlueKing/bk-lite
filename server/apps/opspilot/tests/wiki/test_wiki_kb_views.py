import pytest


@pytest.mark.django_db
class TestWikiKBViews:
    BASE = "/api/v1/opspilot/wiki_mgmt/knowledge_base/"

    def _data(self, resp):
        body = resp.json()
        return body.get("data", body)

    def test_create_and_list(self, api_client):
        resp = api_client.post(
            self.BASE,
            {"name": "kb1", "team": [1], "purpose_md": "# P", "schema_md": "# S"},
            format="json",
        )
        assert resp.status_code in (200, 201), resp.content
        lst = api_client.get(self.BASE)
        assert lst.status_code == 200
        data = self._data(lst)
        assert "count" in data and "items" in data  # 分页格式,与 EntityList 一致
        names = [x["name"] for x in data["items"]]
        assert "kb1" in names

    def test_templates_endpoint(self, api_client):
        resp = api_client.get(self.BASE + "templates/")
        assert resp.status_code == 200
        keys = {t["key"] for t in self._data(resp)}
        assert "ops_qa" in keys and "general" in keys

    def test_generate_purpose_schema_endpoint_fallback(self, api_client):
        resp = api_client.post(
            self.BASE + "generate_purpose_schema/",
            {"template_key": "ops_qa", "description": "运维问答库"},
            format="json",
        )
        assert resp.status_code == 200, resp.content
        data = self._data(resp)
        assert "运维问答库" in data["purpose_md"]
        assert "知识类型" in data["schema_md"]
