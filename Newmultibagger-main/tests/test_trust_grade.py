from research.trust_score import compute_trust_score, trust_grade


def test_grade_bands_match_pass_bar():
    assert [trust_grade(s) for s in (95, 80.1, 70, 55, 40, 0)] == ["A", "A", "B", "C", "D", "F"]


def test_trust_report_includes_grade():
    # The Research tab renders report["grade"]; it was missing, leaving "Grade:" blank.
    report = compute_trust_score()
    assert report["grade"] == trust_grade(report["trust_score"])
