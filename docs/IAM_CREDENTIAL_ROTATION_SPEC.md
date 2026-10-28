# Enterprise IAM Credential Lifecycle & Rotation Specification

**Document Version:** 1.0.0  
**Domain:** Identity Governance, Credential Hygiene, and Organizational Security Policy  
**Applies To:** AWS IAM Users, Access Keys, STS Assumed Roles, and Service Principals  

---

## 1. Scope and Objective

This specification establishes organizational baselines for credential lifecycles, maximum session durations, and automated rotation schedules. Adherence to these thresholds is verified programmatically by ARF-RT's `PolicyWindowValidator` and `TemporalComplianceAuditor`.

---

## 2. Policy Threshold Matrix

| Credential Class | Metric | Standard Threshold | Permissible Exception | Verification Mechanism |
|---|---|---|---|---|
| **Human IAM User Access Key** | Maximum Age | 90 days (7,776,000s) | None | `PolicyConfig.max_rotation_age_seconds` |
| **Service Principal Key** | Maximum Age | 45 days (3,888,000s) | CI/CD Pipeline (60d) | `PolicyConfig.max_rotation_age_seconds` |
| **Console Password** | Inactivity Expiry | 45 days | None | AWS IAM Credential Report |
| **STS Role Session (Direct)** | Max Session Duration | 1 hour (3,600s) | Break-glass admin (4h) | `PolicyConfig.max_session_duration_seconds` |
| **STS Role Session (Chained)**| Max Chained Duration | 1 hour (3,600s) | None (AWS enforced) | `SessionChainValidator` |
| **Remaining TTL Floor** | Minimum Usable TTL | 5 minutes (300s) | None | `PolicyConfig.min_validity_window_seconds` |

---

## 3. Credential Lifecycle States

```
  [ ISSUED ] ────> [ ACTIVE ] ────> [ ROTATION_DUE ] ────> [ STALE ] ────> [ DEACTIVATED ] ────> [ DELETED ]
     │                                     │                   │
     └── (Immediate Revocation) ───────────┴───────────────────┴────> [ REVOKED ]
```

1. **ACTIVE:** Credential age $< 60$ days. Normal traversal permitted.
2. **ROTATION_DUE:** Credential age between $60$ and $90$ days. Warning alerts dispatched to owner.
3. **STALE:** Credential age $\ge 90$ days without rotation or last-used event. Treated as high-risk by `CredentialScorer` (staleness factor $= 1.0$).
4. **DEACTIVATED:** Access key status set to `Inactive`. Path traversal blocked.
5. **REVOKED:** Immediate session revocation via inline deny policy.
