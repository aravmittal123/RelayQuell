import time

from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI()


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/v1/chat/completions")
def completion(payload: dict):
    if payload.get("simulate_error"):
        return JSONResponse({"error": "deterministic upstream failure"}, status_code=503)
    model = payload["model"]
    print(f"mock completion model={model}", flush=True)
    tokens = min(payload.get("max_tokens", 256), 64)
    return {
        "id": "chatcmpl-local",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": f"Deterministic local response via {model}.",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 16,
            "completion_tokens": tokens,
            "total_tokens": 16 + tokens,
        },
    }
