import importlib.util
import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path, PurePosixPath

spec = importlib.util.spec_from_file_location("extract_skill", Path(__file__).parents[1] / "scripts/extract-skill.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
SKILL = b"---\nname: example\ndescription: Example skill\n---\nReview me.\n"


def archive(entries):
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode="w:gz") as tar:
        for name, content, kind in entries:
            info = tarfile.TarInfo(name)
            info.type = kind
            info.size = len(content) if kind == tarfile.REGTYPE else 0
            tar.addfile(info, io.BytesIO(content))
    return data.getvalue()


class ExtractionTests(unittest.TestCase):
    def test_markdown_response_stages_without_overwriting(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "review"
            payload = {"content": [{"type": "text", "text": json.dumps({"markdown": SKILL.decode(), "version_id": "v1"})}]}
            result = module.extract(payload, target)
            self.assertEqual((target / "SKILL.md").read_bytes(), SKILL)
            self.assertEqual(result["version_id"], "v1")
            with self.assertRaises(ValueError):
                module.extract(payload, target)

    def test_archive_preserves_supporting_files(self):
        files = module.archive_files(archive([
            ("example/SKILL.md", SKILL, tarfile.REGTYPE),
            ("example/references/info.md", b"context", tarfile.REGTYPE),
        ]))
        self.assertEqual(files[PurePosixPath("references/info.md")], b"context")

    def test_unsafe_archives_are_refused(self):
        for name, kind in [("../escape", tarfile.REGTYPE), ("/absolute", tarfile.REGTYPE), ("link", tarfile.SYMTYPE), ("link", tarfile.LNKTYPE)]:
            with self.subTest(name=name, kind=kind), self.assertRaises(ValueError):
                module.archive_files(archive([("SKILL.md", SKILL, tarfile.REGTYPE), (name, b"bad", kind)]))

    def test_error_and_duplicate_paths_are_refused(self):
        with self.assertRaises(ValueError):
            module.unwrap({"isError": True, "markdown": SKILL.decode()})
        with self.assertRaises(ValueError):
            module.archive_files(archive([("SKILL.md", SKILL, tarfile.REGTYPE), ("skill.md", SKILL, tarfile.REGTYPE)]))


if __name__ == "__main__":
    unittest.main()
