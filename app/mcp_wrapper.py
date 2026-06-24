import os
import sys
import traceback

log_file_path = os.path.join(os.path.dirname(__file__), "mcp_debug.log")

with open(log_file_path, "a") as log_file:
    log_file.write("\n=== MCP Wrapper Start ===\n")
    log_file.write(f"CWD: {os.getcwd()}\n")
    log_file.write(f"sys.executable: {sys.executable}\n")
    log_file.write(f"sys.path: {sys.path}\n")
    log_file.write(f"ENV: {dict(os.environ)}\n")
    
    try:
        log_file.write("Attempting to import app.mcp_server...\n")
        import app.mcp_server
        log_file.write("Import successful. Running mcp.run()...\n")
        log_file.flush()
        app.mcp_server.mcp.run()
    except Exception as e:
        log_file.write(f"Exception occurred:\n")
        traceback.print_exc(file=log_file)
        log_file.flush()
        raise
