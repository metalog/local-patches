"""Exercise the actual patch updater on isolated Git clones, never live state."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
SOURCE = Path(os.environ.get('HERMES_PATCH_TEST_SOURCE', '/home/ubuntu/.hermes/hermes-agent'))

class TelegramRoutingReapplyTests(unittest.TestCase):
    def run_script(self, root):
        return subprocess.run(['python3', str(HERE / 'reapply-patches.py')],
            env={**os.environ, 'HERMES_REPO': str(root)}, capture_output=True, text=True)

    def clone(self, root):
        subprocess.run(['git', 'clone', '--quiet', '--shared', str(SOURCE), str(root)], check=True)

    def test_reapply_and_idempotency(self):
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as directory:
            root = Path(directory) / 'repo'
            self.clone(root)
            result = self.run_script(root)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('async def _prepare_telegram_topic_request', (root / 'gateway/run_topics.py').read_text())
            self.assertIn('await self._prepare_telegram_topic_request(event)', (root / 'gateway/run_inbound.py').read_text())
            base = (root / 'gateway/platforms/base.py').read_text()
            self.assertIn('response = await self._message_handler(event)\n        thread_meta = _thread_metadata_for_event(event)', base)
            self.assertIn('_final_thread_metadata = _mark_notify_metadata(_thread_metadata_for_event(event))', base)
            before = subprocess.check_output(['git', '-C', str(root), 'diff'])
            result = self.run_script(root)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(before, subprocess.check_output(['git', '-C', str(root), 'diff']))

    def test_conflict_refuses_before_any_patch_is_written(self):
        with tempfile.TemporaryDirectory(dir=os.environ['TMPDIR']) as directory:
            root = Path(directory) / 'repo'
            self.clone(root)
            target = root / 'gateway/run_topics.py'
            target.write_text(target.read_text().replace('def _recover_telegram_topic_thread_id', 'def changed_upstream_recovery'))
            paths = ['gateway/run_topics.py', 'plugins/platforms/telegram/adapter.py', 'tools/mcp_tool_handlers.py', 'gateway/delivery_ledger.py', 'gateway/platforms/base.py', 'gateway/run_startup.py']
            before = {path: (root / path).read_bytes() for path in paths}
            result = self.run_script(root)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(before, {path: (root / path).read_bytes() for path in paths})

if __name__ == '__main__':
    unittest.main()
