from apps.mlops.utils.release_archive import with_archive_description, without_archive_description


def test_archive_description_marker_is_language_neutral_and_keeps_legacy_prefix():
    assert with_archive_description("orig") == "[archived] orig"
    assert with_archive_description("[已归档] orig") == "[已归档] orig"
    assert without_archive_description("[archived] orig") == "orig"
    assert without_archive_description("[已归档] orig") == "orig"
    assert without_archive_description("orig") == "orig"
