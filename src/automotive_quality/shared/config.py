from __future__ import annotations

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Automotive Quality Platform"
    environment: str = "local"
    database_url: str = "postgresql+psycopg://automotive:automotive@localhost:5432/automotive"
    redis_url: str = "redis://localhost:6379/0"
    rate_limit_namespace: str = "automotive-quality"
    rate_limit_window_seconds: int = 60
    rate_limit_ai_requests: int = 10
    rate_limit_jira_requests: int = 10
    rate_limit_mutation_requests: int = 30
    rate_limit_read_requests: int = 120
    rate_limit_read_fail_open: bool = True
    ai_concurrency_per_principal: int = 2
    ai_concurrency_lease_seconds: int = 180
    max_request_body_bytes: int = 1_048_576
    api_trusted_hosts: str = "localhost,127.0.0.1,testserver"
    api_cors_origins: str = ""
    api_cors_allow_credentials: bool = False
    api_docs_enabled: bool = True
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
    api_auth_principals_json: str | None = None

    @model_validator(mode="after")
    def require_shared_environment_authentication(self) -> Settings:
        if self.environment.lower() in {"shared", "staging", "production"} and not self.api_auth_principals_json:
            raise ValueError("API authentication configuration is required in shared environments")
        positive_controls = {
            "rate_limit_window_seconds": self.rate_limit_window_seconds,
            "rate_limit_ai_requests": self.rate_limit_ai_requests,
            "rate_limit_jira_requests": self.rate_limit_jira_requests,
            "rate_limit_mutation_requests": self.rate_limit_mutation_requests,
            "rate_limit_read_requests": self.rate_limit_read_requests,
            "ai_concurrency_per_principal": self.ai_concurrency_per_principal,
            "ai_concurrency_lease_seconds": self.ai_concurrency_lease_seconds,
            "max_request_body_bytes": self.max_request_body_bytes,
        }
        if not self.rate_limit_namespace.strip() or any(value <= 0 for value in positive_controls.values()):
            raise ValueError("Rate-limit and concurrency settings must be positive and namespaced")
        trusted_hosts = {item.strip() for item in self.api_trusted_hosts.split(",") if item.strip()}
        cors_origins = {item.strip() for item in self.api_cors_origins.split(",") if item.strip()}
        if not trusted_hosts:
            raise ValueError("At least one trusted API host is required")
        if self.api_cors_allow_credentials and "*" in cors_origins:
            raise ValueError("Credentialed CORS cannot use a wildcard origin")
        if self.environment.lower() in {"shared", "staging", "production"}:
            if "*" in trusted_hosts:
                raise ValueError("Wildcard trusted hosts are forbidden in shared environments")
            if self.api_docs_enabled:
                raise ValueError("Interactive API documentation must be disabled in shared environments")
            if self.rate_limit_read_fail_open:
                raise ValueError("Read rate limiting must fail closed in shared environments")
        return self

    @property
    def trusted_hosts(self) -> list[str]:
        return [item.strip() for item in self.api_trusted_hosts.split(",") if item.strip()]

    @property
    def cors_origins(self) -> list[str]:
        return [item.strip() for item in self.api_cors_origins.split(",") if item.strip()]

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
