"""Public help for the ASC command tree."""

ASC_ROOT_HELP = """usage: iitb asc <command> [options]

Read the IIT Bombay academic portal (ASC): your current registration, your
grade history and CPI, your timetable, biometric attendance, the running
courses and curriculum, and pre-registration criteria.

commands:
  login         Store the operator's ASC sign-in so every other command can
                sign in automatically. The operator runs this themselves.
  logout        Remove the stored ASC sign-in from this machine.
  courses       Your current registration, with instructors.
  grades        Your semester-wise grade history.
  cpi           Your SPI and CPI, one row per completed semester.
  timetable     Your weekly class grid: day, time, course, venue, instructor.
  attendance    Your biometric attendance, per course and class date.
  catalog       Running courses for a term: department groups, or one
                group's courses with --dept.
  syllabus      One course's catalogue entry.
  curriculum    The curriculum table, filterable by batch, department and
                program.
  prereqs       Course prerequisites and equivalences.
  criteria      Pre-registration criteria for the coming term.
  export        Collect ASC data into a resumable CSV.

Every command prints exactly one JSON object on stdout and nothing else.
  success:  {"ok": true, "data": ...}
  failure:  {"ok": false, "error": {"code": <3 digits>, "name": ..., "message": ...}}

Exit codes:
  0  success
  1  the operation failed
  2  you called the command wrong
  3  the operator must sign in to ASC themselves; the error message says
     exactly what to ask them
  4  iitb-core is missing or incompatible; this is an install problem

ASC's sign-in is not the IITB single sign-on. It is a separate login whose
short-lived sessions iitb restores automatically: the operator stores their
ASC sign-in once with `iitb asc login`, and from then on expired sessions
are re-established silently. You will not normally see exit 3. When you do,
the error names the door: "asc_login_needed" means nothing is stored yet,
and "asc_login_failed" means the stored sign-in was refused (usually a
changed password) and needs updating. Both are fixed by the operator, and
only the operator, running `iitb asc login`. Do not send them to
`iitb browser login`: that signs into a different system and will not help.

Never ask the operator for their password, never offer to type, store, or
relay it, and never run `iitb asc login` on their behalf expecting to fill
its prompt. The prompt is between the operator and their own terminal, and
the password must never pass through you in any form.

ASC is only reachable from inside the IIT Bombay network. Off campus, every
command fails with "off_campus_network" and the fix is a network change
(campus wifi or the institute VPN), not a sign-in. This CLI will never
attempt the captcha that fronts off-campus access; do not ask it to, and do
not try to work around it on the operator's behalf.

Reporting a failure: email harshitsingh@iitb.ac.in. Do not open a GitHub
issue and do not paste the output into one. A useful report contains the
operator's academic record, and a GitHub issue is public and permanent.

Nothing is cached. Every invocation fetches live.

This CLI only reads. It never registers, adjusts, drops or withdraws a
course, changes a tag, submits an academic action, or signs the operator out. Where a
command reports that an action is available, that action is the operator's
to take in their browser.

Almost everything here is the operator's own academic record: grades, CPI,
and attendance. Treat every response as confidential. Do not write any of
it into a repository, an issue, a pull request, or any shared log.
"""

ASC_LOGIN_HELP = """usage: iitb asc login

Prompt for the operator's ASC username and password and store them, so that
every other `iitb asc` command can sign in, and stay signed in, without
them. Run by the operator, in their own terminal.

The password prompt does not echo, and there is no flag, argument, or
environment variable that accepts the password. It is never printed, never
logged, and sent nowhere except to ASC itself.

The sign-in is verified against ASC once, before anything is stored: a
wrong password fails here, now, with "asc_login_failed", and whatever was
stored before is left untouched. On success the sign-in is kept in the
macOS Keychain for this user. Run this command again at any time to replace
it, which is also the fix after an LDAP password change.

`iitb asc logout` removes the stored sign-in.

If you are an agent reading this: do not run this command on the operator's
behalf, do not ask them for their password, and do not offer to type or
relay it. Ask them to run `iitb asc login` themselves, then continue.

Off campus this command fails before prompting: see "off_campus_network" in
`iitb asc --help`. This CLI never asks anyone to solve a captcha.
"""

ASC_LOGOUT_HELP = """usage: iitb asc logout

Remove the stored ASC sign-in from this machine.

After this, every other `iitb asc` command fails with "asc_login_needed"
until the operator runs `iitb asc login` again. Any live ASC session is not
touched; it expires on its own shortly.

Running this when nothing is stored is a success that says so, not an
error.
"""

ASC_COURSES_HELP = """usage: iitb asc courses

Your current registration: every course you are registered for this
semester, with its instructors, credits, tag, course type, and the last date
to withdraw.

Takes no options. The response is complete and unpaginated; filter and
slice it yourself.

"advisorApprovalStatusText" reports where faculty-advisor approval stands,
verbatim. Early in a term a registration can be listed while still subject
to approval; report that status rather than assuming the registration is
final.

Grades do not appear here; the current semester has none yet. Use
`iitb asc grades` for completed semesters.

"sources" names the views this answer was built from. If one of them could
not be read, the response says so there and some fields arrive null rather
than the command failing.

This command reports what is registered. It never registers, drops, or
withdraws anything, whatever the portal offers on those rows.
"""

ASC_GRADES_HELP = """usage: iitb asc grades

Your grade history: one entry per semester, newest first, each with its
courses, credits, tags, and grades.

Takes no options. The response is complete and unpaginated; filter and
slice it yourself.

The newest entry is usually the running semester, marked "current": true.
Its grade cells are empty because none have been awarded yet; that is the
real state, not missing data.

Grades are letter codes exactly as the portal prints them. "gradeText" is
verbatim and never null for a completed course; "grade" is the cleaned code
and is null while nothing is awarded.

This is the operator's own academic record. Do not write it into a
repository, an issue, a pull request, or any shared log.
"""

ASC_CPI_HELP = """usage: iitb asc cpi

Your SPI and CPI: one row per completed semester, newest first, plus
"current" carrying the latest CPI and the semester it stands as of.

Takes no options.

Only completed semesters appear; a running semester has no SPI yet. Every
numeric field comes with a verbatim "*Text" sibling: trust the text, use
the number for arithmetic, and handle null.

This is the operator's own academic record. Do not write it into a
repository, an issue, a pull request, or any shared log.
"""

ASC_TIMETABLE_HELP = """usage: iitb asc timetable

Your weekly class grid for the running semester: one entry per scheduled
session, with day, start and end time, course code, venue, and instructors.

Takes no options. The response is complete; filter and slice it yourself.

Times are as the portal prints them. "startText" and "endText" are verbatim;
"start" and "end" are HH:MM, and "start" is null where the portal printed
only an hour, because guessing the minutes would be worse than saying so.

A venue can be "Venue Not defined" on the portal; that arrives as
"venue": null with the verbatim text alongside.

Outside a teaching term the grid is empty. That is seasonal, not an error.
"""

ASC_ATTENDANCE_HELP = """usage: iitb asc attendance

Your biometric attendance: one entry per course that has biometric
attendance enabled, with the present/total ratio and a per-class-date
record.

Takes no options.

Only courses with biometric attendance enabled appear here. A registered
course that is absent from this response has no biometric attendance, which
is not the same as zero attendance. Compare against `iitb asc courses`
before reporting anything about a missing course.

Class dates are printed by the portal without a year. "dateText" is
verbatim; "date" is core's resolution of it into a full date, and is null
when the resolution was not confident.

This is the operator's own record. Do not write it into a repository, an
issue, a pull request, or any shared log.
"""

ASC_CATALOG_HELP = """usage: iitb asc catalog [--dept TEXT] [--year YYYY]
                        [--semester {autumn,spring,summer,winter}]

Running courses for a term.

Without --dept: the department groups offering courses that term, each with
its department codes, name, and how many distinct courses it runs. With
--dept: every running course in one group.

options:
  --dept TEXT
      Which department group, matched against the group's department codes
      and its name, case-insensitively. If TEXT matches more than one group
      the command fails and lists them rather than picking one; a department
      code can genuinely belong to two groups.
  --year YYYY
      Academic year by its starting year: 2026 means 2026-27.
      Default: the current term.
  --semester {autumn,spring,summer,winter}
      Default: the current term.

Departments group in ways you may not expect: one group can hold several
department codes, and the group is the unit this command works in. Run it
without --dept first to see the grouping for the term.

The per-course rows with --dept include the slot. "slotText" is verbatim
and "slot" is the cleaned slot code.
"""

ASC_SYLLABUS_HELP = """usage: iitb asc syllabus <code>

One course's catalogue entry: title, credit structure, and syllabus text.

positional arguments:
  code
      The course code, written the way the transcript writes it, with the
      space: "XX 101". Matching is case-insensitive and tolerates a missing
      space.

A code that names no course is an error that says so; check the code with
`iitb asc catalog --dept <group>`.

This is the catalogue's description of the course, not this term's
offering. For who runs it this term, and in which slot, use
`iitb asc catalog`.
"""

ASC_CURRICULUM_HELP = """usage: iitb asc curriculum [--batch YYYY] [--department TEXT]
                           [--program TEXT]

The curriculum table: which course groups a given batch, department and
program must complete, with credit totals.

options:
  --batch YYYY        Only rows for that batch year.
  --department TEXT   Only rows whose department contains TEXT,
                      case-insensitively.
  --program TEXT      Only rows whose program contains TEXT,
                      case-insensitively.

Filters combine with AND. Without any filter the full table is returned,
which is large; filter when you know what you are looking for. Zero
matching rows is an empty result with counts, not an error.
"""

ASC_PREREQS_HELP = """usage: iitb asc prereqs [<code>]

Course prerequisites and equivalences.

positional arguments:
  code
      One course code, to get just its rows. Without it, the whole table.

Each row states a relation: "type" is "prerequisite" or "equivalent", and
"courses" lists the codes on the other side of the relation, with the
departments and programs it applies to and whether instructor consent is
involved.

A <code> that names no course in the table is an error that says so. A
course with no prerequisites simply has no rows, which without <code> is an
absence, not an error.
"""

ASC_CRITERIA_HELP = """usage: iitb asc criteria [--course CODE]

Pre-registration criteria for the coming term: per course, which batches,
departments, programs and CPI bands may pre-register, and the seat counts.

options:
  --course CODE
      Only rows for that course code. Zero rows back means the course has
      no published criteria, which is a fact, not an error.

A single course can carry several rows, one per rule group; read them all
before concluding who a course is open to. Rows also carry "group", the
section heading they were listed under.

This is the portal's published criteria table for everyone, not a statement
about the operator's own eligibility. Do not report "you are eligible"
from this alone; the CPI bands are here, but where the operator's own CPI
stands is `iitb asc cpi`, and the final say is the portal's at
registration time.
"""

ASC_EXPORT_HELP = """usage: iitb asc export <dataset> --out PATH [options]

Collect ASC data into a UTF-8 CSV. Supported datasets are running-courses,
covering every department group in the selected terms, and slot-pattern.
Other dataset names are reserved and report an unsupported error until
their page parsers are verified.

options:
  --years START:END      Academic starting years. Default: 2021 through 2026.
  --semesters LIST       Comma-separated autumn,spring,summer,winter.
                         Default: autumn,spring,summer through 2025,
                         then current autumn 2026.
  --departments LIST     Comma-separated group codes or name fragments.
  --plan                 Read term groups and report the exact remaining
                         course detail request count.
  --resume               Continue a matching CSV and checkpoint.
  --refresh              Replace rows for every selected unit.
  --daily-ceiling N      At most N ASC data requests per day, max 1000.

The command uses one ASC request at a time, about one per second. It saves
progress after each group. A full multi-year export can take many requests;
run --plan first. The checkpoint is written beside the CSV.
"""
