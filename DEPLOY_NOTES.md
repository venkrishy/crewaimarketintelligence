# Deploy Notes

Operational notes for running CrewInsight in production on Azure Container Apps.

---

## Overriding Rate Limits at Runtime

Rate limits can be changed without a code redeploy — just update the container's environment variables:

```bash
az containerapp update -n crewinsight-prod-app -g rg-riskscout \
    --set-env-vars "RATE_LIMIT_PER_IP=10/hour" "RATE_LIMIT_GLOBAL_DAILY=100"
```

The per-IP format follows slowapi syntax: `5/hour`, `10/minute`, `100/day` all work.

The container restarts automatically and picks up the new values. Active in-flight requests complete before the restart.

---

## Provisioning Storage for Rate Limiting

The `infra/storage.bicep` module creates the Azure Storage Account and `ratelimits` table automatically as part of the standard Bicep deployment. No manual setup required.

To check current daily request count:

```bash
az storage entity query \
    --account-name <storage-account-name> \
    --table-name ratelimits \
    --filter "PartitionKey eq 'rl' and RowKey eq 'global:$(date -u +%Y%m%d)'"
```

---

## Scaling Notes

Rate limit counters live in Azure Table Storage — shared across all replicas. The Container App can scale up to 5 replicas (`maxReplicas: 5` in `container-app.bicep`) without diverging counters.

If Table Storage is unreachable, both rate limit checks pass through (permissive degradation). The API stays available but limits are temporarily unenforced.
