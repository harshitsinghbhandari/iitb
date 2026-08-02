#!/usr/bin/env python3
"""The shell's own check: envelope, exit codes, error mapping, parsing.

Runnable with nothing installed and nothing live::

    python3 tests/check.py

It covers exactly the logic this repo owns and no more. There is no portal
here, no fixture, no recorded response, and no fake core beyond an object
that raises: a check that pretended to know what the core returns would be
asserting the contract against itself. The portal behaviour is verified live
against the real thing, which is the only place it can be verified honestly.
"""

from __future__ import annotations

import io
import json
import os
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from iitb import cli, core  # noqa: E402
from iitb.errors import REGISTRY, CliError  # noqa: E402

failures: list[str] = []


def check(condition, label):
    if not condition:
        failures.append(label)


def run(*argv):
    """Run the CLI in-process. Returns (exit code, parsed stdout or text)."""
    out = io.StringIO()
    with redirect_stdout(out):
        code = cli.main(list(argv))
    text = out.getvalue()
    try:
        return code, json.loads(text)
    except ValueError:
        return code, text


def fails_with(argv, code):
    status, body = run(*argv)
    name, exit_code, message = REGISTRY[code]
    check(isinstance(body, dict), f"{argv}: stdout is not JSON")
    check(body.get("ok") is False, f"{argv}: envelope is not a failure")
    error = body.get("error", {})
    check(error.get("code") == code, f"{argv}: code {error.get('code')} != {code}")
    check(error.get("name") == name, f"{argv}: name {error.get('name')} != {name}")
    check(error.get("message") == message, f"{argv}: message is not the registry's")
    check(status == exit_code, f"{argv}: exit {status} != {exit_code}")


# --- the registry is internally consistent ----------------------------------

seen_names = set()
for code, (name, exit_code, message) in REGISTRY.items():
    check(100 <= code <= 999, f"code {code} is not 3 digits")
    check(exit_code in (0, 1, 2, 3, 4), f"code {code} has exit {exit_code}")
    check(name not in seen_names, f"name {name} is used twice")
    seen_names.add(name)
    check(bool(message.strip()), f"code {code} has no message")
    # Usage errors are the 2xx block and nothing else is, in both directions.
    check(
        (exit_code == 2) == (200 <= code < 300),
        f"code {code} exits {exit_code}, which does not match the 2xx block",
    )

# Exit 3 is one code across the whole surface: an agent needs a single rule,
# which is that exit 3 means go and get the operator.
exit_three = [code for code, row in REGISTRY.items() if row[1] == 3]
check(exit_three == [103], f"exit 3 is {exit_three}, expected only [103]")
check(REGISTRY[103][0] == "sso_session_ended", "103 is not sso_session_ended")
check(REGISTRY[104][1] == 1, "104 browser_unavailable must be exit 1, not exit 3")
check(REGISTRY[498][1] == 4, "498 core_missing must be exit 4")
check(REGISTRY[499][1] == 1, "499 core_failed must be exit 1")

# --- core exception names map to codes without importing the core -----------

for class_name, expected in [
    ("BrowserUnavailable", 104),
    ("SSOCheckFailed", 170),
    ("SSOSessionEnded", 103),
    ("PortalUnreachable", 110),
    ("PortalResponseUnexpected", 112),
    ("JobNotFound", 114),
    ("DownloadTargetExists", 124),
    ("ConfigUnwritable", 191),
    ("ValueError", 499),
    ("SomethingNobodyNamedYet", 499),
]:
    exc = type(class_name, (Exception,), {})()
    got = core.code_for(exc)
    check(got == expected, f"{class_name} mapped to {got}, expected {expected}")

# An explicit code attribute wins over the name, and a nonsense one does not.
tagged = type("Whatever", (Exception,), {})()
tagged.code = 113
check(core.code_for(tagged) == 113, "an explicit .code should win")
tagged.code = 777
check(core.code_for(tagged) == 499, "an unregistered .code should fall back to 499")

# --- usage errors are the envelope, not argparse's stderr -------------------

fails_with([], 200)
fails_with(["nonsense"], 200)
fails_with(["placements"], 200)
fails_with(["placements", "nonsense"], 200)
fails_with(["placements", "job"], 201)
fails_with(["placements", "job", "not-a-number"], 202)
fails_with(["placements", "jobs", "--status", "sideways"], 202)
fails_with(["placements", "deadlines", "--within", "soon"], 202)
fails_with(["placements", "blog", "posts", "--since", "yesterday"], 202)
fails_with(["placements", "blog", "posts", "--page", "0"], 202)
fails_with(["placements", "blog", "post", "12", "--blog", "alumni"], 202)
fails_with(["placements", "fetch", "not-a-url"], 202)
fails_with(["placements", "fetch", "--out"], 201)

# --- --help is text on stdout at exit 0, and it is the verbatim block -------

for argv, block in [
    ([], cli.ROOT_HELP),
    (["browser"], cli.BROWSER_HELP),
    (["browser", "sso-status"], cli.BROWSER_SSO_STATUS_HELP),
    (["downloads", "set-default"], cli.DOWNLOADS_SET_DEFAULT_HELP),
    (["placements"], cli.PLACEMENTS_HELP),
    (["placements", "jobs"], cli.PLACEMENTS_JOBS_HELP),
    (["placements", "job"], cli.PLACEMENTS_JOB_HELP),
    (["placements", "deadlines"], cli.PLACEMENTS_DEADLINES_HELP),
    (["placements", "applications"], cli.PLACEMENTS_APPLICATIONS_HELP),
    (["placements", "blog"], cli.PLACEMENTS_BLOG_HELP),
    (["placements", "blog", "posts"], cli.PLACEMENTS_BLOG_POSTS_HELP),
    (["placements", "blog", "post"], cli.PLACEMENTS_BLOG_POST_HELP),
    (["placements", "fetch"], cli.PLACEMENTS_FETCH_HELP),
]:
    label = " ".join(["iitb"] + argv + ["--help"])
    status, text = run(*argv, "--help")
    check(status == 0, f"{label}: exit {status} != 0")
    check(isinstance(text, str), f"{label}: printed JSON, not text")
    check(text.strip() == block.strip(), f"{label}: is not the verbatim block")

# Every leaf in the tree has help. Walk it rather than trusting the list above.
def leaves(parser, path=()):
    actions = [a for a in parser._actions if hasattr(a, "choices") and a.choices]
    subparsers = [a for a in actions if hasattr(a, "_name_parser_map")]
    if not subparsers:
        yield path
        return
    for name, child in subparsers[0]._name_parser_map.items():
        yield from leaves(child, path + (name,))


tree = list(leaves(cli.build_parser()))
check(len(tree) == 13, f"the tree has {len(tree)} leaves, expected 13")
for path in tree:
    status, text = run(*path, "--help")
    check(status == 0, f"iitb {' '.join(path)} --help: exit {status} != 0")
    check(len(str(text)) > 120, f"iitb {' '.join(path)} --help: help is too thin")

# --- a missing core is exit 4, and a missing placements core is too ---------

sys.modules["iitb_core"] = None  # type: ignore[assignment]
sys.modules["iitb_core.placements"] = None  # type: ignore[assignment]
fails_with(["placements", "applications"], 498)
fails_with(["browser", "status"], 498)
del sys.modules["iitb_core"], sys.modules["iitb_core.placements"]

# --- downloads: the setting round-trips, and fetch needs it ----------------

with tempfile.TemporaryDirectory() as home:
    real_home = os.environ.get("HOME")
    os.environ["HOME"] = home
    try:
        # No default configured: fetch is 203 at exit 2, before any network.
        fails_with(["placements", "fetch", "https://example.invalid/a.pdf"], 203)

        target = Path(home) / "Downloads" / "iitb"
        status, body = run("downloads", "set-default", str(target))
        check(status == 0, f"set-default: exit {status} != 0")
        check(body.get("ok") is True, "set-default: envelope is not a success")
        check(
            body["data"]["downloadDir"] == str(target.resolve()),
            "set-default: stored path is not the resolved absolute one",
        )
        check(body["data"]["created"] is True, "set-default: should have created it")
        check(target.is_dir(), "set-default: directory was not created")

        from iitb import config

        check(
            config.download_dir() == target.resolve(),
            "the stored default did not round-trip",
        )
        # With a default set, fetch gets past 203 and reaches the core, which
        # is absent in this check, so 498 is the right next failure.
        sys.modules["iitb_core"] = None  # type: ignore[assignment]
        sys.modules["iitb_core.placements"] = None  # type: ignore[assignment]
        fails_with(["placements", "fetch", "https://example.invalid/a.pdf"], 498)
        del sys.modules["iitb_core"], sys.modules["iitb_core.placements"]

        # A path that is a file, not a directory, is a usage error.
        occupied = Path(home) / "file.txt"
        occupied.write_text("x", encoding="utf-8")
        fails_with(["downloads", "set-default", str(occupied)], 202)

        # Unparseable settings are 190, not a crash and not a silent reset
        # to "no default", which would send a download somewhere unexpected.
        (Path(home) / ".config" / "iitb" / "config.json").write_text("{[", "utf-8")
        fails_with(["placements", "fetch", "https://example.invalid/a.pdf"], 190)
    finally:
        if real_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = real_home

# --- a CliError carries detail only when there is one ----------------------

check("detail" not in CliError(103).as_error(), "an empty detail should be dropped")
check(
    CliError(103, detail="x").as_error()["detail"] == "x",
    "a detail should survive into the error object",
)

# --- the shell imports nothing that implies a portal -----------------------
# A dependency says what the core does even when no string does. The one
# leak guard that can live in a public repo is the one whose own text gives
# nothing away: a list of forbidden portal field names would publish the
# field names. That check belongs to the human running the leak checklist
# against the diff, and to the private repo, not here.

source = "\n".join(
    path.read_text(encoding="utf-8")
    for path in (Path(__file__).resolve().parent.parent / "src").rglob("*.py")
)
for banned in ("import requests", "import httpx", "import urllib.request",
               "from bs4", "import lxml", "import selenium", "import cdp"):
    check(banned not in source, f"the shell must not {banned}")

# ---------------------------------------------------------------------------

if failures:
    print(f"FAILED ({len(failures)}):", file=sys.stderr)
    for failure in failures:
        print(f"  {failure}", file=sys.stderr)
    sys.exit(1)
print("ok: envelope, exit codes, error mapping, parsing, help, downloads")
