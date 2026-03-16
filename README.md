# crewinsight

- This is an AI Agentic solution written using CrewAI and deployed in Azure.  
- It is a competitive market intelligence crew that orchestrates research, analysis, strategy, and reporting via a FastAPI front end and Azure-backed tooling.  
- Four specialized CrewAI agents collaborate sequentially to produce a structured competitive intelligence brief.
(1) Researcher, 
(2) Analyst, 
(3) Strategist, and 
(4) Report Writer 
- The frontend for this can be seen at [Crew Insight (theaiguru.dev) ](https://crew-insight.theaiguru.dev/).  

To test it out through the frontend, either click on the sample research targets like "SalesForce" and "CRM" or provide your own values in the company and market segment.  

## Related to:
This is similar to the AI Agent `riskscout`: both are production-ready agentic systems and both are deployed on Azure Container Apps, they share FastAPI + telemetry best practices, and demonstrate multi-agent orchestration, observability, and deployment automation.

## Highlights
- CrewAI `Process.sequential` flow with explicit context passing through Research, Analyst, Strategist, and Report Writer agents.
- Typed report schema (executive summary, competitor profiles, SWOT, strategic recommendations, sources, metadata) validated via Pydantic.
- Azure OpenAI + Azure AI Search RAG tool, resilient telemetry callbacks sent to Application Insights.
- Bicep templates for Container Apps, OpenAI, Search, Log Analytics, and Application Insights with GitHub Actions deployment.
- MCP server (Hugging Face-style or CrewAI-native) documented and integrated to surface crew tools.

## Quickstart
```bash
git clone <repo>
cd crewinsight
python -m pip install -e .
cp .env.example .env
# populate Azure credentials (OpenAI endpoint/key, Search endpoint/key, Container App resource group, MCP config)
uvicorn crewinsight.api.main:app --reload
```

## Architecture Diagram
```
[Input] -> FastAPI /research -> CrewAI Process
   ├─ Research Agent (Azure AI Search / web scraping) → research output
   ├─ Analyst Agent (Python tooling) → SWOT
   ├─ Strategist Agent (reasoning) → recommendations
   └─ Report Writer (Markdown + Pydantic) -> final report
Telemetry -> Application Insights; Metrics -> /metrics endpoint; Deployment -> Azure Container Apps
```


