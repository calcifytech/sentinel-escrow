import os
import datetime
import json
import re
from pydantic import BaseModel, Field
from google.adk import Workflow, Context
from google.adk.agents import LlmAgent
from google.adk.tools import AgentTool, McpToolset
from google.adk.workflow import FunctionNode
from google.adk.events import RequestInput
from google.adk.apps import App
from mcp import StdioServerParameters

from .config import config

# ---------------------------------------------------------------------------
# Shared Workflow State
# ---------------------------------------------------------------------------

class EscrowState(BaseModel):
    contract_text: str = ""
    compliance_issues: str = ""
    funds_available: bool = False
    verification_details: str = ""
    security_check_passed: bool = True
    security_violation_details: str = ""
    human_approval_granted: bool = False
    payment_status: str = "PENDING"

class ApprovalDecision(BaseModel):
    approved: bool = Field(description="Whether the payment is approved or denied")
    comments: str = Field(description="Reason for the decision")

# ---------------------------------------------------------------------------
# Node 1: Security Checkpoint (FunctionNode)
# ---------------------------------------------------------------------------

async def security_checkpoint(ctx: Context, node_input: str):
    # PII scrubbing
    cleaned_text = node_input
    ssn_pattern = r'\b\d{3}-\d{2}-\d{4}\b'
    cc_pattern = r'\b(?:\d[ -]*?){13,16}\b'
    cleaned_text = re.sub(ssn_pattern, "[REDACTED SSN]", cleaned_text)
    cleaned_text = re.sub(cc_pattern, "[REDACTED CARD]", cleaned_text)
    
    # Prompt injection check
    injection_keywords = [
        "ignore previous instructions", 
        "system override", 
        "bypass checkpoint", 
        "you are now a simulator"
    ]
    has_injection = any(kw in node_input.lower() for kw in injection_keywords)
    
    # Domain-specific rule: Escrow transaction limit check (> $50,000)
    large_amount_detected = False
    amount_matches = re.findall(r'\$\s*?(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)', node_input)
    for amt_str in amount_matches:
        try:
            amt = float(amt_str.replace(',', ''))
            if amt > 50000.00:
                large_amount_detected = True
                break
        except ValueError:
            pass
            
    # Structured JSON audit log
    severity = "INFO"
    if has_injection:
        severity = "CRITICAL"
    elif large_amount_detected:
        severity = "WARNING"
        
    audit_entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "node": "security_checkpoint",
        "has_injection": has_injection,
        "has_pii": cleaned_text != node_input,
        "large_amount_detected": large_amount_detected,
        "severity": severity
    }
    print(f"AUDIT_LOG: {json.dumps(audit_entry)}")
    
    ctx.state["contract_text"] = cleaned_text
    
    if has_injection:
        ctx.state["security_check_passed"] = False
        ctx.state["security_violation_details"] = "Prompt injection attempt detected."
        ctx.route = "SECURITY_EVENT"
        return "Security Violation Detected"
    else:
        ctx.state["security_check_passed"] = True
        ctx.route = "APPROVED"
        return cleaned_text

security_node = FunctionNode(func=security_checkpoint, name="security_node")

# ---------------------------------------------------------------------------
# Node 2: Security Alert (FunctionNode)
# ---------------------------------------------------------------------------

async def security_alert(ctx: Context):
    violation = ctx.state.get("security_violation_details", "Unknown violation")
    return f"Execution Blocked: {violation}"

security_alert_node = FunctionNode(func=security_alert, name="security_alert_node")

import sys
mcp_toolset = McpToolset(
    connection_params=StdioServerParameters(
        command=sys.executable,
        args=["-m", "app.mcp_wrapper"]
    )
)

# ---------------------------------------------------------------------------
# Sub-Agent 1: Contract Compliance Auditor (LlmAgent)
# ---------------------------------------------------------------------------

contract_auditor_agent = LlmAgent(
    name="contract_auditor_agent",
    model=config.model,
    instruction="""You are a compliance auditor. You review the contract text and verify compliance.
Use the check_blacklist_payee tool to make sure the payee is not blacklisted.
Check if:
1. Payee name is valid (not empty).
2. Payout amount is positive.
3. Escrow release conditions are specified.
Summarize compliance status and output whether compliance is PASSED or FAILED.""",
    tools=[mcp_toolset]
)

# ---------------------------------------------------------------------------
# Sub-Agent 2: Escrow Funding Agent (LlmAgent)
# ---------------------------------------------------------------------------

escrow_funding_agent = LlmAgent(
    name="escrow_funding_agent",
    model=config.model,
    instruction="""You are a funding auditor. You verify escrow accounts.
Use get_escrow_balance and verify_bank_routing to verify the account balance and routing number.
Check if:
1. Escrow account has sufficient balance for the payout.
2. Escrow bank details are verified.
Summarize funding status and output whether funding is VERIFIED or INSUFFICIENT.""",
    tools=[mcp_toolset]
)

# ---------------------------------------------------------------------------
# Orchestrator Agent (LlmAgent)
# ---------------------------------------------------------------------------

orchestrator = LlmAgent(
    name="orchestrator",
    model=config.model,
    instruction="""You are the Escrow Orchestrator. Your role is to coordinate contract auditing and funding check.
1. Call the contract_auditor_agent to check the contract text compliance. Use the contract text from the state.
2. Call the escrow_funding_agent to verify funding status.
3. Use log_escrow_transaction to record the audit decision.
Combine both summaries and give a final recommendation (recommend RELEASE if compliance passes and funding is verified, otherwise recommend HOLD).""",
    tools=[
        AgentTool(agent=contract_auditor_agent),
        AgentTool(agent=escrow_funding_agent),
        mcp_toolset
    ]
)

# ---------------------------------------------------------------------------
# Node 3: Human Approval Checkpoint (FunctionNode)
# ---------------------------------------------------------------------------

async def human_approval_checkpoint_func(ctx: Context, node_input: str):
    user_input = ctx.resume_inputs.get("human_decision")
    if user_input is None:
        print("[HITL] Pausing workflow for human approval...")
        yield RequestInput(
            interrupt_id="human_decision",
            message=f"Orchestrator Report:\n{node_input}\n\nDo you approve releasing these escrow funds?",
            response_schema=ApprovalDecision
        )
        return
    
    approved = user_input.get("approved", False)
    comments = user_input.get("comments", "")
    
    ctx.state["human_approval_granted"] = approved
    if approved:
        ctx.route = "APPROVED"
        yield f"Approved by human. Comments: {comments}"
    else:
        ctx.route = "DENIED"
        yield f"Denied by human. Comments: {comments}"

human_approval_checkpoint = FunctionNode(
    func=human_approval_checkpoint_func,
    name="human_approval_checkpoint",
    rerun_on_resume=True
)

# ---------------------------------------------------------------------------
# Node 4: Payment Release (FunctionNode)
# ---------------------------------------------------------------------------

async def payment_release_func(ctx: Context):
    ctx.state["payment_status"] = "RELEASED"
    return "Payment successfully released and transferred to payee account."

payment_release = FunctionNode(func=payment_release_func, name="payment_release")

# ---------------------------------------------------------------------------
# Node 5: Payment Rejected (FunctionNode)
# ---------------------------------------------------------------------------

async def payment_rejected_func(ctx: Context):
    ctx.state["payment_status"] = "REJECTED"
    return "Payment escrow release rejected. Funds remain held."

payment_rejected = FunctionNode(func=payment_rejected_func, name="payment_rejected")

# ---------------------------------------------------------------------------
# Workflow Definition
# ---------------------------------------------------------------------------

workflow = Workflow(
    name="sentinel_escrow_workflow",
    state_schema=EscrowState,
    edges=[
        ("START", security_node),
        (security_node, {"APPROVED": orchestrator, "SECURITY_EVENT": security_alert_node}),
        (orchestrator, human_approval_checkpoint),
        (human_approval_checkpoint, {"APPROVED": payment_release, "DENIED": payment_rejected})
    ]
)

# ---------------------------------------------------------------------------
# App Definition
# ---------------------------------------------------------------------------

app = App(
    root_agent=workflow,
    name="app",
)
