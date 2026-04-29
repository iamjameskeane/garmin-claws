from typer.testing import CliRunner

from garmin_claws.cli import app


runner = CliRunner()


def test_cli_help_mentions_agent_friendly_commands():
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "Agent-ready Garmin Connect CLI" in result.stdout
    assert "auth" in result.stdout
    assert "today" in result.stdout
    assert "activities" in result.stdout


def test_auth_status_reports_missing_tokens(monkeypatch, tmp_path):
    monkeypatch.setenv("GARMIN_CLAWS_TOKEN_DIR", str(tmp_path / "missing"))

    result = runner.invoke(app, ["auth", "status"])

    assert result.exit_code == 1
    assert "not found" in result.stdout
    assert "garmin-claws auth login" in result.stdout


def test_auth_login_prints_local_machine_instructions(monkeypatch, tmp_path):
    monkeypatch.setenv("GARMIN_CLAWS_TOKEN_DIR", str(tmp_path / ".garminconnect"))

    result = runner.invoke(app, ["auth", "login", "--print-instructions"])

    assert result.exit_code == 0
    assert "Run this on your local machine" in result.stdout
    assert "garminconnect" in result.stdout
    assert "garmin-claws auth import" in result.stdout


def test_flow_plan_returns_json_without_live_garmin():
    result = runner.invoke(app, ["flow", "plan", "daily-brief", "--json"])

    assert result.exit_code == 0
    assert '"flow": "daily-brief"' in result.stdout
    assert '"commands"' in result.stdout
    assert "today" in result.stdout
