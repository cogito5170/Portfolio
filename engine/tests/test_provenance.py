# -*- coding: utf-8 -*-
"""PROVENANCE.md must stay true: vendored three.js files hash to the upstream blobs listed there, and every
se_new file listed as identical still is (its git blob hash equals the source blob)."""
from __future__ import annotations

import hashlib
import re
import unittest
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent


def blob(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


class ProvenanceTests(unittest.TestCase):
    text = (ENGINE / "PROVENANCE.md").read_text(encoding="utf-8")

    def test_vendored_three_is_byte_identical_to_upstream(self):
        rows = re.findall(r"^\| `([^`]+)` \| `([0-9a-f]{40})` \|$", self.text, re.M)
        self.assertGreaterEqual(len(rows), 16)
        listed = {f for f, _ in rows}
        on_disk = {str(p.relative_to(ENGINE / "vendor" / "three")) for p in (ENGINE / "vendor" / "three").rglob("*") if p.is_file() and p.name != "VENDORED.md"}
        self.assertEqual(listed, on_disk)                 # nothing vendored without a row, no row without a file
        for f, sha in rows:
            with self.subTest(f):
                self.assertEqual(blob(ENGINE / "vendor" / "three" / f), sha)

    def test_identical_se_new_files_are_still_identical(self):
        rows = re.findall(r"^\| `worldengine/([^`]+)` \| `[^`]+` \| `([0-9a-f]{40})` \| identical \|$", self.text, re.M)
        self.assertGreaterEqual(len(rows), 4)
        for f, sha in rows:
            with self.subTest(f):
                self.assertEqual(blob(ENGINE / "worldengine" / f), sha)


if __name__ == "__main__":
    unittest.main()
