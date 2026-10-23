# Temporal Anomaly Classification and Operational Triage Guide

**Document Version:** 1.0  
**Scope:** ARF-RT Temporal Post-Filter & Anomaly Detection Subsystem  
**Date:** 2026-10-23  

---

## 1. Overview

The ARF-RT temporal module evaluates multi-hop cloud identity attack paths against empirical event streams (e.g. AWS CloudTrail). When an attack path fails temporal validation or exhibits anomalous execution windows, the `AnomalyClassifier` categorizes the incident into standardized severity tiers and assigns remediation actions.

---

## 2. Severity Classification Matrix

| Severity | Anomaly ID | Finding Title | Threat Scenario | Default Triage SLA |
|---|---|---|---|---|
| **CRITICAL** | `TC-2` | Expired Credential Usage | Path relies on assumed-role tokens used after STS expiry. | 15 minutes |
| **CRITICAL** | `TC-5` | Impossible Session Concurrency | Identical session credentials used simultaneously across disjoint geographic regions. | 15 minutes |
| **CRITICAL** | `WIN-CONCURRENCY` | Overlapping Session Execution | Disjoint actors executing under identical STS session identities concurrently. | 30 minutes |
| **HIGH** | `TC-1` | Causal Order Inversion | Action observed prior to credential issuance; possible replay or clock manipulation. | 1 hour |
| **HIGH** | `TC-3` | Super-Velocity Hopping | Hop traversal elapsed time is below network/API velocity physical floor. | 2 hours |
| **HIGH** | `WIN-BURST` | Credential Burst Activity | High-frequency AssumeRole calls indicative of automated reconnaissance. | 2 hours |
| **HIGH** | `WIN-REUSE` | Cross-Account Credential Reuse | Credential assumed in Account A and immediately reused in untrusted Account B. | 4 hours |
| **MEDIUM** | `TC-4` | Dormant Credential Resuscitation | IAM user key or role assumed after >90 days of total inactivity. | 24 hours |
| **LOW** | `WIN-GENERIC` | Minor Timing Anomaly | Subtle jitter or sequence variance within permissible tolerance windows. | Next sprint review |

---

## 3. Incident Response Playbooks

### Playbook CRIT-1: Expired Credential Usage (`TC-2`)
1. **Immediate Revocation:** Issue an inline Deny policy on the target role with `aws:CurrentTime` conditions or invoke `RevokeOlderSessions`.
2. **Session Identification:** Extract the `AssumedRoleUser.Arn` and `SessionName` from the corresponding `TemporalHint`.
3. **Forensic Trace:** Query CloudTrail Lake for all API events bearing the compromise session token:
   ```sql
   SELECT eventTime, eventName, requestParameters, responseElements
   FROM cloudtrail_lake
   WHERE userIdentity.sessionContext.sessionIssuer.arn = '<ROLE_ARN>'
     AND eventTime > '<EXPIRY_TIMESTAMP>'
   ```

### Playbook CRIT-2: Impossible Session Concurrency (`TC-5`)
1. **Geographic Cross-Reference:** Compare the `sourceIPAddress` and `awsRegion` of concurrent calls in CloudTrail.
2. **Access Key Invalidation:** If an IAM user generated the session, deactivate the primary IAM Access Key.
3. **Network Isolation:** Verify whether the source IP belongs to an authorized corporate egress CIDR.

---

## 4. Integration with SIEM / SOAR

Exported verdicts from `TemporalAuditLog` can be ingested into Splunk, Microsoft Sentinel, or Elastic SIEM via JSONL logs produced by `scripts/filter_paths_temporal.py`:
```bash
python scripts/filter_paths_temporal.py \
  --paths candidate_paths.json \
  --cloudtrail records.json \
  --out-json verified_paths.json \
  --out-csv metrics_summary.csv
```
