class CollectorReleaseConstants:
    SCHEMA_VERSION = 1
    MAX_COMPRESSED_BYTES = 200 * 1024 * 1024
    MAX_UNCOMPRESSED_BYTES = 400 * 1024 * 1024
    MAX_FILE_BYTES = 200 * 1024 * 1024
    MAX_ENTRIES = 32
    BOMB_RATIO = 50
    PREVIEW_TTL_SECONDS = 1800
    LOCK_TTL_SECONDS = 300
    VERSION_PATTERN = r"^\d+\.\d+\.\d+$"
    ALLOWED_OS = ("linux", "windows")
    ALLOWED_ARCH = ("x86_64", "arm64")
    NESTED_ARCHIVE_SUFFIXES = (".zip", ".tar", ".tgz", ".gz", ".7z")
    STAGING_CACHE_PREFIX = "collector_release_preview:"
    LOCK_CACHE_PREFIX = "collector_release_import:"
    LAYOUT_HINT = "manifest.json + plugin/ + artifacts/{os}/{arch}"
