#_kb-repo-conventions

## Расположение

`~/src/github.com/afpsy/kb` — git-репозиторий.

## Структура

```
kb/
├── fleeting/     — быстрые заметки (голосовые, ручные, draft)
├── quotes/       — цитаты из источников
├── src/          — исходные пакеты (raw-материалы)
├── docs/         — контракты, архитектура, playbook'и
├── prompts/      — промпты
├── scripts/      — скрипты (extract, inspect)
├── apps/         — приложения
└── README.md
```

## Frontmatter для fleeting-заметок

```yaml
---
id: "UUIDv7"          # python3 -c "import uuid; print(uuid.uuid1())"
title: "Название"
date: YYYY-MM-DD
updated_at: ISO8601   # date --iso-8601=seconds
flavour: normal
source: voice          # или hand, import, и т.д.
ingest_status: draft
---
```

## Flavour (роль заметки)

- `normal` — обычная атомарная заметка
- `hub` — структурная заметка/MOC
- `bib` — библиографический источник
- `lit` — заметка по чтению
- `quote` — чистая цитата
- `author` — заметка об авторе

Для голосовых заметок используется `flavour: normal`.

## Именование файлов fleeting/

`YYYY-MM-DD HH:MM <Название>.md` — дата и время + краткое название (5–10 слов).

## Git-workflow

- Всегда `git pull --rebase` перед коммитом — репа активная, часто обновляется.
- Коммит: `voice: <Название>` для голосовых заметок.
- Пуш immediately после коммита.

## Ссылки

- Контракты: `docs/contracts/ingest-contract.md`, `docs/contracts/note-flavours.md`
- Архитектура: `docs/ingest-architecture.md`
- Источник: `README.md` в корне репы
