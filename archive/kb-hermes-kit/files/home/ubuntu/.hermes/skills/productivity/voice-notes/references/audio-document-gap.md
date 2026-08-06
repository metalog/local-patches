## Аудио-документы vs голосовые сообщения

### Проблема

Gateway различает три типа аудио-входов:

| Тип | Telegram API | STT | Маркер | Пример |
|-----|-------------|-----|--------|--------|
| `msg.voice` | Голосовое сообщение | ✅ Да | `[The user sent a voice message~...]` | Запись голосового в Telegram |
| `msg.audio` | Аудиофайл (music) | ✅ Да | `[User sent audio: ...]` | Отправка MP3 как аудио |
| `msg.document` audio | Документ с audio MIME/extension | ❌ Нет | ✅ audio attachment note | Файл с диктофона (.aac) |

### Исправление: пустые аудио-документы

Gateway должен классифицировать Telegram `msg.document` с audio MIME/extension
как `MessageType.AUDIO`. Тогда пустое сообщение с `.aac` не теряется: агент
получает context note вида:

```
[The user sent an audio file attachment: '20260619_161944.aac'. It is saved at: /home/ubuntu/.hermes/cache/documents/doc_xxx.aac. ...]
```

Не использовать `gateway.log` как основной механизм: это race-prone и может
взять не тот файл.

### Где в коде

- `gateway/platforms/telegram.py:6191` — обработка `msg.voice`
- `gateway/platforms/telegram.py:6214` — обработка `msg.audio`
- `gateway/platforms/telegram.py:6242` — обработка `msg.document` (без STT)
- `gateway/run.py:8062` — комментарий: "MessageType.AUDIO — never STT"
- `gateway/run.py:8068` — `MessageType.DOCUMENT` исключён из `audio_paths`
- `gateway/run.py:12242` — `_enrich_message_with_transcription()` вызывается только для voice/audio

### Поддерживаемые аудио-расширения в SUPPORTED_DOCUMENT_TYPES

`.aac`, `.mp3`, `.ogg`, `.wav`, `.m4a`, `.flac`, `.opus` — все есть в `gateway/platforms/base.py:1124`, но STT для них не запускается.

### Рабочее решение (без патча gateway)

1. Агент видит один из маркеров:
   - `[The user sent an audio file attachment: 'file.aac'. It is saved at: /path/to/file.aac ...]`
   - `[User sent audio: /path/to/file.aac]`
   - `[The user sent a voice message: /path/to/file.aac]`
2. Запускает STT + pipeline асинхронно:

```bash
cd /home/ubuntu/.hermes/hermes-agent && python3 -c "
from tools.transcription_tools import transcribe_audio
import subprocess, sys

result = transcribe_audio('/путь/к/файлу.aac')
if result['success']:
    transcript = result['transcript']
    proc = subprocess.Popen(
        ['python3', '/home/ubuntu/bin/pipelines/voice-to-kb.py'],
        stdin=subprocess.PIPE, text=True
    )
    proc.communicate(input=transcript)
    print(f'OK: {transcript[:50]}...')
else:
    print(f'ERROR: {result.get(\"error\", \"unknown\")}')
" 2>/dev/null
```

3. Запускать через `terminal(background=true, notify_on_complete=true)`
4. Ответить пользователю сразу: `⏳ Обрабатываю аудио-файл...`
5. По завершении — агент отвечает с результатом

**Задержка:** ~30-60 сек на CPU (large-v3-turbo), но в фоне — сессия не блокируется.

### Нестабильность маркеров

Пустые аудио-документы (без подписи) **не всегда** получают маркер. Gateway иногда кеширует файл, но не добавляет context note в сообщение. Если агент видит пустое `msg=''` с кешем аудио — нужно проверять `gateway.log` на наличие `Cached user document` с audio-расширением и обрабатывать вручную.

### Known issue: typing indicator

Gateway не снимает typing indicator для audio-документов. Метод `stop_typing()` в `base.py` — no-op. Telegram-клиент показывает «печатает» пока сессия активна. Это визуальный баг, не влияет на обработку.

### Gateway patch (если понадобится)

Минимальный патч: `_media_message_type()` должен возвращать `MessageType.AUDIO` для `msg.document` с audio MIME или audio extension. Тогда STT и typing indicator будут работать как для `msg.audio`.
