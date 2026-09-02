"""MCP server for LipariBank account and compliance operations."""

from pathlib import Path

import httpx
from fastmcp import FastMCP


mcp = FastMCP("LipariBank")
_RESOURCES_DIR = Path(__file__).resolve().parent / "resources"


def _validate_account_id(account_id: int) -> None:
    if account_id <= 0:
        raise ValueError("account_id must be a positive integer")


def _read_policy(filename: str) -> str:
    policy_path = _RESOURCES_DIR / filename
    try:
        return policy_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"Unable to read policy resource: {policy_path}") from exc


@mcp.tool
async def get_account_balance(account_id: int) -> dict:
    """Retrieve an account and its current balance.

    Use this when you need the current balance or account details for a
    LipariBank account.

    Args:
        account_id: Positive numeric identifier of the account.

    Returns:
        The account details returned by the LipariBank account service.
    """
    _validate_account_id(account_id)
    url = f"http://localhost:8080/api/accounts/{account_id}"

    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            response = await client.get(url)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            raise RuntimeError(
                f"Account service returned HTTP {status_code} for account {account_id}"
            ) from exc

        return response.json()


@mcp.tool
async def list_recent_movements(account_id: int, limit: int = 10) -> list[dict]:
    """List the most recent movements for an account.

    Use this when you need to inspect recent transactions for a
    LipariBank account.

    Args:
        account_id: Positive numeric identifier of the account.
        limit: Maximum number of movements requested.

    Returns:
        A list of movement records returned by the LipariBank movement service.
    """
    _validate_account_id(account_id)
    if limit <= 0:
        raise ValueError("limit must be a positive integer")

    url = "http://localhost:8080/api/movements"
    params = {"accountId": account_id, "limit": limit}

    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            raise RuntimeError(
                f"Movement service returned HTTP {status_code} for account {account_id}"
            ) from exc

        return response.json()


@mcp.tool
async def simulate_transfer_what_if(
    source_account_id: int,
    target_account_id: int,
    amount: float,
) -> dict:
    """Simulate a transfer without committing any changes.

    Use this when you need to evaluate the projected balances of a transfer
    before any money is moved.

    Args:
        source_account_id: Positive numeric identifier of the source account.
        target_account_id: Positive numeric identifier of the target account.
        amount: Positive transfer amount.

    Returns:
        A simulation containing current and projected balances and whether the
        source account has sufficient funds.
    """
    _validate_account_id(source_account_id)
    _validate_account_id(target_account_id)
    if source_account_id == target_account_id:
        raise ValueError("source_account_id and target_account_id must differ")
    if amount <= 0:
        raise ValueError("amount must be greater than zero")

    source_account = await get_account_balance(source_account_id)
    target_account = await get_account_balance(target_account_id)
    source_balance = float(source_account["balance"])
    target_balance = float(target_account["balance"])

    return {
        "source_account_id": source_account_id,
        "target_account_id": target_account_id,
        "amount": amount,
        "source_balance": source_balance,
        "target_balance": target_balance,
        "projected_source_balance": source_balance - amount,
        "projected_target_balance": target_balance + amount,
        "sufficient_funds": source_balance >= amount,
    }


@mcp.resource("policy://aml")
def aml_policy() -> str:
    """Read the anti-money-laundering policy."""
    return _read_policy("aml-policy.md")


@mcp.resource("policy://banking-regulation")
def banking_regulation_policy() -> str:
    """Read the current banking regulation policy."""
    return _read_policy("banking-regulation-v2.md")


@mcp.prompt
def draft_compliance_report(audit_period_days: int = 30) -> str:
    """Create a Markdown template for a compliance report draft."""
    if audit_period_days <= 0:
        raise ValueError("audit_period_days must be a positive integer")

    return f"""# LipariBank Compliance Report

## Audit period

- Duration: {audit_period_days} days
- Start date: [YYYY-MM-DD]
- End date: [YYYY-MM-DD]

## Executive summary

[Summarize the overall compliance posture and material findings.]

## Scope and methodology

- Accounts reviewed: [number or identifiers]
- Movements reviewed: [number]
- Policies and regulations consulted: [list]
- Methodology: [describe]

## Findings

### Finding 1 — [Title]

- Severity: [LOW | MEDIUM | HIGH | CRITICAL]
- Evidence: [describe evidence]
- Risk: [describe risk]
- Recommendation: [describe remediation]

## AML assessment

[Document suspicious activity indicators, alerts, and disposition.]

## Recommendations and action plan

| Priority | Action | Owner | Due date | Status |
|---|---|---|---|---|
| [P1] | [Action] | [Owner] | [YYYY-MM-DD] | [Open] |

## Conclusion

[State the conclusion and required follow-up.]
"""


if __name__ == "__main__":
    mcp.run(transport="stdio")
