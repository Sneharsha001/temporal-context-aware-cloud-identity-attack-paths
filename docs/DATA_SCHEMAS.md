# ARF-RT Scenario Schema Specification

## 1. Top-Level Structure
A valid ARF-RT scenario file is a UTF-8 encoded JSON object containing four primary collections:

```json
{
  "nodes": [...],
  "edges": [...],
  "constraints": [...],
  "objectives": [...]
}
```

## 2. Field Definitions

### Nodes (`NodeInput`)
Represents an identity entity in the cloud environment:
- `provider`: String, typically `"aws"`.
- `node_type`: Entity class, e.g. `"IAMUser"`, `"IAMRole"`, `"FederatedUser"`.
- `provider_id`: Canonical ARN or unique resource name.
- `region`: AWS region string, or `"-"` for global IAM resources.

### Edges (`EdgeInput`)
Represents a directed privilege transition:
- `source_node`: ARN of the initiating identity.
- `target_node`: ARN of the assumed identity or accessed resource.
- `action`: Specific IAM or STS action (e.g. `"sts:AssumeRole"`, `"iam:PassRole"`).
- `edge_id`: Unique deterministic hash identifying this transition.

### Objectives (`ObjectiveInput`)
Specifies the security analysis goal:
- `objective_type`: E.g. `"REACHABILITY"`.
- `start_nodes`: Array of initial attacker-controlled principals.
- `target_nodes`: Array of high-value asset roles/principals.
- `max_depth`: Maximum hop distance (default: 6).
- `k`: Number of Top-K candidate paths to compute (default: 5).
