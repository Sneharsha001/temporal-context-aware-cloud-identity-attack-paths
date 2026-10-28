# Proactive Threat Hunting & Anomaly Detection Playbooks

## 1. Objectives & Hunting Methodology

Proactive threat hunting in temporal cloud identity graphs shifts security operations from reactive alerting to hypothesis-driven discovery of stealthy lateral movement paths.

## 2. Temporal Threat Hunting Playbooks

### Playbook TH-01: Ephemeral Role Chaining Over Extended Intervals
- **Hypothesis**: An adversary assumes intermediate low-privilege roles at spaced intervals (e.g., 55 minutes apart) to stay under rate-limiting and session-duration detection thresholds.
- **Hunting Strategy**:
  - Filter graph for chains of length $\ge 3$ where each transition occurs near session expiry ($T_{exp} - 5\text{ min} \le t \le T_{exp}$).
  - Compute entropy of role session names.

### Playbook TH-02: Permission Boundary Drift & Shadow Admin Emergence
- **Hypothesis**: Temporary inline policies attached during maintenance windows were not detached due to automation failures, creating shadow admin paths.
- **Hunting Strategy**:
  - Query ARF-RT graph for entities whose effective privilege exceeds their baseline role profile by $> 40\%$ for longer than 4 hours.
