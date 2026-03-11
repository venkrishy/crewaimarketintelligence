from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    azure_openai_endpoint: str = Field(..., alias="AZURE_OPENAI_ENDPOINT")
    azure_openai_api_key: str = Field(..., alias="AZURE_OPENAI_API_KEY")
    azure_search_endpoint: str = Field(..., alias="AZURE_SEARCH_ENDPOINT")
    azure_search_api_key: str = Field(..., alias="AZURE_SEARCH_API_KEY")
    azure_search_index: str = Field(default="crewinsight-index")
    azure_region: Literal["eastus", "eastus2", "centralus"] = Field("eastus")
    crew_mcp_command: str | None = Field(None)
    crew_mcp_url: str | None = Field(None)
    container_app_name: str = Field("crewinsight")
    container_environment: str = Field("prod")
    report_cost_cap_usd: float = Field(5.0)
    telemetry_sample_rate: float = Field(1.0)

    model_config = {"env_file": ".env", "populate_by_name": True}


def default_settings() -> Settings:
    return Settings()


settings = default_settings()
