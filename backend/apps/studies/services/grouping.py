import random
from collections.abc import Sequence


def assign_groups(
    *,
    patient_ids: Sequence[int],
    groups: Sequence[dict[str, int]],
    seed: int | None = None,
) -> dict[int, int]:
    if not groups:
        raise ValueError("项目没有分组，不能随机分组")
    if any(group["ratio"] <= 0 for group in groups):
        raise ValueError("分组比例必须大于 0")

    shuffled_patients = list(patient_ids)
    random.Random(seed).shuffle(shuffled_patients)

    total_ratio = sum(group["ratio"] for group in groups)
    total_patients = len(shuffled_patients)
    target_counts: dict[int, int] = {}
    remaining = total_patients

    for index, group in enumerate(groups):
        group_id = group["id"]
        if index == len(groups) - 1:
            count = remaining
        else:
            count = round(total_patients * group["ratio"] / total_ratio)
            count = min(count, remaining)
        target_counts[group_id] = count
        remaining -= count

    assignments: dict[int, int] = {}
    cursor = 0
    for group_id, count in target_counts.items():
        for patient_id in shuffled_patients[cursor : cursor + count]:
            assignments[patient_id] = group_id
        cursor += count
    return assignments

