# cptr local patches

## Android terminal input

[`patches/android-terminal-input.patch`](patches/android-terminal-input.patch)
works around xterm.js/Android IME buffering and makes the mobile shortcut bar's
sticky Ctrl key deterministic. It is currently verified with cptr `0.9.21`.

The workaround uses a password input on touch devices to disable predictive IME
composition. Firefox may consequently offer password autofill in the terminal;
this is a known tradeoff.

## Reapply after a cptr upgrade

Clone or update the matching cptr source and run:

```sh
./products/cptr/rebuild-frontend.sh /path/to/computer-source
```

The script fails closed when the patch no longer applies, builds the frontend,
backs up the installed build, installs the patched build, and restarts the user
service. Review the patch against upstream instead of forcing it after a failed
`git apply --check`.
