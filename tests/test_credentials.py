import pytest
from ugc_forge import config
from ugc_forge.providers.google import resolve_api_key, _client


def test_shared_keys_and_project_overrides(tmp_path, monkeypatch):
    monkeypatch.setattr(config, '__file__', str(tmp_path / 'ugc_forge/config.py'))
    (tmp_path / 'pyproject.toml').write_text('')  # looks like a source checkout
    (tmp_path / 'config.yaml').write_text('generation_models:\n  image:\n    api_key: shared-image\n  video:\n    api_key: shared-video\nvideo:\n  resolution: 4k\n')
    project = tmp_path / 'runs/new'
    project.mkdir(parents=True)
    cfg = config.load_config(project)
    assert resolve_api_key(cfg['generation_models']['image']) == 'shared-image'
    assert cfg['video']['resolution'] == '720p'
    assert not (project / 'config.yaml').exists()
    (project / 'config.yaml').write_text('generation_models:\n  image:\n    api_key: project-image\n  video:\n    api_key_env: CUSTOM_VIDEO_KEY\n')
    monkeypatch.setenv('CUSTOM_VIDEO_KEY', 'custom-video')
    cfg = config.load_config(project)
    assert resolve_api_key(cfg['generation_models']['image']) == 'project-image'
    assert resolve_api_key(cfg['generation_models']['video']) == 'custom-video'


def test_direct_key_reaches_client(monkeypatch):
    from google import genai
    monkeypatch.setenv('TEST_KEY', 'environment-key')
    monkeypatch.setattr(genai, 'Client', lambda **kwargs: kwargs)
    assert _client({'api_key': 'config-key', 'api_key_env': 'TEST_KEY'}) == {'api_key': 'config-key'}
    assert resolve_api_key({'api_key': None, 'api_key_env': 'TEST_KEY'}) == 'environment-key'


def test_missing_or_misplaced_keys_do_not_leak(monkeypatch):
    monkeypatch.delenv('MISSING_TEST_KEY', raising=False)
    for value in ['MISSING_TEST_KEY', 'secret-key-value']:
        with pytest.raises(RuntimeError) as error:
            resolve_api_key({'api_key_env': value})
        assert value not in str(error.value)
