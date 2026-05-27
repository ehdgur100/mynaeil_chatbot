from __future__ import annotations

import argparse
import subprocess
import sys


PYTHON = sys.executable


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
                "data_pipeline/crawler.py",
                "--target-count",
                str(args.worknet_target),
            ]
        )

        print("\n=== Seoul jobs3 크롤링/upsert ===")
        run_command(
            [
                PYTHON,
                "data_pipeline/seoul_jobs_crawler.py",
                "--target-count",
                str(args.seoul_target),
            ]
        )

        print("\n=== 50plus job_seoul_50 크롤링 ===")
        run_command(
            [
                PYTHON,
                "crawl_50plus_jobs.py",
                "--output-dir",
                "data/50plus_private_applying",
            ]
        )

        print("\n=== 50plus job_seoul_50 Supabase upsert ===")
        run_command(
            [
                PYTHON,
                "load_50plus_jobs_to_supabase.py",
                "--json-path",
                "data/50plus_private_applying/50plus_jobs_applying.json",
            ],
            allow_failure=True,
        )

        if not args.skip_embeddings:
            print("\n=== 새 일자리 임베딩 생성 ===")
            run_command([PYTHON, "data_pipeline/embed_jobs.py"])

        print("\nJobs sync completed.")
        return 0
    except subprocess.CalledProcessError as exc:
        print(f"Command failed with exit code {exc.returncode}: {exc.cmd}", file=sys.stderr)
        return exc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
