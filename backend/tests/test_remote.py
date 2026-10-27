import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend.remote import fetch_github_repo, parse_github_url


class RemoteTests(unittest.TestCase):
    def test_dot_repository_names_are_rejected(self):
        for url in ("https://github.com/owner/..", "https://github.com/../repo"):
            self.assertIsNone(parse_github_url(url))

    def test_repeated_downloads_do_not_delete_previous_analysis(self):
        def download(owner, repo, ref, target):
            (target / "main.py").write_text("pass", encoding="utf-8")

        with tempfile.TemporaryDirectory() as directory:
            with patch("backend.remote.CACHE_DIR", Path(directory)), patch("backend.remote._clone", return_value=False), patch("backend.remote._download_zip", side_effect=download):
                first = fetch_github_repo("https://github.com/owner/repo")
                second = fetch_github_repo("https://github.com/owner/repo")
                self.assertNotEqual(first, second)
                self.assertTrue((first / "main.py").is_file())
                self.assertTrue((second / "main.py").is_file())

    def test_failed_download_removes_partial_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("backend.remote.CACHE_DIR", Path(directory)), patch("backend.remote._clone", return_value=False), patch("backend.remote._download_zip", side_effect=ValueError("Download failed")):
                with self.assertRaises(ValueError):
                    fetch_github_repo("https://github.com/owner/repo")
            self.assertEqual(list(Path(directory).iterdir()), [])
