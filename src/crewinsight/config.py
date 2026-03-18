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
    finnhub_api_key: str = Field("", alias="FINNHUB_API_KEY")

    # Azure Table Storage (rate limiting)
    azure_storage_account_name: str = Field("", alias="AZURE_STORAGE_ACCOUNT_NAME")
    azure_storage_account_key: str = Field("", alias="AZURE_STORAGE_ACCOUNT_KEY")

    # Rate limits
    # Per-IP format: "<count>/hour" — only the count is used; window is always 1 hour.
    rate_limit_per_ip: str = Field("5/hour", alias="RATE_LIMIT_PER_IP")
    rate_limit_global_daily: int = Field(50, alias="RATE_LIMIT_GLOBAL_DAILY")

    @property
    def rate_limit_per_ip_count(self) -> int:
        """Extract the numeric count from e.g. '5/hour'."""
        try:
            return int(self.rate_limit_per_ip.split("/")[0])
        except (ValueError, IndexError):
            return 5

    model_config = {"env_file": ".env", "populate_by_name": True}


def default_settings() -> Settings:
    return Settings()


settings = default_settings()
