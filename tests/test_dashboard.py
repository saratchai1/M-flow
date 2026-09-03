from mflow_watchdog.config import Settings
from mflow_watchdog.dashboard import DashboardRunState, _run_check, build_summary


def test_dashboard_summary_after_demo_run(tmp_path, monkeypatch):
    monkeypatch.setenv("MFLOW_MOCK_MODE", "success")
    monkeypatch.setenv("VEHICLES_FILE", "vehicles.example.json")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "mflow.db"))
    monkeypatch.setenv("ARTIFACT_DIR", str(tmp_path / "artifacts"))

    settings = Settings.from_env()
    state = DashboardRunState()

    _run_check(settings, state)
    summary = build_summary(settings, state)

    assert summary["mode"] == "DEMO"
    assert summary["summary"]["total"] == 10
    assert summary["summary"]["attention"] == 0
    assert summary["summary"]["not_checked"] == 0
    assert summary["summary"]["clear"] == 5
    assert summary["summary"]["urgent"] + summary["summary"]["unpaid"] == 5
    assert summary["last_updated"] is not None
    assert summary["run"]["running"] is False
    assert summary["run"]["last_error"] is None
    assert len(summary["demo_notifications"]) == 5
