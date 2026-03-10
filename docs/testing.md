# Testing Checklist

- Unit tests for each CrewAI agent/tool should live under `src/crewinsight/tests` and cover schema validation.
- Integration smoke: run a full crew pass with the Salesforce vs. HubSpot scenario and assert `/report/{run_id}` returns a `CrewReport`.
- Deployment smoke: GitHub Actions workflow (`.github/workflows/ci.yml`) provisions the Bicep stack, pushes Docker image, and calls `/research` to verify MCP tools respond.
