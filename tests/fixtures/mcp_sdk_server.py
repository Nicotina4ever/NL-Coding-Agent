"""Real SDK subprocess fixture: no model, network or project mutations."""
import sys
import time

from mcp.server.fastmcp import FastMCP

server = FastMCP("NL protocol fixture", host="127.0.0.1",
                 port=int(sys.argv[1]) if len(sys.argv) > 1 else 8000)


@server.tool()
def echo(text: str) -> dict:
    print("fixture diagnostics", file=sys.stderr)
    return {"echo": text}


@server.tool()
def slow(seconds: float) -> str:
    time.sleep(seconds)
    return "finished"


@server.resource("fixture://context")
def context() -> str:
    return "untrusted fixture context"


if __name__ == "__main__":
    server.run(transport="streamable-http" if len(sys.argv) > 1 else "stdio")
