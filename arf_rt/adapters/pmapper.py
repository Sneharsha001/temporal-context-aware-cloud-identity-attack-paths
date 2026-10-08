"""PMapper graph → ARF-RT nodes and edges.

Accepts PMapper graph data in two formats:

1. Consolidated JSON (recommended for portability):
   {
     "metadata": {"account_id": "123456789012", "pmapper_version": "1.2.0"},
     "nodes": [{"arn": "arn:aws:iam::123:role/R", "is_admin": false, ...}],
     "edges": [{"source": "arn:...", "destination": "arn:...", "reason": "...", ...}]
   }

2. PMapper on-disk directory (from `pmapper graph create`):
   graph_dir/
     metadata.json
     graph.json   (contains nodes, edges, policies, groups)

This module handles 12A: graph translation only.
Constraint resolution (12B) is in aws_org.py and trust_policy_parser.py.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from arf_rt.adapters.arn import (
    ARNComponents,
    arn_to_node_type,
    arn_to_provider_id,
    arn_to_region,
    parse_arn,
)
from arf_rt.adapters.reason_parser import ParsedReason, parse_reason
from arf_rt.util.canon import ARFValidationError, region_norm

logger = logging.getLogger(__name__)


# ===================================================================
# Input models (PMapper format, not ARF-RT format)
# ===================================================================


class PMapperNode(BaseModel):
    """A node from PMapper's graph export."""

    arn: str
    id_value: str = ""
    is_admin: bool = False
    # Trust policy is optional — only roles have it
    trust_policy: dict | None = None
    # Permissions boundary ARN, if set
    permissions_boundary: str | dict | None = None
    # Instance profile ARN(s)
    instance_profile: list[str] | None = None
    # We don't enforce extra=forbid here — PMapper nodes have many fields we don't use
    model_config = ConfigDict(extra="allow")


class PMapperEdge(BaseModel):
    """An edge from PMapper's graph export."""

    source: str       # source ARN
    destination: str   # destination ARN
    reason: str        # human-readable reason
    short_reason: str = ""  # sometimes present
    model_config = ConfigDict(extra="allow")


class PMapperGraph(BaseModel):
    """Top-level PMapper graph structure."""

    metadata: dict = {}
    nodes: list[PMapperNode]
    edges: list[PMapperEdge]
    model_config = ConfigDict(extra="allow")


# ===================================================================
# Translation result
# ===================================================================


class TranslatedGraph:
    """Result of translating a PMapper graph to ARF-RT format.

    Contains nodes, edges, and metadata for building an ARF-RT scenario.
    Trust policies are preserved for later constraint extraction (12B).
    """

    def __init__(
        self,
        nodes: list[dict],
        edges: list[dict],
        trust_policies: dict[str, dict],
        admin_arns: set[str],
        warnings: list[str],
        account_id: str,
    ):
        self.nodes = nodes
        self.edges = edges
        self.trust_policies = trust_policies  # arn → trust policy doc
        self.admin_arns = admin_arns
        self.warnings = warnings
        self.account_id = account_id

    @property
    def node_count(self) -> int:
        return len(self.nodes)

    @property
    def edge_count(self) -> int:
        return len(self.edges)

    @property
    def action_summary(self) -> dict[str, int]:
        """Count edges by action type."""
        counts: dict[str, int] = {}
        for e in self.edges:
            action = e["features"].get("action", "UNKNOWN")
            counts[action] = counts.get(action, 0) + 1
        return dict(sorted(counts.items()))


# ===================================================================
# Loader
# ===================================================================


def load_pmapper_graph(source: str | Path) -> PMapperGraph:
    """Load PMapper graph from file or directory.

    Args:
        source: Path to consolidated JSON file, or PMapper graph directory.

    Returns:
        PMapperGraph with nodes and edges.

    Raises:
        ARFValidationError: If the format is unrecognized.
    """
    source = Path(source)

    if source.is_dir():
        return _load_from_directory(source)
    elif source.is_file() and source.suffix == ".json":
        return _load_from_json(source)
    else:
        raise ARFValidationError(
            f"PMapper source must be a JSON file or directory: {source}"
        )


def _load_from_json(path: Path) -> PMapperGraph:
    """Load from consolidated JSON format."""
    with open(path) as f:
        data = json.load(f)

    if "nodes" not in data or "edges" not in data:
        raise ARFValidationError(
            f"PMapper JSON must contain 'nodes' and 'edges' keys. "
            f"Found: {list(data.keys())}"
        )

    return PMapperGraph(**data)


def _load_from_directory(path: Path) -> PMapperGraph:
    """Load from PMapper on-disk directory format.

    PMapper stores graph data in two possible layouts:

    Layout 1 (real PMapper `pmapper graph create`):
        <account_id>/
            metadata.json
            graph/
                nodes.json
                edges.json
                groups.json
                policies.json

    Layout 2 (simplified):
        <dir>/
            metadata.json or graph.json
    """
    metadata = {}
    nodes = []
    edges = []

    # Try metadata.json
    meta_path = path / "metadata.json"
    if meta_path.exists():
        with open(meta_path) as f:
            metadata = json.load(f)

    # Layout 1: graph/ subdirectory with separate nodes.json + edges.json
    graph_dir = path / "graph"
    if graph_dir.is_dir():
        nodes_path = graph_dir / "nodes.json"
        edges_path = graph_dir / "edges.json"
        if nodes_path.exists():
            with open(nodes_path) as f:
                raw_nodes = json.load(f)
            nodes = [PMapperNode(**n) for n in raw_nodes]
        if edges_path.exists():
            with open(edges_path) as f:
                raw_edges = json.load(f)
            edges = [PMapperEdge(**e) for e in raw_edges]
        if nodes:
            return PMapperGraph(metadata=metadata, nodes=nodes, edges=edges)

    # Layout 2: single graph.json
    graph_path = path / "graph.json"
    if graph_path.exists():
        with open(graph_path) as f:
            data = json.load(f)
        if "nodes" in data:
            nodes = [PMapperNode(**n) for n in data["nodes"]]
        if "edges" in data:
            edges = [PMapperEdge(**e) for e in data["edges"]]
        if "metadata" in data:
            metadata.update(data["metadata"])
        return PMapperGraph(metadata=metadata, nodes=nodes, edges=edges)

    raise ARFValidationError(
        f"PMapper directory must contain graph/nodes.json or graph.json: {path}"
    )


# ===================================================================
# Translation
# ===================================================================


def translate_pmapper_graph(graph: PMapperGraph) -> TranslatedGraph:
    """Translate PMapper graph into ARF-RT node/edge format.

    Translation rules:
        Node ARN → ARF-RT node:
            provider = "aws"
            node_type = mapped from ARN service/resource type
            provider_id = ARN (full, for uniqueness across accounts)
            region = from ARN, "-" for global

        Edge → ARF-RT edge:
            edge_type = action extracted from reason string
            src/dst = node references by provider_id (ARN)
            features = {action, mechanism, pmapper_reason, confidence}

    Args:
        graph: Parsed PMapper graph.

    Returns:
        TranslatedGraph with ARF-RT format nodes, edges, and metadata.
    """
    warnings: list[str] = []
    trust_policies: dict[str, dict] = {}
    admin_arns: set[str] = set()

    # Track which ARNs we've seen as nodes
    known_arns: set[str] = set()

    # --- Translate nodes ---
    arf_nodes: list[dict] = []
    for pnode in graph.nodes:
        try:
            arn_c = parse_arn(pnode.arn)
        except ARFValidationError as e:
            warnings.append(f"Skipping node with invalid ARN: {pnode.arn} ({e})")
            continue

        node = {
            "provider": "aws",
            "node_type": arn_to_node_type(pnode.arn),
            "provider_id": pnode.arn,
            "region": arn_to_region(pnode.arn),
        }
        arf_nodes.append(node)
        known_arns.add(pnode.arn)

        # Preserve trust policy for 12B
        if pnode.trust_policy:
            trust_policies[pnode.arn] = pnode.trust_policy

        # Track admins
        if pnode.is_admin:
            admin_arns.add(pnode.arn)

    # --- Translate edges ---
    arf_edges: list[dict] = []
    for pedge in graph.edges:
        # Validate source/destination exist
        if pedge.source not in known_arns:
            warnings.append(
                f"Edge source ARN not in nodes, auto-creating: {pedge.source}"
            )
            _auto_create_node(pedge.source, arf_nodes, known_arns)
        if pedge.destination not in known_arns:
            warnings.append(
                f"Edge destination ARN not in nodes, auto-creating: {pedge.destination}"
            )
            _auto_create_node(pedge.destination, arf_nodes, known_arns)

        # Parse reason string
        parsed = parse_reason(pedge.reason)

        # Determine region (use source node's region)
        src_region = arn_to_region(pedge.source)
        dst_region = arn_to_region(pedge.destination)
        edge_region = src_region if src_region != "-" else dst_region

        edge = {
            "edge_type": parsed.action,
            "src": {
                "provider": "aws",
                "node_type": arn_to_node_type(pedge.source),
                "provider_id": pedge.source,
                "region": arn_to_region(pedge.source),
            },
            "dst": {
                "provider": "aws",
                "node_type": arn_to_node_type(pedge.destination),
                "provider_id": pedge.destination,
                "region": arn_to_region(pedge.destination),
            },
            "region": edge_region,
            "features": {
                "action": parsed.action,
                "mechanism": parsed.mechanism,
                "pmapper_reason": pedge.reason,
                "confidence": parsed.confidence,
            },
        }
        arf_edges.append(edge)

        if parsed.confidence == "LOW":
            warnings.append(
                f"Low-confidence action parse for edge "
                f"{pedge.source} → {pedge.destination}: {pedge.reason}"
            )

    # Extract account_id from metadata or first node
    account_id = graph.metadata.get("account_id", "")
    if not account_id and graph.nodes:
        try:
            account_id = parse_arn(graph.nodes[0].arn).account_id
        except ARFValidationError:
            pass

    return TranslatedGraph(
        nodes=arf_nodes,
        edges=arf_edges,
        trust_policies=trust_policies,
        admin_arns=admin_arns,
        warnings=warnings,
        account_id=account_id,
    )


def _auto_create_node(
    arn: str, nodes: list[dict], known: set[str]
) -> None:
    """Auto-create a node for an ARN referenced by an edge but not in the node list."""
    if arn in known:
        return
    try:
        node = {
            "provider": "aws",
            "node_type": arn_to_node_type(arn),
            "provider_id": arn,
            "region": arn_to_region(arn),
        }
        nodes.append(node)
        known.add(arn)
    except ARFValidationError:
        pass


def translate_from_file(source: str | Path) -> TranslatedGraph:
    """Convenience: load + translate in one call."""
    graph = load_pmapper_graph(source)
    return translate_pmapper_graph(graph)
