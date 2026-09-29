"""Only the external model is replaced; exercise route parsing and recovery."""
import json

import pytest

from deeptutor.api.routers import flash_deck


def valid_cards():
    return json.dumps({'cards': [{'topic': 'Discriminant', 'front': 'When is a root repeated?',
                                  'back': 'When b^2 - 4ac = 0.'}]})


@pytest.mark.asyncio
async def test_incomplete_json_gets_one_retry_then_returns_complete_cards(monkeypatch):
    responses = iter(['{"cards":[{"front":"unfinished', valid_cards()])
    calls = []
    async def complete(prompt, **kwargs):
        calls.append(prompt)
        return next(responses)
    monkeypatch.setattr(flash_deck, 'llm_complete', complete)
    result = await flash_deck.generate_cards(flash_deck.GenerateCardsRequest(topics=['Discriminant'], num_cards=1))
    assert result['cards'][0]['back'] == 'When b^2 - 4ac = 0.'
    assert result['cards'][0]['id'] == 'c1'
    assert len(calls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize('raw', ['{"cards": []}', '{"cards":[{"front":"", "back":"answer", "topic":"x"}]}'])
async def test_invalid_cards_fail_with_actionable_error_after_two_calls(monkeypatch, raw):
    calls = []
    async def complete(prompt, **kwargs):
        calls.append(prompt)
        return raw
    monkeypatch.setattr(flash_deck, 'llm_complete', complete)
    result = await flash_deck.generate_cards(flash_deck.GenerateCardsRequest(topics=['x'], num_cards=1))
    assert 'cards' not in result
    assert result['retryable'] is True
    assert 'try again' in result['error'].lower()
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_provider_failure_is_not_retried_by_json_recovery(monkeypatch):
    calls = []
    async def complete(prompt, **kwargs):
        calls.append(prompt)
        raise RuntimeError('provider unavailable')
    monkeypatch.setattr(flash_deck, 'llm_complete', complete)
    result = await flash_deck.generate_cards(flash_deck.GenerateCardsRequest(topics=['x'], num_cards=1))
    assert 'error' in result
    assert len(calls) == 1
