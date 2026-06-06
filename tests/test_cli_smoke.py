from typer.testing import CliRunner
from learn_kg.cli import app


def test_cli_init_list_export(tmp_path):
    runner = CliRunner()
    db = f"sqlite:///{tmp_path/'kg.sqlite3'}"
    assert runner.invoke(app, ["init-db", "--db", db]).exit_code == 0
    assert runner.invoke(app, ["list-projects", "--db", db]).exit_code == 0
    dot = tmp_path / "kg.dot"
    html = tmp_path / "kg.html"
    assert runner.invoke(app, ["export-dot", "--db", db, "--out", str(dot)]).exit_code == 0
    assert runner.invoke(app, ["export-html", "--db", db, "--out", str(html)]).exit_code == 0
    assert dot.exists() and html.exists()
