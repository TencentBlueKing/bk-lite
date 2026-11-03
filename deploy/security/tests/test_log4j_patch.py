import hashlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
import zipfile


SPEC = importlib.util.spec_from_file_location("patch_log4j", Path(__file__).parents[1] / "patch_log4j.py")
patch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(patch)


def library(name, version, *, jndi=False):
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as jar:
        jar.writestr(f"META-INF/maven/org.apache.logging.log4j/{name}/pom.properties",
                     f"groupId=org.apache.logging.log4j\nartifactId={name}\nversion={version}\n")
        jar.writestr("preserved.class", b"fixture")
        if jndi:
            jar.writestr("org/apache/logging/log4j/core/lookup/JndiLookup.class", b"fixture")
    return data.getvalue()


class Log4jPatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.available = {name: library(name, "2.25.5", jndi=name == "log4j-core")
                          for name in ("log4j-api", "log4j-core", "log4j-slf4j2-impl")}

    def conductor(self, *, version="2.25.4", extra=None):
        source = self.root / "source.jar"
        with zipfile.ZipFile(source, "w") as jar:
            for name in self.available:
                jar.writestr(f"BOOT-INF/lib/{name}-{version}.jar", library(name, version))
            jar.writestr("BOOT-INF/classpath.idx", f'- "BOOT-INF/lib/log4j-api-{version}.jar"\n')
            jar.writestr("BOOT-INF/layers.idx", f'- "BOOT-INF/lib/log4j-api-{version}.jar"\n')
            jar.writestr("META-INF/BOOT.SF", b"")
            jar.writestr("app.class", b"unchanged")
            if extra:
                jar.writestr(*extra)
        return source

    def test_conductor_replaces_every_module_and_classpath_index(self):
        output = self.root / "patched.jar"
        patch.patch_conductor(self.conductor(), output, self.available, "2.25.5")
        with zipfile.ZipFile(output) as jar:
            self.assertEqual(jar.read("app.class"), b"unchanged")
            self.assertNotIn("2.25.4", "\n".join(jar.namelist()))
            self.assertIn(b"2.25.5", jar.read("BOOT-INF/classpath.idx"))
            self.assertIn(b"2.25.5", jar.read("BOOT-INF/layers.idx"))
            self.assertEqual(jar.read("META-INF/BOOT.SF"), b"")
            for name in self.available:
                path = f"BOOT-INF/lib/{name}-2.25.5.jar"
                self.assertEqual(patch.coordinate(jar.read(path)), (name, "2.25.5"))
                self.assertEqual(jar.getinfo(path).compress_type, zipfile.ZIP_STORED)

    def test_conductor_is_idempotent(self):
        output = self.root / "patched.jar"
        patch.patch_conductor(self.conductor(version="2.25.5"), output, self.available, "2.25.5")
        with zipfile.ZipFile(output) as jar:
            self.assertEqual(patch.coordinate(jar.read("BOOT-INF/lib/log4j-core-2.25.5.jar")), ("log4j-core", "2.25.5"))

    def test_in_place_jar_edit_is_rejected_without_changing_input(self):
        source = self.conductor()
        before = source.read_bytes()
        with self.assertRaisesRegex(ValueError, "in-place"):
            patch.patch_conductor(source, source, self.available, "2.25.5")
        self.assertEqual(source.read_bytes(), before)

    def test_elasticsearch_rejects_stale_output(self):
        output = self.root / "patched"
        output.mkdir()
        stale = output / "log4j-api-2.17.1.jar"
        stale.write_bytes(b"stale")
        with self.assertRaisesRegex(ValueError, "empty directory"):
            patch.patch_elasticsearch(self.root / "missing-source", output, self.available, "2.25.5")
        self.assertEqual(stale.read_bytes(), b"stale")

    def test_conductor_rejects_signed_outer_jar_and_unreviewed_versions(self):
        for source in (self.conductor(extra=("META-INF/vendor.SF", b"signature")),):
            with self.assertRaisesRegex(ValueError, "Signed"):
                patch.patch_conductor(source, self.root / "output.jar", self.available, "2.25.5")
        with self.assertRaisesRegex(ValueError, "Unreviewed"):
            patch.patch_conductor(self.conductor(version="2.26.0"), self.root / "output.jar", self.available, "2.25.5")

    def test_conductor_rejects_unpinned_module(self):
        extra = ("BOOT-INF/lib/log4j-unknown-2.25.4.jar", library("log4j-unknown", "2.25.4"))
        with self.assertRaisesRegex(ValueError, "Unreviewed"):
            patch.patch_conductor(self.conductor(extra=extra), self.root / "output.jar", self.available, "2.25.5")

    def test_artifact_checksum_and_metadata_are_verified(self):
        data = self.available["log4j-api"]
        path = self.root / "log4j-api-2.25.5.jar"
        path.write_bytes(data)
        manifest = {"version": "2.25.5", "artifacts": {"log4j-api": {"sha256": hashlib.sha256(data).hexdigest()}}}
        self.assertEqual(patch.artifacts(self.root, manifest)["log4j-api"], data)
        path.write_bytes(data + b"tampered")
        with self.assertRaisesRegex(ValueError, "checksum"):
            patch.artifacts(self.root, manifest)
        wrong = library("log4j-core", "2.25.5")
        path.write_bytes(wrong)
        manifest["artifacts"]["log4j-api"]["sha256"] = hashlib.sha256(wrong).hexdigest()
        with self.assertRaisesRegex(ValueError, "metadata"):
            patch.artifacts(self.root, manifest)

    def test_elasticsearch_keeps_vendor_jndi_removal_and_preserves_input(self):
        source = self.root / "lib"
        source.mkdir()
        api = library("log4j-api", "2.17.1")
        (source / "log4j-api-2.17.1.jar").write_bytes(api)
        (source / "elasticsearch-log4j-7.17.21.jar").write_bytes(library("log4j-core", "2.17.1"))
        output = self.root / "patched"
        patch.patch_elasticsearch(source, output, self.available, "2.25.5")
        self.assertEqual((source / "log4j-api-2.17.1.jar").read_bytes(), api)
        self.assertEqual(sorted(p.name for p in output.iterdir()), ["elasticsearch-log4j-7.17.21.jar", "log4j-api-2.25.5.jar"])
        with zipfile.ZipFile(output / "elasticsearch-log4j-7.17.21.jar") as jar:
            self.assertNotIn("org/apache/logging/log4j/core/lookup/JndiLookup.class", jar.namelist())
            self.assertEqual(jar.read("preserved.class"), b"fixture")


if __name__ == "__main__":
    unittest.main()
