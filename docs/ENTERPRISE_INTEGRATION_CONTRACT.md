# Enterprise Integration Contract: REST, CLI, and Webhooks

## 1. Overview

The ARF-RT Temporal Engine exposes strongly-typed API endpoints, event schemas, and CLI contracts for seamless SIEM, SOAR, and ticketing integration.

## 2. API Endpoints

### `POST /v1/temporal/graph/query`
Executes temporal reachability query across graph state at timestamp $t$.

**Request Body**:
```json
{
  "source_principal_arn": "arn:aws:iam::123456789012:user/developer-ci",
  "target_action": "iam:PassRole",
  "target_resource_arn": "arn:aws:iam::123456789012:role/ProductionEKSAdmin",
  "timestamp": "2026-10-28T12:00:00Z"
}
```

**Response Body**:
```json
{
  "reachable": true,
  "confidence_score": 0.94,
  "temporal_window": {
    "valid_from": "2026-10-28T11:45:00Z",
    "valid_until": "2026-10-28T12:45:00Z"
  },
  "shortest_path_hops": [
    "arn:aws:iam::123456789012:user/developer-ci",
    "arn:aws:iam::123456789012:role/StagingDeployer",
    "arn:aws:iam::123456789012:role/ProductionEKSAdmin"
  ]
}
```
