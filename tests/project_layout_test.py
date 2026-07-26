from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class ProjectLayoutTest(unittest.TestCase):
    def test_moved_crawlers_support_help_from_repository_root(self) -> None:
        scripts = (
            "data_pipeline/jobs/worknet_crawler.py",
            "data_pipeline/jobs/seoul_jobs_crawler.py",
        )

        for script in scripts:
            with self.subTest(script=script):
                result = subprocess.run(
                    [sys.executable, script, "--help"],
                    cwd=REPO_ROOT,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_sync_scripts_reference_relocated_modules(self) -> None:
        expected_paths = {
            "scripts/sync_jobs_daily.py": (
                "data_pipeline/jobs/worknet_crawler.py",
                "data_pipeline/jobs/seoul_jobs_crawler.py",
                "data_pipeline/jobs/fiftyplus_jobs_crawler.py",
                "scripts/maintenance/delete_expired_jobs.py",
            ),
            "scripts/sync_education_daily.py": (
                "data_pipeline/education/job_training_crawler.py",
                "data_pipeline/education/ai_digital_crawler.py",
                "data_pipeline/education/center_education_crawler.py",
                "scripts/maintenance/delete_expired_education.py",
            ),
        }

        for relative_path, expected in expected_paths.items():
            source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
            for path in expected:
                with self.subTest(script=relative_path, path=path):
                    self.assertIn(path, source)


if __name__ == "__main__":
    unittest.main()
