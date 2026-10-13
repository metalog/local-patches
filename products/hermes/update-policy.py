#!/usr/bin/env python3
"""External, fail-closed local update policy shared by CLI and gateway.

Normal updates use the stable wrapper (backup/stash, exact release, atomic
patch preflight, validation, THEN restart). Native read-only/metadata operations
remain native; unsupported mutation flags are rejected rather than ignored.
"""
import os
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
READ_ONLY = {"check", "plan", "list_venv_holders", "install_id"}
ALLOWED = {"gateway", "yes", "channel"}


def route(args, repo):
    if any(getattr(args, key, False) for key in READ_ONLY) or getattr(args, "set_channel", None):
        return False
    root = Path(repo).resolve()
    home = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes")).resolve()
    if root != (Path.home() / ".hermes/hermes-agent").resolve() or home != (Path.home() / ".hermes").resolve():
        raise SystemExit("Local stable updater is scoped to the default installation/profile; refusing update")
    unsupported = [key for key, value in vars(args).items()
                   if value and key not in ALLOWED | {"func", "command"}]
    if unsupported or getattr(args, "channel", None) not in (None, "stable"):
        raise SystemExit("Local patch policy refuses unsupported update options: " + ", ".join(unsupported or ["channel"]))
    wrapper = HERE / "hermes-update-stable"
    if not os.access(wrapper, os.X_OK):
        raise SystemExit("Local stable updater missing; refusing native update")
    print("Local patch policy: latest stable release; patches validated before restart", flush=True)
    if getattr(args, "gateway", False):
        # setsid does not escape KillMode=mixed's service cgroup. Put the
        # updater AND its exit-code writer in a separate transient system unit.
        import shlex
        import getpass
        command = (f"{shlex.quote(str(wrapper))} latest >> {shlex.quote(str(home / '.update_output.txt'))} 2>&1; "
                   f"rc=$?; printf '%s' \"$rc\" > {shlex.quote(str(home / '.update_exit_code'))}; exit \"$rc\"")
        os.execv("/usr/bin/sudo", ["sudo", "-n", "/usr/bin/systemd-run", "--collect", "--wait",
                 "--unit=hermes-local-update-" + str(os.getpid()),
                 "--uid=" + getpass.getuser(), "--setenv=HERMES_HOME=" + str(home),
                 "--setenv=HOME=" + str(Path.home()), "/bin/bash", "-c", command])
    os.execv(str(wrapper), [str(wrapper), "latest"])


def launch(argv):
    # Let the authoritative native parser handle profiles, flags and help. The
    # source cmd_update guard calls route; this external entry survives checkout
    # replacement and refuses mutating updates if that guard was lost.
    repo = Path.home() / ".hermes/hermes-agent"
    source = (repo / "hermes_cli/main.py").read_text()
    if "# HERMES_LOCAL_UPDATE_POLICY" not in source and "update" in argv:
        raise SystemExit("Local update guard missing; reapply local patches before updating")
    os.execv(str(repo / ".hermes/bin/hermes"), [str(repo / ".hermes/bin/hermes"), *argv])


if __name__ == "__main__":
    launch(sys.argv[1:])
