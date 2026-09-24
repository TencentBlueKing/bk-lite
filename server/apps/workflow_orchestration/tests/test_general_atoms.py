from apps.workflow_orchestration.services.atoms import ATOM_CATALOG, http_atom


def test_mvp_atom_catalog_exposes_platform_atoms_without_removed_general_atoms():
    assert "bklite_http_request" in ATOM_CATALOG
    assert "bklite_document_render" in ATOM_CATALOG
    assert "bklite_job_execute" in ATOM_CATALOG
    assert "bklite_notification" in ATOM_CATALOG
    assert "bklite_set" not in ATOM_CATALOG
    assert "bklite_json_transform" not in ATOM_CATALOG


def test_http_atom_passes_structured_response_between_runtime_boundaries(mocker):
    response = mocker.Mock()
    response.status_code = 200
    response.headers = {"Content-Type": "application/json", "Content-Length": "48"}
    response.iter_content.return_value = [b'{"service":"billing","hosts":[{"ip":"10.0.0.1"}]}']
    response.close.return_value = None
    mocker.patch(
        "apps.workflow_orchestration.atom_packages.http_runtime.safe_request",
        return_value=response,
    )
    mocker.patch(
        "apps.workflow_orchestration.atom_packages.http_runtime.SSRFValidator.validate",
        side_effect=lambda url: url,
    )

    output = http_atom(
        {
            "method": "GET",
            "url": "https://example.com/status",
            "timeout": 5,
            "response_format": "JSON",
            "success_status_codes": [200],
            "team": 1,
        }
    )

    assert output["status_code"] == 200
    assert output["body"]["service"] == "billing"
    assert output["body"]["hosts"][0]["ip"] == "10.0.0.1"
