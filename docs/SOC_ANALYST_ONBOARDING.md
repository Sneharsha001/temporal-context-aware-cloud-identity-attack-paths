# Security Operations Center (SOC) Analyst Onboarding & Triage Tutorial

## 1. Welcome to Temporal Attack Path Analysis

As a SOC Tier 1/2/3 analyst, working with temporal identity graphs requires understanding that privileges are non-static: they fluctuate based on active sessions, schedule-based automation, and ephemeral STS credentials.

## 2. Five-Minute Triage Checklist

When an alert fires from ARF-RT:
1. **Check Severity & Confidence**: High-severity paths with confidence $>0.85$ indicate immediate privilege escalation risk.
2. **Review the Path Visualization**: Note intermediate hops and trust boundary transitions.
3. **Inspect Active Session Expiration**: Determine remaining window ($t_{now} \to t_{exp}$) before auto-mitigation or session termination.
4. **Execute Quick Isolation**: If confirmed malicious, invoke `aws iam put-user-policy` or revoke active sessions via STS revocation list.
