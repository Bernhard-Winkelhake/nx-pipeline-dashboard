# -*- coding: utf-8 -*-
"""
NX batch pipeline.

This file is launched by Siemens NX run_journal.exe.
Configuration is supplied through NX_PIPELINE_CONFIG because run_journal.exe
parses command-line switches itself.
"""

import json
import os
import sys
import time
import traceback
from pathlib import Path

import NXOpen


def load_config():
    config_path = os.environ.get("NX_PIPELINE_CONFIG")
    if not config_path:
        raise RuntimeError("Environment variable NX_PIPELINE_CONFIG is not set.")

    path = Path(config_path)
    if not path.is_file():
        raise RuntimeError("Pipeline config not found: {}".format(path))

    # PowerShell may write a UTF-8 BOM depending on version.
    with path.open("r", encoding="utf-8-sig") as handle:
        config = json.load(handle)

    required = ("root", "framework", "report", "project")
    missing = [key for key in required if not config.get(key)]
    if missing:
        raise RuntimeError(
            "Pipeline config is missing: {}".format(", ".join(missing))
        )
    return config


def load_framework(framework_src):
    framework_src = Path(framework_src).resolve()
    runner_file = framework_src / "check_runner.py"
    if not runner_file.is_file():
        raise RuntimeError(
            "Invalid framework path. Expected: {}".format(runner_file)
        )

    framework_str = str(framework_src)
    if framework_str not in sys.path:
        sys.path.insert(0, framework_str)

    from check_runner import CheckRunner
    return CheckRunner


def discover_parts(root):
    return sorted(
        path for path in Path(root).rglob("*.prt")
        if path.is_file()
    )


def open_part(path):
    session = NXOpen.Session.GetSession()
    part, load_status = session.Parts.OpenActiveDisplay(
        str(path),
        NXOpen.DisplayPartOption.ReplaceExisting,
    )
    session.Parts.SetWork(part)

    try:
        load_status.Dispose()
    except Exception:
        pass

    return part


def close_part(part):
    if part is None:
        return

    try:
        part.Close(NXOpen.BasePartCloseOption.SkipSave, None)
    except Exception:
        pass


def fatal_report(path, exc):
    return {
        "schema_version": 1,
        "part": Path(path).name,
        "path": str(path),
        "status": "ERROR",
        "summary": {
            "total": 1,
            "failed": 1,
            "warnings": 0,
            "passed": 0,
            "skipped": 0,
        },
        "results": [{
            "rule_id": "PIPELINE_FATAL",
            "check_name": "Pipeline processing",
            "status": "FAILED",
            "severity": "ERROR",
            "message": str(exc),
            "object_name": None,
            "object_type": None,
        }],
    }


def run_part(CheckRunner, path):
    part = None
    try:
        part = open_part(path)

        # Expected nx-testframework interface.
        runner = CheckRunner(part)
        results = runner.run()
        report = runner.build_report(results)

        if not isinstance(report, dict):
            raise RuntimeError("CheckRunner.build_report() must return a dict.")

        report["path"] = str(path)
        return report

    except Exception as exc:
        print("ERROR {}: {}".format(path, exc))
        traceback.print_exc()
        return fatal_report(path, exc)

    finally:
        close_part(part)



def format_duration(seconds):
    seconds = max(0, int(round(seconds)))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)

    if hours:
        return "{}h {:02d}m {:02d}s".format(hours, minutes, secs)
    if minutes:
        return "{}m {:02d}s".format(minutes, secs)
    return "{}s".format(secs)


def build_summary(reports):
    statuses = [report.get("status") for report in reports.values()]
    return {
        "parts_total": len(reports),
        "parts_passed": statuses.count("PASSED"),
        "parts_failed": statuses.count("FAILED"),
        "parts_error": statuses.count("ERROR"),
    }


def main():
    config = load_config()

    root = Path(config["root"]).resolve()
    out_dir = Path(config["report"]).resolve()

    if not root.is_dir():
        raise RuntimeError("Parts root folder does not exist: {}".format(root))

    CheckRunner = load_framework(config["framework"])
    parts = discover_parts(root)

    print("Discovered {} .prt file(s).".format(len(parts)))
    out_dir.mkdir(parents=True, exist_ok=True)

    reports = {}
    batch_started = time.time()

    for index, path in enumerate(parts, 1):
        part_started = time.time()

        elapsed = time.time() - batch_started
        avg = (elapsed / (index - 1)) if index > 1 else 0.0
        remaining = avg * (len(parts) - index + 1) if index > 1 else 0.0
        percent = ((index - 1) / float(len(parts)) * 100.0) if parts else 100.0

        if index == 1:
            print("[{}/{}] {:.1f}% | ETA: calculating... | {}".format(
                index, len(parts), percent, path
            ))
        else:
            print("[{}/{}] {:.1f}% | avg {:.1f}s/part | ETA {} | {}".format(
                index, len(parts), percent, avg, format_duration(remaining), path
            ))

        reports[str(path)] = run_part(CheckRunner, path)

        part_seconds = time.time() - part_started
        total_elapsed = time.time() - batch_started
        completed = index
        avg = total_elapsed / completed
        remaining = avg * (len(parts) - completed)
        percent = (completed / float(len(parts)) * 100.0) if parts else 100.0

        print("  -> done in {:.1f}s | {:.1f}% | elapsed {} | ETA {}".format(
            part_seconds,
            percent,
            format_duration(total_elapsed),
            format_duration(remaining),
        ))

    payload = {
        "schema_version": 1,
        "project": config["project"],
        "root": str(root),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "summary": build_summary(reports),
        "files": reports,
    }

    output = out_dir / "results.json"
    with output.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)

    total_seconds = time.time() - batch_started
    print("")
    print("Batch finished: {} part(s) in {} (avg {:.1f}s/part).".format(
        len(parts),
        format_duration(total_seconds),
        (total_seconds / len(parts)) if parts else 0.0,
    ))
    print("Wrote: {}".format(output))


if __name__ == "__main__":
    main()
