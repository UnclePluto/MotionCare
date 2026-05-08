from apps.studies.services.grouping import assign_groups


def test_assign_groups_respects_equal_ratio_for_four_patients():
    groups = [
        {"id": 1, "ratio": 1},
        {"id": 2, "ratio": 1},
    ]
    patient_ids = [101, 102, 103, 104]

    assignments = assign_groups(patient_ids=patient_ids, groups=groups, seed=7)

    counts = {1: 0, 2: 0}
    for group_id in assignments.values():
        counts[group_id] += 1
    assert counts == {1: 2, 2: 2}


def test_assign_groups_handles_two_to_one_ratio_for_six_patients():
    groups = [
        {"id": 1, "ratio": 2},
        {"id": 2, "ratio": 1},
    ]
    patient_ids = [101, 102, 103, 104, 105, 106]

    assignments = assign_groups(patient_ids=patient_ids, groups=groups, seed=9)

    counts = {1: 0, 2: 0}
    for group_id in assignments.values():
        counts[group_id] += 1
    assert counts == {1: 4, 2: 2}

