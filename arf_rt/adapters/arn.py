"""AWS ARN parser and component extraction.

ARN format: arn:partition:service:region:account-id:resource-type/resource-id
             arn:partition:service:region:account-id:resource-type:resource-id

Examples:
    arn:aws:iam::123456789012:role/MyRole
    arn:aws:iam::123456789012:user/admin
    arn:aws:sts::123456789012:assumed-role/MyRole/session
    arn:aws:lambda:us-east-1:123456789012:function:my-func
    arn:aws:s3:::my-bucket
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from arf_rt.util.canon import ARFValidationError


@dataclass(frozen=True)
class ARNComponents:
    """Parsed components of an AWS ARN."""

    partition: str       # aws, aws-cn, aws-us-gov
    service: str         # iam, sts, s3, lambda, ec2, ...
    region: str          # us-east-1, "" for global services
    account_id: str      # 12-digit account ID, "" for some services
    resource_type: str   # role, user, function, instance, ...
    resource_id: str     # the actual resource name/path
    raw: str             # original ARN string


# Regex for standard ARN format
_ARN_PATTERN = re.compile(
    r"^arn:([a-z\-]+):([a-z0-9\-]+):([a-z0-9\-]*):(\d*):(.+)$"
)


def parse_arn(arn: str) -> ARNComponents:
    """Parse an AWS ARN into its components.

    Handles both colon-separated and slash-separated resource types:
        arn:aws:iam::123456789012:role/MyRole       → type=role, id=MyRole
        arn:aws:lambda:us-east-1:123:function:func  → type=function, id=func

    Args:
        arn: Full AWS ARN string.

    Returns:
        ARNComponents with all fields populated.

    Raises:
        ARFValidationError: If the ARN doesn't match expected format.
    """
    m = _ARN_PATTERN.match(arn)
    if not m:
        raise ARFValidationError(f"Invalid ARN format: {arn}")

    partition, service, region, account_id, resource = m.groups()

    # Parse resource: could be "type/id", "type:id", or just "id"
    if "/" in resource:
        # arn:aws:iam::123:role/MyRole
        # arn:aws:iam::123:role/path/to/MyRole (IAM paths)
        parts = resource.split("/", 1)
        resource_type = parts[0]
        resource_id = parts[1]
    elif ":" in resource:
        # arn:aws:lambda:us-east-1:123:function:my-func
        parts = resource.split(":", 1)
        resource_type = parts[0]
        resource_id = parts[1]
    else:
        # arn:aws:s3:::my-bucket (resource with no type prefix)
        resource_type = ""
        resource_id = resource

    return ARNComponents(
        partition=partition,
        service=service,
        region=region,
        account_id=account_id,
        resource_type=resource_type,
        resource_id=resource_id,
        raw=arn,
    )


def extract_account_id(arn: str) -> str:
    """Extract the 12-digit account ID from an ARN.

    Returns empty string for ARNs without account IDs (e.g., S3 buckets).
    """
    return parse_arn(arn).account_id


def arn_to_node_type(arn: str) -> str:
    """Map an ARN to an ARF-RT node_type.

    Mapping:
        iam:role     → IAMRole
        iam:user     → IAMUser
        iam:group    → IAMGroup
        sts:*        → IAMRole (assumed roles are still roles)
        lambda:*     → LambdaFunction
        ec2:instance → EC2Instance
        s3:*         → S3Bucket
        (other)      → service:resource_type
    """
    c = parse_arn(arn)

    _TYPE_MAP = {
        ("iam", "role"): "IAMRole",
        ("iam", "user"): "IAMUser",
        ("iam", "group"): "IAMGroup",
        ("iam", "policy"): "IAMPolicy",
        ("iam", "instance-profile"): "InstanceProfile",
        ("sts", "assumed-role"): "IAMRole",
        ("lambda", "function"): "LambdaFunction",
        ("ec2", "instance"): "EC2Instance",
        ("s3", ""): "S3Bucket",
    }

    key = (c.service, c.resource_type)
    if key in _TYPE_MAP:
        return _TYPE_MAP[key]

    # Fallback: construct from service and resource type
    if c.resource_type:
        return f"{c.service}:{c.resource_type}"
    return c.service


def arn_to_region(arn: str) -> str:
    """Extract region from ARN, defaulting to '-' for global services."""
    c = parse_arn(arn)
    return c.region if c.region else "-"


def arn_to_provider_id(arn: str) -> str:
    """Extract a stable provider_id from an ARN.

    For IAM principals, this is the role/user name (last path component).
    For other resources, this is the full resource_id.

    Returns the full ARN for assumed-role ARNs to preserve session info.
    """
    c = parse_arn(arn)

    if c.service == "iam" and c.resource_type in ("role", "user"):
        # arn:aws:iam::123:role/path/to/MyRole → MyRole
        # But we keep the full path for uniqueness
        return c.resource_id

    if c.service == "sts" and c.resource_type == "assumed-role":
        # arn:aws:sts::123:assumed-role/RoleName/session → RoleName
        parts = c.resource_id.split("/")
        return parts[0] if parts else c.resource_id

    return c.resource_id
