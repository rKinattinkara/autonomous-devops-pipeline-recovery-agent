from src.models.remediation_result import RemediationResult
from src.models.policy_result import PolicyResult


BLOCKED_KEYWORDS = [
    "secret",
    "password",
    "token",
    "credential",
    "iam",
    "delete database",
    "drop database",
    "destroy",
    "terraform destroy",
]

REVIEW_KEYWORDS = [
    "terraform",
    "kubernetes",
    "deployment",
    "helm",
    "network",
    "firewall",
    "database",
    "production",
]

LOW_RISK_EXTENSIONS = [
    ".py",
    ".js",
    ".ts",
    ".java",
    ".cs",
]


def evaluate_remediation(
    remediation: RemediationResult,
) -> PolicyResult:

    combined_text = (
        remediation.summary
        + " "
        + remediation.proposed_change
        + " "
        + remediation.patch
        + " "
        + remediation.target_file
    ).lower()

    if remediation.risk.upper() == "HIGH":
        return PolicyResult(
            decision="BLOCK",
            risk="HIGH",
            reasons=[
                "Remediation Agent classified this change as HIGH risk."
            ],
            allowed_to_execute=False,
            requires_human_approval=True,
        )

    # ---------------------------------------------------------
    # BLOCKED actions
    # ---------------------------------------------------------

    blocked_matches = [
        keyword
        for keyword in BLOCKED_KEYWORDS
        if keyword in combined_text
    ]

    if blocked_matches:
        return PolicyResult(
            decision="BLOCK",
            risk="HIGH",
            reasons=[
                f"Blocked keyword detected: {keyword}"
                for keyword in blocked_matches
            ],
            allowed_to_execute=False,
            requires_human_approval=True,
        )

    # ---------------------------------------------------------
    # REVIEW-required actions
    # ---------------------------------------------------------

    review_matches = [
        keyword
        for keyword in REVIEW_KEYWORDS
        if keyword in combined_text
    ]

    if review_matches:
        return PolicyResult(
            decision="REVIEW",
            risk="MEDIUM",
            reasons=[
                f"Sensitive infrastructure change detected: {keyword}"
                for keyword in review_matches
            ],
            allowed_to_execute=False,
            requires_human_approval=True,
        )

    # ---------------------------------------------------------
    # Low-risk application code
    # ---------------------------------------------------------

    if any(
        remediation.target_file.endswith(extension)
        for extension in LOW_RISK_EXTENSIONS
    ):
        return PolicyResult(
            decision="ALLOW",
            risk="LOW",
            reasons=[
                "Change is limited to application source code.",
                "No secrets, infrastructure, IAM, or destructive operation detected.",
            ],
            allowed_to_execute=True,
            requires_human_approval=False,
        )

    # ---------------------------------------------------------
    # Unknown cases
    # ---------------------------------------------------------

    return PolicyResult(
        decision="REVIEW",
        risk="MEDIUM",
        reasons=[
            "Change type is not explicitly covered by the current safety policy."
        ],
        allowed_to_execute=False,
        requires_human_approval=True,
    )