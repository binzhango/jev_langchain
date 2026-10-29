"""Protect first-run configuration, especially existing settings and secrets."""
import os

from dotenv import dotenv_values

from jev_harness import launch


def template(tmp_path):
    (tmp_path / '.env.example').write_text('LOCAL_LLM_BASE_URL=http://localhost:1234/v1\nLOCAL_LLM_MODEL=default-model\n')


def test_existing_configuration_is_untouched(tmp_path, monkeypatch):
    original = 'JEV_TOKEN=existing-private-token\n'
    (tmp_path / '.env').write_text(original)
    monkeypatch.setattr('builtins.input', lambda _: (_ for _ in ()).throw(AssertionError('Unexpected prompt')))
    launch.configure(tmp_path, True)
    assert (tmp_path / '.env').read_text() == original


def test_first_run_quotes_values_and_hides_credentials(tmp_path, monkeypatch, capsys):
    template(tmp_path)
    for key in ('LOCAL_LLM_BASE_URL', 'LOCAL_LLM_MODEL', 'LOCAL_LLM_API_KEY', 'JEV_TOKEN', 'TYPESAFE_API_KEY'):
        monkeypatch.delenv(key, raising=False)
    answers = iter(['http://localhost:1234/v1', "model's-name"])
    secrets = iter(['local-secret', "jev's-secret"])
    monkeypatch.setattr('builtins.input', lambda _: next(answers))
    monkeypatch.setattr(launch, 'getpass', lambda _: next(secrets))
    launch.configure(tmp_path, True)
    values = dotenv_values(tmp_path / '.env')
    assert values['LOCAL_LLM_MODEL'] == "model's-name"
    assert values['JEV_TOKEN'] == "jev's-secret"
    assert values['LOCAL_LLM_API_KEY'] == 'local-secret'
    assert os.stat(tmp_path / '.env').st_mode & 0o777 == 0o600
    output = capsys.readouterr().out
    assert "jev's-secret" not in output and 'local-secret' not in output


def test_noninteractive_setup_does_not_copy_exported_secrets(tmp_path, monkeypatch):
    template(tmp_path)
    monkeypatch.setenv('JEV_TOKEN', 'environment-only-secret')
    launch.configure(tmp_path, False)
    assert 'environment-only-secret' not in (tmp_path / '.env').read_text()
    assert dotenv_values(tmp_path / '.env')['LOCAL_LLM_MODEL'] == 'default-model'
