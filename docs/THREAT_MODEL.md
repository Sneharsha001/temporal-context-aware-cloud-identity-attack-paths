# ARF-RT Threat Model & Security Posture

## 1. Adversary Capabilities & Classes

ARF-RT analyzes cloud environments under four distinct adversary profile tiers:

### Tier 1: Compromised Identity (Initial Access)
- The attacker holds valid AWS long-term credentials or a temporary STS token for a specific IAM user or role.
- Attacker lacks administrative permissions but can query IAM or call sts:GetCallerIdentity.

### Tier 2: Network-Constrained Adversary
- Operates outside corporate VPN or authorized transit VPC CIDRs.
- Affected by IP condition keys (`aws:SourceIp`, `aws:VpcSourceIp`).
- Must route through bastion hosts or proxy instances to achieve context feasibility.

### Tier 3: Unauthenticated / Non-MFA Attacker
- Possesses static access keys without hardware or virtual MFA device possession.
- Blocked by policy statements requiring `aws:MultiFactorAuthPresent == "true"`.

### Tier 4: Lateral Mover & Escalator
- Actively attempts privilege escalation via `iam:PassRole`, `sts:AssumeRole`, or lambda execution triggers.

## 2. Ingestion Defense & Safety Boundaries
- **Replay Safety Boundary:** ARF-RT only parses structured JSON artifacts; it never initiates network requests or calls AWS STS/IAM endpoints directly.
- **Untrusted Input Sanitation:** Pydantic models with `extra="forbid"` prevent attribute injection or state pollution.
