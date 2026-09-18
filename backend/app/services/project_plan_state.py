import hashlib
import json
from typing import Any, Literal

ApprovalStatus = Literal["unapproved", "approved", "stale"]


def context_fingerprint(context: dict[str, Any]) -> str:
    canonical = json.dumps(context, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def approval_status(context: dict[str, Any], latest: dict[str, Any] | None) -> ApprovalStatus:
    if latest is None:
        return "unapproved"
    return "approved" if latest.get("context_fingerprint") == context_fingerprint(context) else "stale"
