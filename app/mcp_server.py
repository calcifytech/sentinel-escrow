from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Sentinel Escrow Server")

@mcp.tool()
def get_escrow_balance(account_id: str) -> float:
    """Gets the current balance of the specified escrow account."""
    # Simulated balance check
    return 25000.00

@mcp.tool()
def verify_bank_routing(routing_number: str) -> bool:
    """Verifies that the routing number is valid and registered."""
    # Simple check: routing numbers must be exactly 9 digits
    clean_routing = "".join(filter(str.isdigit, routing_number))
    return len(clean_routing) == 9

@mcp.tool()
def check_blacklist_payee(name: str) -> bool:
    """Checks if the payee name is on a simulated compliance sanctions list."""
    blacklist = ["darkweb llc", "malware corp", "scam inc"]
    return any(item in name.lower() for item in blacklist)

@mcp.tool()
def log_escrow_transaction(action: str, amount: float, payee: str) -> str:
    """Records an escrow transaction (e.g., AUDIT, HOLD, RELEASE) in the secure audit log."""
    log_msg = f"[MCP LEDGER] Action: {action.upper()} | Amount: ${amount:.2f} | Payee: {payee}"
    print(log_msg)
    return log_msg

if __name__ == "__main__":
    mcp.run()
