from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    sourcing_mode: Literal['fixture', 'live'] = 'fixture'
    # Separate switch so the taste engine can call Claude while sourcing stays on free fixtures.
    taste_mode: Literal['fixture', 'live'] = 'fixture'
    apify_token: str = ''
    # NICHE_ANTHROPIC_API_KEY wins: some hosts (e.g. Claude Code cloud sessions) reserve ANTHROPIC_API_KEY.
    anthropic_api_key: str = Field(default='', validation_alias=AliasChoices(
        'NICHE_ANTHROPIC_API_KEY', 'ANTHROPIC_API_KEY', 'anthropic_api_key'))
    # Not read from ANTHROPIC_BASE_URL on purpose: hosts can set that to their own gateway.
    anthropic_base_url: str = Field(default='https://api.anthropic.com', validation_alias='NICHE_ANTHROPIC_BASE_URL')
    claude_model: str = 'claude-opus-5-5'
    sourcing_api_key: str = ''
    database_path: str = 'data/sourcing.sqlite3'
    actor_timeout_seconds: int = Field(default=180, ge=10, le=600)
    max_actor_charge_usd: float = Field(default=.5, gt=0, le=20)
    cors_origins: list[str] = ['http://localhost:3000', 'http://127.0.0.1:3000']
    etsy_actor: str = 'one_dollar_store/etsy-listings-scraper'
    resale_actor: str = 'crawlerbros/mercari-poshmark-depop-scraper'
    grailed_actor: str = 'devilscrapes/grailed-listings-scraper'
    # Niche's own actors (backend/actors), deployed privately to the team's Apify account.
    mainstream_actor: str = 'zaarahemd/niche-mainstream'
    secondhand_actor: str = 'zaarahemd/niche-secondhand'
    # Google Shopping costs $0.02 per result on Apify's free plan ($0.005 on paid plans), at least 10 per phrase.
    mainstream_queries: int = Field(default=1, ge=1, le=3)
    mainstream_items_per_query: int = Field(default=10, ge=10, le=60)
    upload_dir: str = 'data/uploads'
    public_api_url: str = 'http://127.0.0.1:8000'
    nessie_api_key: str = ''
    # SpacetimeDB live state (blank URL disables publishing; the app still works by polling).
    spacetime_url: str = ''
    spacetime_db: str = 'niche'
    spacetime_token: str = ''

    def validate_live(self):
        if self.sourcing_mode == 'live' and not (self.apify_token and self.anthropic_api_key):
            raise ValueError('Live mode requires APIFY_TOKEN and NICHE_ANTHROPIC_API_KEY (or ANTHROPIC_API_KEY)')
        if self.taste_mode == 'live' and not self.anthropic_api_key:
            raise ValueError('Live taste mode requires NICHE_ANTHROPIC_API_KEY (or ANTHROPIC_API_KEY)')
