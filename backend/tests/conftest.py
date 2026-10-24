from sourcing.config import Settings

# Tests must never read a developer's .env: it may hold live keys and switch on paid Claude/Apify calls.
Settings.model_config['env_file'] = None


import pytest


@pytest.fixture(autouse=True)
def no_live_keys_from_env(monkeypatch):
    # Cloud sessions export real Moss keys; without this, chat tests would write to the team's Moss project.
    for name in ('MOSS_PROJECT_ID', 'MOSS_PROJECT_KEY', 'CARTESIA_API_KEY', 'NICHE_CARTESIA_API_KEY'):
        monkeypatch.delenv(name, raising=False)
