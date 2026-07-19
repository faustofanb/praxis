from __future__ import annotations

from conftest import read_json, run_praxis


def capability_ids(payload):
    return [item["id"] for item in payload["data"]["capabilities"]]


def test_profile_resolve_is_deterministic_and_topological():
    first = read_json(run_praxis("profile", "resolve", "base", "--json"))
    second = read_json(run_praxis("profile", "resolve", "base", "--json"))
    assert first["data"] == second["data"]
    ids = capability_ids(first)
    assert ids.index("workspace") < ids.index("project-registry") < ids.index("task-policy")


def test_profile_resolve_rejects_duplicate_missing_and_cycles():
    for profile_id, code in [
        ("fixture-duplicate-capability", "CAPABILITY_DUPLICATE"),
        ("fixture-missing-capability", "CAPABILITY_NOT_FOUND"),
        ("fixture-cycle", "PROFILE_CYCLE"),
        ("fixture-path-traversal", "CAPABILITY_PATH_TRAVERSAL"),
    ]:
        proc = run_praxis("profile", "resolve", profile_id, "--json")
        payload = read_json(proc)
        assert proc.returncode != 0
        assert payload["code"] == code


def test_mom_aotu_profiles_resolve_as_thin_compositions():
    mom = read_json(run_praxis("profile", "resolve", "mom", "--json"))["data"]
    aotu = read_json(run_praxis("profile", "resolve", "aotu", "--json"))["data"]
    assert mom["profile"]["id"] == "mom"
    assert aotu["profile"]["id"] == "aotu"
    assert mom["profile"].get("runtime_files") in (None, [])
    assert aotu["profile"].get("runtime_files") in (None, [])
    assert mom["parameters"]["delivery_contract"] == "standard"
    assert aotu["parameters"]["delivery_contract"] == "strict-confirmation"


def test_java_vue_profile_contains_no_mom_aotu_business_terms():
    payload = read_json(run_praxis("profile", "resolve", "java-vue", "--json"))["data"]
    text = str(payload).lower()
    forbidden = ["ifc-mom", "mom-agent", "aotu", "pda", "magicapi", "etl"]
    assert not any(term in text for term in forbidden)
