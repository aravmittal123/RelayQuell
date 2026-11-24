from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI()


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/mcp")
def call(payload: dict):
    request_id = payload.get("id")
    if payload.get("method") == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "tools": [
                    {
                        "name": name,
                        "description": name.replace("_", " "),
                        "inputSchema": {"type": "object"},
                    }
                    for name in ("charge_card", "query_inventory")
                ]
            },
        }
    params = payload.get("params", {})
    name, args = params.get("name"), params.get("arguments", {})
    if args.get("simulate_error"):
        return JSONResponse({"error": "deterministic upstream failure"}, status_code=503)
    if name not in ("charge_card", "query_inventory"):
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32601, "message": "Unknown tool"},
        }
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {
            "content": [
                {
                    "type": "text",
                    "text": f"{name}: success (simulation; no real payment)",
                }
            ],
            "isError": False,
        },
    }
