# Case Study: Enterprise Multi-Account Cloud Identity Defense

## Scenario Background
An enterprise AWS organization consisting of 4 member accounts (Security, Production, Staging, Shared Services) with 14 IAM principals and 16 privilege edges was audited for lateral movement vulnerabilities.

## The Blindspot of Naive Analysis
Standard graph tools reported an attack path probability of **55%**, assuming 4 sequential assume-role transitions each with 74% individual likelihood ($0.74^4 \approx 0.30$, combined paths ~55%).

## The ARF-RT Solution
1. **Structural Correlation:** Identified that all 4 edges traversed accounts subject to a common organization SCP restricting external IP addresses.
2. **Information Update:** A single passive audit or probe observing `DENY` immediately collapsed path probability from 55% to **1.2%** (a 46x reduction).
3. **Outcome:** Prevented hundreds of hours of false positive remediation by prioritizing genuine unconstrained pathways.
