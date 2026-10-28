# Temporal Identity Threat Model & Attack Vector Taxonomy

**Document Version:** 1.0.0  
**Scope:** Identity-Based Attacks, Time-Window Evasion, and Token Chaining Tactics  
**Classification:** TTP Taxonomy (MITRE ATT&CK for Cloud Alignment)  

---

## 1. Introduction

Adversaries targeting cloud infrastructure increasingly exploit the temporal characteristics of authentication mechanisms. Static analysis misses these attacks because individual permission edges appear legitimate. This taxonomy categorizes the primary temporal attack vectors modeled and detected by ARF-RT.

---

## 2. Threat Vector Categories

### T-101: Session Lifetime Stretching (TTL Extension)
- **MITRE ATT&CK Mapping:** T1078.004 (Valid Accounts: Cloud Accounts)
- **Description:** An attacker compromises a short-lived role session, but before expiration, repeatedly invokes `sts:AssumeRole` on secondary roles configured with high `MaxSessionDuration` (up to 43,200s / 12 hours).
- **Temporal Signature:** Exponential divergence between initial token issued timestamp and subsequent chained hop expiration times.
- **ARF-RT Detection:** `SessionChainValidator` flags chains violating the AWS 1-hour chained duration rule and computes session expansion factors.

### T-102: Post-Expiration Replay & Token Zombie Paths
- **MITRE ATT&CK Mapping:** T1550.001 (Use Alternate Authentication Material: Application Access Token)
- **Description:** Execution of multi-hop attack paths relying on cached or leaked STS session tokens whose validity has expired according to server timestamp metadata.
- **Temporal Signature:** Request timestamp $T_{\text{event}} > T_{\text{expiry}}$.
- **ARF-RT Detection:** `TemporalEvaluator` TC-2 constraint check returns deterministic `INFEASIBLE` verdict.

### T-103: Impossible Travel / Velocity Inversion
- **MITRE ATT&CK Mapping:** T1078 (Valid Accounts)
- **Description:** Consecutive privilege escalation hops occurring within intervals below minimum human or network latency thresholds across distinct geographical AWS regions.
- **Temporal Signature:** $\Delta T_{\text{hop}} < 1.0\text{s}$ across multi-region API endpoints.
- **ARF-RT Detection:** `TemporalEvaluator` TC-3 minimum velocity constraint and `TemporalAnomalyFilter` z-score outlier detection.

### T-104: Dormant Principal Reactivation (Stale Credential Hijacking)
- **MITRE ATT&CK Mapping:** T1098 (Account Manipulation)
- **Description:** Exploitation of long-unused IAM user access keys or inactive service roles that have evaded automated rotation cycles (> 90 days of inactivity).
- **Temporal Signature:** $T_{\text{now}} - T_{\text{last\_used}} > 90 \text{ days}$.
- **ARF-RT Detection:** `TemporalComplianceAuditor` (CIS 1.3/NIST AC-2) and `CredentialScorer` staleness factor weighting.

### T-105: Transitive Chaining Depth Overflow
- **MITRE ATT&CK Mapping:** T1548 (Abuse Elevation Control Mechanism)
- **Description:** Constructing deeply nested AssumeRole delegation chains to obfuscate provenance and exhaust investigative depth budgets in SOC audit logs.
- **Temporal Signature:** Chain depth $K \ge 5$ across distinct trust domains.
- **ARF-RT Detection:** `SessionChainValidator` max chain depth bounds enforcement.
