from apps.node_mgmt.constants.collector import CollectorConstants
from apps.node_mgmt.services.node_status_filter import (
    INSTALL_STATUS_ERROR,
    INSTALL_STATUS_SUCCESS,
    collector_status_codes_from_filter_values,
    hosted_collectors_for_filter,
    node_matches_collector_filter,
)


def test_not_started_alias_expands_to_reported_and_installed():
    assert collector_status_codes_from_filter_values(["not_started"]) == {4, 11}


def test_unknown_status_values_are_dropped():
    assert collector_status_codes_from_filter_values(["2", "nope", 99]) == {2}


def test_empty_hosted_list_does_not_match():
    assert node_matches_collector_filter([], wanted_codes={2}, collector_name=None) is False


def test_any_collector_error_matches():
    hosted = hosted_collectors_for_filter(
        reported=[{"collector_id": "telegraf_linux", "status": 0}, {"collector_id": "vector_linux", "status": 2}],
        install_rows=[],
        collector_name_by_id={"telegraf_linux": "Telegraf", "vector_linux": "Vector"},
    )
    assert node_matches_collector_filter(hosted, wanted_codes={2}, collector_name=None) is True


def test_named_collector_ignores_other_component_error():
    hosted = hosted_collectors_for_filter(
        reported=[{"collector_id": "telegraf_linux", "status": 0}, {"collector_id": "vector_linux", "status": 2}],
        install_rows=[],
        collector_name_by_id={"telegraf_linux": "Telegraf", "vector_linux": "Vector"},
    )
    assert node_matches_collector_filter(hosted, wanted_codes={2}, collector_name="Telegraf") is False
    assert node_matches_collector_filter(hosted, wanted_codes={2}, collector_name="Vector") is True


def test_name_match_is_case_insensitive_and_ignores_os_suffix_id():
    hosted = hosted_collectors_for_filter(
        reported=[{"collector_id": "telegraf_windows", "status": 2}],
        install_rows=[],
        collector_name_by_id={"telegraf_windows": "Telegraf"},
    )
    assert node_matches_collector_filter(hosted, wanted_codes={2}, collector_name="telegraf") is True


def test_install_only_collector_is_merged_when_absent_from_reported():
    hosted = hosted_collectors_for_filter(
        reported=[{"collector_id": "telegraf_linux", "status": 0}],
        install_rows=[
            {"collector_id": "telegraf_linux", "status": INSTALL_STATUS_SUCCESS},
            {"collector_id": "vector_linux", "status": INSTALL_STATUS_ERROR},
        ],
        collector_name_by_id={"telegraf_linux": "Telegraf", "vector_linux": "Vector"},
    )
    ids = [item["collector_id"] for item in hosted]
    assert ids == ["telegraf_linux", "vector_linux"]
    assert node_matches_collector_filter(hosted, wanted_codes={12}, collector_name=None) is True


def test_ignore_error_empty_config_displays_as_normal():
    hosted = hosted_collectors_for_filter(
        reported=[
            {
                "collector_id": "filebeat_linux",
                "status": 2,
                "verbose_message": CollectorConstants.IGNORE_ERROR_EMPTY_CONFIG_MESSAGES[1],
            }
        ],
        install_rows=[],
        collector_name_by_id={"filebeat_linux": "Filebeat"},
    )
    assert hosted[0]["status"] == 0
    assert node_matches_collector_filter(hosted, wanted_codes={2}, collector_name=None) is False
