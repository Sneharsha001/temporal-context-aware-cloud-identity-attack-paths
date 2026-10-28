# SOC 2 Type II & ISO/IEC 27001:2022 Compliance Mapping

**Document Version:** 1.0.0  
**Scope:** Trust Services Criteria (Security, Availability) & ISO 27001 Annex A Controls  
**Assessment Target:** Identity & Access Governance, Credential Expiration, and Auditability  

---

## 1. SOC 2 Type II Trust Services Criteria (TSC) Mapping

| TSC Common Criteria | Criterion Summary | ARF-RT Temporal Control Realization | Audit Artifact |
|---|---|---|---|
| **CC6.1** | The entity implements logical access security software, infrastructure, and architectures over protected information assets. | Real-time temporal path evaluation verifies that no traversable privilege paths exist through expired or unauthorized identity boundaries. | `TemporalSummaryReporter` & `PolicyValidationResult` |
| **CC6.2** | Prior to issuing credentials, the entity registers and authorizes new internal and external users. | `SessionChainValidator` ensures chained role assumptions originate from verified initial principals with valid issuance timestamps. | `ChainValidationResult` JSON logs |
| **CC6.3** | The entity revokes access credentials when access is no longer required or upon termination. | `TemporalComplianceAuditor` automatically audits against CIS-1.3 (90-day stale key deactivation) and generates revocation playbooks. | `ComplianceAuditReport` & `RemediationAction` |
| **CC6.6** | The entity implements logical boundaries to protect data from unauthorized access. | Structural constraint grouping maps AWS SCP and permission boundary correlations, preventing unauthorized lateral movement. | Equivalence class collapse summaries |
| **CC7.2** | The entity monitors system components to detect anomalies and unauthorized logical access. | `CredentialAlertEngine` and `TemporalAnomalyFilter` emit structured alerts for impossible travel and abnormal velocity events. | `Alert` JSON stream & SIEM feed |

---

## 2. ISO/IEC 27001:2022 Control Mapping

| ISO 27001:2022 Control | Control Title | Implementation Guidance |
|---|---|---|
| **A.5.15** | Access control | Enforce least privilege and verify temporal freshness of role delegations. |
| **A.5.17** | Authentication information | Enforce mandatory rotation intervals and bound maximum STS session durations. |
| **A.5.18** | Access rights | Audit privilege graphs for dormant permissions and unused cross-account roles. |
| **A.8.15** | Logging | Log all path feasibility decisions and verification timestamps to tamper-evident JSONL audit trails. |
| **A.8.16** | Monitoring activities | Continuous monitoring of privilege window drift using `TemporalDriftDetector`. |
