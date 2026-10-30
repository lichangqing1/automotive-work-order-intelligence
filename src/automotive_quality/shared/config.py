from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Automotive Quality Platform"
    environment: str = "local"
    database_url: str = "postgresql+psycopg://automotive:automotive@localhost:5432/automotive"
    redis_url: str = "redis://localhost:6379/0"
    llm_provider: str = "mock"
    llm_model: str = "default"
    openai_api_key: str | None = None
    retrieval_top_k: int = 5
    log_level: str = "INFO"
    issue_tracker: str = "local"
    jira_base_url: str | None = None
    jira_email: str | None = None
    jira_api_token: str | None = None
    jira_project_key: str = "QA"
    jira_review_issue_type: str = "Task"
    jira_bug_issue_type: str = "Bug"
    jira_approved_statuses: str = "Approved,Done"
    jira_rejected_statuses: str = "Rejected"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
