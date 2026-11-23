import asyncio

import httpx

from inferencepilot.fakes.fake_vllm import Settings, create_app
from inferencepilot.quality import agreement, greedy_outputs


def test_fake_server_greedy_token_agreement():
    async def check():
        app = create_app(Settings(model="fake", token_delay=0, prefill_per_token=0))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://fake"
        ) as client:
            first = await greedy_outputs(
                client, "fake", ["a fixed prompt", "another prompt"], max_tokens=3
            )
            second = await greedy_outputs(
                client, "fake", ["a fixed prompt", "another prompt"], max_tokens=3
            )
        assert first == [[0, 1, 2], [0, 1, 2]]
        assert agreement(first, second)["exact_match_rate"] == 1

    asyncio.run(check())


def test_agreement_rejects_decoded_text_instead_of_ids():
    async def check():
        def handler(request):
            return httpx.Response(
                200,
                json={
                    "choices": [{"logprobs": {"tokens": ["decoded"]}}],
                    "usage": {"completion_tokens": 1},
                },
            )

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler), base_url="http://fake"
        ) as client:
            import pytest

            with pytest.raises(ValueError, match="token IDs"):
                await greedy_outputs(client, "fake", ["fixed"], max_tokens=1)

    asyncio.run(check())
