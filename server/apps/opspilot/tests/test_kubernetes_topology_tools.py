def test_import_get_current_cluster_name():
    from apps.opspilot.metis.llm.tools.kubernetes import get_current_cluster_name

    # The function should be importable from package root
    assert callable(get_current_cluster_name)
