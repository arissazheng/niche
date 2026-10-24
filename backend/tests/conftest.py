from sourcing.config import Settings

# Tests must never read a developer's .env: it may hold live keys and switch on paid Claude/Apify calls.
Settings.model_config['env_file'] = None
