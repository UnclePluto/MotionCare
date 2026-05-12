import pytest

from apps.crf.registry_loader import load_crf_registry


@pytest.mark.django_db
def test_load_crf_registry_returns_template_id():
    reg = load_crf_registry()
    assert reg["template_id"]
    assert isinstance(reg["fields"], list)
    assert len(reg["fields"]) >= 1
