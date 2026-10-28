# AWS CloudTrail Ingestion & High-Fidelity Configuration Guide

**Document Version:** 1.0.0  
**Scope:** Multi-Account CloudTrail Log Delivery, S3 Bucket Architecture, and ARF-RT Parsing  
**Audience:** Cloud Platform Engineers, Security Infrastructure Architects  

---

## 1. Overview

ARF-RT's temporal context engine uses AWS CloudTrail management events to extract temporal hints (`TemporalHint`), establish principal observation windows, and identify session issuance and expiration intervals. This guide details optimal CloudTrail configuration to maximize hint coverage without incurring unnecessary ingestion overhead.

---

## 2. Recommended CloudTrail Configuration

To support high-fidelity temporal analysis:

1. **Multi-Region Trail:** Enabled across all active AWS regions (`IncludeGlobalServiceEvents = true`).
2. **Organization Trail:** Deployed via AWS Organizations root to capture multi-account role assumptions (`sts:AssumeRole`, `sts:AssumeRoleWithSAML`, `sts:AssumeRoleWithWebIdentity`).
3. **Log File Validation:** Enabled (`EnableLogFileValidation = true`) to ensure tamper evidence.
4. **Target Events:**
   - Management Events (Read/Write)
   - STS API Calls (`AssumeRole*`, `GetCallerIdentity`, `GetSessionToken`)
   - IAM API Calls (`CreateAccessKey`, `UpdateAccessKey`, `DeleteAccessKey`, `GetCredentialReport`)

---

## 3. High-Value CloudTrail Fields for ARF-RT

The parser (`arf_rt.temporal.cloudtrail_parser`) targets the following JSON attributes:

| Event Attribute | Target TemporalHint Field | Extraction Logic |
|---|---|---|
| `eventTime` | `earliest_observed` / `latest_observed` | Tracks bounding window of principal activity |
| `serviceEventDetails.issuedAt` | `credential_issued` | STS token issuance timestamp |
| `serviceEventDetails.expiresAt` | `credential_expiry` | STS token hard expiration timestamp |
| `userIdentity.sessionContext.sessionIssuer.userName` | `edge_id` source | Maps IAM role assumption source |
| `requestParameters.roleArn` | `edge_id` destination | Maps IAM target role assumption |

---

## 4. Ingestion Workflow & Offline Replay

```
  [ AWS CloudTrail ] ───> [ Amazon S3 Logs ] ───> [ GZIP / JSON Export ] ───> [ ARF-RT Parser ] ───> [ Temporal Hints ]
```

Execute hint extraction via CLI:

```bash
python scripts/analyze_cloudtrail.py --log-file s3_cloudtrail_records.json --output hints.json
```
