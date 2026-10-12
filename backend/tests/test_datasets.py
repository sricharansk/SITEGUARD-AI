"""OSHA Severe Injury Reports pipeline, tested on a SYNTHETIC fixture in the official column layout."""

from datetime import date
from pathlib import Path

import pytest

from app.datasets import osha_sir

FIXTURE = Path(__file__).parent / "fixtures" / "osha_sir_synthetic_fixture.csv"


def test_reads_construction_rows_only_and_drops_duplicates():
    records, stats = osha_sir.read(FIXTURE)
    assert stats["rows"] == 7
    assert {r.id for r in records} == {"SYN-1", "SYN-2", "SYN-3", "SYN-4", "SYN-6"}  # retail NAICS 445110 dropped
    assert stats["dropped_duplicate_id"] == 1
    assert all(r.naics.startswith("23") for r in records)
    assert not hasattr(records[0], "employer")


def test_since_filter():
    records, stats = osha_sir.read(FIXTURE, since=date(2024, 1, 1))
    assert "SYN-6" not in {r.id for r in records} and stats["dropped_before_since"] == 1


def test_missing_required_column_is_a_clear_error(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("ID,EventDate,Primary NAICS\n1,01/01/2025,236220\n")
    with pytest.raises(osha_sir.SchemaError, match="narrative"):
        osha_sir.read(bad)


def test_oiics_mapping():
    assert osha_sir.oiics_class("Fall to lower level") == "Fall from height"
    assert osha_sir.oiics_class("Direct exposure to electricity") == "Electrical contact"
    assert osha_sir.oiics_class("Caught in or compressed by collapsing materials") == "Excavation collapse / caught-in"
    assert osha_sir.oiics_class("Caught in running equipment or machinery") is None  # no taxonomy counterpart
    assert osha_sir.oiics_class("Something new") is None


def test_evaluate_and_report_never_expose_employers(tmp_path):
    records, stats = osha_sir.read(FIXTURE)
    ev = osha_sir.evaluate(records)
    assert ev["records"] == 5
    assert ev["severity_high_or_critical"] == 1.0  # every severe injury triaged HIGH or CRITICAL
    assert ev["mapped_to_taxonomy"] == 4 and ev["class_agreement"] == 1.0
    assert ev["amputations_rated_critical"] == 1.0
    m = osha_sir.manifest(FIXTURE, stats, None)
    assert len(m["sha256"]) == 64
    md = osha_sir.to_markdown(m, ev)
    assert "Synthetic Builder" not in md and "Test St" not in md
    assert "Do not use it to rank or judge employers" in md


def test_dataset_registry_is_complete():
    import yaml

    from app.core.config import get_settings

    rows = yaml.safe_load((get_settings().seed_dir.parent / "dataset_registry.yaml").read_text())
    required = {"id", "name", "source_url", "license", "commercial_use", "purpose", "limitations", "status", "acquired"}
    assert len({r["id"] for r in rows}) == len(rows)
    for r in rows:
        assert required <= set(r), (r["id"], required - set(r))
        assert r["commercial_use"] in {"allowed", "review-required", "not-allowed-unless-permission"}
        assert r["status"] in {"pipeline-ready", "planned", "reference-only"}
