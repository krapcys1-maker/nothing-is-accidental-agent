"""Private diagnostic redaction and atomic durability tests (offline only)."""
from __future__ import annotations

from dataclasses import replace
import json

import pytest

from app.operations.controlled_live import write_operator_report
from app.research.diagnostics import (
    ResponseDiagnostics,
    _DEFAULT_FILE_OPS,
    write_diagnostics,
)


SECRET_RAW = """provider output
sk-ant-test-secret
Authorization: Bearer test-secret
api_key=test-secret
nested_exception=RuntimeError(password=test-secret)
headers={"x-api-key":"test-secret"}
"""
FORBIDDEN = (
    "sk-ant-test-secret",
    "Authorization",
    "Bearer",
    "api_key",
    "nested_exception",
    "headers",
    "test-secret",
)


def _diagnostic() -> ResponseDiagnostics:
    return ResponseDiagnostics(
        run_id="safe-run",
        stage="SINGLE",
        stop_reason="end_turn",
        input_tokens=10,
        output_tokens=20,
        cache_read_tokens=0,
        cache_write_tokens=0,
        web_search_requests=1,
        raw_response=SECRET_RAW,
    )


def test_private_diagnostic_and_operator_report_share_recursive_sanitizer(tmp_path):
    diagnostic = write_diagnostics(tmp_path / "data", _diagnostic())
    report = write_operator_report(
        tmp_path / "reports",
        "safe-report",
        {
            "detail": SECRET_RAW,
            "nested": {
                "headers": {"Authorization": "Bearer test-secret"},
                "api_key": "sk-ant-test-secret",
            },
        },
    )
    diagnostic_text = diagnostic.read_text(encoding="utf-8")
    report_text = report.read_text(encoding="utf-8")
    rendered = diagnostic_text + report_text
    assert "[REDACTED]" in rendered
    assert json.loads(report.read_text(encoding="utf-8"))["nested"]
    for forbidden in FORBIDDEN:
        assert forbidden not in diagnostic_text
    for secret_value in ("sk-ant-test-secret", "test-secret", "Bearer"):
        assert secret_value not in report_text


@pytest.mark.parametrize(
    ("failure_point", "replacement"),
    [
        ("temp_write", {"write_file": lambda *_args: _raise_io("temp write")}),
        ("file_fsync", {"fsync_file": lambda *_args: _raise_io("file fsync")}),
        ("replace", {"replace_file": lambda *_args: _raise_io("replace")}),
        (
            "directory_fsync",
            {"fsync_directory": lambda *_args: _raise_io("directory fsync")},
        ),
    ],
)
def test_atomic_diagnostic_failpoints_leave_no_unsanitized_temporary_file(
    tmp_path, failure_point, replacement,
):
    file_ops = replace(_DEFAULT_FILE_OPS, **replacement)
    with pytest.raises(OSError, match=failure_point.replace("_", " ")):
        write_diagnostics(tmp_path / "data", _diagnostic(), _file_ops=file_ops)

    run_dir = tmp_path / "data" / "debug" / "research" / "safe-run"
    assert not list(run_dir.glob("*.tmp"))
    final = run_dir / "SINGLE_raw_response.txt"
    if final.exists():
        content = final.read_text(encoding="utf-8")
        for forbidden in FORBIDDEN:
            assert forbidden not in content


def _raise_io(label: str):
    raise OSError(label)
