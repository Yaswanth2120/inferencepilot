"""Controllable fake OpenAI endpoints, with deliberately synthetic tokenization."""

import asyncio
import json
import random

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from inferencepilot.fakes.timing import Settings, delays


class Completion(BaseModel):
    model: str = "fake-model"
    prompt: str = ""
    messages: list[dict] = Field(default_factory=list)
    max_tokens: int = Field(default=4, ge=1, le=8192)
    stream: bool = False
    seed: int = 0
    logprobs: int | None = None
    return_tokens_as_token_ids: bool = False


def chunk(index, chat, finished=False):
    choice = {"index": 0, "finish_reason": "length" if finished else None}
    content = "" if finished else f" token{index}"
    choice["delta" if chat else "text"] = {"content": content} if chat else content
    return {
        "id": "fake-completion",
        "object": "chat.completion.chunk" if chat else "text_completion",
        "choices": [choice],
    }


def create_app(settings=None):
    settings = settings or Settings()
    app = FastAPI()
    app.state.active = 0
    app.state.rng = random.Random(settings.seed)

    @app.get("/fake/timing")
    async def timing(seed: int = 0, prompt_tokens: int = 8, output_tokens: int = 4):
        """Expose synthetic scheduler time for deterministic power experiments, not wall time."""
        return {
            "synthetic": True,
            "seconds": sum(delays(settings, prompt_tokens, output_tokens, 1, seed)),
        }

    @app.get("/health")
    async def health():
        if not settings.healthy:
            raise HTTPException(503, "injected unhealthy state")
        return {"status": "ok"}

    @app.get("/v1/models")
    async def models():
        return {"object": "list", "data": [{"id": settings.model, "object": "model"}]}

    async def respond(body, chat):
        if body.model != settings.model:
            raise HTTPException(404, "model not found")
        if app.state.rng.random() < settings.failure_rate:
            raise HTTPException(500, "injected failure")
        if app.state.rng.random() < settings.hang_rate:
            await asyncio.sleep(settings.hang_seconds)
        prompt = body.prompt or " ".join(str(m.get("content", "")) for m in body.messages)
        prompt_tokens = len(prompt.split())

        async def tokens():
            app.state.active += 1
            try:
                schedule = delays(
                    settings, prompt_tokens, body.max_tokens, app.state.active, body.seed
                )
                await asyncio.sleep(schedule[0])
                for index, delay in enumerate(schedule[1:]):
                    await asyncio.sleep(delay)
                    yield index
            finally:
                app.state.active -= 1

        if body.stream:

            async def events():
                async for index in tokens():
                    yield f"data: {json.dumps(chunk(index, chat))}\n\n"
                yield f"data: {json.dumps(chunk(0, chat, True))}\n\n"
                yield "data: [DONE]\n\n"

            return StreamingResponse(events(), media_type="text/event-stream")
        output = [f" token{index}" async for index in tokens()]
        choice = {"index": 0, "finish_reason": "length"}
        choice["message" if chat else "text"] = (
            {"role": "assistant", "content": "".join(output)} if chat else "".join(output)
        )
        if body.logprobs is not None and not chat:
            choice["logprobs"] = {
                "tokens": [
                    f"token_id:{i}" if body.return_tokens_as_token_ids else f" token{i}"
                    for i in range(len(output))
                ]
            }
        return {
            "id": "fake-completion",
            "object": "chat.completion" if chat else "text_completion",
            "model": settings.model,
            "choices": [choice],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": len(output),
                "total_tokens": prompt_tokens + len(output),
            },
        }

    @app.post("/v1/completions")
    async def completions(body: Completion):
        return await respond(body, False)

    @app.post("/v1/chat/completions")
    async def chat_completions(body: Completion):
        return await respond(body, True)

    return app
