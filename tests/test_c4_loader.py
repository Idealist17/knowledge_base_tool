from pathlib import Path
from learn_kg.c4_loader import discover_contest_ids, select_contest_ids, load_c4_project


def test_discover_and_select_c4_ids():
    root = Path("tests/fixtures/c4")
    assert discover_contest_ids(root) == [2, 1]
    assert select_contest_ids(root, skip_ids="2", limit=1) == [1]


def test_load_c4_project():
    p = load_c4_project(Path("tests/fixtures/c4"), 1)
    assert p.name == "c4-1"
    assert p.platform_id == "c4-1"
    assert p.source_files
    assert p.audit_report and "Reentrancy" in p.audit_report.content
