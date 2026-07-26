from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


PYTHON = sys.executable
REPO_ROOT = Path(__file__).resolve().parents[1]
JOB_TRAINING_CRAWLER = REPO_ROOT / "data_pipeline/education/job_training_crawler.py"
AI_DIGITAL_CRAWLER = REPO_ROOT / "data_pipeline/education/ai_digital_crawler.py"
CENTER_EDUCATION_CRAWLER = REPO_ROOT / "data_pipeline/education/center_education_crawler.py"
EDUCATION_LOADER = REPO_ROOT / "data_pipeline/education/education_loader.py"
EXPIRED_EDUCATION_CLEANUP = REPO_ROOT / "scripts/maintenance/delete_expired_education.py"
DATA_DIR = REPO_ROOT / "data"

JOBS = [
    {
        "name": "취업훈련 모집중",
        "crawl": [
            PYTHON,
            str(JOB_TRAINING_CRAWLER),
            "--output-dir",
            str(DATA_DIR / "50plus_education_applying"),
        ],
        "json": DATA_DIR / "50plus_education_applying/50plus_education_applying.json",
    },
    {
        "name": "AI디지털교육 모집중",
        "crawl": [
            PYTHON,
            str(AI_DIGITAL_CRAWLER),
            "--state",
            "JOIN",
            "--output-dir",
            str(DATA_DIR / "50plus_ai_digital_joining"),
        ],
        "json": DATA_DIR / "50plus_ai_digital_joining/50plus_ai_digital_joining.json",
    },
    {
        "name": "AI디지털교육 모집예정",
        "crawl": [
            PYTHON,
            str(AI_DIGITAL_CRAWLER),
            "--state",
            "PEND",
            "--output-dir",
            str(DATA_DIR / "50plus_ai_digital_pending"),
        ],
        "json": DATA_DIR / "50plus_ai_digital_pending/50plus_ai_digital_pending.json",
    },
    {
        "name": "50플러스센터교육 모집중",
        "crawl": [
            PYTHON,
            str(CENTER_EDUCATION_CRAWLER),
            "--state",
            "JOIN",
            "--output-dir",
            str(DATA_DIR / "50plus_center_education_joining"),
        ],
        "json": DATA_DIR / "50plus_center_education_joining/50plus_center_education_joining.json",
    },
    {
        "name": "50플러스센터교육 모집예정",
        "crawl": [
            PYTHON,
            str(CENTER_EDUCATION_CRAWLER),
            "--state",
            "PEND",
            "--output-dir",
            str(DATA_DIR / "50plus_center_education_pending"),
        ],
        "json": DATA_DIR / "50plus_center_education_pending/50plus_center_education_pending.json",
    },
]


def run_command(command: list[str]) -> None:
    print(f"\n$ {' '.join(command)}")
    subprocess.run(command, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Daily crawl/upsert/cleanup job for 50plus education data."
    )
    parser.add_argument(
        "--skip-embeddings",
        action="store_true",
        help="Upload rows without regenerating embeddings.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Embedding and Supabase upsert batch size.",
    )
    args = parser.parse_args()

    try:
        for job in JOBS:
            print(f"\n=== {job['name']} 크롤링 ===")
            run_command(job["crawl"])

            json_path = job["json"]
            if not json_path.exists():
                raise RuntimeError(f"Expected crawl output not found: {json_path}")

            load_command = [
                PYTHON,
                str(EDUCATION_LOADER),
                "--json-path",
                str(json_path),
                "--batch-size",
                str(args.batch_size),
            ]
            if args.skip_embeddings:
                load_command.append("--skip-embeddings")
            print(f"\n=== {job['name']} Supabase upsert ===")
            run_command(load_command)

        print("\n=== 지난 마감일 교육 삭제 ===")
        run_command([PYTHON, str(EXPIRED_EDUCATION_CLEANUP)])

        print("\nEducation sync completed.")
        return 0
    except subprocess.CalledProcessError as exc:
        print(f"Command failed with exit code {exc.returncode}: {exc.cmd}", file=sys.stderr)
        return exc.returncode
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
