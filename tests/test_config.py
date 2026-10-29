import pytest
from jev_harness.config import Settings


@pytest.mark.parametrize('value', ['0', '1.25', '2'])
def test_threshold_from_environment(monkeypatch, value):
    monkeypatch.setenv('JEV_RISK_THRESHOLD', value)
    settings = Settings.from_env()
    assert settings.risk_threshold == float(value)
    assert settings.execution_identity()['risk_threshold'] == float(value)


@pytest.mark.parametrize('value', ['-0.1', '2.1', 'nan', 'inf', 'not-a-number'])
def test_invalid_threshold_rejected(monkeypatch, value):
    monkeypatch.setenv('JEV_RISK_THRESHOLD', value)
    with pytest.raises(ValueError):
        Settings.from_env()
