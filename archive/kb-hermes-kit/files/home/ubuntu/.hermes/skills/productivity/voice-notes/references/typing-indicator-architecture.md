# Gateway Typing Indicator — архитектура и root cause

## Жизненный цикл typing в gateway

### Запуск
В `gateway/platforms/base.py:4182` при обработке каждого входящего сообщения создаётся фоновая задача:
```python
typing_task = asyncio.create_task(
    self._keep_typing(event.source.chat_id, stop_event=interrupt_event, ...)
)
```

### Цикл `_keep_typing` (base.py:3147)
- Отправляет `send_typing(chat_id)` каждые **2 секунды**
- Каждый вызов ограничен таймаутом ~1.5с (чтобы медленная сеть не сдвигала cadence)
- Проверяет `_typing_paused` — пропускает отправку если chat_id в этой множестве
- Прерывается через `stop_event` (interrupt) или `CancelledError`

### Остановка
В `finally` блоке `base.py:4573`:
```python
await _stop_typing_task()
```
Который вызывает `_stop_typing_refresh` (base.py:3229):
1. Добавляет chat_id в `_typing_paused`
2. Отменяет `typing_task` через `.cancel()`
3. Ждёт завершения с таймаутом 0.5с
4. Вызывает `stop_typing(chat_id)` на платформе

### Telegram `stop_typing` — no-op
`telegram.py` не переопределяет `stop_typing()`. Базовый класс (base.py:2606):
```python
async def stop_typing(self, chat_id: str) -> None:
    """Stop a persistent typing indicator — no-op for one-shot platforms."""
    pass
```
**Telegram Bot API не имеет действия «отменить печатание».** Typing-indicator одноразовый — истекает через ~5 секунд.

## Где typing перезапускается после остановки

`telegram.py:2577-2578` — после КАЖДОГО `send()`:
```python
# Re-trigger typing indicator after sending a message.
await self.send_typing(chat_id, metadata=metadata)
```
**Цель:** чтобы typing не пропадал между промежуточными сообщениями (прогресс-репорты, tool output).

**Следствие:** даже после `_stop_typing_task()`, если что-то вызывает `send()` — typing запускается заново. Последний `sendTyping` протухает через ~5с, но если агент ещё работает и шлёт сообщения — typing держится.

## Диагностические точки

| Что искать | Где |
|---|---|
| Запуск typing loop | `base.py:4182` — `asyncio.create_task(self._keep_typing(...))` |
| Остановка typing loop | `base.py:4573` — `await _stop_typing_task()` в `finally` |
| re-trigger typing | `telegram.py:2578` — `await self.send_typing()` после `send()` |
| rich-result re-trigger | `telegram.py:2352` — `await self.send_typing()` после успешного rich send |
| `stop_typing` no-op | `base.py:2606` — `pass` |
| `_typing_paused` set | `base.py:1913` —用于 approval waits и typing stop |
| interrupt event | `base.py:4170` — `self._active_sessions[session_key]` |

## Предлагаемый патч

**Убрать `send_typing()` из `telegram.py:send()`** — оставить только в `_keep_typing` цикле.

Тогда typing живёт ровно столько, сколько работает агент. После отмены цикла — последний typing протухает за ~5с.

**Потенциальный побочный эффект:** typing будет пропадать между промежуточными сообщениями (прогресс-репорты вроде «Проверяю: ...»). Нужно проверить, насколько это заметно в реальном использовании.

**Не патчить без понимания:** rich-result path (line 2352) тоже вызывает `send_typing()` — он нужен для multi-part ответов где rich formatting отправляется частями.
