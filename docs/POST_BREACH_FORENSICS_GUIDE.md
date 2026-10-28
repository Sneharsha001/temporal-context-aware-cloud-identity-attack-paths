# Post-Breach Temporal Forensics & Blast-Radius Reconstruction

## 1. Executive Summary

When an IAM identity compromise occurs in a complex multi-account AWS environment, static log analysis fails to determine whether ephemeral privilege escalations or temporal role-assumption windows were leveraged by the threat actor.

The ARF-RT Temporal Engine provides deterministic historical state reconstruction, mapping precise blast radiuses and identifying dormant backdoors.

## 2. Forensic Investigation Workflow

```mermaid
flowchart TD
    Compromise[1. Compromised Identity Identified] --> TimeWindow[2. Define Temporal Incident Window t0 -> t1]
    TimeWindow --> IngestEvents[3. Ingest CloudTrail & IAM Delta Logs]
    IngestEvents --> ReplayState[4. ARF-RT Deterministic State Replay]
    ReplayState --> ReachabilityAnalysis[5. Reconstruct Lateral & Temporal Reachability Graph]
    ReachabilityAnalysis --> BlastRadiusReport[6. Generate Forensic Blast-Radius & Remediation Artifacts]
```

## 3. Key Investigation Metrics

- **Maximum Escalation Horizon ($H_{max}$)**: The furthest privilege level reachable from the compromised entity during active session TTLs.
- **Cross-Account Blast Vector**: Identification of all trust relationships traversed via `sts:AssumeRole`.
- **Dormant Access Key Inception**: Detection of secondary credentials minted during temporary elevation windows.
