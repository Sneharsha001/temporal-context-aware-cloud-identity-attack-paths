# Enterprise Cloud Identity & Temporal Reasoning Glossary

## Standard Terminology

- **Attack Path**: A directed chain of principal nodes, credential transitions, and action edges leading from an unprivileged entity to a crown jewel resource.
- **Blast Radius**: The transitive closure of all reachable nodes from a compromised identity under temporal session constraints.
- **Ephemeral Escalation**: An elevation of privilege that exists strictly during the lifetime of a temporary security token issued by AWS STS.
- **Permission Boundary**: An advanced AWS IAM feature that sets the maximum permissions an identity-based policy can grant to an IAM principal.
- **Temporal Horizon**: The maximum temporal window $[t_{start}, t_{end}]$ considered when evaluating sequential reachability over an identity graph.
- **Trust Relationship**: A policy statement embedded within an IAM role allowing designated external principals to assume the role.
