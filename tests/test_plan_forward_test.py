import json

from bidefy.crawler import store
from tools import plan_forward_test as fwd


def test_report_reads_the_archive_and_states_the_gate(tmp_path):
    store.append_rows([{"tender_id": "1", "matched": True, "estimate_bdt": 1e6, "plan_method": "OTM",
                        "app_id": "9", "package_no": "P"}], tmp_path, "plan_estimates")
    store.append_rows([{"tender_id": "1", "value_crore": 0.09, "signed_on": "2099-01-01"}], tmp_path, "contracts")
    metrics = tmp_path / "metrics.json"
    metrics.write_text(json.dumps({"award_value_model": {"security_mape": 0.067}}), encoding="utf-8")
    r = fwd.report(tmp_path, metrics)
    # one award is far short of the gate, and the report says so rather than guessing
    assert r["n"] == 1 and r["verdict"] == "too few awards yet"
    assert r["would_serve"] is False and "of 200 awards scored" in r["gate"]
    assert r["security_mape_to_beat"] == 0.067
