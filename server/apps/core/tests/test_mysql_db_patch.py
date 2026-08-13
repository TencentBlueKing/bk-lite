from types import SimpleNamespace

from django.db.backends.mysql.operations import DatabaseOperations

from apps.core.db_patches import mysql


def test_regex_patch_only_changes_mysql_57_and_is_idempotent(monkeypatch):
    def modern_regex_lookup(self, lookup_type):
        return f"modern:{lookup_type}"

    monkeypatch.setattr(DatabaseOperations, "regex_lookup", modern_regex_lookup)
    mysql._patch_regex_lookup()
    patched = DatabaseOperations.regex_lookup

    mysql57 = SimpleNamespace(connection=SimpleNamespace(mysql_is_mariadb=False, mysql_version=(5, 7, 30)))
    mysql80 = SimpleNamespace(connection=SimpleNamespace(mysql_is_mariadb=False, mysql_version=(8, 0, 40)))
    mariadb = SimpleNamespace(connection=SimpleNamespace(mysql_is_mariadb=True, mysql_version=(10, 11, 0)))

    assert patched(mysql57, "regex") == "%s REGEXP BINARY %s"
    assert patched(mysql57, "iregex") == "%s REGEXP %s"
    assert patched(mariadb, "regex") == "%s REGEXP BINARY %s"
    assert patched(mysql80, "regex") == "modern:regex"

    mysql._patch_regex_lookup()
    assert DatabaseOperations.regex_lookup is patched
