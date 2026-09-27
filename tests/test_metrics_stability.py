"""The run-to-run noise floor is read out of git history, so the reading itself needs a test."""
import json
import subprocess
from pathlib import Path

from tools import metrics_stability


def _repo(tmp_path: Path, series: list[tuple[str, float, float]]) -> Path:
    """A throwaway repository whose metrics.json was rewritten once per training run."""
    def run(*a):
        r = subprocess.run(["git", *a], cwd=tmp_path, capture_output=True, text=True)
        assert r.returncode == 0, f"git {' '.join(a)}: {r.stdout}{r.stderr}"
        return r
    run("init", "-q")
    run("config", "user.email", "t@t.t")
    run("config", "user.name", "t")
    (tmp_path / "models").mkdir()
    path = tmp_path / "models" / "metrics.json"
    for stamp, coverage, deferral in series:
        path.write_text(json.dumps({
            "award_value_model": {"trained_at": stamp, "coverage_80": coverage,
                                  "history_coverage_80": coverage, "history_mape": 0.38,
                                  "history_band_width_median": 5.0, "security_coverage_80": 0.77,
                                  "security_mape": 0.077, "deferral_rate": deferral},
            "category_classifier": {"accuracy_acted": 0.93, "deferral_rate": deferral,
                                    "macro_f1": 0.7},
        }), encoding="utf-8")
        run("add", "-A")
        run("commit", "-q", "-m", f"run {stamp}")
    return tmp_path


def _run(tmp_path: Path, monkeypatch) -> dict:
    monkeypatch.setattr(metrics_stability, "ROOT", tmp_path)
    monkeypatch.setattr(metrics_stability, "OUT", tmp_path / "models" / "stability.json")
    metrics_stability.main()
    return json.loads((tmp_path / "models" / "stability.json").read_text(encoding="utf-8"))


def test_reads_the_step_between_runs_out_of_history(tmp_path: Path, monkeypatch):
    _repo(tmp_path, [("t1", 0.780, 0.16), ("t2", 0.783, 0.155), ("t3", 0.781, 0.15),
                     ("t4", 0.785, 0.145), ("t5", 0.782, 0.14), ("t6", 0.784, 0.135)])
    out = _run(tmp_path, monkeypatch)
    assert out["runs"] == 6 and out["from"] == "t1" and out["to"] == "t6"
    cov = out["figures"]["award_value_model.coverage_80"]
    assert cov["first"] == 0.78 and cov["last"] == 0.784
    assert cov["spread"] == 0.005                      # 0.785 - 0.780
    assert cov["typical_step"] == 0.003                # median of .003 .002 .004 .003 .002
    assert cov["kind"] == "pct" and cov["expected_steady"] is True


def test_a_figure_carries_what_kind_of_number_it_is(tmp_path: Path, monkeypatch):
    """A band width is a multiple and an F1 a score; printing either as a percent prints nonsense."""
    _repo(tmp_path, [(f"t{i}", 0.78 + i / 1000, 0.15) for i in range(6)])
    figs = _run(tmp_path, monkeypatch)["figures"]
    assert figs["award_value_model.history_band_width_median"]["kind"] == "multiple"
    assert figs["category_classifier.macro_f1"]["kind"] == "score"
    # Deferral is expected to fall as the crawl collects securities and labels, so it is not
    # counted toward the noise floor.
    assert figs["award_value_model.deferral_rate"]["expected_steady"] is False
    assert figs["category_classifier.deferral_rate"]["expected_steady"] is False


def test_a_commit_that_did_not_retrain_is_not_counted_twice(tmp_path: Path, monkeypatch):
    """Runs are told apart by their training stamp, not by the commit that carried the file."""
    root = _repo(tmp_path, [("t1", 0.78, 0.16), ("t1", 0.781, 0.16), ("t2", 0.79, 0.15),
                            ("t3", 0.78, 0.14)])
    out = _run(root, monkeypatch)
    assert out["runs"] == 3


def test_too_little_history_reports_nothing_rather_than_a_guess(tmp_path: Path, monkeypatch):
    """A spread measured over a couple of runs understates the floor, and understating the floor is
    how a change gets read as a result. On a shallow clone the tool must say nothing instead."""
    _repo(tmp_path, [("t1", 0.78, 0.16), ("t2", 0.79, 0.15)])
    out = _run(tmp_path, monkeypatch)
    assert out["figures"] == {} and out["runs"] == 2


def test_a_figure_carries_which_way_is_better(tmp_path: Path, monkeypatch):
    """Without a direction the page announces a regression as the improvement of the week."""
    _repo(tmp_path, [(f"t{i}", 0.78, 0.15) for i in range(6)])
    figs = _run(tmp_path, monkeypatch)["figures"]
    assert figs["category_classifier.deferral_rate"]["better"] == "down"
    assert figs["award_value_model.history_mape"]["better"] == "down"
    assert figs["award_value_model.history_band_width_median"]["better"] == "down"
    assert figs["category_classifier.macro_f1"]["better"] == "up"
    assert figs["award_value_model.history_coverage_80"]["better"] == "up"


def test_a_git_failure_is_swallowed_rather_than_failing_the_nightly(tmp_path: Path, monkeypatch):
    """This runs one step before the crawl is committed, so it must never exit non-zero.

    A table of noise figures that can discard hours of crawling is a worse trade than no table.
    """
    import json as _json
    (tmp_path / "models").mkdir(parents=True)
    monkeypatch.setattr(metrics_stability, "ROOT", tmp_path)          # not a git repository
    monkeypatch.setattr(metrics_stability, "OUT", tmp_path / "models" / "stability.json")
    metrics_stability.main()                                          # must not raise
    out = _json.loads((tmp_path / "models" / "stability.json").read_text(encoding="utf-8"))
    assert out["figures"] == {} and out["runs"] == 0 and out["error"]
