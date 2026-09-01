"""
code-review-suite.py — orchestrator multi-agent per code review del LipariBank.
Lancia 4 subagent specializzati in parallelo, sintetizza i findings.
"""

import asyncio
import json
import os
import time
import uuid
from datetime import timedelta
from pathlib import Path
import subprocess

from opencode_agent_sdk import SDKClient, AgentOptions, AssistantMessage, ResultMessage, TextBlock


SUBAGENTS = [
    ("code-reviewer-banking-domain", "Review di dominio banking"),
    ("security-reviewer", "OWASP + Spring Security"),
    ("performance-reviewer", "N+1, blocking I/O, pool tuning"),
    ("rest-contract-reviewer", "DTO + status code + OpenAPI"),
]

SDK_MODEL = "big-pickle"
SDK_SERVER_URL = "http://127.0.0.1:4096"
SDK_TOOLS = ["Read", "Grep", "Glob"]
SDK_MAX_TURNS = 15

TOKEN_BUDGET = 200_000
TIME_BUDGET_SECONDS = 600
COST_BUDGET_USD = 5.0

# Costo Sonnet 4.6: ~$3/M input + $15/M output. Stima conservativa: $9/M average
COST_PER_TOKEN = 9 / 1_000_000
"""
Il costo del run di questo script sarà sempre 0 perchè big-pickle è gratuito
"""



async def run_subagent(name: str, description: str, pr_diff: str, cid: str) -> dict:
    print(f"[{cid}] Starting subagent: {name}")
    findings = []
    total_tokens = 0
    error = None

    agent_prompt_path = Path(f".opencode/agents/{name}.md")
    system_context = ""
    if agent_prompt_path.exists():
        system_context = agent_prompt_path.read_text(encoding="utf-8") + "\n\n"

    print(f"[{cid}] Current working directory: {os.getcwd()}")
    client = SDKClient(options=AgentOptions(
        cwd=os.getcwd(),
        allowed_tools=SDK_TOOLS,
        # permission_mode="acceptEdits", non serve visto che non sono permesse modifiche
        max_turns=SDK_MAX_TURNS,
        model=SDK_MODEL,
        server_url=SDK_SERVER_URL,
    ))

    try:
        await client.connect()
        await client.query(f"""{system_context} Review the following changes carefully.

Diff or file paths to review:
{pr_diff}

Output ONLY a JSON array of findings, no prose. Schema:
[{{"severity": "...", "file": "...", "line": N, "description": "...", "fix": "..."}}]
""")

        async for message in client.receive_response():
            if isinstance(message, AssistantMessage) and message.content:
                text_parts = []
                for block in message.content:
                    if isinstance(block, TextBlock):
                        text_parts.append(block.text)
                if text_parts:
                    full_text = "\n".join(text_parts)
                    try:
                        parsed = extract_json_array(full_text)
                        if parsed:
                            findings = parsed
                    except Exception:
                        pass
            if isinstance(message, ResultMessage):
                usage = getattr(message, "usage", None)
                if usage:
                    total_tokens = getattr(usage, "total_tokens", 0)
    except Exception as e:
        error = str(e)
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass

    print(f"[{cid}] Completed {name}: {len(findings)} findings, {total_tokens} tokens")
    return {
        "name": name,
        "description": description,
        "findings": findings,
        "tokens": total_tokens,
        "error": error,
    }


def extract_json_array(content: str) -> list:
    """Trova il primo array JSON ben formato nella response."""
    start = content.find("[")
    end = content.rfind("]") + 1
    if start == -1 or end == 0:
        return []
    return json.loads(content[start:end])


def synthesize_report(results: list, cid: str, total_tokens: int, elapsed_s: float, cost_usd: float) -> str:
    md = f"# Code Review Suite — Run `{cid}`\n\n"
    md += f"**Elapsed**: {elapsed_s:.1f}s · **Tokens**: {total_tokens:,} · **Cost**: ${cost_usd:.3f}\n\n"
    md += "---\n\n"

    severity_count = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}

    for result in results:
        md += f"## {result['name']}\n"
        md += f"_{result['description']}_\n\n"
        if result["error"]:
            md += f"❌ Errore: {result['error']}\n\n"
            continue
        if not result["findings"]:
            md += "✅ OK no findings\n\n"
            continue
        for finding in result["findings"]:
            sev = finding.get("severity", "MEDIUM")
            severity_count[sev] = severity_count.get(sev, 0) + 1
            md += f"- **[{sev}]** `{finding['file']}:{finding['line']}` — {finding['description']}\n"
            md += f"  - **Fix**: {finding['fix']}\n"
        md += "\n"

    md += "---\n\n## Summary\n\n"
    for sev, count in severity_count.items():
        md += f"- {sev}: {count}\n"

    return md


async def main(pr_diff: str):
    cid = str(uuid.uuid4())
    start = time.time()
    print(f"Code Review Suite — Run {cid}")
    print(f"Subagents: {len(SUBAGENTS)}")

    tasks = [
        run_subagent(name, desc, pr_diff, cid)
        for name, desc in SUBAGENTS
    ]
    results = await asyncio.gather(*tasks)

    elapsed = time.time() - start
    total_tokens = sum(r["tokens"] for r in results)
    cost = total_tokens * COST_PER_TOKEN

    if total_tokens > TOKEN_BUDGET:
        print(f"⚠️ TOKEN BUDGET EXCEEDED: {total_tokens} > {TOKEN_BUDGET}")
    if cost > COST_BUDGET_USD:
        print(f"⚠️ COST BUDGET EXCEEDED: ${cost:.2f} > ${COST_BUDGET_USD}")
    if elapsed > TIME_BUDGET_SECONDS:
        print(f"⚠️ TIME BUDGET EXCEEDED: {elapsed:.0f}s > {TIME_BUDGET_SECONDS}s")

    report = synthesize_report(results, cid, total_tokens, elapsed, cost)

    output_path = Path(f"review-report-{cid}.md")
    output_path.write_text(report)
    print(f"\n✅ Report saved to {output_path}")
    print(f"   Total: {total_tokens:,} tokens · ${cost:.3f} · {elapsed:.1f}s")

def get_git_diff(diff_target: str = "HEAD~1") -> str:
    result = subprocess.run(
        ["git", "diff", diff_target],
        capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        print(f"⚠️ git diff fallito: {result.stderr.strip()}")
        return ""
    return result.stdout

if __name__ == "__main__":
    import sys
    # pr_diff = sys.argv[1] if len(sys.argv) > 1 else "git diff HEAD~1"
    pr_diff = get_git_diff()
    if not pr_diff:
        print("⚠️ Nessuna diff trovata (git diff HEAD~1 è vuoto o ha fallito).")
    else:
        print("diff trovate")

    print(pr_diff)
    
    asyncio.run(main(pr_diff))