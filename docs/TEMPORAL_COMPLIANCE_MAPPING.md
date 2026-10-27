# Temporal Security Compliance & Framework Mapping Guide

**Document Version:** 1.0.0  
**Scope:** AWS Identity & Access Management (IAM), STS Session Chaining, and CloudTrail Replay  
**Applicable Standards:** CIS AWS Foundations Benchmark v3.0.0, NIST SP 800-53 Rev 5, SOC 2 Type II  

---

## 1. Executive Summary

Static cloud attack path engines often evaluate privilege escalation graphs under timeless assumptions: if an edge exists, it is presumed traversable indefinitely. In modern enterprise environments, access keys rotate, STS session tokens expire, and security standards mandate maximum allowable session lifetimes.

ARF-RT v0.8.0 introduces an automated **Temporal Compliance and Risk Aggregation Engine** (`arf_rt.temporal`) that continuously audits identity attack paths against recognized security baselines. This document details the formal mapping between temporal constraints, risk scoring algorithms, and industry compliance frameworks.

---

## 2. Regulatory & Framework Cross-Reference

| Framework Control | Description | Evaluated Temporal Attribute | ARF-RT Module | Default Enforcement Threshold |
|---|---|---|---|---|
| **CIS AWS 1.3** | Ensure credentials unused for 90 days are disabled | `TemporalHint.last_used` | `TemporalComplianceAuditor` | `max_rotation_days <= 90.0` |
| **CIS AWS 1.4** | Ensure access keys are rotated every 90 days | `TemporalHint.credential_issued` / `last_used` | `PolicyWindowValidator` | `max_rotation_age <= 7776000s` |
| **CIS AWS 1.16** | Ensure IAM role MaxSessionDuration is restricted | `credential_issued` to `credential_expiry` | `PolicyWindowValidator` | `max_session_duration <= 43200s` (12h) |
| **AWS Chaining Rule** | Enforce 1-hour cap on transitive role-chained sessions | Hop index $\ge 1$ in `AssumeRole` path | `SessionChainValidator` | `chain_duration <= 3600s` (1h) |
| **NIST AC-2** | Account Management & Inactive Credential Disabling | `TemporalHint.last_used` | `TemporalComplianceAuditor` | Inactivity $> 90$ days flags violation |
| **NIST IA-5** | Authenticator Management & Token Expiry | `TemporalHint.credential_expiry` | `PolicyWindowValidator` | Rejects expired tokens (`allow_expired=False`) |
| **NIST SC-10** | Network Disconnect & Session Termination | Active duration of session tokens | `TemporalComplianceAuditor` | Flags indefinite or unbonded sessions |

---

## 3. Mathematical Risk Formulations

### 3.1 Individual Edge Risk Scoring (`CredentialScorer`)

For an edge $e_i$, exploitation risk $R(e_i) \in [0.0, 1.0]$ is computed as:

$$R(e_i) = w_{\text{exp}} \cdot f_{\text{expiry}}(e_i) + w_{\text{stale}} \cdot f_{\text{staleness}}(e_i) + w_{\text{churn}} \cdot f_{\text{churn}}(e_i)$$

Where:
- $f_{\text{expiry}}$ measures proximity to token expiration ($1.0$ if already expired, decaying as remaining TTL grows).
- $f_{\text{staleness}}$ measures days since last IAM usage relative to rotation policy thresholds.
- $f_{\text{churn}}$ penalizes high-velocity ephemeral credentials that evade logging.

### 3.2 Path Risk Compounding (`TemporalRiskAggregator`)

For an attack path $\pi = (e_1, e_2, \dots, e_k)$:

1. **Bottleneck Strategy (Weakest Link):**
   $$\text{Score}_{\text{bottleneck}}(\pi) = \max_{i=1}^k R(e_i)$$
2. **Probabilistic Path Product:**
   $$\text{Score}_{\text{product}}(\pi) = 1 - \prod_{i=1}^k \big(1 - R(e_i)\big)$$
3. **Geometric Mean:**
   $$\text{Score}_{\text{geom}}(\pi) = \left(\prod_{i=1}^k \max(R(e_i), \varepsilon)\right)^{1/k}$$
4. **Weighted Target Proximity:**
   $$\text{Score}_{\text{weighted}}(\pi) = \frac{\sum_{i=1}^k i \cdot R(e_i)}{\sum_{i=1}^k i}$$

---

## 4. Role Chaining & Session Invariance Constraints

When an adversary chains `AssumeRole` hops ($A \to B \to C$):
1. **AWS 1-Hour Constraint:** Under AWS STS security architecture, role chaining automatically limits the maximum session duration of subsequent hops to 1 hour (3600 seconds), regardless of the role's IAM policy configuration. `SessionChainValidator` flags any path whose hop assumptions violate this physical runtime constraint.
2. **Causal Monotonicity:** Token issuance timestamps must satisfy:
   $$T_{\text{issued}}(e_{i+1}) \ge T_{\text{issued}}(e_i)$$
   Any backward timestamp progression indicates logging anomalies, replay attacks, or invalid traversal sequences.

---

## 5. Automated Remediation Playbooks (`TemporalRemediationPlanner`)

The remediation planner synthesizes compliance violations into concrete, prioritized AWS CLI remediation commands:

### Priority 1: Expired or Compromised Active Sessions
```bash
aws iam put-role-policy \
  --role-name <ROLE_NAME> \
  --policy-name RevokeOldSessions \
  --policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Deny","Action":"*","Resource":"*"}]}'
```

### Priority 2: Stale Inactive Credentials
```bash
aws iam update-access-key \
  --user-name <USER_NAME> \
  --access-key-id <ACCESS_KEY_ID> \
  --status Inactive
```

### Priority 3: Excessive Session Duration
```bash
aws iam update-role \
  --role-name <ROLE_NAME> \
  --max-session-duration 3600
```

---

## 6. Verification and Tooling Integration

Run the compliance audit and remediation playbooks across scenario files or CloudTrail logs:

```bash
# Compliance evaluation
python scripts/audit_temporal_compliance.py --input scenario.json --strict

# Remediation playbook generation
python scripts/generate_remediation_plan.py --input scenario.json --format shell --out remediate.sh
```
