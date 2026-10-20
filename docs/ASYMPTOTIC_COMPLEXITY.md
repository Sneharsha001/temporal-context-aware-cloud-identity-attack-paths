# Asymptotic Complexity Bounds for ARF-RT Core Algorithms

## 1. Disjoint-Set Union-Find (Correlation Grouping)
- **Time Complexity:** $O(|\mathcal{E}| \cdot \alpha(|\mathcal{V}|))$, where $\alpha$ is the inverse Ackermann function ($\alpha(n) \le 4$ for all practical universe sizes).
- **Space Complexity:** $O(|\mathcal{V}|)$ words for parent and rank arrays.

## 2. Best-First Top-K Search with Pruning
- **Priority Queue Operations:** Using a binary min-heap, extracting the optimal candidate path requires $O(\log K)$ time.
- **Worst-Case Search Time:** $O(K \cdot |\mathcal{E}| \log |\mathcal{V}|)$.
- **Pruning Bound ($p_{\text{worst}}$):** Branches with cumulative traversability probability strictly lower than the current $K$-th best path bound are pruned immediately without expanding descendants.
