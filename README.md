# iitb

> ### This repository is the open shell only. It is not usable on its own.
>
> Everything the portals actually need lives in `iitb-core`, a separate
> protected runtime. `iitb-core` is not publicly available, it is not
> distributed here, and it is not on PyPI or any other index. Without it this
> CLI does not function: every portal command answers error 498 `core_missing`
> at exit 4, which is a clean refusal rather than a crash. `pip install iitb`
> does not give you a working tool. Nothing in this repo will change that.
>
> A binarized `iitb-core` may be granted to people affiliated with IIT Bombay
> who write in, solely at the author's discretion. That discretion is
> absolute: asking is not a claim on it, there is no queue, and there is no
> timeline. The address is dev@theharshitsingh.com, which is also the only
> contact address for this project.

An agent-first command line over the IIT Bombay portals: placements, Moodle,
and mail. Everything prints one JSON object on stdout and nothing else, so an
agent never has to parse prose.

**It only reads.** No command in this CLI changes anything on an IITB server.
It never applies to a job or withdraws an application, never starts a quiz
attempt, submits an assignment, posts in a forum or marks anything done, and
never sends, deletes, moves or files an email. Reading a message does not even
mark it read. That is a property of the whole surface rather than a default:
there is no flag anywhere that turns writing on.

**What is here is the shape of the CLI**, which is the part worth reading and
the part worth copying: the command tree, the help text, the output envelope
and the error-code registry, and nothing about the portals themselves.

## The envelope

```
success   {"ok": true, "data": ...}                     exit 0
failure   {"ok": false, "error": {"code", "name",
                                  "message", "detail"}}
--help    plain text                                    exit 0
```

Exit codes: `0` success, `1` the operation failed, `2` you called the
command wrong, `3` only the operator can restore access and `error.name`
says which door to send them to (`sso_session_ended` is
`iitb browser login`; `mail_not_configured` and `mail_token_rejected` are
`iitb mail login`), `4` the core is missing or incompatible.

That holds on every exit path, not just the ones with a code. Anything
unexpected comes back as error 105 `internal_error` at exit 1, with the
traceback appended to a log under `~/.config/iitb/` that the error names, so
a bug is something a caller can parse and report rather than a silent
non-zero exit.

`iitb version` reports the installed `iitb` and `iitb-core` versions, which
are the two numbers a bug report needs. `iitb --version` answers the same
object and points back at the command.

## The tree

```
iitb browser     start, attach, status, sso-status, stop, login
iitb placements  jobs, job, deadlines, applications, blog posts, blog post
iitb moodle      courses, course, deadlines, grades, fetch
iitb mail        login, mailboxes, list, read, fetch
iitb downloads   set-default
iitb version
```

Some tasks it is built to answer:

```
iitb placements deadlines --within 48h --eligible
iitb placements jobs --status open --company acme
iitb moodle deadlines --announcements 10
iitb moodle course "XX 101" --no-content
iitb mail list --unseen --since 2026-08-01
```

`--help` is the documentation. The whole tree is discoverable from it, which
is the property this CLI is built around: a fresh agent session with no
context should be able to work the portals from `iitb --help` alone.

```
iitb --help
```

## Running it

The shell is argparse plus one import of `iitb-core`, and `iitb-core` is
protected: it is not on PyPI, not on any public index, and not distributed. So
`pip install iitb` will not give you a working CLI, and nothing here pretends
otherwise. The dependency is declared because it is real, not because it
resolves. Obtaining a core at all is the notice at the top of this file.

With the core present, the shell installs against it:

```
uv tool install --editable ./iitb --with-editable <path to the core>
```

Without the core, every portal command answers error 498 `core_missing` at
exit 4, which is the honest result rather than a crash. `--help` and the
argument parsing work regardless, and so does the check below.

## Check

```
python3 tests/check.py
```

No dependencies, no network, no browser, and no core needed. It covers what
this repo owns: the envelope, the error-code registry, the exit-code mapping,
argument parsing, that no command anywhere in the tree accepts a secret as an
argument, that no institute hostname or url is in the source, and that every
`--help` in the tree prints its block verbatim. Portal behaviour is verified
live against the real thing, because that is the only place it can be verified
honestly.

## Layout

```
src/iitb/cli.py      the command tree, the help text, dispatch
src/iitb/errors.py   the error-code registry: code, name, exit code, message
src/iitb/core.py     the one seam into the private core
src/iitb/config.py   settings under ~/.config/iitb/
```

No portal knowledge lives in this repo, and none ever will. No hostname, no
endpoint, no selector, no session mechanic. The shell does not know what the
core does, only how to ask it and how to report what came back.

## Reporting a failure

Email dev@theharshitsingh.com. Do not open a GitHub issue and do not paste
command output into one: a useful report contains portal data, and an issue
is public and permanent.

## Licence

Apache-2.0. See [LICENSE](LICENSE).
