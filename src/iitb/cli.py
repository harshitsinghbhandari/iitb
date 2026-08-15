"""The `iitb` command tree.

A thin shell, on purpose. It parses the command line, dispatches into
`iitb_core`, wraps whatever comes back in the envelope, maps whatever was
raised to an error code, and prints one JSON object. No portal logic lives
here and none ever will.

The help text below is the product. The success test for this CLI is a
fresh agent session with zero context learning the whole tree from `--help`
alone, so the help blocks are written to be read by an agent that has never
seen this repo, and each one is printed verbatim: argparse reformats nothing
and adds nothing of its own.

Everything that is printed on the way out:

    success   {"ok": true, "data": ...}                      exit 0
    failure   {"ok": false, "error": {"code", "name",
                                      "message", "detail"}}  exit 1/2/3/4
    --help    plain text                                     exit 0

and nothing else on stdout, ever.

"Ever" is structural rather than aspirational: `main` catches `BaseException`
below every known mapping, so an exit path nobody planned for still prints one
parseable object (error 105) instead of exiting non-zero in silence. Silence is
the single outcome a consumer cannot branch on, because it arrives as a parse
error on empty input rather than as a name it can read.
"""

from __future__ import annotations

import argparse
import getpass
import json
import re
import sys
import traceback
from datetime import date, datetime, timezone
from importlib import metadata

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
  browser      Run the headless browser this CLI owns, sign the operator
               in once, and check whether that sign-on is still live.
  placements   Read the placements and internships portal: postings, your
               eligibility for them, your applications, and the blog.
  moodle       Read Moodle: your enrolled courses, everything inside them,
               your grades, the files, and what is coming up.
  mail         Read the operator's IITB email: folders, messages, and the
               files attached to them.
  downloads    Download a file by url using the operator's own identity, and
               configure where downloaded files are written.
  version      Report the installed iitb and iitb-core versions.

Every command prints exactly one JSON object on stdout and nothing else.
  success:  {"ok": true, "data": ...}
  failure:  {"ok": false, "error": {"code": <3 digits>, "name": ..., "message": ...}}

That holds on every exit path. A failure nobody planned for still comes back
as one object, error 105 "internal_error" at exit 1, rather than as silence.

`--help` is the one exception: it prints plain text, like this. Run it on
any command in the tree.

`iitb --version` works too and stays inside the envelope, but `iitb version`
is the command; the flag is there so that reaching for it is not a dead end.

Exit codes:
  0  success
  1  the operation failed
  2  you called the command wrong
  3  only the operator can restore access, and they do it by signing in
     once; "error.name" says which door to send them to
  4  iitb-core is missing or incompatible; this is an install problem

Branch on the exit code first and "error.name" second. "error.name" is a
stable slug, so it stays true across renumbering; "error.code" is the
3-digit number for the same thing.

There are two doors, and sending the operator to the wrong one wastes
their time and fixes nothing:
  sso_session_ended                        `iitb browser login`
  mail_not_configured, mail_token_rejected `iitb mail login`

Where to start:
  iitb browser sso-status    is the operator signed in?
  iitb browser login         open a window so they sign in once
  iitb placements --help     the placements command tree
  iitb moodle --help         the moodle command tree
  iitb mail --help           the mail command tree
  iitb downloads --help      download a file by url, set where files land
  iitb version               which versions are installed

Portal commands start the browser themselves and restore an expired
session themselves. The browser is headless, so nothing appears on the
operator's screen. You do not need to run anything first, and you should
never ask the operator to sign in, open a page, or click anything to make
a command work unless a command exits 3.

`iitb mail` is the exception to all of that: it uses no browser, it shares
nothing with the other three, it has its own credential, and nothing can
renew that credential except the operator running `iitb mail login`.

Nothing is cached. Every invocation fetches live, so re-run a command
instead of reusing an earlier answer.

This CLI only reads. It never applies to a job, withdraws an application,
uploads anything, posts a comment, starts a quiz attempt, submits an
assignment, marks anything done, or sends, deletes or files an email.

Reporting a failure: email dev@theharshitsingh.com. Do not open a GitHub
issue and do not paste the output into one. A useful report contains portal
data, and a GitHub issue is public and permanent.
"""

BROWSER_HELP = """
usage: iitb browser <command>

Run the browser this CLI owns, and check whether the operator's IITB single
sign-on session is live.

The CLI drives its own Chrome with its own profile, kept apart from the
operator's everyday browser. It runs headless, so nothing appears on the
operator's screen while a command works.

Google Chrome has to be installed for any of this, and it is the only
thing this CLI needs that it cannot install for itself. If it is missing,
every browser-backed command fails with error 171 and says so: install
Chrome from google.com/chrome, or point IITB_CHROME_BIN at an existing
Chrome binary if it lives somewhere unusual.

`iitb browser login` is the one exception, and the one thing the operator
ever has to do: it opens a visible window, they sign in to IITB SSO once by
hand, and every later command rides that session with no window at all.

commands:
  login        Open a window so the operator signs in once. Headful.
  start        Start the iitb browser, or report the one already running.
  attach       Report the running iitb browser without starting one.
  status       Report whether the iitb browser is running.
  sso-status   Report whether the operator's IITB single sign-on is live.
  stop         Shut the iitb browser down.

Portal commands start the browser themselves when they need it, so
`iitb browser start` is not a prerequisite for anything. These commands
are for checking on the runtime and for shutting it down.

This CLI never signs in. It does not type a password, a one-time code, or
a captcha, and it must not be asked to. `iitb browser login` opens the
window and then waits: the typing is the operator's, all of it. When there
is no session the CLI says so and stops.
"""

BROWSER_LOGIN_HELP = """
usage: iitb browser login

Open a visible browser window so the operator signs in to IITB SSO once.

This is the only command that shows a window, and the only one that needs a
human. Everything else runs headless against the session this establishes,
which lives in the browser's own profile and outlives the window.

Run this when a command exits 3. Then re-run that command.

  signed in    exit 0, {"ok": true, "data": {"loggedIn": true, "user": ...}}
  not signed   exit 3, error 103. The window was open and no session
               appeared, so nothing changed. Run it again.

The window opens on the IITB sign-in page and then this waits, for up to
five minutes, watching for a session to appear. It does not type, click,
or submit anything: the password, the one-time code and the captcha are
the operator's, and this CLI must never be asked to enter them.

If a session is already live this returns straight away, so it is safe to
run when you are not sure.
"""

BROWSER_START_HELP = """
usage: iitb browser start

Start the iitb browser and report how to reach it.

Headless: no window appears. Idempotent: if the browser is already up this
reuses it rather than starting a second one, and "launched" comes back
false. The profile is persistent, so a sign-in survives a stop and a later
start.

Fails with error 104 if Chrome cannot be started or reached, and with
error 171 if there is no Google Chrome installed to start.
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
  no session     exit 3, error 103. Ask the operator to run
                 `iitb browser login`. Only they can fix it.
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

Download a file by url, and configure where downloaded files are written.

commands:
  fetch         Download one file by url, using the operator's own identity.
  set-default   Set the default download directory.

The setting is shared by every command that downloads, and each source writes
into its own folder underneath it. `iitb moodle fetch` and `iitb mail fetch`
use the same setting.

`fetch` here is the one for a link: something the operator was sent or read,
that opens for them and not for a stranger. It is the command to reach for
when you have a url and no other handle on the file.
"""

DOWNLOADS_FETCH_HELP = """
usage: iitb downloads fetch <url> [--out PATH] [--force]

Download one file that opens only for the operator's own IITB identity.

positional arguments:
  url
      The url of the file, exactly as it was published: in an announcement, in
      an email, wherever the operator found it. Give the link to the file
      itself, not the page that mentions it.

options:
  --out PATH
      Where to write the file. If PATH is an existing directory, the file is
      written into it under its published filename. Otherwise PATH is the
      filename to write.
      Without --out, the file goes to a folder named for the service it came
      from, inside your default download directory, which is set once with
      `iitb downloads set-default`. Until that is set, --out is required.
  --force
      Overwrite an existing file. Without it, an existing file is an error and
      nothing is written.

Not every url works, and the ones that do not fail before anything is
downloaded, with "detail" saying which url was refused and why. Two in
particular: a file on Moodle is `iitb moodle fetch`, which can also name it by
activity id, and a file attached to an email is `iitb mail fetch`.

A link to a file on a third-party drive is refused as well. The browser this
CLI owns carries the operator's IITB sign-on and is signed in to nothing else,
those are separate identities, and signing in to another one is not something
this CLI does or may be asked to do. Hand that link to the operator instead.

The file is written under the name the source publishes it as, which is often
not the text of the link and sometimes has no extension. The name is never
invented and an extension is never added; the response reports the content
type so you can tell the operator what the file actually is.

On success the response gives the absolute path written, the byte count, the
content type, and a sha256, so a repeated download can be recognised without
reading the file.

This command never writes a file that is not the file you asked for. If it
cannot get the real file it fails and writes nothing at all, not even a partial
file. It only ever reads: downloading changes nothing wherever the file lives.

A link that has expired or been withdrawn fails with "download_not_found".
That is a fact about the link, not about this CLI: ask the operator for a
current one rather than retrying or asking them to sign in.

Downloaded files are routinely other people's personal data: names, roll
numbers, phone numbers. Do not copy what is inside one into a repository, an
issue, a pull request, or any shared log.
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
     it, by running `iitb browser login` and signing in once
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
usage: iitb placements job [<job-id>] [--company TEXT --job-code CODE]
                           [--text]

Show one posting in full: description, eligibility, locations, stipend,
selection process, and deadline.

Name the posting in one of two ways: by its id, or by the job code the blog
announces it under together with the company that published it. Give the id,
or give both --company and --job-code. Any other combination is a usage
error.

positional arguments:
  job-id
      Numeric posting id, as returned in "jobId" by `iitb placements jobs`,
      `iitb placements deadlines`, or `iitb placements applications`.
      Posting ids are unique and stable.

options:
  --company TEXT
      The company to look the job code up within. Matched the same way as on
      `iitb placements jobs`: the company name contains TEXT,
      case-insensitively. Required with --job-code.
  --job-code CODE
      The "jobCode" a posting carries, as the placements blog writes it. A
      job code is only unique within one company, which is why --company is
      required with it. A code that still matches more than one posting is
      error 115, which lists what it matched rather than guessing.
  --text
      Return description fields as plain text instead of HTML. HTML is the
      default because postings use tables that do not survive flattening.

Blog posts announce shortlists, tests and walk-ins by job code, so this is
the route from something the blog said to the posting it said it about.

A posting has no attachments of its own. Documents that relate to it are
published on the placements blog; see `iitb placements blog --help`.
"""

MOODLE_HELP = """
usage: iitb moodle <command> [options]

Read the IIT Bombay Moodle: your enrolled courses, everything inside them,
your grades, the files, and what is coming up.

commands:
  courses     List the courses you are enrolled in this term.
  course      Show everything visible inside one course: its sections and
              every activity in them, with content.
  deadlines   Show what is due: structured due dates, and the announcements
              that in practice carry the real ones.
  grades      Show your grades, across all courses or inside one.
  fetch       Download a file from a course to disk.

Naming a course: every command that takes a course accepts either its
numeric id or its code, for example "XX 101-2026-1", "XX 101", or "xx101".
Matching ignores case and spaces. If what you typed matches more than one
course, the command fails and lists them rather than picking one. Course ids
change when the institute rebuilds Moodle, so never store one; run
`iitb moodle courses` and use what it returns now.

Every command prints exactly one JSON object on stdout and nothing else.
  success:  {"ok": true, "data": ...}
  failure:  {"ok": false, "error": {"code": <3 digits>, "name": ..., "message": ...}}

Exit codes:
  0  success
  1  the operation failed
  2  you called the command wrong
  3  the operator's IITB single sign-on has ended and only they can restore
     it, by running `iitb browser login` and signing in once
  4  iitb-core is missing or incompatible; this is an install problem

Expired sessions are restored automatically. You will not normally see exit
3, and you should never ask the operator to sign in, open a page, or click
anything to make a command work. If a command still fails after that, it is
a bug, not something the operator can fix by hand.

Reporting a failure: email dev@theharshitsingh.com. Do not open a GitHub
issue and do not paste the output into one. A useful report contains portal
data, and a GitHub issue is public and permanent.

Nothing is cached. Every invocation fetches live. Enrolments change during
the term and course pages change during the week, so re-run a command
instead of reusing an earlier answer.

This CLI only reads. It never starts a quiz attempt, submits or saves an
assignment, posts or replies in a forum, marks anything done, or changes an
enrolment or a setting. Where a command reports that something exists, going
and doing it is the operator's to do in the browser.

Course pages and announcements can contain other students' names and roll
numbers. Do not write course content into a repository, an issue, a pull
request, or any shared log.
"""

MOODLE_COURSES_HELP = """
usage: iitb moodle courses

List every course you are currently enrolled in, with its id, code, name and
term.

Takes no options. The list is complete and unpaginated; filter and slice it
yourself.

Each course carries:
  courseId   the numeric id every other command accepts
  code       the course code, for example "XX 101-2026-1"
  name       the full course name
  term       the term the course belongs to
  state      "upcoming", "current" or "ended", worked out from the course's
             own start and end dates
  url        the course page, for the operator to open

Start here. Enrolments sync from the institute roll system through the term,
so courses appear and disappear mid-semester, and every id in the response
changes if the institute rebuilds Moodle. Resolve a course from this command
each time rather than reusing an id you saw earlier.

Two enrolled courses can share a full name and differ only in their code.
That is not a duplicate; they are separate courses with separate content.
"""

MOODLE_COURSE_HELP = """
usage: iitb moodle course <course> [--no-content] [--include TYPE[,TYPE...]]
                                   [--posts] [--text]

Show everything visible inside one course: every section, and every activity
in every section, with the content of each one.

positional arguments:
  course
      The course, by numeric id or by code. See `iitb moodle --help` for how
      names are matched.

options:
  --no-content
      Return the structure only: every section and activity with its id,
      name, type and url, and no content at all. This is by far the cheapest
      form of this command and the right first look at a course you have not
      seen. Cannot be combined with --include.
  --include TYPE[,TYPE...]
      Fetch content only for activities of these types. Everything else
      still appears, with its id, name, type and url, marked
      "contentStatus": "skipped". Types: file, page, link, assignment,
      forum, folder, quiz. Default: all of them.
  --posts
      Also fetch every post in every forum discussion. Without it, forums
      come back with the list of discussions and their reply counts, which
      is usually what you want. With it, this command costs noticeably more.
  --text
      Return descriptions and page bodies as plain text instead of HTML.
      HTML is the default because course pages use tables and lists that do
      not survive flattening.

This command is not free, and its cost grows with the number of activities
in the course. Use --no-content or --include when you do not need
everything.

Activities come back with a "type": file, page, link, assignment, forum,
folder or quiz. An activity whose type this version of iitb does not model
comes back as "unmapped" with its name and url intact, so you can still tell
the operator it is there and where to find it. That is not an error.

Each activity carries "contentStatus":
  ok         content was read
  skipped    you excluded it with --include or --no-content
  unmapped   this version has no reader for this type; the activity is real
             and its url works
  failed     reading this one activity failed; the rest of the response is
             still good, and "contentError" says what happened

A single activity failing does not fail the command. Check
counts.contentFailed before telling the operator you have seen everything.

A file's name on Moodle is often not the activity's name, and some files
have no extension at all. Each file activity reports both, so use "filename"
when you mean the file and "name" when you mean the activity.

Course content can contain other students' names and roll numbers. Do not
write it into a repository, an issue, a pull request, or any shared log.
"""

MOODLE_DEADLINES_HELP = """
usage: iitb moodle deadlines [<course>] [--announcements N] [--since DATE]

Show what is due. Answers in two separate parts, and you need both.

positional arguments:
  course
      Limit to one course, by numeric id or by code. Without it, every
      course you are enrolled in.

options:
  --announcements N
      How many recent announcement threads to return per course. Default: 5.
      Use 0 to skip announcements entirely and return only structured dates.
  --since DATE
      Return every announcement posted on or after DATE (YYYY-MM-DD)
      instead of a fixed count. Overrides --announcements.

"deadlines" holds structured due dates: dates Moodle itself knows about,
read off assignments, quizzes and the calendar. "sources" names exactly what
was checked to build it.

Moodle only has a due date when a course explicitly sets one, and many
courses never do. An empty "deadlines" list means Moodle has not been told
about any due date, which is not the same thing as nothing being due.

"announcements" holds the recent posts in each course's Announcements forum,
in full, with author and time. This is where dated obligations are actually
written at IIT Bombay: "the test is on Tuesday in the lecture hall", "send
the form back before the weekend". They are returned exactly as written.
This command does not turn them into dates and will not guess at one,
because a wrong timestamp read out to the operator is worse than the
sentence it came from.

So the answer to "what is due in this course" is two numbers and some
reading: counts.deadlines and counts.announcements. Report both. "No due
dates are set in Moodle, but an announcement posted on the 29th says a form
is due Friday morning" is the answer the operator needs. "Nothing is due" is
not, and it is what you will say if you only read the first list.

Announcement text can contain other students' names and roll numbers. Do not
write it into a repository, an issue, a pull request, or any shared log.
"""

MOODLE_GRADES_HELP = """
usage: iitb moodle grades [<course>]

Show your grades.

positional arguments:
  course
      One course, by numeric id or by code, to get its individual grade
      items. Without it, one line per enrolled course: the overview.

Every grade cell comes back twice: "gradeText" is exactly what the portal
shows, and "grade" is that value as a number, or null when it is not a
number or could not be read with confidence. Trust "gradeText". Use "grade"
only for arithmetic, and handle null.

A grade of "-" means nothing has been posted for that item yet. It is the
real state, not missing data, and it is what most of a course looks like
early in a term.
"""

MOODLE_FETCH_HELP = """
usage: iitb moodle fetch <target> [--out PATH] [--force]

Download one file from a course to disk.

positional arguments:
  target
      Either the numeric "activityId" of a file activity, or a Moodle file
      url exactly as returned in a "fileUrl" field by `iitb moodle course`
      or `iitb moodle deadlines`. A url that is not on Moodle is rejected.

      Use the id for a file activity. Use the url for anything attached to
      something else: an assignment's attachment, a file in a forum post, an
      image inside a page. Activity names are not unique inside a course and
      are not accepted here.

options:
  --out PATH
      Where to write the file. If PATH is an existing directory, the file is
      written into it under its published filename. Otherwise PATH is the
      filename to write.
      Without --out, the file goes to the "moodle" folder inside your
      default download directory, which is set once with
      `iitb downloads set-default`. Until that is set, --out is required.
  --force
      Overwrite an existing file. Without it, an existing file is an error
      and nothing is written.

The file is written under the name Moodle publishes it as, which is often
not the activity's name and sometimes has no extension. The name is never
invented and an extension is never added; the response reports the content
type so you can tell the operator what the file actually is.

On success the response gives the absolute path written, the byte count, the
content type, and a sha256, so a repeated download can be recognised without
reading the file.

This command never writes a file that is not the file you asked for. If it
cannot get the real file it fails and writes nothing at all, not even a
partial file.
"""

MAIL_HELP = """
usage: iitb mail <command> [options]

Read the operator's IIT Bombay email: which folders exist, what is in one of
them, one message in full, and the files attached to it.

commands:
  login       Store the operator's mail credential. Interactive, and the one
              command in this CLI that is.
  mailboxes   List the folders on the account, with message and unread counts.
  list        List messages in a folder, newest first, headers only.
  read        Show one message in full, without marking it read.
  fetch       Save the files attached to one message to disk.

Every command prints exactly one JSON object on stdout and nothing else.
  success:  {"ok": true, "data": ...}
  failure:  {"ok": false, "error": {"code": <3 digits>, "name": ..., "message": ...}}

Exit codes:
  0  success
  1  the operation failed
  2  you called the command wrong
  3  only the operator can restore access to their mail, by running
     `iitb mail login` and typing their own access token once
  4  iitb-core is missing or incompatible; this is an install problem

This tree uses no browser and shares nothing with the other portals. Its
credential is its own: the operator stores it once with `iitb mail login`, and
nothing here can renew it. So exit 3 on this surface is never
`iitb browser login`, and running that would fix nothing. The two names to
read are `mail_not_configured`, meaning there is no credential yet, and
`mail_token_rejected`, meaning the one there has stopped working. Both mean
the same thing to you: ask the operator, and wait.

Naming a message: a message is a UID together with the folder it is in. UIDs
are unique inside one folder and mean nothing outside it, so `read` and
`fetch` take `--mailbox` alongside the UID, and a UID from
`iitb mail list --mailbox Sent` will not be found in INBOX. Nothing is cached
and mail keeps arriving, so re-run `iitb mail list` rather than reusing an
earlier answer.

This CLI only reads mail. It never sends, replies to, forwards, deletes,
moves or files a message, never marks one read or unread, and never changes a
setting on the account. Reading a message leaves it exactly as unread as it
was, and there is no flag that changes that. Sending in particular is not
half-built or one flag away: there is no code here that could send anything.

Mail is other people's personal data: their names, their addresses, what they
wrote, and the files they attached. Do not write a subject, an address, a
body or an attachment name into a repository, an issue, a pull request, or
any shared log. Report what the operator asked about and nothing more.

Reporting a failure: email dev@theharshitsingh.com. Do not open a GitHub
issue and do not paste the output into one. A useful report contains somebody
else's mail, and a GitHub issue is public and permanent.
"""

MAIL_LOGIN_HELP = """
usage: iitb mail login [<ldap-id>]

Store the operator's mail credential, after checking that it works.

This is the one command in this CLI that talks to a human, and the only one
that ever prompts. It asks for two things, on the operator's own terminal:

  IITB LDAP id            visible as they type it
  IITB SSO access token   hidden; not echoed, not printed, not logged

positional arguments:
  ldap-id
      The operator's IITB LDAP id, so that the token is the only thing they
      have to type. Optional; without it, this prompts for that as well.

The token is never a command-line argument, and there is no flag for it. That
is deliberate and it is not an omission to be fixed: an argument is visible to
every other process on the machine while the command runs, and it is written
into the shell's history file, where it stays. It is read from the hidden
prompt, or from stdin when stdin is a pipe, and from nowhere else.

An agent must never run this command. Ask the operator to run it themselves,
in their own terminal. Never ask them for the token, never offer to type it
for them, and never accept it in a chat message: a token that has been pasted
into a transcript has been disclosed, and a disclosed token cannot be
undisclosed.

The credential is checked against the live server before anything is stored,
so a token that does not work is never saved and a failed attempt cannot
damage a credential that was already working. It is stored under
~/.config/iitb/, readable only by the operator, and it is never printed: the
receipt names the file and reports that the check passed, and carries no
token.

  stored      exit 0, {"ok": true, "data": {"ldapId", "credentialPath", ...}}
  refused     exit 3, error 151. Nothing was stored, and any credential that
              was already there is untouched. The token is wrong or has
              expired; get a fresh one and run this again.
  cancelled   exit 2, error 201. Nothing was stored.

Run this when a command exits 3 with `mail_not_configured` or
`mail_token_rejected`. Nothing else in this CLI can restore mail access, and
no other command will ever prompt for anything.
"""

MAIL_MAILBOXES_HELP = """
usage: iitb mail mailboxes

List every folder on the account, with what is in each one.

Takes no options. The list is complete and unpaginated.

Each folder carries:
  name         the folder's name, exactly as the account holds it, and the
               spelling `--mailbox` expects elsewhere
  messages     how many messages it holds, or null if it could not be asked
  unseen       how many of those are unread, or null for the same reason
  selectable   false for a folder that only contains other folders and so
               cannot be listed or read

Start here. Folder names are the operator's own and this CLI invents no
aliases for them, so every `--mailbox` elsewhere takes a name out of this
list. The counts are what make this worth running before `iitb mail list`:
they answer "where is the unread mail" in one call.
"""

MAIL_LIST_HELP = """
usage: iitb mail list [--mailbox NAME] [--unseen] [--from TEXT]
                      [--since DATE] [--search TEXT] [--limit N]

List messages in one folder, newest first. Headers only: no body is fetched,
and nothing is marked read.

options:
  --mailbox NAME
      Which folder to list. Default: INBOX. Names come from
      `iitb mail mailboxes`.
  --unseen
      Only messages that are still unread.
  --from TEXT
      Only messages whose From header contains TEXT. Best-effort: an
      empty result is not proof of absence. See below.
  --since DATE
      Only messages received on or after DATE (YYYY-MM-DD).
  --search TEXT
      Only messages containing TEXT anywhere, including in the body.
      Best-effort: an empty result is not proof of absence. See below.
  --limit N
      How many messages to return, counting back from the newest.
      Default: 50.

Filters compose: every one you give has to hold.

--from and --search are slow, and it is the server that is slow rather than
this CLI. Neither is indexed, so answering one means reading every message in
the folder, and on a folder holding five figures of messages that is tens of
seconds for a single call. --unseen and --since are indexed and come back
immediately. A command that has been running for half a minute with --from or
--search is working, not hung: do not kill it, do not retry it in a loop, and
tell the operator it is going to take a moment rather than letting them watch
a silent terminal.

--from and --search are also BEST-EFFORT, and this is the more important of the
two warnings. Both are answered by the mail server's own content search, not by
this CLI, and that search is known to miss messages: a message with unusual
headers can be skipped even though it is really in the folder and really in the
window you asked for. It is skipped silently, and nothing in the response
distinguishes it from a message that does not exist. So an empty or small
result from --from or --search is NOT proof of absence. Never report one as
"there is no such mail". Say what you looked for, and say that this kind of
search can miss things.

When it matters whether something is there, do not use --from or --search at
all. List the window instead, with --since and --mailbox and a --limit big
enough to cover it, and read the addresses and subjects in the response
yourself. Date-bounded listing does return the messages the content search
misses, so that is the only way to answer "is there anything from X" as a fact.

Newest first means newest by arrival, which is the order the account itself
keeps. It is not the order of the Date header: that header is written by the
sender's own machine, so a wrong clock there would otherwise push a message to
the top of the list or off the end of --limit. Each message reports its date
both ways, parsed into "date" (UTC) and "dateLocal" (IST) and verbatim into
"dateText". A date that could not be parsed is null beside the text it came
from, never a guess.

"counts" gives two numbers: "matched" is how many messages the filters found,
"returned" is how many came back after --limit. When they differ, say so
rather than reporting the tail as the whole. With --from or --search,
"matched" is what the server's content search returned, which makes it a lower
bound rather than a total: "matched": 0 there means the search found nothing,
not that the folder holds nothing. Read it as a count of hits, never as
evidence of absence.

Each message carries "uid" and "mailbox" together, because that pair is what
`iitb mail read` and `iitb mail fetch` take. "hasAttachments" is true when the
message carries any part that is not body text, which is the same rule those
two use, so the three commands never disagree about what is attached.

Subjects, addresses and names here belong to the people who wrote them. Do not
write them into a repository, an issue, a pull request, or any shared log.
"""

MAIL_READ_HELP = """
usage: iitb mail read <uid> [--mailbox NAME]

Show one message in full: every header, the body, and what is attached to it.

positional arguments:
  uid
      The message's UID, as returned in "uid" by `iitb mail list`. A UID is
      unique inside one folder and means nothing outside it, so pass
      --mailbox the folder you took it from.

options:
  --mailbox NAME
      The folder that UID belongs to. Default: INBOX.

Reading a message does not mark it read. Its unread state after this command
is exactly what it was before, and there is no flag to change that, because
this CLI does not alter the account. An agent may skim an inbox on the
operator's behalf without leaving a trace of having done it.

"body" carries both forms of the message. "text" is the plain-text part, and
it is what to reason over. "html" is the formatted part, kept because about
one message in ten has no plain-text part at all, and because a table in an
announcement does not survive being flattened. "body.format" says which of the
two are present, so you never have to guess why one of them is null.

"headers" is every header on the message, in order, duplicates kept, rather
than the subset this CLI guessed you would want.

"attachments" lists what is attached, each with a filename, a content type and
a byte count, but not the bytes; `iitb mail fetch` is what writes them to
disk. An attachment is any part that is not body text, so a forwarded message
and an inline image are both listed, and the count here is exactly what
`iitb mail fetch` would write.

The whole of this response is somebody's personal data. Do not write a
subject, an address, a body or an attachment name into a repository, an issue,
a pull request, or any shared log. Tell the operator what it says and stop
there.
"""

MAIL_FETCH_HELP = """
usage: iitb mail fetch <uid> [--mailbox NAME] [--out PATH] [--force]

Save the files attached to one message to disk.

positional arguments:
  uid
      The message's UID, as returned in "uid" by `iitb mail list` or
      `iitb mail read`. Pass --mailbox the folder you took it from.

options:
  --mailbox NAME
      The folder that UID belongs to. Default: INBOX.
  --out PATH
      An existing directory to write into. PATH is a directory rather than a
      filename, because one message can carry any number of attachments and
      the names are the senders'.
      Without --out, the files go to the "mail" folder inside your default
      download directory, which is set once with
      `iitb downloads set-default`. Until that is set, --out is required.
  --force
      Overwrite files that already exist. Without it, an existing file is an
      error and nothing at all is written.

Every attachment on the message is written; there is no way to ask for one of
them. A message with nothing attached is error 157 rather than an empty
success, so read "hasAttachments" on the listing first if you are not sure.

Files are written under the names their senders gave them, each reduced to a
bare filename, so a name can never write outside the directory you chose. A
part that arrived with no name of its own is given one that says what it is,
and that is the only name this CLI invents anywhere. Two attachments sharing
one name both survive: the second gets a numbered suffix rather than
overwriting the first.

Each written file is reported with its absolute path, its byte count, its
content type and a sha256, so a repeated download can be recognised without
reading the file back off disk.

Fetching attachments does not mark the message read either.

An attachment is a file a stranger sent. Write it where the operator asked and
nowhere else, never into a repository, and treat what is inside it as theirs.
"""

VERSION_HELP = """
usage: iitb version

Report the versions of the two packages this CLI is made of.

  {"ok": true, "data": {"iitb": "<version>", "iitb_core": "<version>"}}

"iitb" is this command surface; "iitb_core" is the implementation it calls.
Both numbers belong at the top of a bug report, because exit 4 means the two
do not fit together and diagnosing that needs to know which two.

An iitb-core that is not installed is reported here the way it is reported
everywhere else: error 498 at exit 4, rather than a null version at exit 0.

`iitb --version` prints the same object with a "use" field pointing back at
this command.
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

# The activity types `--include` accepts. These are the student's own words for
# things on a course page, they are the whole discoverability of the flag, and
# the help block lists them, so they are public. "unmapped" is deliberately not
# one of them: it is a result, not a request, and accepting it would imply
# content can be fetched for a type this version has already said it cannot
# read.
INCLUDE_CHOICES = ("file", "page", "link", "assignment", "forum", "folder", "quiz")

# Announcement threads per course when --announcements is not given. Held here
# rather than read from the core, because it is a number the help block states
# and this repo owns every string in that block.
DEFAULT_ANNOUNCEMENTS = 5

# The same rule for mail's two defaults. The core has both, and reading them
# from it would mean the help block could go stale against the value it states
# without anything failing. Held here, they are one string and one number that
# a check can hold to the block, and a core that disagrees is a seam change
# rather than a silent drift. "INBOX" is not portal knowledge: it is the one
# mailbox name the protocol itself reserves.
DEFAULT_MAILBOX = "INBOX"
DEFAULT_LIMIT = 50

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


def whole_number(raw: str) -> int:
    """A count that may legitimately be zero.

    Separate from `positive_int` because `--announcements 0` is a real request:
    it suppresses the announcements bucket and returns the structured dates
    alone, which is what an agent that only wants the first list should say.
    """
    if not raw.isdigit():
        raise argparse.ArgumentTypeError(f"{raw!r} is not a whole number 0 or above")
    return int(raw)


def include_types(raw: str) -> list[str]:
    """`--include file,assignment` into a list, rejecting anything not a type."""
    values = [part.strip() for part in raw.split(",") if part.strip()]
    if not values:
        raise argparse.ArgumentTypeError("no activity type was given")
    unknown = [value for value in values if value not in INCLUDE_CHOICES]
    if unknown:
        raise argparse.ArgumentTypeError(
            f"{', '.join(unknown)} is not an activity type; the types are "
            f"{', '.join(INCLUDE_CHOICES)}"
        )
    return values


def fetch_target(raw: str) -> str:
    """Digits, or something url-shaped. Nothing else reaches the core.

    Shape only. Whether a url is one this CLI will download from is the core's
    to decide, because which host that is portal knowledge and does not live in
    this repo. Checking the shape here is still worth it: it turns
    `iitb moodle fetch nonsense` into a usage error instead of a browser start.
    """
    text = raw.strip()
    if not text or not (text.isdigit() or "://" in text):
        raise argparse.ArgumentTypeError(
            f"{raw!r} is neither a numeric activity id nor a file url"
        )
    return text


def download_url(raw: str) -> str:
    """Something url-shaped, and nothing else reaches the core.

    Shape only, like `fetch_target`. Which urls this CLI actually downloads from
    is the core's to decide, because that vocabulary does not live in this repo.
    Checking the shape here still earns its place: it turns a typo into a usage
    error instead of a browser start.
    """
    text = raw.strip()
    if not text or "://" not in text:
        raise argparse.ArgumentTypeError(f"{raw!r} is not a url")
    return text


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
MOODLE = "iitb_core.moodle"
MAIL = "iitb_core.mail"
DOWNLOADS = "iitb_core.downloads"


def browser_start(args) -> dict:
    return core.call(BROWSER, "start")


def browser_attach(args) -> dict:
    return core.call(BROWSER, "attach")


def browser_status(args) -> dict:
    return core.call(BROWSER, "status")


def browser_stop(args) -> dict:
    return core.call(BROWSER, "stop")


def browser_login(args) -> dict:
    """Hand the operator a window, wait for them, report where they ended up.

    The same shape `sso-status` returns, and the same rule about exit 3: this
    fails with 103 when the sign-in was not completed, because the state after
    it is the state 103 describes. A session that was already live comes back
    immediately and is a plain success, so running this when unsure is free.

    The wait itself is the core's. This blocks until it answers, which is a
    human's worth of time, and nothing is printed until it does.
    """
    data = core.call(BROWSER, "login")
    if not data.get("logged_in"):
        raise CliError(103, detail=data.get("detail"))
    return {"loggedIn": True, "user": data.get("user")}


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


def downloads_fetch(args) -> object:
    """The same pre-flight the two portal fetches make, for the same reason.

    Nowhere to write is knowable here, with nothing live involved, and deciding
    it now is what makes the promise in the help text true: this fails before
    the network rather than after downloading a file it has nowhere to put.
    """
    if args.out is None and config.download_dir() is None:
        raise CliError(203)
    return core.call(
        DOWNLOADS, "fetch", url=args.url, out=args.out, force=args.force
    )


def placements_jobs(args) -> object:
    return core.call(
        PLACEMENTS,
        "jobs",
        status=args.status,
        eligible=args.eligible,
        company=args.company,
    )


def placements_job(args) -> object:
    """One posting, named by id or by company and job code.

    The exclusion is checked here rather than with an argparse mutually
    exclusive group, because the pair is a unit: argparse can say "not both" or
    "at least one of", and what this needs is "the id, or the pair, and a half
    of the pair is not an answer".
    """
    if args.job_id is not None and (args.company or args.job_code):
        raise CliError(
            204,
            detail="give a posting id, or --company with --job-code, not both",
        )
    if args.job_id is None and not (args.company and args.job_code):
        raise CliError(
            201,
            detail=(
                "name a posting: a posting id, or --company and --job-code "
                "together. A job code alone does not identify one."
            ),
        )
    return core.call(
        PLACEMENTS,
        "job",
        job_id=args.job_id,
        company=args.company,
        job_code=args.job_code,
        text=args.text,
    )


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


def moodle_courses(args) -> object:
    return core.call(MOODLE, "courses")


def moodle_course(args) -> object:
    """One course, whole.

    The one thing decided here rather than passed through: `--no-content` says
    fetch nothing and `--include` says fetch a subset, so the pair has no
    reading. Refusing is one flag away from resolution; guessing is not.
    """
    if args.no_content and args.include:
        raise CliError(
            204,
            detail=(
                "--no-content fetches no content and --include fetches a "
                "subset of it; give one or the other"
            ),
        )
    return core.call(
        MOODLE,
        "course",
        course_token=args.course,
        no_content=args.no_content,
        include=args.include,
        posts=args.posts,
        text=args.text,
    )


def moodle_deadlines(args) -> object:
    return core.call(
        MOODLE,
        "deadlines",
        course_token=args.course,
        announcements=args.announcements,
        since=args.since,
    )


def moodle_grades(args) -> object:
    return core.call(MOODLE, "grades", course_token=args.course)


def moodle_fetch(args) -> object:
    """The first command in this CLI that writes a file.

    The one check the shell owns: with no `--out` and no default download
    directory there is nowhere to write, and that is knowable here, with no
    portal involved. Deciding it now is what makes the promise in the help text
    true, that this fails before the network rather than after downloading a
    file it then has nowhere to put.
    """
    if args.out is None and config.download_dir() is None:
        raise CliError(203)
    return core.call(
        MOODLE, "fetch", target=args.target, out=args.out, force=args.force
    )


# ----------------------------------------------------------------------
# Mail. The one surface with no browser under it, and the one command in
# the whole CLI that reads from a human instead of from argv.
# ----------------------------------------------------------------------


def ask(prompt: str) -> str:
    """One visible line from the operator, prompted on stderr.

    `input()` would be shorter and is wrong here: it writes its prompt to
    stdout, and stdout carries exactly one JSON object per invocation. A
    prompt printed there is a prompt that lands in the middle of the thing
    the caller is parsing.
    """
    sys.stderr.write(prompt)
    sys.stderr.flush()
    line = sys.stdin.readline()
    if not line:
        raise EOFError
    return line.strip()


def mail_login(args) -> dict:
    """Collect two values from the operator and hand them straight to the core.

    **The token is read here and only here, from a hidden prompt.** There is no
    flag for it, there is no positional for it, and adding one would not be a
    convenience: an argument is readable by every other process on the machine
    for as long as the command runs, and the shell writes it into a history
    file that outlives the session. The LDAP id is a positional because it is
    not a secret and typing it every time is friction for nothing.

    Neither value is stored, logged, or looked at here. This asks, passes them
    on, and returns the core's receipt, which is built without the token in it.
    The verification against the live server happens on the core's side of the
    seam, before anything is written, so a rejected token never reaches disk.
    """
    # Asked before the prompt, not after, so an operator about to replace a
    # working credential is told so while they can still stop. No network.
    state = core.call(MAIL, "configured")
    sys.stderr.write(
        "iitb mail login: the token is hidden as you type, and is never "
        "printed, logged, or returned.\nDo not paste it into a chat window, "
        "an agent session, or a log.\n"
    )
    if state.get("configured"):
        sys.stderr.write(
            f"This replaces the credential already stored at "
            f"{state.get('credentialPath')}.\n"
        )

    try:
        ldap_id = args.ldap_id or ask("IITB LDAP id: ")
        token = getpass.getpass(
            "IITB SSO access token (hidden): ", stream=sys.stderr
        )
    except (EOFError, KeyboardInterrupt):
        raise CliError(
            201, detail="the login was cancelled; nothing was stored"
        ) from None

    return core.call(MAIL, "login", ldap_id=ldap_id, token=token)


def mail_mailboxes(args) -> object:
    return core.call(MAIL, "mailboxes")


def mail_list(args) -> object:
    return core.call(
        MAIL,
        "list",
        mailbox=args.mailbox,
        unseen=args.unseen,
        sender=args.sender,
        since=args.since,
        search=args.search,
        limit=args.limit,
    )


def mail_read(args) -> object:
    return core.call(MAIL, "read", uid=args.uid, mailbox=args.mailbox)


def mail_fetch(args) -> object:
    """The same pre-flight `moodle fetch` makes, for the same reason.

    Nowhere to write is knowable before the network, and mail is the surface
    where finding it out afterwards costs the most: the fetch that would have
    to be thrown away has already pulled somebody's whole message down.
    """
    if args.out is None and config.download_dir() is None:
        raise CliError(203)
    return core.call(
        MAIL,
        "fetch",
        uid=args.uid,
        mailbox=args.mailbox,
        out=args.out,
        force=args.force,
    )


# ----------------------------------------------------------------------
# Versions. The one command that answers about the install rather than a
# portal, and so the one that does not go through the core seam.
# ----------------------------------------------------------------------


def installed(distribution: str) -> str | None:
    try:
        return metadata.version(distribution)
    except metadata.PackageNotFoundError:
        return None


def version_data(hint: bool = False) -> dict:
    """Both versions, or 498 if there is no core to report one for.

    A missing core is the failure this command exists to diagnose, so it is
    reported as that failure. Answering `"iitb_core": null` at exit 0 would
    report an install problem as a success, which is exactly the reading that
    sends someone hunting through `dist-info` directories instead.
    """
    core_version = installed("iitb-core")
    if core_version is None:
        raise CliError(498, detail="iitb-core is not installed")
    # No install at all is possible when running straight from a source tree,
    # which is not a failure: the shell is running, so it is here to be asked.
    data = {"iitb": installed("iitb") or "unknown", "iitb_core": core_version}
    if hint:
        data["use"] = "iitb version"
    return data


def report_version(args) -> dict:
    return version_data()


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


class Answered(Exception):
    """A payload produced during the parse, ready for the envelope.

    `--version` has to be answered while parsing, the way `--help` is: the root
    parser requires a subcommand, so a flag on its own is rejected before any
    handler could run. argparse's own help action raises SystemExit for this;
    the envelope needs the payload as well, so this carries it out.
    """

    def __init__(self, data) -> None:
        self.data = data
        super().__init__("answered during the parse")


class VersionAction(argparse.Action):
    """`iitb --version`, answered in JSON like everything else."""

    def __init__(self, option_strings, dest=argparse.SUPPRESS, **kwargs):
        super().__init__(option_strings, dest, nargs=0, **kwargs)

    def __call__(self, parser, namespace, values, option_string=None):
        raise Answered(version_data(hint=True))


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
    root.add_argument("--version", action=VersionAction, help=argparse.SUPPRESS)
    top = commands(root, "command")

    _build_browser(top)
    _build_placements(top)
    _build_moodle(top)
    _build_mail(top)
    _build_downloads(top)
    make(top, "version", VERSION_HELP, report_version)
    return root


def _build_browser(top) -> None:
    browser = make(top, "browser", BROWSER_HELP)
    sub = commands(browser, "subcommand")
    make(sub, "login", BROWSER_LOGIN_HELP, browser_login)
    make(sub, "start", BROWSER_START_HELP, browser_start)
    make(sub, "attach", BROWSER_ATTACH_HELP, browser_attach)
    make(sub, "status", BROWSER_STATUS_HELP, browser_status)
    make(sub, "sso-status", BROWSER_SSO_STATUS_HELP, browser_sso_status)
    make(sub, "stop", BROWSER_STOP_HELP, browser_stop)


def _build_downloads(top) -> None:
    """The setting, and the one command that takes a url and nothing else.

    A url is a plain string here beyond being url-shaped: which services this
    CLI downloads from is the core's knowledge, and rejecting a host in this
    repo would publish the list of hosts it accepts.
    """
    downloads = make(top, "downloads", DOWNLOADS_HELP)
    sub = commands(downloads, "subcommand")

    fetch = make(sub, "fetch", DOWNLOADS_FETCH_HELP, downloads_fetch)
    hidden(fetch, "url", metavar="<url>", type=download_url)
    hidden(fetch, "--out", metavar="PATH", default=None)
    hidden(fetch, "--force", action="store_true")

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
    hidden(job, "job_id", metavar="<job-id>", type=numeric_id, nargs="?", default=None)
    hidden(job, "--company", metavar="TEXT", default=None)
    hidden(job, "--job-code", metavar="CODE", default=None)
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


def _build_moodle(top) -> None:
    """Five leaves, and nothing mutating is reachable from any of them.

    A course is a plain string here, not a `numeric_id`: the positional takes
    an id or a code, and which one it is is the core's to work out against the
    live enrolment. Rejecting a non-numeric course here would make the whole
    addressing rule unreachable.
    """
    moodle = make(top, "moodle", MOODLE_HELP)
    sub = commands(moodle, "subcommand")

    make(sub, "courses", MOODLE_COURSES_HELP, moodle_courses)

    course = make(sub, "course", MOODLE_COURSE_HELP, moodle_course)
    hidden(course, "course", metavar="<course>")
    hidden(course, "--no-content", action="store_true")
    hidden(
        course,
        "--include",
        metavar="TYPE[,TYPE...]",
        type=include_types,
        default=None,
    )
    hidden(course, "--posts", action="store_true")
    hidden(course, "--text", action="store_true")

    deadlines = make(sub, "deadlines", MOODLE_DEADLINES_HELP, moodle_deadlines)
    hidden(deadlines, "course", metavar="<course>", nargs="?", default=None)
    hidden(
        deadlines,
        "--announcements",
        metavar="N",
        type=whole_number,
        default=DEFAULT_ANNOUNCEMENTS,
    )
    hidden(deadlines, "--since", metavar="DATE", type=iso_date, default=None)

    grades = make(sub, "grades", MOODLE_GRADES_HELP, moodle_grades)
    hidden(grades, "course", metavar="<course>", nargs="?", default=None)

    fetch = make(sub, "fetch", MOODLE_FETCH_HELP, moodle_fetch)
    hidden(fetch, "target", metavar="<target>", type=fetch_target)
    hidden(fetch, "--out", metavar="PATH", default=None)
    hidden(fetch, "--force", action="store_true")


def _build_mail(top) -> None:
    """Five leaves, one of which prompts, and no argument anywhere is a secret.

    The property to keep while editing this function: **nothing in this tree
    accepts a token**. Not as a flag, not as a positional, not as an
    environment variable read here. `login` is the only command that handles
    one at all, and it reads it from a hidden prompt inside its handler. The
    check asserts it, because the reason is invisible in the diff that would
    break it: a `--token` flag looks like a convenience and is a disclosure,
    since arguments are world-readable in the process table and are written to
    the shell's history file.

    A mailbox is a plain string, like a moodle course: folder names are the
    operator's own and the only vocabulary that could reject one lives on the
    account, not here.
    """
    mail = make(top, "mail", MAIL_HELP)
    sub = commands(mail, "subcommand")

    login = make(sub, "login", MAIL_LOGIN_HELP, mail_login)
    hidden(login, "ldap_id", metavar="<ldap-id>", nargs="?", default=None)

    make(sub, "mailboxes", MAIL_MAILBOXES_HELP, mail_mailboxes)

    listing = make(sub, "list", MAIL_LIST_HELP, mail_list)
    hidden(listing, "--mailbox", metavar="NAME", default=DEFAULT_MAILBOX)
    hidden(listing, "--unseen", action="store_true")
    # `--from` is the operator's word for it and `from` is a Python keyword, so
    # the destination is named rather than derived.
    hidden(listing, "--from", metavar="TEXT", dest="sender", default=None)
    hidden(listing, "--since", metavar="DATE", type=iso_date, default=None)
    hidden(listing, "--search", metavar="TEXT", default=None)
    hidden(listing, "--limit", metavar="N", type=positive_int, default=DEFAULT_LIMIT)

    read = make(sub, "read", MAIL_READ_HELP, mail_read)
    hidden(read, "uid", metavar="<uid>", type=numeric_id)
    hidden(read, "--mailbox", metavar="NAME", default=DEFAULT_MAILBOX)

    fetch = make(sub, "fetch", MAIL_FETCH_HELP, mail_fetch)
    hidden(fetch, "uid", metavar="<uid>", type=numeric_id)
    hidden(fetch, "--mailbox", metavar="NAME", default=DEFAULT_MAILBOX)
    hidden(fetch, "--out", metavar="PATH", default=None)
    hidden(fetch, "--force", action="store_true")


# ----------------------------------------------------------------------
# The envelope
# ----------------------------------------------------------------------


INTERNAL_ERROR = 105


def emit(payload: dict) -> None:
    """Print one object, built whole before a byte of it is written.

    Serialising first rather than streaming into stdout is what keeps a failed
    serialisation from printing half an object and then the error object for
    the failure. Half an object is unparseable, which is the failure mode this
    whole layer exists to make impossible.
    """
    sys.stdout.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def internal_error(exc: BaseException) -> CliError:
    """Anything at all, as the registry's last-resort failure.

    Only the exception's class name goes in `detail`. An exception's message is
    whatever it was holding when it died, which on this CLI can be portal data,
    so the message stays in the log file on the operator's own laptop and the
    error object names the file.
    """
    when = datetime.now(timezone.utc).isoformat(timespec="seconds")
    where = config.append_traceback(
        f"--- {when} {' '.join(sys.argv)}\n"
        + "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    )
    detail = type(exc).__name__
    if where is not None:
        detail += f"; traceback appended to {where}"
    return CliError(INTERNAL_ERROR, detail=detail)


def main(argv: list[str] | None = None) -> int:
    """One JSON object on stdout and one exit code, on every path there is.

    `dispatch` owns the failures that have a code. This layer owns the ones
    nobody planned for, which are exactly the ones that would otherwise leave
    stdout empty: an unexpected exception, an interrupt, a `SystemExit` raised
    at a non-zero code from somewhere below. Each becomes error 105 at exit 1,
    so what a consumer reads is always a name it can branch on rather than a
    parse error on nothing.
    """
    try:
        return dispatch(argv)
    except BaseException as exc:  # noqa: BLE001 - the last resort, on purpose
        try:
            emit({"ok": False, "error": internal_error(exc).as_error()})
        except Exception:  # noqa: BLE001 - stdout itself is gone; nothing to do
            pass
        # 105's exit code, written out rather than read from the registry: the
        # one path that must not depend on anything else still working.
        return 1


def dispatch(argv: list[str] | None) -> int:
    try:
        args = build_parser().parse_args(argv)
        emit({"ok": True, "data": args.handler(args)})
        return 0
    except Answered as answer:  # --version, produced during the parse
        emit({"ok": True, "data": answer.data})
        return 0
    except CliError as err:
        emit({"ok": False, "error": err.as_error()})
        return err.exit_code
    except SystemExit as exc:  # --help printed its text and stopped
        if exc.code:
            raise  # a non-zero exit with an empty stdout is what 105 is for
        return 0


def run() -> None:
    sys.exit(main())


if __name__ == "__main__":
    run()
