import pandas as pd
import pytest


@pytest.fixture
def sample_input_df():
    # Minimal input structure; tests that require a specific schema will monkeypatch resolver/builders.
    return pd.DataFrame({
        "AnyIdentifier": ["A", "B"],
        "SomeValue": [1, 2],
    })


def write_xlsx(df: pd.DataFrame, path):
    """Helper to write an Excel file deterministically."""
    df.to_excel(path, index=False, engine="openpyxl")


def read_xlsx(path):
    return pd.read_excel(path, engine="openpyxl")

import time

def pytest_sessionstart(session):
    # Start time for the whole test session (monotonic is robust)
    session.config._physprops_test_start_time = time.perf_counter()


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """
    Always print a compact x/y summary line at the end, including elapsed time.
    Only list failing/error tests by nodeid.
    """
    stats = terminalreporter.stats

    passed = len(stats.get("passed", []))
    failed = len(stats.get("failed", []))
    errors = len(stats.get("error", []))
    skipped = len(stats.get("skipped", []))
    xfailed = len(stats.get("xfailed", []))
    xpassed = len(stats.get("xpassed", []))

    total = passed + failed + errors + skipped + xfailed + xpassed

    start = getattr(config, "_physprops_test_start_time", None)
    elapsed = (time.perf_counter() - start) if start is not None else None

    terminalreporter.write_sep("=", "TEST SUMMARY")

    if elapsed is not None:
        terminalreporter.write_line(
            f"{passed} out of {total} tests passed "
            f"({failed} failed, {errors} errors) in {elapsed:.2f}s"
        )
    else:
        terminalreporter.write_line(
            f"{passed} out of {total} tests passed "
            f"({failed} failed, {errors} errors)"
        )

    # Only mention failing/error tests (names only; pytest will show tracebacks above)
    if failed:
        terminalreporter.write_line("Failed tests:")
        for rep in stats["failed"]:
            terminalreporter.write_line(f"  - {rep.nodeid}")

    if errors:
        terminalreporter.write_line("Error tests:")
        for rep in stats["error"]:
            terminalreporter.write_line(f"  - {rep.nodeid}")