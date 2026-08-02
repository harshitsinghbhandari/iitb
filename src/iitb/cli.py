"""The `iitb` command tree.

A thin shell, on purpose. It parses the command line, dispatches into
`iitb_core`, wraps whatever comes back in the envelope, maps whatever was
raised to an error code, and prints one JSON object. No portal logic lives
here and none ever will.

The help text below is the product. The success test for this CLI is a
fresh agent session with zero context learning the whole tree from `--help`
alone, so the help blocks are written to be read by an agent that has never
seen this repo, and they are reproduced here verbatim from the approved
command-surface design.

Everything that is printed on the way out:

    success   {"ok": true, "data": ...}                      exit 0
    failure   {"ok": false, "error": {"code", "name",
                                      "message", "detail"}}  exit 1/2/3/4
    --help    plain text                                     exit 0

and nothing else on stdout, ever.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date

from . import config, core
from .errors import CliError

# ----------------------------------------------------------------------
# Help text. Verbatim public artifact; see the module docstring.
# ----------------------------------------------------------------------

ROOT_HELP = """
usage: iitb <command> [options]

Read IIT Bombay portals from the command line. Built for agents: every
command prints one JSON object and nothing else.

commands:
  browser      Run the browser this CLI owns, and check whether the
               operator's IITB single sign-on is live.
  placements   Read the placements and internships portal: postings, your
               eligibility for them, your applications, and the blog.
  downloads    Configure where downloaded files are written.

Every command prints exactly one JSON object on stdout and nothing else.
  success:  {"ok": true, "data": ...}
  failure:  {"ok": false, "error": {"code": <3 digits>, "name": ..., "message": ...}}

`--help` is the one exception: it prints plain text, like this. Run it on
any command in the tree.

Exit codes:
  0  success
  1  the operation failed
  2  you called the command wrong
  3  the operator's IITB single sign-on has ended and only they can restore
     it; the error message says exactly what to ask them
  4  iitb-core is missing or incompatible; this is an install problem

Branch on the exit code first and "error.name" second. "error.name" is a
stable slug, so it stays true across renumbering; "error.code" is the
3-digit number for the same thing.

Where to start:
  iitb browser sso-status    is the operator signed in?
  iitb placements --help     the placements command tree
  iitb downloads --help      set the default download directory once

Portal commands start the browser themselves and restore an expired
session themselves. You do not need to run anything first, and you should
never ask the operator to sign in, open a page, or click anything to make
a command work unless a command exits 3.

Nothing is cached. Every invocation fetches live, so re-run a command
instead of reusing an earlier answer.

This CLI only reads. It never applies to a job, withdraws an application,
uploads anything, or posts a comment.

Reporting a failure: email dev@theharshitsingh.com. Do not open a GitHub
issue and do not paste the output into one. A useful report contains portal
data, and a GitHub issue is public and permanent.
"""

BROWSER_HELP = """
usage: iitb browser <command>

Run the browser this CLI owns, and check whether the operator's IITB single
sign-on session is live.

The CLI drives its own Chrome with its own profile, kept apart from the
operator's everyday browser. The operator signs in to IITB SSO in that
window once, by hand, and every later command rides that session.

commands:
  start        Start the iitb browser, or report the one already running.
  attach       Report the running iitb browser without starting one.
  status       Report whether the iitb browser is running.
  sso-status   Report whether the operator's IITB single sign-on is live.
  stop         Shut the iitb browser down.

Portal commands start the browser themselves when they need it, so
`iitb browser start` is not a prerequisite for anything. These commands
are for checking on the runtime and for shutting it down.

This CLI never signs in. It does not type a password, a one-time code, or
a captcha, and it must not be asked to. When there is no session it says
so and stops; restoring it is the operator's to do.
"""

BROWSER_START_HELP = """
usage: iitb browser start

Start the iitb browser and report how to reach it.

Idempotent: if the browser is already up this reuses it rather than
starting a second one, and "launched" comes back false. The profile is
persistent, so a sign-in survives a stop and a later start.

Fails with error 104 if Chrome cannot be started or reached.
"""

BROWSER_ATTACH_HELP = """
usage: iitb browser attach

Report the running iitb browser. Never starts one.

Use this when you want to know that the browser is already up, and get its
connection details. Fails with error 104 if it is not running; start it
with `iitb browser start`.
"""

BROWSER_STATUS_HELP = """
usage: iitb browser status

Report whether the iitb browser is running. Never starts one and never
connects to one.

A browser that is down is not an error here: "running" comes back false and
the command still exits 0. This is the command to run when something else
reported error 104.
"""

BROWSER_SSO_STATUS_HELP = """
usage: iitb browser sso-status

Report whether the operator's IITB single sign-on session is live.

Detect only. This never signs in and never asks the browser to. It starts
the iitb browser if it is not already running, because the session lives in
that browser's profile.

  session live   exit 0, {"ok": true, "data": {"loggedIn": true, ...}}
  no session     exit 3, error 103. The message says exactly what to ask
                 the operator. Only they can fix it.
  check failed   exit 1, error 170. The session state is unknown, which is
                 not the same as ended: do not send the operator to sign in
                 on a 170.

You do not need to run this before a portal command. Run it when you want
to tell the operator where they stand, or when a portal command exited 3.
"""

BROWSER_STOP_HELP = """
usage: iitb browser stop

Shut the iitb browser down cleanly.

The profile survives, so the operator's sign-in survives with it and a
later `iitb browser start` picks the session back up.

A browser that was not running is not an error: "stopped" comes back false
with a "reason", and the command exits 0.
"""

DOWNLOADS_HELP = """
usage: iitb downloads <command>

Configure where this CLI writes the files it downloads.

commands:
  set-default   Set the default download directory.

The setting is shared by every portal, and each portal writes into its own
folder underneath it, so placements downloads land in
<default>/placements/. Until a default is set, download commands require
--out.
"""

DOWNLOADS_SET_DEFAULT_HELP = """
usage: iitb downloads set-default <path>

Set the default directory for downloaded files.

positional arguments:
  path
      Directory to write downloads into. "~" is expanded, the path is
      stored absolute and resolved, and the directory is created if it does
      not exist yet.

The setting is stored under ~/.config/iitb/ and applies to every portal.
Run it once; it persists. Passing --out to a download command always wins
over it.
"""

PLACEMENTS_HELP = """
usage: iitb placements <command> [options]

Read the IIT Bombay placements and internships portal: job postings, your
eligibility for them, your applications, and the placements blog.

commands:
  jobs           List job and internship postings, with your eligibility.
  job            Show one posting in full, including stipend and selection
                 process.
  deadlines      List application deadlines that are still open, soonest
                 first.
  applications   List the jobs you have already signed, with the stage each
                 one has reached.
  blog           Read the placements blog: announcements and the documents
                 attached to them.

Every command prints exactly one JSON object on stdout and nothing else.
  success:  {"ok": true, "data": ...}
  failure:  {"ok": false, "error": {"code": <3 digits>, "name": ..., "message": ...}}

Exit codes:
  0  success
  1  the operation failed
  2  you called the command wrong
  3  the operator's IITB single sign-on has ended and only they can restore
     it; the error message says exactly what to ask them
  4  iitb-core is missing or incompatible; this is an install problem

Expired sessions are restored automatically. You will not normally see exit
3, and you should never ask the operator to sign in, open a page, or click
anything to make a command work. If a command still fails after that, it is
a bug, not something the operator can fix by hand.

Reporting a failure: email dev@theharshitsingh.com. Do not open a GitHub
issue and do not paste the output into one. A useful report contains portal
data, and a GitHub issue is public and permanent.

Nothing is cached. Every invocation fetches live. Your eligibility for a
posting can change during the day and a posting can open and close within two
hours, so re-run a command instead of reusing an earlier answer.

This CLI only reads. It never applies to a job, withdraws an application,
uploads anything, or posts a comment. Where a command reports that an action
is available, that action is the operator's to take in the browser.
"""

PLACEMENTS_JOBS_HELP = """
usage: iitb placements jobs [--status {open,closing-today,closed,all}]
                            [--eligible] [--company TEXT]

List job and internship postings for your current season, with your
eligibility for each one already worked out. Sorted by deadline, soonest
first, always, whatever the filters.

options:
  --status {open,closing-today,closed,all}
      Which postings to include. Default: open.
        open           accepting applications right now
        closing-today  open, and closing before midnight tonight (IST)
        closed         no longer accepting applications
        all            every posting in the season
  --eligible
      Only postings you can act on right now: the portal marks you eligible
      and your CPI meets the posting's cutoff. Both values come from the
      portal. There is no profile to configure and nothing to keep in sync.
  --company TEXT
      Only postings whose company name contains TEXT, case-insensitive.

Each posting carries "eligible", the single yes/no answer to "can the operator
actually apply for this". It is true only when both halves hold: the portal's
own eligibility decision for them, and the CPI cutoff the posting itself
states. It is deliberately the stricter of those two readings, so a posting
they otherwise qualify for still comes back "eligible": false when the CPI is
below that posting's cutoff. Alongside it, "eligibility" carries the facts
behind the answer, so you can tell the operator why a posting is out of reach
instead of silently dropping it.

Eligibility is widened during the day as the placements team opens postings
to more cohorts. A posting you were ineligible for this morning may be open
to you this afternoon. Re-run; do not trust an earlier answer.

"action" reports what the portal currently offers on that posting. This CLI
never performs it.

The response is complete and unpaginated. Filter and slice it yourself.
"""

PLACEMENTS_JOB_HELP = """
usage: iitb placements job <job-id> [--text]

Show one posting in full: description, eligibility, locations, stipend,
selection process, and deadline.

positional arguments:
  job-id
      Numeric posting id, as returned in "jobId" by `iitb placements jobs`,
      `iitb placements deadlines`, or `iitb placements applications`.
      Posting ids are unique and stable. The "jobCode" on a posting is only
      unique within one company, so it does not work here.

options:
  --text
      Return description fields as plain text instead of HTML. HTML is the
      default because postings use tables that do not survive flattening.

A posting has no attachments of its own. Documents that relate to it are
published on the placements blog; see `iitb placements blog --help`.
"""

PLACEMENTS_DEADLINES_HELP = """
usage: iitb placements deadlines [--within DURATION] [--eligible]
                                 [--include-applied]

List application deadlines that are still open, soonest first.

options:
  --within DURATION
      Only deadlines within DURATION from now. Accepts forms like 90m, 48h,
      7d. Default: no limit; every open posting.
  --eligible
      Only postings you can act on right now. Same meaning as on
      `iitb placements jobs`.
  --include-applied
      Include postings you have already signed. They are left out by
      default, because their deadline is no longer something you have to act
      on.

This is a deadline-shaped view of the same postings `iitb placements jobs`
returns. Use `jobs` when you want the posting, `deadlines` when you want the
clock.

Each entry gives the deadline in UTC, the same moment rendered in IST, and
the seconds remaining at the time of the fetch.
"""

PLACEMENTS_APPLICATIONS_HELP = """
usage: iitb placements applications

List every job you have signed this season, most recently signed first, with
the stage each application has reached.

Each application carries "stage": the full ordered list of selection stages
for that job, and which one you are currently at. A new application sits at
"Applied" with nothing filled in after it. That is the portal's real answer,
not missing data.

"applicationType" is "normal" for a posting you were eligible for, and
"bonus" for one signed through the bonus route.

"canWithdraw" reports whether the portal currently offers to withdraw this
application. This CLI never withdraws anything.

The response is complete and unpaginated. Filter and slice it yourself.
"""

PLACEMENTS_BLOG_HELP = """
usage: iitb placements blog <command> [options]

Read the placements blog. This is where the placements team announces
eligibility changes, deadline extensions, walk-ins, and interim selections,
and where documents such as the internship policy are published. When a
posting's eligibility changes, the blog is where the reason is written down.

commands:
  posts   List blog posts, newest first.
  post    Show one post in full, with the documents it links.

There are separate internship, placement, and phd blogs. Both commands
default to the one matching your current season.

Post bodies can contain other students' names and roll numbers. Do not write
a post body into a repository, an issue, a pull request, or any shared log.
"""

PLACEMENTS_BLOG_POSTS_HELP = """
usage: iitb placements blog posts [--blog {internship,placement,phd}]
                                  [--page N] [--since DATE] [--max-pages N]

List blog posts, newest first.

options:
  --blog {internship,placement,phd}
      Which blog to read. Default: the one matching your current season.
  --page N
      Which page of the archive to read, counting from 1. Default: 1.
      Ignored when --since is given.
  --since DATE
      Return every post published on or after DATE (YYYY-MM-DD), reading
      back through the archive as far as needed. Use this for "anything new
      since yesterday" instead of guessing a page number.
  --max-pages N
      Stop after reading N pages of archive while --since walks back.
      Default: 5. If the walk stops early, the response sets "truncated" to
      true and "reachedDate" tells you how far back it got.
"""

PLACEMENTS_BLOG_POST_HELP = """
usage: iitb placements blog post <post-id>
                                 [--blog {internship,placement,phd}] [--text]

Show one blog post in full, including every document it links.

positional arguments:
  post-id
      Numeric post id, as returned in "postId" by
      `iitb placements blog posts`.

options:
  --blog {internship,placement,phd}
      Which blog the post is on. Default: the one matching your current
      season. Post ids are per blog, so an id from one blog will not be
      found on another.
  --text
      Return the body as plain text instead of HTML. HTML is the default
      because announcements use tables that do not survive flattening.

"documents" lists every downloadable file linked from the body, each with the
url the file is published at. This CLI does not download it for you.

Post bodies can contain other students' names and roll numbers. Do not write
a post body into a repository, an issue, a pull request, or any shared log.
"""

BLOG_CHOICES = ("internship", "placement", "phd")
STATUS_CHOICES = ("open", "closing-today", "closed", "all")

# ----------------------------------------------------------------------
# Argument types. Every value the shell can reject itself, it rejects here,
# so a usage error never costs a network round trip.
# ----------------------------------------------------------------------

_DURATION = re.compile(r"^(\d+)([smhd])$")
_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def numeric_id(raw: str) -> int:
    if not raw.isdigit():
        raise argparse.ArgumentTypeError(
            f"{raw!r} is not a numeric id; ids are digits only"
        )
    return int(raw)


def positive_int(raw: str) -> int:
    if not raw.isdigit() or int(raw) < 1:
        raise argparse.ArgumentTypeError(f"{raw!r} is not a whole number 1 or above")
    return int(raw)


def duration(raw: str) -> int:
    """`90m`, `48h`, `7d` to seconds."""
    match = _DURATION.match(raw.strip())
    if not match:
        raise argparse.ArgumentTypeError(
            f"{raw!r} is not a duration; use forms like 90m, 48h, 7d"
        )
    return int(match.group(1)) * _SECONDS[match.group(2)]


def iso_date(raw: str) -> str:
    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"{raw!r} is not a date; use YYYY-MM-DD"
        ) from None


# ----------------------------------------------------------------------
# Handlers. Each one parses nothing and shapes nothing: it hands the core
# what the parser produced and returns the core's payload untouched.
# ----------------------------------------------------------------------

BROWSER = "iitb_core.browser"
PLACEMENTS = "iitb_core.placements"


def browser_start(args) -> dict:
    return core.call(BROWSER, "start")


def browser_attach(args) -> dict:
    return core.call(BROWSER, "attach")


def browser_status(args) -> dict:
    return core.call(BROWSER, "status")


def browser_stop(args) -> dict:
    return core.call(BROWSER, "stop")


def browser_sso_status(args) -> dict:
    """Report the session, or exit 3 when only the operator can fix it.

    Exit 3 rather than a truthful exit 0 with `loggedIn: false`, so that one
    rule holds across the whole CLI: exit 3 means go and get the operator,
    anything else means it is the machine's problem. An agent should never
    have to read a field to find out whether it needs a human.
    """
    data = core.call(BROWSER, "sso_status")
    if not data.get("logged_in"):
        raise CliError(103, detail=data.get("detail"))
    return {"loggedIn": True, "user": data.get("user")}


def downloads_set_default(args) -> dict:
    return config.set_download_dir(args.path)


def placements_jobs(args) -> object:
    return core.call(
        PLACEMENTS,
        "jobs",
        status=args.status,
        eligible=args.eligible,
        company=args.company,
    )


def placements_job(args) -> object:
    return core.call(PLACEMENTS, "job", job_id=args.job_id, text=args.text)


def placements_deadlines(args) -> object:
    return core.call(
        PLACEMENTS,
        "deadlines",
        within=args.within,
        eligible=args.eligible,
        include_applied=args.include_applied,
    )


def placements_applications(args) -> object:
    return core.call(PLACEMENTS, "applications")


def placements_blog_posts(args) -> object:
    return core.call(
        PLACEMENTS,
        "blog",
        post_id=None,
        blog=args.blog,
        page=args.page,
        since=args.since,
        max_pages=args.max_pages,
    )


def placements_blog_post(args) -> object:
    return core.call(
        PLACEMENTS, "blog", post_id=args.post_id, blog=args.blog, text=args.text
    )


# ----------------------------------------------------------------------
# The parser tree
# ----------------------------------------------------------------------


def usage_code(message: str) -> int:
    """Which 2xx code an argparse complaint is.

    argparse writes prose to stderr and exits 2 on its own. The shell has to
    intercept that and answer in the envelope instead, or the "one JSON
    object per invocation" promise is false in exactly the case an agent is
    most likely to hit while it is still learning the tree.
    """
    text = message.lower()
    head, _, tail = text.partition(":")
    if "not allowed with argument" in text:
        return 204
    if head.startswith("argument") and "command" in head:
        return 200
    if "the following arguments are required" in text:
        return 200 if "command" in tail else 201
    if "expected one argument" in text or "expected at least one" in text:
        return 201
    return 202


class Parser(argparse.ArgumentParser):
    """An ArgumentParser that answers in the envelope instead of on stderr."""

    def error(self, message):  # noqa: D102 - argparse hook
        raise CliError(usage_code(message), detail=message)

    def exit(self, status=0, message=None):  # noqa: D102 - argparse hook
        if status == 0:
            raise SystemExit(0)
        raise CliError(200, detail=(message or "").strip() or None)


def split_help(block: str) -> tuple[str, str]:
    """A verbatim help block into (usage, description).

    The blocks are the public artifact and must print exactly as written, so
    the shell feeds argparse the usage line and the body separately and lets
    argparse add nothing of its own.
    """
    lines = block.strip("\n").split("\n")
    end = 1
    while end < len(lines) and lines[end].strip():
        end += 1
    usage = "\n".join([lines[0][len("usage: ") :]] + lines[1:end])
    return usage, "\n".join(lines[end:]).strip("\n")


def make(parent, name: str, block: str, handler=None) -> Parser:
    """Add one subcommand whose --help is the given block, verbatim."""
    usage, description = split_help(block)
    parser = parent.add_parser(
        name,
        usage=usage,
        description=description,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    parser.add_argument("-h", "--help", action="help", help=argparse.SUPPRESS)
    if handler is not None:
        parser.set_defaults(handler=handler)
    return parser


def commands(parser: Parser, dest: str):
    return parser.add_subparsers(
        dest=dest, metavar="<command>", required=True, help=argparse.SUPPRESS
    )


def hidden(parser: Parser, *args, **kwargs):
    """Add an argument argparse must not document: the block already does."""
    parser.add_argument(*args, help=argparse.SUPPRESS, **kwargs)


def build_parser() -> Parser:
    usage, description = split_help(ROOT_HELP)
    root = Parser(
        prog="iitb",
        usage=usage,
        description=description,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )
    root.add_argument("-h", "--help", action="help", help=argparse.SUPPRESS)
    top = commands(root, "command")

    _build_browser(top)
    _build_placements(top)
    _build_downloads(top)
    return root


def _build_browser(top) -> None:
    browser = make(top, "browser", BROWSER_HELP)
    sub = commands(browser, "subcommand")
    make(sub, "start", BROWSER_START_HELP, browser_start)
    make(sub, "attach", BROWSER_ATTACH_HELP, browser_attach)
    make(sub, "status", BROWSER_STATUS_HELP, browser_status)
    make(sub, "sso-status", BROWSER_SSO_STATUS_HELP, browser_sso_status)
    make(sub, "stop", BROWSER_STOP_HELP, browser_stop)


def _build_downloads(top) -> None:
    downloads = make(top, "downloads", DOWNLOADS_HELP)
    sub = commands(downloads, "subcommand")
    set_default = make(
        sub, "set-default", DOWNLOADS_SET_DEFAULT_HELP, downloads_set_default
    )
    hidden(set_default, "path", metavar="<path>")


def _build_placements(top) -> None:
    placements = make(top, "placements", PLACEMENTS_HELP)
    sub = commands(placements, "subcommand")

    jobs = make(sub, "jobs", PLACEMENTS_JOBS_HELP, placements_jobs)
    hidden(jobs, "--status", choices=STATUS_CHOICES, default="open")
    hidden(jobs, "--eligible", action="store_true")
    hidden(jobs, "--company", metavar="TEXT", default=None)

    job = make(sub, "job", PLACEMENTS_JOB_HELP, placements_job)
    hidden(job, "job_id", metavar="<job-id>", type=numeric_id)
    hidden(job, "--text", action="store_true")

    deadlines = make(sub, "deadlines", PLACEMENTS_DEADLINES_HELP, placements_deadlines)
    hidden(deadlines, "--within", metavar="DURATION", type=duration, default=None)
    hidden(deadlines, "--eligible", action="store_true")
    hidden(deadlines, "--include-applied", action="store_true")

    make(sub, "applications", PLACEMENTS_APPLICATIONS_HELP, placements_applications)

    blog = make(sub, "blog", PLACEMENTS_BLOG_HELP)
    blog_sub = commands(blog, "blog_command")

    posts = make(blog_sub, "posts", PLACEMENTS_BLOG_POSTS_HELP, placements_blog_posts)
    hidden(posts, "--blog", choices=BLOG_CHOICES, default=None)
    hidden(posts, "--page", metavar="N", type=positive_int, default=1)
    hidden(posts, "--since", metavar="DATE", type=iso_date, default=None)
    hidden(posts, "--max-pages", metavar="N", type=positive_int, default=5)

    post = make(blog_sub, "post", PLACEMENTS_BLOG_POST_HELP, placements_blog_post)
    hidden(post, "post_id", metavar="<post-id>", type=numeric_id)
    hidden(post, "--blog", choices=BLOG_CHOICES, default=None)
    hidden(post, "--text", action="store_true")


# ----------------------------------------------------------------------
# The envelope
# ----------------------------------------------------------------------


def emit(payload: dict) -> None:
    json.dump(payload, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        emit({"ok": True, "data": args.handler(args)})
        return 0
    except CliError as err:
        emit({"ok": False, "error": err.as_error()})
        return err.exit_code
    except SystemExit as exc:  # --help printed its text and stopped
        return int(exc.code or 0)
    except KeyboardInterrupt:
        return 1


def run() -> None:
    sys.exit(main())


if __name__ == "__main__":
    run()
