# ARF-RT Factor Graph Representation & Belief Propagation

## 1. Factor Graph Architecture
ARF-RT represents cloud identity attack topologies as bipartite factor graphs:
$$\mathcal{F} = (\mathcal{V}_{\text{var}}, \mathcal{V}_{\text{fac}}, \mathcal{E}_{\mathcal{F}})$$

- **Variable Nodes ($\mathcal{V}_{\text{var}}$):** Binary random variables $X_e \in \{0, 1\}$ representing edge traversal states.
- **Factor Nodes ($\mathcal{V}_{\text{fac}}$):** Joint probability functions representing policy constraints:
  - $\psi_{\text{prior}}(X_e)$: Initial prior probability from template observations.
  - $\psi_{\text{SCP}}(\mathbf{X}_c)$: Structural constraint factor forcing joint failure:
    $$\psi_{\text{SCP}}(\mathbf{X}_c) = \begin{cases} 1 & \text{if all } X_e = 0 \text{ under SCP deny} \\ 1 & \text{if SCP allows} \\ 0 & \text{contradictory assignment} \end{cases}$$

## 2. Message Passing & Belief Update
Messages from variable node $X_e$ to factor node $\psi_a$:
$$\mu_{X_e \to \psi_a}(x) = \prod_{b \in \text{ne}(X_e) \setminus \{a\}} \mu_{\psi_b \to X_e}(x)$$
Since tree-decompositions of SCP clusters form forest components, exact inference completes in linear time $O(|\mathcal{E}|)$.
