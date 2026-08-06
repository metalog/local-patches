# Hermes ovh-new local kit

Переносимый набор локальных доработок Hermes для `ovh-new`.

Содержит:

- `~/.hermes/local-patches/` - idempotent reapply script и patch snapshots.
- `~/bin/hermes-update-local` - wrapper для `hermes update` с повторным применением локальных патчей и restart gateway.
- `~/bin/reapply-hermes-local-patches` - ручной reapply entrypoint.
- `~/bin/pipelines/audio-to-kb.py` и `voice-to-kb.py` - voice note ingest в `kb/fleeting`.
- `~/.hermes/skills/productivity/voice-notes/` - Hermes skill для голосовых заметок.

Восстановление на новой VM:

```bash
cd ~/src/github.com/afpsy/kb/docs/ops/hermes-ovh-new
./install.sh
~/bin/reapply-hermes-local-patches
sudo -n systemctl restart hermes-gateway
```

После восстановления проверить:

```bash
cd ~/.hermes/hermes-agent
. venv/bin/activate
pytest tests/gateway/test_telegram_audio_vs_voice.py tests/gateway/test_telegram_rich_messages.py -q
```

Важно:

- Секреты и `~/.hermes/config.yaml` сюда не входят.
- Перед `install.sh` Hermes должен быть уже установлен в `~/.hermes/hermes-agent`.
- `audio-to-kb.py` ожидает `~/src/github.com/afpsy/kb` на хосте.
- Для обновления Hermes использовать `hermes-update-local`, а не голый `hermes update`.
