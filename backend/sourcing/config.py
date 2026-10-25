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
    # Bright Data: Pinterest/Instagram imports. NICHE_BRIGHTDATA_API_KEY wins, like the Claude key.
    brightdata_api_key: str = Field(default='', validation_alias=AliasChoices(
        'NICHE_BRIGHTDATA_API_KEY', 'BRIGHTDATA_API_KEY', 'brightdata_api_key'))
    # A Web Unlocker zone (Bright Data dashboard) for Pinterest board links; blank turns board links off.
    brightdata_unlocker_zone: str = ''
    # A SERP API zone: with the Web Unlocker zone, searches also find independent labels on any shop platform
    # (sourcing/webshops.py). Blank turns that source off.
    brightdata_serp_zone: str = ''
    # Not read from ANTHROPIC_BASE_URL on purpose: hosts can set that to their own gateway.
    anthropic_base_url: str = Field(default='https://api.anthropic.com', validation_alias='NICHE_ANTHROPIC_BASE_URL')
    claude_model: str = 'claude-opus-5-5'
    # Gemini with Grounding with Google Maps, for the optional "Shops near you" list under search results.
    gemini_api_key: str = ''
    # Flash-Lite: ~3 s with Maps grounding and the same shop quality in tests; 3.8 Flash took ~35 s.
    gemini_model: str = 'gemini-3.1-flash-lite'
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
    # Independent labels' own Shopify stores, fetched directly (backend/actors/niche_actors/indie.py).
    indie_actor: str = 'arissazheng/niche-indie'
    # Google Shopping costs $0.02 per result on Apify's free plan ($0.005 on paid plans), at least 10 per phrase.
    mainstream_queries: int = Field(default=1, ge=1, le=3)
    mainstream_items_per_query: int = Field(default=10, ge=10, le=60)
    upload_dir: str = 'data/uploads'
    # Snowflake (SQL API + Cortex REST): public listing history for the market price check. Off when unset.
    snowflake_account_url: str = ''
    snowflake_pat: str = ''
    snowflake_warehouse: str = 'COMPUTE_WH'
    snowflake_database: str = 'NICHE'
    snowflake_embed_model: str = 'snowflake-arctic-embed-l-v2.0'  # 1024-dim; separated near/far items best in tests
    snowflake_model: str = 'claude-sonnet-4-5'
    public_api_url: str = 'http://127.0.0.1:8000'
    nessie_api_key: str = ''
    # SpacetimeDB live state (blank URL disables publishing; the app still works by polling).
    spacetime_url: str = ''
    spacetime_db: str = 'niche'
    spacetime_token: str = ''
    # Cartesia: speech-to-text (ink-whisper) and the assistant's spoken replies (sonic). Blank turns voice off; the
    # key never leaves the backend.
    cartesia_api_key: str = Field(default='', validation_alias=AliasChoices(
        'NICHE_CARTESIA_API_KEY', 'CARTESIA_API_KEY', 'cartesia_api_key'))
    cartesia_base_url: str = 'https://api.cartesia.ai'
    cartesia_stt_model: str = 'ink-whisper'
    cartesia_tts_model: str = 'sonic-3'  # most natural-sounding; ~0.3s to first byte once warm
    cartesia_voice_id: str = 'e8e5fffb-252c-436d-b842-8879b84445b6'  # "Cathy - Coworker": casual, young adult
    # Moss semantic search over listings a shopper was already shown (taste/finds.py). Blank turns it off.
    moss_project_id: str = ''
    moss_project_key: str = ''
    moss_url: str = 'https://service.usemoss.dev'

    def validate_live(self):
        if self.sourcing_mode == 'live' and not (self.apify_token and self.anthropic_api_key):
            raise ValueError('Live mode requires APIFY_TOKEN and NICHE_ANTHROPIC_API_KEY (or ANTHROPIC_API_KEY)')
        if self.taste_mode == 'live' and not self.anthropic_api_key:
            raise ValueError('Live taste mode requires NICHE_ANTHROPIC_API_KEY (or ANTHROPIC_API_KEY)')
