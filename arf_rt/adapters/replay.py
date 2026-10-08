"""ReplayAdapter: ingest ScenarioInput into SQLite (spec §18).

Ingest order (spec §18):
  1. nodes        — resolve node_ids deterministically
  2. templates    — create/lookup templates, compute features_fp + template_id
  3. edges        — resolve src/dst node refs, link to template, compute edge_id
  4. constraints  — compute constraint_id, insert
  5. edge_constraints — resolve edge/constraint refs, insert links
  6. objectives   — resolve node refs, sort lists, compute objective_id
  7. observations — resolve edge refs, validate, insert with warnings

Key behaviors:
  - Node references can be node_id (str) or tuple dict {provider, node_type, provider_id, region}
  - strength=DIRECT without evidence_hash → downgrade to INFERRED + warning (spec §18.4)
  - constraint_relevant defaults to 0 if missing (spec §18.5)
  - All IDs are deterministic via canon.py functions
"""

from __future__ import annotations

import sqlite3
from typing import Any

from arf_rt.config import DEFAULT_ALPHA_I, DEFAULT_BETA_I
from arf_rt.models.core import (
    ConstraintInput,
    EdgeConstraintInput,
    EdgeInput,
    NodeInput,
    ObjectiveInput,
    ObservationInput,
    ScenarioInput,
    TemplateInput,
)
from arf_rt.models.enums import ObservationStrength
from arf_rt.storage.sqlite_store import transaction
from arf_rt.util.canon import (
    ARFValidationError,
    canonical_json,
    features_fp as compute_features_fp,
    make_constraint_id,
    make_constraint_key,
    make_edge_id,
    make_flags_json,
    make_node_id,
    make_objective_id,
    make_template_id,
    make_template_key,
    properties_fp as compute_properties_fp,
    region_norm,
)


class ReplayAdapter:
    """Ingests a validated ScenarioInput into a SQLite DB.

    Usage:
        conn = sqlite_store.connect(db_path)
        adapter = ReplayAdapter(conn)
        warnings = adapter.ingest(scenario)
    """

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        # Lookup caches populated during ingest
        self._node_map: dict[str, str] = {}  # (cache key) → node_id
        self._edge_map: dict[str, str] = {}  # (cache key) → edge_id
        self._edge_id_index: dict[str, str] = {}  # edge_id → edge_id
        self._edge_prefix_indexes: dict[int, dict[str, str | None]] = {}
        self._edge_struct_index: dict[tuple[str, str, str, str], str] = {}
        self._constraint_map: dict[str, str] = {}  # (cache key) → constraint_id
        self._template_cache: dict[str, str] = {}  # template_id → template_id
        self._warnings: list[dict[str, Any]] = []
        self._edge_ref_scan_fallbacks = 0

    def ingest(self, scenario: ScenarioInput) -> list[dict[str, Any]]:
        """Ingest a full scenario into the DB.

        Returns list of warning dicts [{code, severity, message, context}, ...]
        """
        self._warnings = []

        with transaction(self._conn) as tx:
            self._ingest_nodes(scenario.nodes, tx)
            self._ingest_templates(scenario.templates or [], tx)
            self._ingest_edges(scenario.edges, tx)
            self._ingest_constraints(scenario.constraints or [], tx)
            self._ingest_edge_constraints(scenario.edge_constraints or [], tx)
            self._ingest_objectives(scenario.objectives, tx)
            self._ingest_observations(scenario.observations or [], tx)
            self._flush_warnings(tx)

        return self._warnings

    # ------------------------------------------------------------------
    # Nodes
    # ------------------------------------------------------------------

    def _ingest_nodes(
        self, nodes: list[NodeInput], tx: sqlite3.Connection
    ) -> None:
        for node in nodes:
            r = node.region  # already normalized by Pydantic validator
            node_id = make_node_id(node.provider, node.node_type, node.provider_id, r)

            props_json = canonical_json(node.properties or {})

            tx.execute(
                """INSERT OR IGNORE INTO nodes
                   (node_id, provider, node_type, provider_id, region,
                    display_name, properties_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    node_id,
                    node.provider,
                    node.node_type,
                    node.provider_id,
                    r,
                    node.display_name,
                    props_json,
                ),
            )

            # Cache for reference resolution
            cache_key = self._node_cache_key(
                node.provider, node.node_type, node.provider_id, r
            )
            self._node_map[cache_key] = node_id
            self._node_map[node_id] = node_id  # direct ID lookup

    def _resolve_node_ref(self, ref: str | dict) -> str:
        """Resolve a node reference to a node_id."""
        if isinstance(ref, str):
            # Direct node_id
            if ref in self._node_map:
                return self._node_map[ref]
            raise ARFValidationError(f"Unknown node_id reference: {ref!r}")

        if isinstance(ref, dict):
            r = region_norm(ref.get("region"))
            cache_key = self._node_cache_key(
                ref["provider"], ref["node_type"], ref["provider_id"], r
            )
            if cache_key in self._node_map:
                return self._node_map[cache_key]
            # Try computing the ID directly
            node_id = make_node_id(
                ref["provider"], ref["node_type"], ref["provider_id"], r
            )
            if node_id in self._node_map:
                return node_id
            raise ARFValidationError(
                f"Cannot resolve node reference: {ref!r}"
            )

        raise ARFValidationError(
            f"Node reference must be str or dict, got {type(ref).__name__}"
        )

    @staticmethod
    def _node_cache_key(
        provider: str, node_type: str, provider_id: str, region: str
    ) -> str:
        return f"{provider}|{node_type}|{provider_id}|{region}"

    # ------------------------------------------------------------------
    # Templates
    # ------------------------------------------------------------------

    def _ingest_templates(
        self, templates: list[TemplateInput], tx: sqlite3.Connection
    ) -> None:
        for tpl in templates:
            self._ensure_template(
                tpl.provider,
                tpl.edge_type,
                tpl.features,
                tpl.feature_schema_version,
                tpl.alpha_agg_i,
                tpl.beta_agg_i,
                tx,
            )

    def _ensure_template(
        self,
        provider: str,
        edge_type: str,
        features: dict,
        feature_schema_version: int,
        alpha_agg_i: int,
        beta_agg_i: int,
        tx: sqlite3.Connection,
    ) -> str:
        """Create or lookup a template. Returns template_id."""
        feat_fp = compute_features_fp(features)
        template_id = make_template_id(
            provider, edge_type, feat_fp, feature_schema_version
        )

        if template_id in self._template_cache:
            return template_id

        template_key = make_template_key(provider, edge_type, feat_fp)
        features_json = canonical_json(features)

        tx.execute(
            """INSERT OR IGNORE INTO templates
               (template_id, template_key, provider, edge_type,
                features_json, features_fp, feature_schema_version,
                alpha_agg_i, beta_agg_i, sample_count,
                base_alpha_agg_i, base_beta_agg_i, base_sample_count)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, 0)""",
            (
                template_id,
                template_key,
                provider,
                edge_type,
                features_json,
                feat_fp,
                feature_schema_version,
                alpha_agg_i,
                beta_agg_i,
                alpha_agg_i,
                beta_agg_i,
            ),
        )

        self._template_cache[template_id] = template_id
        return template_id

    # ------------------------------------------------------------------
    # Edges
    # ------------------------------------------------------------------

    def _ingest_edges(
        self, edges: list[EdgeInput], tx: sqlite3.Connection
    ) -> None:
        for edge in edges:
            src_node_id = self._resolve_node_ref(edge.src)
            dst_node_id = self._resolve_node_ref(edge.dst)

            features = edge.features or {}
            r = edge.region  # already normalized

            # Auto-create template from edge features
            template_id = self._ensure_template(
                provider=self._get_edge_provider(src_node_id, tx),
                edge_type=edge.edge_type,
                features=features,
                feature_schema_version=1,
                alpha_agg_i=DEFAULT_ALPHA_I,
                beta_agg_i=DEFAULT_BETA_I,
                tx=tx,
            )

            feat_fp = compute_features_fp(features)
            edge_id = make_edge_id(
                edge.edge_type, src_node_id, dst_node_id, r, template_id
            )

            flags_json = make_flags_json(prior_only=True)
            features_json = canonical_json(features)

            tx.execute(
                """INSERT OR IGNORE INTO edges
                   (edge_id, edge_type, src_node_id, dst_node_id, region,
                    template_id, alpha_i, beta_i, status, frozen,
                    flags_json, features_json, features_fp,
                    base_alpha_i, base_beta_i, base_status, base_frozen,
                    base_flags_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    edge_id,
                    edge.edge_type,
                    src_node_id,
                    dst_node_id,
                    r,
                    template_id,
                    edge.alpha_i,
                    edge.beta_i,
                    edge.status,
                    1 if edge.frozen else 0,
                    flags_json,
                    features_json,
                    feat_fp,
                    edge.alpha_i,
                    edge.beta_i,
                    edge.status,
                    1 if edge.frozen else 0,
                    flags_json,
                ),
            )

            # Cache for reference resolution
            self._index_edge_id(edge_id)
            # Also cache by src+dst+type for edge_ref resolution
            edge_cache = f"{edge.edge_type}|{src_node_id}|{dst_node_id}|{r}|{template_id}"
            self._edge_map[edge_cache] = edge_id
            self._index_edge_struct_ref(edge.edge_type, src_node_id, dst_node_id, r, edge_id)

    def _index_edge_id(self, edge_id: str) -> None:
        """Index an edge_id for exact and on-demand prefix lookup."""
        self._edge_map[edge_id] = edge_id
        self._edge_id_index[edge_id] = edge_id
        self._edge_prefix_indexes.clear()

    def _index_edge_struct_ref(
        self,
        edge_type: str,
        src_node_id: str,
        dst_node_id: str,
        region: str,
        edge_id: str,
    ) -> None:
        """Index the first edge for the structured ref fields used by fixtures."""
        key = self._edge_struct_key(edge_type, src_node_id, dst_node_id, region)
        self._edge_struct_index.setdefault(key, edge_id)

    @staticmethod
    def _edge_struct_key(
        edge_type: str, src_node_id: str, dst_node_id: str, region: str
    ) -> tuple[str, str, str, str]:
        return (edge_type, src_node_id, dst_node_id, region)

    def _get_edge_provider(
        self, node_id: str, tx: sqlite3.Connection
    ) -> str:
        """Get the provider for a node (for auto-template creation)."""
        row = tx.execute(
            "SELECT provider FROM nodes WHERE node_id = ?", (node_id,)
        ).fetchone()
        if row is None:
            raise ARFValidationError(f"Node {node_id} not found in DB")
        return row["provider"]

    def _resolve_edge_ref(self, ref: str | dict) -> str:
        """Resolve an edge reference to an edge_id."""
        if isinstance(ref, str):
            if ref in self._edge_id_index:
                return self._edge_id_index[ref]
            if ref in self._edge_map:
                return self._edge_map[ref]
            if len(ref) < 64:
                match = self._resolve_edge_prefix(ref)
                if match is not None:
                    return match
            raise ARFValidationError(f"Unknown edge_id reference: {ref!r}")

        if isinstance(ref, dict):
            if "edge_id" in ref:
                return self._resolve_edge_ref(ref["edge_id"])

            # Edge ref by component fields: resolve src/dst then look up
            src_id = self._resolve_node_ref(ref.get("src", ref.get("src_node_id", "")))
            dst_id = self._resolve_node_ref(ref.get("dst", ref.get("dst_node_id", "")))
            edge_type = ref.get("edge_type", "")
            r = region_norm(ref.get("region"))
            key = self._edge_struct_key(edge_type, src_id, dst_id, r)
            if key in self._edge_struct_index:
                return self._edge_struct_index[key]

            fallback = self._scan_edge_map_for_struct_ref(edge_type, src_id, dst_id, r)
            if fallback is not None:
                return fallback

            raise ARFValidationError(
                f"Cannot resolve edge reference: {ref!r}"
            )

        raise ARFValidationError(
            f"Edge reference must be str or dict, got {type(ref).__name__}"
        )

    def _resolve_edge_prefix(self, prefix: str) -> str | None:
        """Resolve a unique edge_id prefix without scanning per observation."""
        prefix_len = len(prefix)
        prefix_index = self._edge_prefix_indexes.get(prefix_len)
        if prefix_index is None:
            prefix_index = {}
            for edge_id in self._edge_id_index:
                candidate = edge_id[:prefix_len]
                if candidate not in prefix_index:
                    prefix_index[candidate] = edge_id
                elif prefix_index[candidate] != edge_id:
                    prefix_index[candidate] = None
            self._edge_prefix_indexes[prefix_len] = prefix_index

        if prefix not in prefix_index:
            return None
        edge_id = prefix_index[prefix]
        if edge_id is None:
            raise ARFValidationError(f"Ambiguous edge_id prefix: {prefix!r}")
        return edge_id

    def _scan_edge_map_for_struct_ref(
        self, edge_type: str, src_id: str, dst_id: str, region: str
    ) -> str | None:
        """Legacy fallback for non-indexed structured edge refs."""
        self._edge_ref_scan_fallbacks += 1
        prefix = f"{edge_type}|{src_id}|{dst_id}|{region}|"
        for cache_key, edge_id in self._edge_map.items():
            if cache_key.startswith(prefix):
                return edge_id
        return None

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------

    def _ingest_constraints(
        self, constraints: list[ConstraintInput], tx: sqlite3.Connection
    ) -> None:
        for cst in constraints:
            r = cst.region  # already normalized
            props = cst.properties or {}
            prop_fp = compute_properties_fp(props)

            constraint_id = make_constraint_id(
                cst.provider, cst.constraint_type,
                cst.scope_type, cst.scope_id, r, prop_fp,
            )

            constraint_key = make_constraint_key(
                cst.provider, cst.constraint_type,
                cst.scope_type, cst.scope_id, r, prop_fp,
            )

            props_json = canonical_json(props)

            tx.execute(
                """INSERT OR IGNORE INTO constraints
                   (constraint_id, constraint_key, provider, constraint_type,
                    scope_type, scope_id, region, properties_json,
                    properties_fp, status, validation_status, confidence_q)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    constraint_id,
                    constraint_key,
                    cst.provider,
                    cst.constraint_type,
                    cst.scope_type,
                    cst.scope_id,
                    r,
                    props_json,
                    prop_fp,
                    cst.status,
                    cst.validation_status,
                    cst.confidence_q,
                ),
            )

            # Cache
            self._constraint_map[constraint_id] = constraint_id
            cache_key = (
                f"{cst.provider}|{cst.constraint_type}|"
                f"{cst.scope_type}|{cst.scope_id}|{r}|{prop_fp}"
            )
            self._constraint_map[cache_key] = constraint_id

    def _resolve_constraint_ref(self, ref: str | dict) -> str:
        """Resolve a constraint reference to a constraint_id."""
        if isinstance(ref, str):
            if ref in self._constraint_map:
                return self._constraint_map[ref]
            raise ARFValidationError(
                f"Unknown constraint_id reference: {ref!r}"
            )

        if isinstance(ref, dict):
            r = region_norm(ref.get("region"))
            props = ref.get("properties", {})
            prop_fp = compute_properties_fp(props)
            cache_key = (
                f"{ref['provider']}|{ref['constraint_type']}|"
                f"{ref['scope_type']}|{ref['scope_id']}|{r}|{prop_fp}"
            )
            if cache_key in self._constraint_map:
                return self._constraint_map[cache_key]

            constraint_id = make_constraint_id(
                ref["provider"], ref["constraint_type"],
                ref["scope_type"], ref["scope_id"], r, prop_fp,
            )
            if constraint_id in self._constraint_map:
                return constraint_id

            raise ARFValidationError(
                f"Cannot resolve constraint reference: {ref!r}"
            )

        raise ARFValidationError(
            f"Constraint reference must be str or dict, got {type(ref).__name__}"
        )

    # ------------------------------------------------------------------
    # Edge–Constraint links
    # ------------------------------------------------------------------

    def _ingest_edge_constraints(
        self,
        edge_constraints: list[EdgeConstraintInput],
        tx: sqlite3.Connection,
    ) -> None:
        for ec in edge_constraints:
            edge_id = self._resolve_edge_ref(ec.edge_ref)
            constraint_id = self._resolve_constraint_ref(ec.constraint_ref)

            tx.execute(
                """INSERT OR IGNORE INTO edge_constraints
                   (edge_id, constraint_id, relation_type)
                   VALUES (?, ?, ?)""",
                (edge_id, constraint_id, ec.relation_type),
            )

    # ------------------------------------------------------------------
    # Objectives
    # ------------------------------------------------------------------

    def _ingest_objectives(
        self, objectives: list[ObjectiveInput], tx: sqlite3.Connection
    ) -> None:
        for obj in objectives:
            start_ids = sorted(
                self._resolve_node_ref(r) for r in obj.start_nodes
            )
            target_ids = sorted(
                self._resolve_node_ref(r) for r in obj.target_nodes
            )

            objective_id = make_objective_id(
                obj.objective_type, start_ids, target_ids,
                obj.max_depth, obj.k,
            )

            start_json = canonical_json(start_ids)
            target_json = canonical_json(target_ids)

            tx.execute(
                """INSERT OR IGNORE INTO objectives
                   (objective_id, objective_type, start_nodes_json,
                    target_nodes_json, max_depth, k)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    objective_id,
                    obj.objective_type,
                    start_json,
                    target_json,
                    obj.max_depth,
                    obj.k,
                ),
            )

    # ------------------------------------------------------------------
    # Observations
    # ------------------------------------------------------------------

    def _ingest_observations(
        self, observations: list[ObservationInput], tx: sqlite3.Connection
    ) -> None:
        for obs in observations:
            edge_id = self._resolve_edge_ref(obs.edge_ref)
            strength = obs.strength
            evidence_hash = obs.evidence_hash

            # Spec §18.4: DIRECT without evidence_hash → INFERRED + warning
            if (
                strength == ObservationStrength.DIRECT
                and evidence_hash is None
            ):
                strength = ObservationStrength.INFERRED
                self._add_warning(
                    code="DOWNGRADED_DIRECT_NO_EVIDENCE",
                    severity="WARN",
                    message=(
                        f"Observation on edge {edge_id} had strength=DIRECT "
                        f"but no evidence_hash; downgraded to INFERRED"
                    ),
                    context={"edge_id": edge_id},
                )

            tx.execute(
                """INSERT INTO observations
                   (edge_id, probe_type, result, reason_class, strength,
                    signal_q, is_counterfactual, constraint_relevant,
                    evidence_hash, observed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    edge_id,
                    obs.probe_type,
                    obs.result,
                    obs.reason_class,
                    str(strength),
                    obs.signal_q,
                    1 if obs.is_counterfactual else 0,
                    1 if obs.constraint_relevant else 0,
                    evidence_hash,
                    obs.observed_at,
                ),
            )

    # ------------------------------------------------------------------
    # Warnings
    # ------------------------------------------------------------------

    def _add_warning(
        self,
        code: str,
        severity: str = "WARN",
        message: str = "",
        context: dict | None = None,
    ) -> None:
        self._warnings.append({
            "code": code,
            "severity": severity,
            "message": message,
            "context": context or {},
        })

    def _flush_warnings(self, tx: sqlite3.Connection) -> None:
        """Write all accumulated warnings to run_warnings table."""
        for w in self._warnings:
            ctx_json = canonical_json(w["context"])
            tx.execute(
                """INSERT INTO run_warnings
                   (code, severity, message, context_json)
                   VALUES (?, ?, ?, ?)""",
                (w["code"], w["severity"], w["message"], ctx_json),
            )
