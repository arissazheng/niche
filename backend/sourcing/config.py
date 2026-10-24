from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    sourcing_mode: Literal['fixture', 'live'] = 'fixture'
    # Separate switch so the taste engine can call Claude while sourcing stays on free fixtures.
    taste_mode: Literal['fixture', 'live'] = 'fixture'
    apify_token: str = ''
    anthropic_api_key: str = ''
    claude_model: str = 'claude-opus-5-5'
    sourcing_api_key: str = ''
    database_path: str = 'data/sourcing.sqlite3'
    actor_timeout_seconds: int = Field(default=120, ge=10, le=600)
    max_actor_charge_usd: float = Field(default=.5, gt=0, le=20)
    cors_origins: list[str] = ['http://localhost:3000', 'http://127.0.0.1:3000']
    etsy_actor: str = 'one_dollar_store/etsy-listings-scraper'
    resale_actor: str = 'crawlerbros/mercari-poshmark-depop-scraper'
    grailed_actor: str = 'devilscrapes/grailed-listings-scraper'
    upload_dir: str = 'data/uploads'
    public_api_url: str = 'http://127.0.0.1:8000'
    stripe_secret_key: str = ''
    nessie_api_key: str = ''
    nessie_account_id: str = ''
    nessie_merchant_id: str = ''

    def validate_live(self):
        if self.sourcing_mode == 'live' and not (self.apify_token and self.anthropic_api_key):
            raise ValueError('Live mode requires APIFY_TOKEN and ANTHROPIC_API_KEY')
        if self.taste_mode == 'live' and not self.anthropic_api_key:
            raise ValueError('Live taste mode requires ANTHROPIC_API_KEY')
