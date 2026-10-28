# PCI-DSS v4.0 Requirement 7 & 8 Identity Control Mapping

## 1. Regulatory Context

Payment Card Industry Data Security Standard (PCI-DSS) v4.0 mandates strict access control, identity lifecycle management, and non-repudiation across Cardholder Data Environments (CDE).

## 2. Requirement Mapping Matrix

| PCI-DSS v4.0 Req | Requirement Description | ARF-RT Temporal Enforcement Mechanism |
| :--- | :--- | :--- |
| **7.2.1** | Access is defined for system components and resources based on need-to-know. | Continuous reachability analysis verifies minimum privilege access paths across AWS accounts. |
| **7.2.2** | Privileges are assigned based on job classification and function. | Automated detection of cross-boundary role assumptions violating baseline job profiles. |
| **7.2.5** | Application and system accounts and access privileges are reviewed at least once every six months. | Historical temporal snapshot reporting provides automated periodic access audit logs. |
| **8.3.6** | Passwords/passphrases are changed periodically if not using dynamic/temporary credentials. | Static IAM access key age tracking; automated flagging of long-lived access keys $>90$ days. |
| **8.6.2** | Passwords/passphrases for application and system accounts are protected against misuse. | Temporal token expiry analysis ensuring temporary STS credentials do not exceed required TTL. |
