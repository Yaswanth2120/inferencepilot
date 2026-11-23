import asyncio

import httpx
import pytest

from inferencepilot.fakes.fake_vllm import Settings, create_app, delays


def test_delay_model():
    base = Settings(jitter=0.2)
    first = delays(base, 10, 3, 1, 7)
    assert first == delays(base, 10, 3, 1, 7)
    assert first != delays(base, 10, 3, 1, 8)
    assert delays(Settings(jitter=0.2, inject_slowdown_pct=20), 10, 3, 1, 7) == pytest.approx(
        [value * 1.2 for value in first]
    )
    assert delays(base, 20, 3, 1, 7)[0] == first[0] * 2
    assert delays(base, 10, 3, 3, 7) == pytest.approx([value * 1.2 for value in first])


@pytest.mark.parametrize("chat", [False, True])
@pytest.mark.parametrize("stream", [False, True])
def test_endpoints(chat, stream):
    async def exercise():
        app = create_app(Settings(token_delay=0, prefill_per_token=0))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://fake"
        ) as client:
            assert (await client.get("/health")).status_code == 200
            assert (await client.get("/v1/models")).json()["data"][0]["id"] == "fake-model"
            body = (
                {
                    "model": "fake-model",
                    "max_tokens": 3,
                    "stream": stream,
                    "messages": [{"role": "user", "content": "hello there"}],
                }
                if chat
                else {
                    "model": "fake-model",
                    "prompt": "hello there",
                    "max_tokens": 3,
                    "stream": stream,
                }
            )
            endpoint = "/v1/chat/completions" if chat else "/v1/completions"
            response = await client.post(endpoint, json=body)
            assert response.status_code == 200
            if stream:
                assert response.text.endswith("data: [DONE]\n\n")
                assert response.text.count("data: ") == 5  # 3 tokens + finish + DONE
                assert '"delta"' in response.text if chat else '"text"' in response.text
            else:
                assert response.json()["usage"]["completion_tokens"] == 3
            assert app.state.active == 0
            assert (await client.post(endpoint, json={"model": "absent"})).status_code == 404
            assert (await client.post(endpoint, json={"max_tokens": -1})).status_code == 422

    asyncio.run(exercise())


def test_injected_failure_and_hang():
    async def exercise():
        for settings in (Settings(failure_rate=1), Settings(hang_rate=1, hang_seconds=10)):
            app = create_app(settings)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://fake"
            ) as client:
                if settings.failure_rate:
                    assert (await client.post("/v1/completions", json={})).status_code == 500
                else:
                    with pytest.raises(asyncio.TimeoutError):
                        await asyncio.wait_for(client.post("/v1/completions", json={}), 0.02)
                assert app.state.active == 0

    asyncio.run(exercise())


def test_stream_applies_seeded_slowdown(monkeypatch):
    sleeps = []

    async def record_sleep(delay):
        sleeps.append(delay)

    async def exercise(settings):
        app = create_app(settings)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://fake"
        ) as client:
            response = await client.post(
                "/v1/completions",
                json={
                    "prompt": "one two",
                    "stream": True,
                    "max_tokens": 3,
                    "seed": 7,
                },
            )
            assert response.status_code == 200

    monkeypatch.setattr("inferencepilot.fakes.fake_vllm.asyncio.sleep", record_sleep)
    asyncio.run(exercise(Settings()))
    baseline = list(sleeps)
    sleeps.clear()
    asyncio.run(exercise(Settings(inject_slowdown_pct=20)))
    assert sleeps == pytest.approx([value * 1.2 for value in baseline])
