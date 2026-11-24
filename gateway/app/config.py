from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env.runtime", extra="ignore")
    flagsmith_api_url: str = "http://localhost:8000/api/v1/"
    flagsmith_server_key: str = ""
    flagsmith_master_api_key: str = ""
    flagsmith_project_id: int = 0
    flagsmith_env_key: str = ""
    flagsmith_quarantine_segment_id: int = 0
    flagsmith_health_webhook_url: str = ""
    upstream_mcp_url: str = "http://localhost:8090/mcp"
    upstream_llm_url: str = "http://localhost:8091/v1/chat/completions"
    upstream_llm_api_key: str = ""
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ]
    max_document_age_seconds: int = 30
