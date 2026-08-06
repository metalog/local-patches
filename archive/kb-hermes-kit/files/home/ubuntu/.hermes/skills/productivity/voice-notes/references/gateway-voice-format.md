## Gateway voice message format

Source: `gateway/run.py` → `_enrich_message_with_transcription()`

### Successful transcription (line 12296-12298)

```python
f'[The user sent a voice message~ '
f'Here\'s what they said: "{transcript}"]'
```

Result: `[The user sent a voice message~ Here's what they said: "транскрипция"]`

### Error patterns

- No STT provider: `[The user sent a voice message but I can't listen to it right now — no STT provider is configured.]`
- Transcription error: `[The user sent a voice message but I had trouble transcribing it~ (ошибка)]`
- General error: `[The user sent a voice message but something went wrong when I tried to listen to it~ Let them know!]`

### Echo to user (line 8111-8115)

After successful STT, gateway sends echo message to user:

```python
f'🎙️ "{_tx}"'
```

### Message assembly (line 12332-12341)

Transcription prefix is prepended to user text:
- If user text is placeholder `(The user sent a message with no text content)` → replaced with prefix
- If user text exists → `prefix\n\nuser_text`
- If no user text → just prefix

### Audio document note

When an audio file is sent as a Telegram document (e.g. `.aac` from dictaphone),
Telegram gateway classifies it as `MessageType.AUDIO`. Normal inbound processing
prepends an audio attachment note with the saved local path:

```
[The user sent an audio file attachment: '20260619_161944.aac'. It is saved at: /home/ubuntu/.hermes/cache/documents/doc_xxx.aac. ...]
```

Queued media placeholders may still use `[User sent audio: /path]`.

### STT parameters

- Provider: local (faster-whisper)
- Model: large-v3-turbo
- Device: cpu
- Precision: int8
- Language: ru
- Session blocks during STT (10-30 sec on CPU)
- **STT НЕ запускается для `msg.document`** — только для `msg.voice` и `msg.audio`
