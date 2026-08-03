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

# The moodle block. Every one of them is operational: the surface adds no exit
# 3 and no usage code of its own, which is the property the block was designed
# around and the one a later edit is most likely to break by promoting a
# session failure to exit 3.
for code in range(140, 150):
    check(code in REGISTRY, f"moodle code {code} is missing from the registry")
    check(REGISTRY[code][1] == 1, f"moodle code {code} is not exit 1")
check(
    not any(240 <= code < 270 for code in REGISTRY),
    "240-269 is reserved for moodle usage and was ruled deliberately empty",
)

# --- core exception names map to codes without importing the core -----------

for class_name, expected in [
    ("BrowserUnavailable", 104),
    ("SSOCheckFailed", 170),
    ("SSOSessionEnded", 103),
    ("PortalUnreachable", 110),
    ("PortalResponseUnexpected", 112),
    ("JobNotFound", 114),
    ("DownloadTargetExists", 124),
    ("CourseNotFound", 140),
    ("CourseAmbiguous", 141),
    ("MoodleUnreachable", 142),
    # The acronym case, which the naive slug rule gets wrong: this must not
    # come out as moodle_h_t_t_p_error and fall through to 499.
    ("MoodleHTTPError", 143),
    ("MoodleResponseUnexpected", 144),
    ("MoodleSessionRecoveryFailed", 145),
    ("CourseStructureUnavailable", 146),
    ("ActivityNotFound", 147),
    ("ActivityHasNoFile", 148),
    ("GradeReportUnavailable", 149),
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
# A posting is named by id, or by company and job code together. Half of the
# pair is 201 and both routes at once is 204, and neither reaches the core.
fails_with(["placements", "job", "--job-code", "7"], 201)
fails_with(["placements", "job", "--company", "acme"], 201)
fails_with(["placements", "job", "12", "--job-code", "7"], 204)
fails_with(["placements", "job", "12", "--company", "acme"], 204)
fails_with(["placements", "job", "12", "--company", "acme", "--job-code", "7"], 204)
fails_with(["placements", "jobs", "--status", "sideways"], 202)
fails_with(["placements", "deadlines", "--within", "soon"], 202)
fails_with(["placements", "blog", "posts", "--since", "yesterday"], 202)
fails_with(["placements", "blog", "posts", "--page", "0"], 202)
fails_with(["placements", "blog", "post", "12", "--blog", "alumni"], 202)

# moodle. A course is a string on purpose, so "not a number" is not a usage
# error here: the positional takes an id or a code and only the live enrolment
# can tell which. What is a usage error is a missing course, a type that is not
# a type, a count that is not a count, and the one pair of flags that has no
# reading. None of these may reach the core.
fails_with(["moodle"], 200)
fails_with(["moodle", "nonsense"], 200)
fails_with(["moodle", "course"], 201)
fails_with(["moodle", "course", "XX 101", "--include", "nope"], 202)
# "unmapped" is a result, not a request, so it is not includable either.
fails_with(["moodle", "course", "XX 101", "--include", "file,unmapped"], 202)
fails_with(["moodle", "course", "XX 101", "--include", ""], 202)
fails_with(["moodle", "course", "XX 101", "--no-content", "--include", "file"], 204)
fails_with(["moodle", "deadlines", "--announcements", "five"], 202)
fails_with(["moodle", "deadlines", "--announcements", "-1"], 202)
fails_with(["moodle", "deadlines", "--since", "yesterday"], 202)
fails_with(["moodle", "fetch"], 201)
fails_with(["moodle", "fetch", "not-an-id-or-a-url"], 202)

# The values that must survive the parse rather than being rejected by it.
parsed = cli.build_parser().parse_args(
    ["moodle", "deadlines", "XX 101", "--announcements", "0"]
)
check(parsed.announcements == 0, "--announcements 0 did not survive the parse")
check(parsed.course == "XX 101", "a course with a space did not survive the parse")
parsed = cli.build_parser().parse_args(["moodle", "deadlines"])
check(
    parsed.announcements == cli.DEFAULT_ANNOUNCEMENTS and parsed.course is None,
    "deadlines with no argument did not default to every course at the default depth",
)
check(
    cli.include_types(" file , assignment ") == ["file", "assignment"],
    "--include did not split on commas and strip whitespace",
)
check(
    "unmapped" not in cli.INCLUDE_CHOICES,
    "unmapped is a result, not a type --include may ask for",
)

# --- browser login: the seam it calls, and the two answers it maps ---------
# The command blocks on a human, so the half this repo owns is the wiring on
# either side of that wait: it calls one core seam with no arguments, a session
# comes back as a success carrying the user, and a sign-in that never happened
# is exit 3 with 103, the same code every other surface uses for "go and get
# the operator". The core is replaced here, so nothing opens a window and
# nothing waits five minutes for one.

answer: dict = {}
reached = []
canonical_call = core.call
try:
    core.call = lambda *a, **k: reached.append((a, k)) or answer

    answer = {"logged_in": True, "user": "someone", "detail": "live"}
    status, body = run("browser", "login")
    check(status == 0, f"browser login: exit {status} != 0")
    check(
        reached == [((cli.BROWSER, "login"), {})],
        f"browser login called {reached}, not the login seam with no arguments",
    )
    check(
        body.get("data") == {"loggedIn": True, "user": "someone"},
        f"browser login returned {body.get('data')}, not the session and its user",
    )

    # Not signed in is not a truthful exit 0 with a false field: an agent must
    # never have to read a field to find out that it needs a human.
    answer = {"logged_in": False, "user": None, "detail": "the window was closed"}
    fails_with(["browser", "login"], 103)
    status, body = run("browser", "login")
    check(
        body.get("error", {}).get("detail") == "the window was closed",
        "browser login dropped the core's runtime detail",
    )
finally:
    core.call = canonical_call

# The public message is where the operator is told what to run, so the command
# name has to be in it: a 103 that does not name `iitb browser login` leaves an
# agent to invent the remedy.
check(
    "iitb browser login" in REGISTRY[103][2],
    "the 103 message does not name `iitb browser login`",
)
check(
    "iitb browser login" in cli.ROOT_HELP,
    "the root help does not name `iitb browser login`",
)

# --- --help is text on stdout at exit 0, and it is the verbatim block -------

for argv, block in [
    ([], cli.ROOT_HELP),
    (["browser"], cli.BROWSER_HELP),
    (["browser", "login"], cli.BROWSER_LOGIN_HELP),
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
    (["moodle"], cli.MOODLE_HELP),
    (["moodle", "courses"], cli.MOODLE_COURSES_HELP),
    (["moodle", "course"], cli.MOODLE_COURSE_HELP),
    (["moodle", "deadlines"], cli.MOODLE_DEADLINES_HELP),
    (["moodle", "grades"], cli.MOODLE_GRADES_HELP),
    (["moodle", "fetch"], cli.MOODLE_FETCH_HELP),
    (["version"], cli.VERSION_HELP),
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
check(len(tree) == 19, f"the tree has {len(tree)} leaves, expected 19")
for path in tree:
    status, text = run(*path, "--help")
    check(status == 0, f"iitb {' '.join(path)} --help: exit {status} != 0")
    check(len(str(text)) > 120, f"iitb {' '.join(path)} --help: help is too thin")

# --- a missing core is exit 4, and a missing placements core is too ---------

sys.modules["iitb_core"] = None  # type: ignore[assignment]
sys.modules["iitb_core.placements"] = None  # type: ignore[assignment]
sys.modules["iitb_core.moodle"] = None  # type: ignore[assignment]
fails_with(["placements", "applications"], 498)
fails_with(["browser", "status"], 498)
fails_with(["moodle", "courses"], 498)
del sys.modules["iitb_core"], sys.modules["iitb_core.placements"]
del sys.modules["iitb_core.moodle"]

# --- downloads: the setting round-trips and survives being read back -------
# No v1 command downloads, so the setting is exercised through the command that
# writes it and the accessor a download command will read it with, rather than
# through a consumer that does not exist yet.

with tempfile.TemporaryDirectory() as home:
    real_home = os.environ.get("HOME")
    os.environ["HOME"] = home
    try:
        from iitb import config

        check(config.download_dir() is None, "an unset default should read as None")

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

        check(
            config.download_dir() == target.resolve(),
            "the stored default did not round-trip",
        )
        # Round-tripping through this module proves nothing about the seam: the
        # core resolves the same setting out of the same file whenever it is not
        # handed one, so the key on disk is a shared contract and this pins it.
        # Spelt differently on the two sides, `set-default` writes a setting the
        # core never finds, and every check above still passes.
        stored = json.loads(
            (Path(home) / ".config" / "iitb" / "config.json").read_text("utf-8")
        )
        check(
            stored.get("downloadsDir") == str(target.resolve()),
            f"set-default wrote {sorted(stored)}, not the key the core reads",
        )

        # `moodle fetch` is the setting's first consumer, and the half of it
        # this repo owns is: no --out and no default is 203, decided before
        # anything touches the network. The core is replaced here so that a
        # regression shows up as "it called the core" rather than as a browser
        # starting during a check that is supposed to need nothing live.
        reached = []
        canonical_call = core.call
        try:
            core.call = lambda *a, **k: reached.append((a, k)) or {}

            (Path(home) / ".config" / "iitb" / "config.json").unlink()
            fails_with(["moodle", "fetch", "12"], 203)
            check(not reached, "fetch reached the core with nowhere to write")

            run("downloads", "set-default", str(Path(home) / "dl"))
            status, body = run("moodle", "fetch", "12")
            check(status == 0, f"fetch with a default configured: exit {status} != 0")
            check(len(reached) == 1, "fetch with a default did not reach the core")
            # --out is passed through untouched: resolving it, including the
            # per-portal subfolder under the default, is the core's job.
            check(
                reached and reached[0][1].get("out") is None,
                "fetch invented an --out instead of leaving the default to the core",
            )
            reached.clear()
            run("moodle", "fetch", "12", "--out", "/tmp/x", "--force")
            check(
                reached and reached[0][1] == {"target": "12", "out": "/tmp/x", "force": True},
                f"fetch passed {reached and reached[0][1]} to the core",
            )
        finally:
            core.call = canonical_call

        # A path that is a file, not a directory, is a usage error.
        occupied = Path(home) / "file.txt"
        occupied.write_text("x", encoding="utf-8")
        fails_with(["downloads", "set-default", str(occupied)], 202)

        # Unparseable settings are 190, not a crash and not a silent reset
        # to "no default", which would send a download somewhere unexpected.
        (Path(home) / ".config" / "iitb" / "config.json").write_text("{[", "utf-8")
        try:
            config.download_dir()
            check(False, "unreadable settings did not raise")
        except CliError as exc:
            check(exc.code == 190, f"unreadable settings raised {exc.code}, not 190")
    finally:
        if real_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = real_home

# --- version is JSON on both routes, and --version points at the command ---

# This check runs with nothing installed as happily as it runs inside the
# install, and `version` answers differently in the two: an absent core is 498
# at exit 4, which is the failure the command exists to diagnose rather than a
# null version reported as a success. Both readings are checked, whichever one
# the environment running this is in.

if cli.installed("iitb-core") is None:
    fails_with(["version"], 498)
    fails_with(["--version"], 498)
else:
    status, body = run("version")
    check(status == 0, f"version: exit {status} != 0")
    check(body.get("ok") is True, "version: envelope is not a success")
    check(
        set(body.get("data", {})) == {"iitb", "iitb_core"},
        f"version: data is {sorted(body.get('data', {}))}, not both versions",
    )

    status, flagged = run("--version")
    check(status == 0, f"--version: exit {status} != 0")
    check(flagged.get("ok") is True, "--version: envelope is not a success")
    check(
        flagged.get("data", {}).get("use") == "iitb version",
        "--version does not point at the canonical command",
    )
    check(
        flagged.get("data", {}).get("iitb_core") == body.get("data", {}).get("iitb_core"),
        "--version and `version` disagree about the core version",
    )

# --version must never fall through to unknown_command, installed or not.
status, body = run("--version")
check(
    body.get("error", {}).get("name") != "unknown_command",
    "--version fell through to unknown_command",
)
check("iitb version" in cli.ROOT_HELP, "`iitb version` is not in the root help")
check("--version" in cli.ROOT_HELP, "`--version` is not in the root help")
check("iitb version" in cli.VERSION_HELP, "the version help does not name its command")

# --- every exit path prints one object, including the ones nobody planned --
# The defect this guards against is a non-zero exit with zero bytes on stdout:
# the consumer gets a parse error on empty input instead of `error.name`, and
# cannot tell "ask the operator" from "bad install" from "retry". So the check
# is not that a known failure maps correctly (above), it is that an *unknown*
# one is still an object. Each raise below is a different way of leaving
# through the floor.

for label, raised in [
    ("an unexpected exception", RuntimeError("boom")),
    ("an interrupt", KeyboardInterrupt()),
    ("a bare non-zero exit", SystemExit(7)),
]:
    with tempfile.TemporaryDirectory() as home:
        real_home = os.environ.get("HOME")
        os.environ["HOME"] = home
        canonical = cli.report_version
        try:
            def explode(args, _raised=raised):
                raise _raised

            cli.report_version = explode
            status, body = run("version")
        finally:
            cli.report_version = canonical
            if real_home is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = real_home

        check(isinstance(body, dict), f"{label}: stdout is not one JSON object")
        error = body.get("error", {}) if isinstance(body, dict) else {}
        check(body.get("ok") is False if isinstance(body, dict) else False,
              f"{label}: envelope is not a failure")
        check(error.get("code") == 105, f"{label}: code {error.get('code')} != 105")
        check(error.get("name") == "internal_error", f"{label}: name is not internal_error")
        check(status == 1, f"{label}: exit {status} != 1")
        check(
            error.get("detail", "").startswith(type(raised).__name__),
            f"{label}: detail does not name the exception class",
        )
        log = Path(home) / ".config" / "iitb" / "logs" / "internal-error.log"
        check(log.is_file(), f"{label}: no traceback was logged")
        check(str(log) in error.get("detail", ""), f"{label}: detail does not name the log")
        if log.is_file():
            check(
                type(raised).__name__ in log.read_text(encoding="utf-8"),
                f"{label}: the log does not carry the traceback",
            )

# A payload the envelope cannot serialise prints the failure, not half an
# object followed by it. Streaming the JSON straight into stdout would.
canonical = cli.report_version
try:
    cli.report_version = lambda args: {"unserialisable": object()}
    status, body = run("version")
finally:
    cli.report_version = canonical
check(isinstance(body, dict), "an unserialisable payload did not print one object")
check(status == 1, f"an unserialisable payload exited {status}, not 1")

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
print(
    "ok: envelope, exit codes, error mapping, parsing, help, downloads, "
    "version, and one object on every exit path"
)
