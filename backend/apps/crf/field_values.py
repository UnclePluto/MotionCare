"""Read CRF values without coercing or rewriting historical answers.

Data uses canonical roots (patient_baseline / visit). For repeated children pass
one row and its relative field definition. Metadata keys are literal strings.
"""

from collections.abc import Mapping
from copy import deepcopy
from apps.crf.answer_values import has_crf_answer_marker

MISSING = object()
BAD_PARENT = object()


def lookup_path(data: dict, path: str):
    """Return the raw value, MISSING, or BAD_PARENT; numeric segments index rows."""
    current = data
    for part in path.split("."):
        if isinstance(current, Mapping):
            if part not in current:
                return MISSING
            current = current[part]
        elif isinstance(current, list) and part.isdecimal():
            if int(part) >= len(current):
                return MISSING
            current = current[int(part)]
        else:
            return BAD_PARENT
    return current


def get_field_value(data: dict, field: dict) -> object:
    """Read raw answers; a non-null partial-date representation takes precedence.

    Missing or inaccessible paths return None. Validation uses lookup_path to
    separately report malformed parents and simultaneous date representations.
    """
    canonical = field.get('date_answer_storage')
    if canonical:
        answer = lookup_path(data, canonical)
        if answer is not MISSING and answer is not BAD_PARENT: return answer
    partial = field.get("partial_date_storage")
    if partial:
        value = lookup_path(data, partial)
        if value is not MISSING and value is not BAD_PARENT and value is not None:
            return value
    value = lookup_path(data, field["storage"])
    return None if value is MISSING or value is BAD_PARENT else value


def get_field_metadata(data: dict, field: dict) -> object:
    """Read the metadata entry using its full storage key literally, not as a path."""
    definition = field.get("metadata")
    if not definition:
        return None
    container = lookup_path(data, definition["storage"])
    if container is MISSING or container is None:
        return None
    if not isinstance(container, Mapping):
        return BAD_PARENT
    return container.get(definition["key"])


def prepare_visit_date_patch(patch: dict) -> dict:
    """Explicit logical edits alone coordinate the native projection and old parts."""
    result=deepcopy(patch)
    answer=lookup_path(result,'form_data.crf.meta.visit_date_answer')
    parts=lookup_path(result,'form_data.crf.meta.visit_date_parts')
    if 'visit_date' in result or (answer is not MISSING and answer is not BAD_PARENT):
        logical=result['visit_date'] if 'visit_date' in result else answer
        if logical is None and answer is MISSING and parts is not MISSING and parts is not BAD_PARENT and parts is not None:logical=deepcopy(parts)
        current=result
        for key in ('form_data','crf','meta'):
            if key in current and not isinstance(current[key],Mapping):return result
            current=current.setdefault(key,{})
        current['visit_date_answer']=deepcopy(logical)
        # Explicitly submitted non-null old parts remain for conflict validation.
        if parts is MISSING:current['visit_date_parts']=None
        result['visit_date']=deepcopy(logical)
    elif parts is not MISSING and parts is not BAD_PARENT:
        result['visit_date']=deepcopy(parts)
        if isinstance(result.get('form_data',{}).get('crf',{}).get('meta'),dict):
            result['form_data']['crf']['meta']['visit_date_answer']=deepcopy(parts)
    return result


def merge_crf_patch(current: dict, patch: dict) -> dict:
    """Copy and recursively merge objects; arrays/scalars/null replace explicitly.

    Keys are always literal, including dotted metadata keys. Omitted keys and
    historical values survive unchanged; neither argument shares mutable state
    with the returned candidate.
    """
    result = deepcopy(current)
    for key, value in patch.items():
        if isinstance(result.get(key), dict) and isinstance(value, dict) and not has_crf_answer_marker(result[key]) and not has_crf_answer_marker(value):
            result[key] = merge_crf_patch(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def _same_crf_value(left, right):
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(_same_crf_value(left[k], right[k]) for k in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(_same_crf_value(a, b) for a, b in zip(left, right))
    return left == right


def _row_id_indices(rows):
    result = {}
    for index, row in enumerate(rows):
        if isinstance(row, dict) and isinstance(row.get("_row_id"), str):
            result.setdefault(row["_row_id"], []).append(index)
    return result


def match_crf_rows(current: list, candidate: list) -> dict[int, int]:
    """Map final row indices to provable old rows without consuming one twice."""
    old_ids, new_ids = _row_id_indices(current), _row_id_indices(candidate)
    matched, used = {}, set()
    for row_id, indices in new_ids.items():
        old = old_ids.get(row_id, [])
        if len(indices) == len(old) == 1:
            matched[indices[0]] = old[0]
            used.add(old[0])
    for index, row in enumerate(candidate):
        if index in matched:
            continue
        for old_index, old_row in enumerate(current):
            if old_index not in used and _same_crf_value(row, old_row):
                matched[index] = old_index
                used.add(old_index)
                break
    for index, row in enumerate(candidate):
        if index in matched or index in used or index >= len(current):
            continue
        old_row = current[index]
        if not isinstance(row, dict) or (
            isinstance(old_row, dict)
            and _same_crf_value(old_row.get("_row_id"), row.get("_row_id"))
        ):
            matched[index] = index
            used.add(index)
    return matched


def changed_crf_paths(current, candidate, *, prefix="") -> set[str]:
    """Changed leaves at final indices; keys (including metadata) stay literal.

    Rows first match unique stable IDs, then consume identical old rows one by
    one (legacy missing/duplicate IDs never collapse a row). Ambiguous remaining
    rows may only match the same position and ID. No similarity heuristic or
    clinical value migration is performed. New duplicate IDs are always touched.
    """
    if has_crf_answer_marker(current) or has_crf_answer_marker(candidate):
        return set() if _same_crf_value(current,candidate) else {prefix}
    if isinstance(current, dict) and isinstance(candidate, dict):
        changed = set()
        for key in current.keys() | candidate.keys():
            path = f"{prefix}.{key}" if prefix else key
            changed.update(
                changed_crf_paths(
                    current.get(key, MISSING), candidate.get(key, MISSING), prefix=path
                )
            )
        return changed
    if isinstance(current, list) and isinstance(candidate, list):
        if not candidate:
            return {prefix} if current else set()
        if not any(isinstance(row, dict) for row in current + candidate):
            return set() if _same_crf_value(current, candidate) else {prefix}

        old_ids, new_ids = _row_id_indices(current), _row_id_indices(candidate)
        matched = match_crf_rows(current, candidate)
        changed = set()
        for index, row in enumerate(candidate):
            previous = current[matched[index]] if index in matched else MISSING
            path = f"{prefix}.{index}"
            changed.update(changed_crf_paths(previous, row, prefix=path))
            row_id = row.get("_row_id") if isinstance(row, dict) else None
            if isinstance(row_id, str) and len(new_ids[row_id]) > max(
                1, len(old_ids.get(row_id, []))
            ):
                changed.add(path + "._row_id")
        return changed
    return set() if _same_crf_value(current, candidate) else {prefix}
