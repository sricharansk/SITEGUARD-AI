import yaml

from app.core.config import REPO_ROOT

REGISTRY = REPO_ROOT / "data" / "dataset_registry.yaml"
REQUIRED = {"id", "name", "publisher", "source_url", "access_date", "version", "license", "commercial_use", "purpose"}
COMMERCIAL = {"allowed", "review-required", "not-allowed-unless-permission"}


def test_registry_entries_are_complete_and_governed():
    entries = yaml.safe_load(REGISTRY.read_text())
    ids = [e["id"] for e in entries]
    assert len(ids) == len(set(ids))
    for e in entries:
        assert REQUIRED <= e.keys(), e["id"]
        assert e["commercial_use"] in COMMERCIAL, e["id"]
        if "NC" in str(e["license"]):
            assert e["commercial_use"] == "not-allowed-unless-permission", e["id"]
        if e["status"] == "downloaded":
            for key in ("source_url", "access_date", "version", "checksum_sha256"):
                assert e[key], f"{e['id']} is downloaded but has no {key}"
