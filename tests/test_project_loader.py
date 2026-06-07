from pathlib import Path
from learn_kg.models import ProjectSpec
from learn_kg.project_loader import load_project


def test_project_spec_parse_colon_path():
    spec = ProjectSpec.parse("foo:/tmp/foo:c4-1")
    assert spec.name == "foo"
    assert str(spec.path) == "/tmp/foo"
    assert spec.platform_id == "c4-1"


def test_load_project():
    spec = ProjectSpec(name="simple", path=Path("tests/fixtures/simple_project"), platform_id="simple-1")
    p = load_project(spec, Path("tests/fixtures/simple_project/audit.md"))
    assert p.source_files
    assert p.audit_report is not None
