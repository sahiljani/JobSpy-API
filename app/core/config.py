from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    app_name: str = Field(default='jobspy-async-api', alias='APP_NAME')
    app_env: str = Field(default='development', alias='APP_ENV')
    app_host: str = Field(default='0.0.0.0', alias='APP_HOST')
    app_port: int = Field(default=8080, alias='APP_PORT')
    log_level: str = Field(default='INFO', alias='LOG_LEVEL')

    database_url: str = Field(alias='DATABASE_URL')
    redis_url: str = Field(default='redis://127.0.0.1:6379/1', alias='REDIS_URL')
    api_key: str = Field(default='change-me', alias='API_KEY')

    webhook_retry_seconds: str = Field(default='0,60,120,300,900,1800', alias='WEBHOOK_RETRY_SECONDS')

    max_search_terms: int = Field(default=25, alias='MAX_SEARCH_TERMS')
    max_sites: int = Field(default=5, alias='MAX_SITES')
    max_results_wanted: int = Field(default=50, alias='MAX_RESULTS_WANTED')
    max_proxies: int = Field(default=50, alias='MAX_PROXIES')
    max_hours_old: int = Field(default=720, alias='MAX_HOURS_OLD')

    default_results_wanted: int = Field(default=20, alias='DEFAULT_RESULTS_WANTED')
    default_hours_old: int = Field(default=48, alias='DEFAULT_HOURS_OLD')
    default_country_indeed: str = Field(default='Canada', alias='DEFAULT_COUNTRY_INDEED')
    default_progress_interval_seconds: int = Field(default=5, alias='DEFAULT_PROGRESS_INTERVAL_SECONDS')
    default_max_runtime_seconds: int = Field(default=1800, alias='DEFAULT_MAX_RUNTIME_SECONDS')

    celery_task_soft_time_limit: int = Field(default=1900, alias='CELERY_TASK_SOFT_TIME_LIMIT')
    celery_task_time_limit: int = Field(default=2000, alias='CELERY_TASK_TIME_LIMIT')

    @field_validator('webhook_retry_seconds')
    @classmethod
    def validate_retry_seconds(cls, value: str) -> str:
        parts = [p.strip() for p in value.split(',') if p.strip()]
        if not parts:
            raise ValueError('WEBHOOK_RETRY_SECONDS cannot be empty')
        for part in parts:
            if not part.isdigit():
                raise ValueError('WEBHOOK_RETRY_SECONDS must be comma-separated integers')
        return ','.join(parts)

    @property
    def webhook_retry_schedule(self) -> List[int]:
        return [int(p) for p in self.webhook_retry_seconds.split(',')]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
