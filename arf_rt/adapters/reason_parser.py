"""PMapper reason string parser.

PMapper edge 'reason' fields describe how one principal can access another.
This module extracts the AWS API action from those reason strings.

Common patterns:
    "can call sts:AssumeRole to access"                 → sts:AssumeRole
    "can call iam:CreateAccessKey to access"             → iam:CreateAccessKey
    "can use EC2 to run an instance with ... to access"  → ec2:RunInstances
    "can use Lambda to edit ... to access"               → lambda:UpdateFunctionCode
    "can use SSM to access"                              → ssm:StartSession
    "(admin) can access"                                 → ADMIN_ACCESS
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ParsedReason:
    """Parsed components of a PMapper edge reason."""

    action: str           # AWS API action (e.g., "sts:AssumeRole")
    mechanism: str        # How the access works (direct_call, ec2, lambda, ssm, admin, unknown)
    raw: str              # Original reason string
    confidence: str       # HIGH (exact action known), MEDIUM (inferred), LOW (unknown mechanism)


# Pattern: "can call <service:Action>"
_DIRECT_CALL = re.compile(r"can call ([a-zA-Z0-9\-]+:[a-zA-Z0-9]+)")

# Pattern: "can access via <service:Action>" (PMapper v1.1.5+ format)
_ACCESS_VIA = re.compile(r"can access via ([a-zA-Z0-9\-]+:[a-zA-Z0-9]+)")

# Pattern: "can use EC2 to run an instance"
_EC2_RUN = re.compile(r"can use EC2 to run an instance", re.IGNORECASE)

# Pattern: "can use EC2 to ..." (other EC2 mechanisms)
_EC2_OTHER = re.compile(r"can use EC2", re.IGNORECASE)

# Pattern: "can use Lambda to edit" or "can use Lambda"
_LAMBDA = re.compile(r"can use Lambda", re.IGNORECASE)

# Pattern: "can use SSM"
_SSM = re.compile(r"can use SSM", re.IGNORECASE)

# Pattern: "can use CloudFormation"
_CFN = re.compile(r"can use CloudFormation", re.IGNORECASE)

# Pattern: "can use SageMaker"
_SAGEMAKER = re.compile(r"can use SageMaker", re.IGNORECASE)

# Pattern: "can use Glue"
_GLUE = re.compile(r"can use Glue", re.IGNORECASE)

# Pattern: "can use CodeBuild"
_CODEBUILD = re.compile(r"can use CodeBuild", re.IGNORECASE)

# Pattern: "(admin)" or "is an admin"
_ADMIN = re.compile(r"\(admin\)|is an admin", re.IGNORECASE)

# Pattern: "can access" (generic fallback)
_GENERIC = re.compile(r"can access", re.IGNORECASE)


def parse_reason(reason: str) -> ParsedReason:
    """Parse a PMapper edge reason string into structured data.

    Args:
        reason: The 'reason' field from a PMapper edge.

    Returns:
        ParsedReason with extracted action and mechanism.
    """
    if not reason:
        return ParsedReason(
            action="UNKNOWN",
            mechanism="unknown",
            raw=reason,
            confidence="LOW",
        )

    # 1. Direct API call — highest confidence
    m = _DIRECT_CALL.search(reason)
    if m:
        action = m.group(1)
        return ParsedReason(
            action=action,
            mechanism="direct_call",
            raw=reason,
            confidence="HIGH",
        )

    # 1b. "can access via <service:Action>" — PMapper v1.1.5 format
    m = _ACCESS_VIA.search(reason)
    if m:
        action = m.group(1)
        return ParsedReason(
            action=action,
            mechanism="direct_call",
            raw=reason,
            confidence="HIGH",
        )

    # 2. Admin access
    if _ADMIN.search(reason):
        return ParsedReason(
            action="ADMIN_ACCESS",
            mechanism="admin",
            raw=reason,
            confidence="HIGH",
        )

    # 3. EC2 instance — run instance with role
    if _EC2_RUN.search(reason):
        return ParsedReason(
            action="ec2:RunInstances",
            mechanism="ec2",
            raw=reason,
            confidence="MEDIUM",
        )

    # 4. EC2 other mechanisms
    if _EC2_OTHER.search(reason):
        return ParsedReason(
            action="ec2:RunInstances",
            mechanism="ec2",
            raw=reason,
            confidence="MEDIUM",
        )

    # 5. Lambda
    if _LAMBDA.search(reason):
        return ParsedReason(
            action="lambda:UpdateFunctionCode",
            mechanism="lambda",
            raw=reason,
            confidence="MEDIUM",
        )

    # 6. SSM
    if _SSM.search(reason):
        return ParsedReason(
            action="ssm:StartSession",
            mechanism="ssm",
            raw=reason,
            confidence="MEDIUM",
        )

    # 7. CloudFormation
    if _CFN.search(reason):
        return ParsedReason(
            action="cloudformation:CreateStack",
            mechanism="cloudformation",
            raw=reason,
            confidence="MEDIUM",
        )

    # 8. SageMaker
    if _SAGEMAKER.search(reason):
        return ParsedReason(
            action="sagemaker:CreateNotebookInstance",
            mechanism="sagemaker",
            raw=reason,
            confidence="MEDIUM",
        )

    # 9. Glue
    if _GLUE.search(reason):
        return ParsedReason(
            action="glue:CreateDevEndpoint",
            mechanism="glue",
            raw=reason,
            confidence="MEDIUM",
        )

    # 10. CodeBuild
    if _CODEBUILD.search(reason):
        return ParsedReason(
            action="codebuild:StartBuild",
            mechanism="codebuild",
            raw=reason,
            confidence="MEDIUM",
        )

    # 11. Generic fallback
    if _GENERIC.search(reason):
        logger.warning("Unrecognized PMapper reason pattern: %s", reason)
        return ParsedReason(
            action="UNKNOWN",
            mechanism="unknown",
            raw=reason,
            confidence="LOW",
        )

    # 12. Completely unrecognized
    logger.warning("Unrecognized PMapper reason: %s", reason)
    return ParsedReason(
        action="UNKNOWN",
        mechanism="unknown",
        raw=reason,
        confidence="LOW",
    )
