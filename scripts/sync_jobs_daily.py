from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


PYTHON = sys.executable
REPO_ROOT = Path(__file__).resolve().parents[1]
WORKNET_CRAWLER = REPO_ROOT / "data_pipeline/jobs/worknet_crawler.py"
SEOUL_JOBS_CRAWLER = REPO_ROOT / "data_pipeline/jobs/seoul_jobs_crawler.py"
FIFTYPLUS_JOBS_CRAWLER = REPO_ROOT / "data_pipeline/jobs/fiftyplus_jobs_crawler.py"
FIFTYPLUS_JOBS_LOADER = REPO_ROOT / "data_pipeline/jobs/fiftyplus_jobs_loader.py"
JOB_EMBEDDER = REPO_ROOT / "data_pipeline/jobs/embed_jobs.py"
EXPIRED_JOBS_CLEANUP = REPO_ROOT / "scripts/maintenance/delete_expired_jobs.py"
FIFTYPLUS_JOBS_OUTPUT = REPO_ROOT / "data/50plus_private_applying"


def run_command(command: list[str], allow_failure: bool = False) -> None:
    print(f"\n$ {' '.join(command)}")
    result = subprocess.run(command)
    if result.returncode and not allow_failure:
        raise subprocess.CalledProcessError(result.returncode, command)
    if result.returncode:
        print(f"[Warning] Command failed but sync will continue: {' '.join(command)}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Daily crawl/upsert job for jobs, jobs3, and job_seoul_50."
    )
    parser.add_argument(
        "--skip-embeddings",
        action="store_true",
        help="Skip embedding generation for newly inserted job rows.",
    )
    parser.add_argument("--worknet-target", type=int, default=2000)
    parser.add_argument("--seoul-target", type=int, default=3000)
    args = parser.parse_args()

    try:
        print("\n=== Worknet jobs 크롤링/upsert ===")
        run_command(
            [
                PYTHON,
                str(WORKNET_CRAWLER),
                "--target-count",
                str(args.worknet_target),
            ]
        )

        print("\n=== Seoul jobs3 크롤링/upsert ===")
        run_command(
            [
                PYTHON,
                str(SEOUL_JOBS_CRAWLER),
                "--target-count",
                str(args.seoul_target),
            ]
        )

        print("\n=== 50plus job_seoul_50 크롤링 ===")
        run_command(
            [
                PYTHON,
                str(FIFTYPLUS_JOBS_CRAWLER),
                "--biz-se",
                "IN49008",
                "--output-dir",
                str(FIFTYPLUS_JOBS_OUTPUT),
            ]
        )

        print("\n=== 50plus job_seoul_50 Supabase upsert ===")
        run_command(
            [
                PYTHON,
                str(FIFTYPLUS_JOBS_LOADER),
                "--json-path",
                str(FIFTYPLUS_JOBS_OUTPUT / "50plus_jobs_applying.json"),
            ],
            allow_failure=True,
        )

        print("\n=== 지난 마감 직업 공고 삭제 ===")
        run_command([PYTHON, str(EXPIRED_JOBS_CLEANUP)])

        if not args.skip_embeddings:
            print("\n=== 새 일자리 임베딩 생성 ===")
            run_command([PYTHON, str(JOB_EMBEDDER)])

        print("\nJobs sync completed.")
        return 0
    except subprocess.CalledProcessError as exc:
        print(f"Command failed with exit code {exc.returncode}: {exc.cmd}", file=sys.stderr)
        return exc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
