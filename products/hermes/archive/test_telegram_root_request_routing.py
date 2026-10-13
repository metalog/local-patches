"""Root requests must never inherit the latest Telegram topic."""
from types import SimpleNamespace
from unittest.mock import AsyncMock


def test_stripped_reply_uses_explicit_replied_topic_not_latest():
    from plugins.platforms.telegram.adapter import TelegramAdapter
    chat = SimpleNamespace(type='private', id=208214988)
    reply = SimpleNamespace(chat=chat, message_thread_id=111, is_topic_message=True)
    message = SimpleNamespace(chat=chat, message_thread_id=None,
                              is_topic_message=False, reply_to_message=reply)
    assert TelegramAdapter._effective_message_thread_id(message) == '111'

import pytest

@pytest.mark.asyncio
@pytest.mark.parametrize('background', [False, True])
async def test_final_delivery_uses_topic_created_by_handler(background):
    from tests.gateway.test_active_session_text_merge import _make_initialized_adapter
    from gateway.session_identity import replace_source
    adapter = _make_initialized_adapter()
    event = _make_event('synthetic request')
    async def handler(event):
        event.source = replace_source(event.source, thread_id='333')
        return 'synthetic answer'
    adapter._message_handler = handler
    adapter._send_with_retry = AsyncMock(return_value=SimpleNamespace(success=True, message_id='9'))
    if not background:
        await adapter._dispatch_inline_reply(event)
        assert adapter._send_with_retry.await_args.kwargs['metadata']['thread_id'] == '333'
    else:
        adapter._start_typing_refresh = lambda *args: None
        adapter._stop_typing_refresh = AsyncMock()
        adapter._extract_response_content = AsyncMock(return_value=SimpleNamespace(
            text_content='synthetic answer', media_files=[], images=[], local_files=[]))
        adapter._wants_auto_tts = lambda *args: False
        adapter._send_final_text = AsyncMock()
        adapter._deliver_attachments = AsyncMock()
        await adapter._process_message_background(event, 'synthetic-root-key')
        assert adapter._send_final_text.await_args.args[3]['thread_id'] == '333'

from tests.gateway.test_telegram_topic_mode import _make_runner, _make_event, _make_source, _seed_two_topic_bindings
from hermes_state import SessionDB
from gateway.config import Platform

@pytest.mark.parametrize('thread_id', [None, '', '1'])
def test_root_never_recovers_latest_binding(tmp_path, thread_id):
    db = SessionDB(db_path=tmp_path / 'state.db')
    _seed_two_topic_bindings(db)
    runner = _make_runner(db)
    assert runner._recover_telegram_topic_thread_id(_make_source(thread_id=thread_id)) is None

@pytest.mark.asyncio
async def test_each_root_request_creates_distinct_topic_and_session(tmp_path):
    db = SessionDB(db_path=tmp_path / 'state.db')
    _seed_two_topic_bindings(db)
    runner = _make_runner(db)
    from gateway.session import SessionStore
    runner.session_store = SessionStore(tmp_path / 'sessions', runner.config)
    runner.session_store._db = db
    adapter = runner.adapters[Platform.TELEGRAM]
    adapter._create_dm_topic = AsyncMock(side_effect=[333, 444])
    keys, ids = [], []
    for _ in range(2):
        event = _make_event('synthetic independent request')
        assert await runner._prepare_telegram_topic_request(event)
        source, entry, key = await runner._hmwa_resolve_session(event, event.source)
        assert source.thread_id in {'333', '444'}
        assert entry.session_id not in {'sess-A', 'sess-B'}
        keys.append(key)
        ids.append(entry.session_id)
    assert keys[0] != keys[1]
    assert ids[0] != ids[1]
    assert adapter._create_dm_topic.await_count == 2

@pytest.mark.asyncio
async def test_existing_topic_reply_keeps_route(tmp_path):
    db = SessionDB(db_path=tmp_path / 'state.db')
    _seed_two_topic_bindings(db)
    runner = _make_runner(db)
    event = _make_event('synthetic reply', thread_id='111')
    event.reply_to_message_id = '42'
    assert await runner._prepare_telegram_topic_request(event)
    source, entry, key = await runner._hmwa_resolve_session(event, event.source)
    assert source.thread_id == '111'
    assert entry.session_id == 'sess-A'
    runner.adapters[Platform.TELEGRAM]._create_dm_topic.assert_not_awaited()

@pytest.mark.asyncio
async def test_topic_creation_failure_does_not_fall_back(tmp_path):
    db = SessionDB(db_path=tmp_path / 'state.db')
    _seed_two_topic_bindings(db)
    runner = _make_runner(db)
    event = _make_event('synthetic request')
    assert not await runner._prepare_telegram_topic_request(event)
    assert event.source.thread_id is None

@pytest.mark.asyncio
@pytest.mark.parametrize('text,internal', [('/topic', False), ('wake', True)])
async def test_commands_and_internal_events_do_not_create_topics(tmp_path, text, internal):
    db = SessionDB(db_path=tmp_path / 'state.db')
    _seed_two_topic_bindings(db)
    runner = _make_runner(db)
    event = _make_event(text)
    event.internal = internal
    assert await runner._prepare_telegram_topic_request(event)
    runner.adapters[Platform.TELEGRAM]._create_dm_topic.assert_not_awaited()


@pytest.mark.asyncio
async def test_inbound_creates_topic_before_busy_session_lookup(tmp_path):
    db = SessionDB(db_path=tmp_path / 'state.db')
    _seed_two_topic_bindings(db)
    runner = _make_runner(db)
    event = _make_event('synthetic independent request')
    runner.adapters[Platform.TELEGRAM]._create_dm_topic = AsyncMock(return_value=333)
    runner._hm_admit_event = AsyncMock(return_value=(event, event.source, False))
    runner._hm_estop_gate = lambda *args: None
    runner._hm_pending_reply_intercepts = AsyncMock(return_value=None)
    runner._hm_evict_idle_stale_agent = lambda key: None
    runner._hm_evict_reaped_agent = lambda key: None
    runner._is_session_running = lambda key: True
    runner._hm_handle_running_session_message = AsyncMock(return_value='busy')
    assert await runner._handle_message(event) == 'busy'
    _, source, key = runner._hm_handle_running_session_message.await_args.args
    assert source.thread_id == '333'
    assert key == runner._session_key_for_source(_make_source(thread_id='333'))

@pytest.mark.parametrize('own,reply_chat,reply_topic,reply_is_topic,expected', [
    ('222', 208214988, 111, True, '222'),
    (None, 999, 111, True, None),
    (None, 208214988, 111, False, None),
    (None, 208214988, None, True, None),
])
def test_reply_recovery_requires_explicit_same_chat_topic(own, reply_chat, reply_topic, reply_is_topic, expected):
    from plugins.platforms.telegram.adapter import TelegramAdapter
    chat = SimpleNamespace(type='private', id=208214988)
    reply = SimpleNamespace(chat=SimpleNamespace(type='private', id=reply_chat),
                            message_thread_id=reply_topic, is_topic_message=reply_is_topic)
    message = SimpleNamespace(chat=chat, message_thread_id=own,
                              is_topic_message=own is not None, reply_to_message=reply)
    assert TelegramAdapter._effective_message_thread_id(message) == expected

