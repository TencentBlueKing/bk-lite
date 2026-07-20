import re
import unittest
from pathlib import Path


MOBILE_ROOT = Path(__file__).resolve().parents[1]
TAG_CONFIG = MOBILE_ROOT / "src/constants/workbenchTags.ts"
TAG_CONSUMERS = (
    MOBILE_ROOT / "src/app/workbench/page.tsx",
    MOBILE_ROOT / "src/app/search/page.tsx",
)


class WorkbenchTagConfigTest(unittest.TestCase):
    def test_pages_share_a_key_safe_tag_config(self):
        config_source = TAG_CONFIG.read_text(encoding="utf-8")

        self.assertIn("export const APP_TAGS", config_source)
        self.assertIn("export type AppTagKey", config_source)
        self.assertRegex(
            config_source,
            re.compile(r"APP_TAG_LABEL_KEYS[^=]*=.*satisfies Record<AppTagKey, string>", re.DOTALL),
        )
        self.assertRegex(
            config_source,
            re.compile(r"APP_TAG_COLORS[^=]*=.*satisfies Record<AppTagKey, AppTagColor>", re.DOTALL),
        )

        for consumer in TAG_CONSUMERS:
            source = consumer.read_text(encoding="utf-8")
            self.assertIn("@/constants/workbenchTags", source)
            self.assertNotRegex(source, r"const appTagsMap\s*[:=]")
            self.assertNotRegex(source, r"const appTagColors\s*[:=]")


if __name__ == "__main__":
    unittest.main()
