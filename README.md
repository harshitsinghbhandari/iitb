# iitb

A CLI for IITB portals, built agent-first.

This repo is the command surface: the command tree, help text, and output
conventions. The implementation lives in a private core package.

Everything prints one JSON object on stdout and nothing else, so an agent
never has to parse prose:

```
success   {"ok": true, "data": ...}                     exit 0
failure   {"ok": false, "error": {"code", "name",
                                  "message", "detail"}}
--help    plain text                                    exit 0
```

Exit codes: `0` success, `1` the operation failed, `2` you called the
command wrong, `3` the operator's IITB single sign-on has ended and only
they can restore it, `4` the core is missing or incompatible.

## Install

The shell depends on `iitb-core`, which is not published. Clone both repos
side by side and install the shell with the core alongside it:

```
uv tool install --editable ./iitb --with-editable ./iitb-core
```

That puts `iitb` on your PATH. Then:

```
iitb --help
```

`--help` is the documentation. The whole tree is discoverable from it, which
is the property this CLI is built around: a fresh agent session with no
context should be able to work the portals from `iitb --help` alone.

## Check

```
python3 tests/check.py
```

No dependencies, no network, no browser. It covers what this repo owns: the
envelope, the error-code registry, the exit-code mapping, argument parsing,
and that every `--help` in the tree prints its block verbatim. Portal
behaviour is verified live against the real thing, because that is the only
place it can be verified honestly.

## Layout

```
src/iitb/cli.py      the command tree, the help text, dispatch
src/iitb/errors.py   the error-code registry: code, name, exit code, message
src/iitb/core.py     the one seam into the private core
src/iitb/config.py   settings under ~/.config/iitb/
```

No portal knowledge lives in this repo, and none ever will. The shell is
argparse plus one import; it does not know what the core does, only how to
ask it and how to report what came back.

## Reporting a failure

Email dev@theharshitsingh.com. Do not open a GitHub issue and do not paste
command output into one: a useful report contains portal data, and an issue
is public and permanent.
