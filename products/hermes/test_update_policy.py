"""No live updates: exercise policy, native parser/entry and wrapper failure gates."""
import argparse
import ast
import os
from pathlib import Path
import runpy
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
REPO = Path.home() / '.hermes/hermes-agent'
sys.path.insert(0, str(REPO))
POLICY = runpy.run_path(str(HERE / 'update-policy.py'))

class UpdatePolicyTests(unittest.TestCase):
    def args(self, *argv):
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers(dest='command')
        runpy.run_path(str(REPO / 'hermes_cli/subcommands/update.py'))['build_update_parser'](sub, cmd_update=lambda args: None)
        return parser.parse_args(['update', *argv])

    def test_cli_and_gateway_use_same_stable_wrapper(self):
        for argv in [(), ('--yes',), ('--channel', 'stable')]:
            with self.subTest(argv=argv), patch.dict(os.environ, {'HERMES_HOME': str(Path.home()/'.hermes')}), patch('os.execv', side_effect=SystemExit(0)) as execute:
                with self.assertRaises(SystemExit):
                    POLICY['route'](self.args(*argv), REPO)
                self.assertEqual(execute.call_args.args, (str(HERE/'hermes-update-stable'), [str(HERE/'hermes-update-stable'), 'latest']))

    def test_readonly_and_metadata_stay_native(self):
        for argv in [(' --check'.strip(),), ('--plan',), ('--install-id',), ('--list-venv-holders',), ('--set-channel', 'stable')]:
            with patch('os.execv') as execute:
                self.assertFalse(POLICY['route'](self.args(*argv), REPO))
                execute.assert_not_called()

    def test_unsupported_mutations_and_other_profile_refuse(self):
        for argv in [('--branch', 'main'), ('--channel', 'main'), ('--no-backup',), ('--keep-stash',), ('--no-gateway-restart',)]:
            with patch('os.execv') as execute, self.assertRaises(SystemExit):
                POLICY['route'](self.args(*argv), REPO)
            execute.assert_not_called()
        with patch.dict(os.environ, {'HERMES_HOME': '/not-default'}), self.assertRaises(SystemExit):
            POLICY['route'](self.args(), REPO)

    def test_native_module_guard_precedes_update_work(self):
        tree = ast.parse((REPO/'hermes_cli/main.py').read_text())
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'cmd_update')
        node.decorator_list = []
        node.body = node.body[:5]  # docstring/import/path/missing check/route call
        ns = {'Path': Path, 'PROJECT_ROOT': REPO}
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<guard>', 'exec'), ns)
        with patch('os.execv', side_effect=SystemExit(0)) as execute:
            with self.assertRaises(SystemExit):
                ns['cmd_update'](self.args('--gateway'))
            execute.assert_called_once()
            self.assertEqual(execute.call_args.args[0], '/usr/bin/sudo')
            command = execute.call_args.args[1]
            self.assertIn('/usr/bin/systemd-run', command)
            self.assertIn('.update_exit_code', command[-1])
            self.assertIn('hermes-update-stable', command[-1])

    def test_external_launcher_survives_missing_guard_fail_closed(self):
        with patch.object(Path, 'read_text', return_value='unpatched checkout'), patch('os.execv') as execute:
            with self.assertRaises(SystemExit):
                POLICY['launch'](['update', '--gateway'])
            execute.assert_not_called()

    def test_gateway_spawn_keeps_ipc_exit_status(self):
        tree = ast.parse((REPO/'gateway/slash_commands.py').read_text())
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_spawn_detached_update')
        import shlex, sys
        ns = {'sys': sys, 'shlex': shlex}
        exec(compile(ast.Module(body=[node], type_ignores=[]), '<spawn>', 'exec'), ns)
        with patch('subprocess.Popen') as spawn:
            ns['_spawn_detached_update']([str(Path.home()/'.local/bin/hermes')], Path('/output'), Path('/exit'))
            command = spawn.call_args.args[0][-1]
            self.assertIn('update --gateway', command)
            self.assertIn('> /output 2>&1', command)
            self.assertIn('> /exit', command)

    def test_wrapper_conflict_gate_is_before_success_and_restart(self):
        source = (HERE/'hermes-update-stable').read_text()
        self.assertLess(source.index('HERMES_REPO="$REPO" "$PATCH_SCRIPT"'), source.index('UPDATE_SUCCEEDED=1'))
        self.assertIn('if (( UPDATE_SUCCEEDED )); then', source)
        self.assertIn('gateway was left stopped for inspection', source)

if __name__ == '__main__':
    unittest.main()
