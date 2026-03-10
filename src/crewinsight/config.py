from typing import Literal

from pydantic import BaseSettings, Field, HttpUrl


class Settings(BaseSettings):
    azure_openai_endpoint: str = Field(..., env="AZURE_OPENAI_ENDPOINT")
    azure_openai_api_key: str = Field(..., env="AZURE_OPENAI_API_KEY")
    azure_search_endpoint: str = Field(..., env="AZURE_SEARCH_ENDPOINT")
    azure_search_api_key: str = Field(..., env="AZURE_SEARCH_API_KEY")
    azure_search_index: str = Field(default="crewinsight-index")
    azure_region: Literal["eastus", "eastus2", "centralus"] = Field("eastus")
    crew_mcp_command: str | None = Field(None, env="CREW_MCP_COMMAND")
    crew_mcp_url: HttpUrl | None = Field(None, env="CREW_MCP_URL")
    container_app_name: str = Field("crewinsight", env="CONTAINER_APP_NAME")
    container_environment: str = Field("prod", env="CONTAINER_APP_ENV")
    report_cost_cap_usd: float = Field(5.0)
    telemetry_sample_rate: float = Field(1.0)

    class Config:
        env_file = ".env"
        model_config_schema = {
            "extra": "forbid",
        }


default_settings() -> Settings:
    return Settings()

settings = default_settings()
