"""在已构建的 Debian 13 候选镜像内手动运行；不接入启动或发布链路。"""

from io import BytesIO
import os
from pathlib import Path
import subprocess
import unittest

from PIL import Image, ImageDraw, ImageFont, _imagingft, features
import PIL


class PillowRuntimeTests(unittest.TestCase):
    def test_freetype_uses_system_brotli(self):
        result = subprocess.run(
            ["ldd", _imagingft.__file__], check=True, capture_output=True, text=True, timeout=10,
        )
        self.assertIn("libfreetype.so.6 => /", result.stdout)
        self.assertIn("libbrotlidec.so.1 => /", result.stdout)
        self.assertNotIn("pillow.libs", result.stdout)
        self.assertNotIn("not found", result.stdout)
        self.assertFalse((Path(PIL.__file__).parent.parent / "pillow.libs").exists())

    def test_original_version_and_image_formats(self):
        self.assertEqual(PIL.__version__, os.environ["PILLOW_EXPECTED_VERSION"])
        for feature in ("jpg", "zlib", "libtiff", "webp", "jpg_2000", "avif", "raqm"):
            with self.subTest(feature=feature):
                self.assertTrue(features.check(feature))
        for image_format in ("JPEG", "PNG", "TIFF", "WEBP", "JPEG2000", "AVIF"):
            with self.subTest(image_format=image_format):
                buffer = BytesIO()
                Image.new("RGB", (16, 16), (40, 80, 120)).save(buffer, format=image_format)
                buffer.seek(0)
                with Image.open(buffer) as decoded:
                    decoded.load()
                    self.assertEqual(decoded.size, (16, 16))

    def test_font_layout_and_drawing(self):
        font = ImageFont.truetype("DejaVuSans.ttf", 20, layout_engine=ImageFont.Layout.RAQM)
        image = Image.new("RGB", (256, 64), "white")
        ImageDraw.Draw(image).text((0, 0), "BK-Lite العربية", font=font, fill="black")
        self.assertLess(min(image.convert("L").getdata()), 255)


if __name__ == "__main__":
    unittest.main()
