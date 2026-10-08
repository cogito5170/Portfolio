# -*- coding: utf-8 -*-
"""Static site (XR-06): builds from the repo, uses relative paths only, and every listed world opens from the
built folder in a real browser. Run from engine/."""
from __future__ import annotations

import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ENGINE))

from worldengine import headless, site  # noqa: E402

BROWSER, WHY = headless.available()


class SiteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="we_site_"))
        cls.r = site.build(cls.tmp / "site")
        cls.out = Path(cls.r["out"])

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_every_repo_world_is_listed(self):
        self.assertEqual(sorted(w["file"] for w in self.r["worlds"]), sorted(p.name for p in (ENGINE / "worlds").glob("*.world.json")))

    def test_no_absolute_or_external_urls(self):
        for f in [self.out / "index.html", self.out / "runtime" / "index.html"]:
            text = f.read_text(encoding="utf-8")
            self.assertEqual(re.findall(r'(?:src|href)="(?:/|https?:)[^"]*"', text), [], f)
        imports = json.loads(re.search(r'<script type="importmap">(.*?)</script>', (self.out / "runtime" / "index.html").read_text(encoding="utf-8")).group(1))
        for target in imports["imports"].values():
            self.assertTrue(target.startswith("../"), target)
            self.assertTrue((self.out / "runtime" / target).resolve().exists() or target.endswith("/"), target)

    def test_tests_are_not_shipped(self):
        self.assertFalse((self.out / "runtime" / "tests").exists())

    @unittest.skipUnless(BROWSER, "no headless browser: %s" % WHY)
    def test_every_world_opens_from_the_built_site(self):
        for r in site.smoke(self.out):
            with self.subTest(r["file"]):
                self.assertTrue(r["ok"], r["reason"])


if __name__ == "__main__":
    unittest.main()
