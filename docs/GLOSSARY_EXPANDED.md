# ARF-RT Research Glossary & Terminology

### 1. Bayesian Reasoning Concepts
- **Prior Probability ($P(e)$):** The initial estimated likelihood that an attacker can traverse a privilege edge $e$ without additional live probing.
- **Posterior Probability ($P(e \mid o)$):** The updated probability of edge traversability after observing probe result $o \in \{0, 1\}$.
- **Residual Information Gain (RIG):** The reduction in Shannon entropy conditioned on an allow or deny observation.
- **Expected Information Gain (EIG):** The probability-weighted sum of RIG outcomes across all possible probe results.

### 2. AWS IAM & Identity Semantics
- **Principal:** An IAM user, role, federated session, or service identity capable of performing authenticated actions.
- **Service Control Policy (SCP):** Organization-level policy guardrail that restricts maximum available permissions across an account hierarchy.
- **Permission Boundary:** An advanced IAM policy construct that sets the maximum allowable permissions an identity can possess.
- **Role Assumption Boundary:** The hop transitioning from an originating principal to an assumed IAM role target.

### 3. CCPF Context Constraints
- **Context Conditioned Path Feasibility (CCPF):** Formal pre-filtering framework that evaluates runtime constraints on candidate paths.
- **Witness:** A formal certificate or counterexample demonstrating why a constraint evaluated to `INFEASIBLE`.
- **Passive Audit Mode:** Operating mode where CCPF evaluates paths and logs verdicts without pruning or altering search ranking.
