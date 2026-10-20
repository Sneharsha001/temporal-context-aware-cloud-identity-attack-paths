# Case Study: Cross-Account OIDC/SAML Federation Compromise

## Threat Context
Cloud organizations frequently establish trust boundaries via external Identity Providers (IdP) using OpenID Connect (OIDC) or SAML 2.0 assertions. Misconfigured audience keys (`aud`) or missing subject (`sub`) claims can permit unauthorized lateral access across accounts.

## ARF-RT Evaluation
- **Trust Condition Factor:** Modeled `sts:AssumeRoleWithWebIdentity` transitions with condition constraints on token issuer and claims.
- **Topological Discovery:** Identified an unmonitored lateral escalation hop from a GitHub Actions workflow role into a staging administrative role.
- **EIG Recommendation:** Suggested a single non-destructive probe validating the token thumbprint, collapsing uncertainty over 8 candidate paths in a single evaluation.
