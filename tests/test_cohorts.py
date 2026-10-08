from fallbackledger import replay, summarize, validate


def test_common_case_membership_and_all_exclusions(data):
    v = validate(*data).validated
    s = summarize(v, replay(v))
    common = next(c for c in s.cohorts if c.id == ("common", "both"))
    assert [r.case.case_id for r in common.rows if r.included] == ["04", "05"]
    case03 = next(r for r in common.rows if r.case.case_id == "03")
    assert len(case03.exclusions) == 2 and {e.reason for e in case03.exclusions} == {
        "point_failed"
    }
