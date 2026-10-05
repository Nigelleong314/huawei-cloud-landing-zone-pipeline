"""Generated descriptions use the wording reviewed for handover.

A delivered estate had its tag-policy and ER route-table descriptions
rewritten by hand into operator-facing sentences; a rebuild put the terse
generator wording back. The builders now emit the reviewed wording.
"""

from lz_pipeline.core.builders import build_01_foundation, _tag_policy_description


def test_tag_policy_wording():
    assert (_tag_policy_description({"TagKey": "env", "TagValue": "dev, uat, prd"})
            == "Require env to be dev, uat, or prd across all services")
    assert (_tag_policy_description({"TagKey": "Project", "TagValue": None})
            == "Require the project tag key across all services; any value is allowed")
    assert (_tag_policy_description({"TagKey": "env", "TagValue": ["dev", "prd"],
                                     "Scope": "ecs:instance, evs:volume"})
            == "Require env to be dev or prd for ecs:instance and evs:volume resources")


def test_foundation_tfvars_carry_the_wording():
    spec = {"Global": {"Settings": {"home_region": "ap-southeast-1"}},
            "01_Foundation": {"TagPolicies": [
                {"Name": "enforce-owner-tagging", "TagKey": "owner"}]}}
    tp = build_01_foundation(spec)["tag_policies"][0]
    assert list(tp) == ["name", "description", "content"]
    assert tp["description"] == "Require the owner tag key across all services; any value is allowed"
