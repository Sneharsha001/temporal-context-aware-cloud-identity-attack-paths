# ARF-RT Mathematical Foundations

## 1. Probabilistic Attack Path Representation

Let $\mathcal{G} = (\mathcal{V}, \mathcal{E})$ be the directed privilege graph where vertices $\mathcal{V}$ represent cloud identities (IAM users, roles) and edges $\mathcal{E}$ represent potential privilege transitions.

Each edge $e \in \mathcal{E}$ is associated with a binary latent variable $X_e \in \{0, 1\}$ denoting whether the transition is traversable ($X_e = 1$) or impassable ($X_e = 0$).

A candidate attack path $\pi = (e_1, e_2, \dots, e_k)$ is viable if and only if:
$$X_\pi = \prod_{i=1}^k X_{e_i} = 1$$

## 2. Structural Correlation & Component Partitioning

Let $\mathcal{C}$ be the set of policy constraints (e.g. SCPs, trust policies). Each constraint $c \in \mathcal{C}$ covers a subset of edges $\mathcal{E}_c \subseteq \mathcal{E}$.
If edges $e_i, e_j \in \mathcal{E}_c$ depend on the same constraint, their traversal indicators are conditionally dependent:
$$P(X_{e_i} = 0 \mid X_{e_j} = 0) > P(X_{e_i} = 0)$$

ARF-RT identifies equivalence classes using Disjoint-Set Union (Union-Find) and binds representative edges to eliminate overcounting.

## 3. Expected Information Gain (EIG)

Let $\mathcal{P} = \{\pi_1, \pi_2, \dots, \pi_M\}$ be the candidate Top-K attack paths. The Shannon entropy over path distributions is:
$$H(\mathcal{P}) = - \sum_{\pi \in \mathcal{P}} P(\pi) \ln P(\pi)$$

The Residual Information Gain (RIG) given observation outcome $o \in \{\text{allow}, \text{deny}\}$ for candidate edge probe $e$ is:
$$\text{RIG}(e, o) = H(\mathcal{P}) - H(\mathcal{P} \mid X_e = o)$$

The Expected Information Gain (EIG) is the expected value of RIG across both outcomes:
$$\text{EIG}(e) = P(X_e = 1) \cdot \text{RIG}(e, \text{allow}) + P(X_e = 0) \cdot \text{RIG}(e, \text{deny})$$
Optimal probe selection chooses:
$$e^* = \arg\max_{e \in \mathcal{E}_{\text{candidate}}} \text{EIG}(e)$$
