# Enterprise SIEM & EventBridge Integration Guide

**Document Version:** 1.0.0  
**Scope:** SIEM Event Ingestion, AWS Security Hub Findings, and Amazon EventBridge Routing  
**Target Systems:** Splunk Enterprise, Datadog Cloud SIEM, Microsoft Sentinel, AWS Security Hub  

---

## 1. Overview

ARF-RT's temporal context engine evaluates privilege escalation risks, credential lifetimes, and session anomalies in AWS environments. To provide security operations centers (SOCs) with real-time detection and automated orchestration, ARF-RT alert artifacts and findings integrate directly into enterprise Security Information and Event Management (SIEM) systems and Amazon EventBridge buses.

This guide outlines the JSON schema representations, EventBridge rule patterns, and SIEM field mappings required to ingest ARF-RT temporal alerts into production monitoring pipelines.

---

## 2. Standard Alert Event Schema

All temporal alerts emitted by `arf_rt.temporal.credential_alert_engine` conform to the canonical event structure below:

```json
{
  "version": "1.0.0",
  "source": "arf-rt.temporal",
  "detail-type": "Credential Temporal Risk Alert",
  "time": "2026-10-28T12:00:00Z",
  "resources": [
    "arn:aws:iam::123456789012:role/ProductionDataPipelineRole"
  ],
  "detail": {
    "alert_id": "ALT-9281-CRIT",
    "edge_id": "RoleA->RoleB",
    "severity": "CRITICAL",
    "rule_name": "EXPIRED_CREDENTIAL_ACTIVE_PATH",
    "risk_score": 0.9420,
    "confidence_q": 850,
    "findings": [
      {
        "type": "SESSION_EXPIRY",
        "description": "STS session expired 3600s prior to downstream traversal",
        "timestamp": "2026-10-28T11:00:00Z"
      }
    ],
    "remediation": {
      "priority": 1,
      "action_type": "REVOKE_SESSION",
      "aws_cli": "aws iam put-role-policy --role-name ProductionDataPipelineRole --policy-name RevokeOldSessions --policy-document '{\"Version\":\"2012-10-17\",\"Statement\":[{\"Effect\":\"Deny\",\"Action\":\"*\",\"Resource\":\"*\"}]}'"
    }
  }
}
```

---

## 3. Amazon EventBridge Event Bus Architecture

When integrated with AWS native monitoring, ARF-RT publishes findings to a custom EventBridge event bus (`arn:aws:events:us-east-1:123456789012:event-bus/arf-rt-bus`).

### 3.1 Event Pattern Filtering

To route only `CRITICAL` and `HIGH` severity alerts to automated SOAR Lambdas or PagerDuty:

```json
{
  "source": ["arf-rt.temporal"],
  "detail-type": ["Credential Temporal Risk Alert"],
  "detail": {
    "severity": ["CRITICAL", "HIGH"]
  }
}
```

---

## 4. AWS Security Hub Finding Mapping (ASFF)

ARF-RT findings map to the AWS Security Finding Format (ASFF) v1.4:

| ASFF Field | ARF-RT Source Field | Example Value |
|---|---|---|
| `SchemaVersion` | Constant | `"2018-10-08"` |
| `Id` | `detail.alert_id` | `"arf-rt/us-east-1/ALT-9281-CRIT"` |
| `ProductArn` | Constant | `"arn:aws:securityhub:us-east-1:123456789012:product/custom/arf-rt"` |
| `GeneratorId` | `detail.rule_name` | `"EXPIRED_CREDENTIAL_ACTIVE_PATH"` |
| `Severity.Label` | `detail.severity` | `"CRITICAL"` |
| `Severity.Normalized`| `detail.risk_score * 100` | `94` |
| `Title` | Dynamic Summary | `"Critical Temporal Attack Path Viability Detected"` |
| `Compliance.Status` | Compliance Engine | `"FAILED"` |

---

## 5. Splunk Common Information Model (CIM) Mapping

For Splunk ingestion under the **Alerts** and **Authentication** data models:

- `src`: Origin IAM User or assumed role principal
- `dest`: Target AWS account ID or resource ARN
- `app`: `"ARF-RT"`
- `signature`: Rule name (`rule_name`)
- `severity`: Normalized to `informational`, `low`, `medium`, `high`, `critical`
- `action`: `"blocked"` or `"allowed"` depending on feasibility verdict
