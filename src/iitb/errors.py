"""The iitb error-code registry.

Every failure the CLI can report is one row in `REGISTRY`: a 3-digit JSON
code, a stable name, the process exit code, and the public message.

Three properties of this table are the contract, and they are why it lives
in one file instead of being scattered over the commands:

- **The number is permanent.** A code never changes meaning. Blocks are
  reserved so a surface added later cannot collide with one added earlier.
- **The name is the thing to branch on.** A transcript reading
  `sso_session_ended` explains itself where `103` does not, and the name
  survives any renumbering.
- **The message is public and portal-neutral.** It may name an `iitb`
  command. It may not name a host, an endpoint, an auth artifact, or an
  HTTP status. Anything specific belongs in `detail`, which the core
  produces at runtime and this repo never authors.

Codes 121, 122, 123 and 124, and usage code 203, describe downloading. They
were minted for placements, which then shipped no command that downloads, and
kept on the rule that a code never changes meaning and its number is never
freed for reuse. `iitb moodle fetch` is the consumer they were kept for. Their
names say "document" where moodle says "file", which is a wording mismatch and
not a meaning one, so they are reused as written: minting `file_fetch_failed`
alongside `document_fetch_failed` would give the CLI two codes for one
condition, which is the one thing a registry exists to prevent.

Block reservations::

    100-109  shared: session, browser, runtime, and the shell itself
    110-139  placements
    140-169  moodle           (140-149 defined, 150-169 free)
    170-189  browser
    190-199  shared: config and downloads
    200-219  shared usage
    220-239  placements usage (reserved, none needed yet)
    240-269  moodle usage     (reserved; examined and deliberately empty)
    498-499  core

Moodle needs no usage code of its own. Every shape error it can produce is
already 201, 202, 203 or 204, and its three candidates (an ambiguous course, a
fetch target that is not a file, an activity type with no reader) are existence
questions rather than shape ones, which are exit 1 by the standing rule: shape
is usage, existence is operational. Recorded rather than left silent, so an
implementer finding an empty reserved block knows it was examined.
"""

from __future__ import annotations

# code -> (name, process exit code, public message)
REGISTRY: dict[int, tuple[str, int, str]] = {
    # --- 100 to 109: session and runtime -------------------------------
    # An expired session is the core's to restore, silently, before it does
    # anything else. These fire only when that restoration itself failed,
    # which makes them operational failures rather than requests to a human.
    101: (
        "portal_session_recovery_failed",
        1,
        "Could not restore the placements portal session. This is not "
        "something the operator needs to do by hand; report it as described "
        "by `iitb placements --help`.",
    ),
    102: (
        "document_session_recovery_failed",
        1,
        "Could not restore the placements document session. This is not "
        "something the operator needs to do by hand; report it as described "
        "by `iitb placements --help`.",
    ),
    # The one code in the whole registry that asks a human for anything, and it
    # stays one code now that there is a command to point them at. A
    # `iitb browser login` that ran and ended with no session is this, not a
    # code of its own: the state it leaves behind is exactly the state this
    # describes, and minting a second exit 3 would cost every consumer the
    # single rule that exit 3 means go and get the operator.
    103: (
        "sso_session_ended",
        3,
        "The operator's IITB single sign-on session has ended, and only they "
        "can restore it. Ask them to run `iitb browser login`, which opens a "
        "window for them to sign in once, then run this command again. Do not "
        "attempt to sign in on their behalf.",
    ),
    104: (
        "browser_unavailable",
        1,
        "Could not start the iitb browser. Run `iitb browser status` to see "
        "why.",
    ),
    # The last resort, and the only code no command raises on purpose. It is
    # what makes "exactly one JSON object per invocation" structural rather than
    # incidental: anything unexpected on any exit path becomes this instead of a
    # silent non-zero exit, which is the one outcome an agent cannot branch on.
    105: (
        "internal_error",
        1,
        "iitb failed in a way it has no code for. This is a bug in iitb, not "
        "something the operator can fix; report it as described by "
        "`iitb --help`. The traceback was written to a log file under "
        "~/.config/iitb/, and `detail` names it.",
    ),
    # --- 110 to 139: placements operations ------------------------------
    110: (
        "portal_unreachable",
        1,
        "Could not reach the placements portal. Check the network and try "
        "again.",
    ),
    111: (
        "portal_http_error",
        1,
        "The placements portal refused the request. If it keeps happening, "
        "report it as described by `iitb placements --help`.",
    ),
    112: (
        "portal_response_unexpected",
        1,
        "The placements portal returned something this version of iitb does "
        "not understand. Retrying will not help. Report it as described by "
        "`iitb placements --help`.",
    ),
    113: (
        "portal_rate_limited",
        1,
        "The placements portal is rate limiting this session. Wait and try "
        "again.",
    ),
    # Worded for both ways of naming a posting: by id, and by company and job
    # code. The code means what it always meant, "that posting is not here";
    # only the sentence stopped assuming an id was how you asked for it.
    114: (
        "job_not_found",
        1,
        "No such posting in this season. List the postings that do exist with "
        "`iitb placements jobs --status all`.",
    ),
    115: (
        "job_code_ambiguous",
        1,
        "That job code matches more than one posting, so it does not name a "
        "single one. `detail` lists what it matched; ask for one of them by "
        "its posting id.",
    ),
    120: (
        "blog_post_not_found",
        1,
        "No blog post with that id on that blog. Post ids are per blog, so "
        "an id from one will not be found on another. List them with "
        "`iitb placements blog posts`.",
    ),
    121: (
        "document_fetch_failed",
        1,
        "The document could not be downloaded. Nothing was written.",
    ),
    122: (
        "document_type_unexpected",
        1,
        "What came back was not the document that was asked for, so nothing "
        "was written. Report it as described by `iitb placements --help`.",
    ),
    123: (
        "download_path_unwritable",
        1,
        "The download directory is missing or not writable. Nothing was "
        "written.",
    ),
    124: (
        "download_target_exists",
        1,
        "That file already exists, so nothing was written. Pass --force to "
        "overwrite it, or --out to write somewhere else.",
    ),
    # --- 140 to 169: moodle operations ----------------------------------
    # All exit 1. None of them is exit 3 and none of them asks a human for
    # anything: exit 3 stays one code with one meaning across the whole CLI,
    # and that code is 103. A moodle session that has lapsed while the
    # operator's sign-on is still alive is the ordinary path, restored before
    # anything is printed; a restoration that then fails is 145, never 103.
    140: (
        "course_not_found",
        1,
        "No course you are enrolled in matches that. Run `iitb moodle courses` "
        "to see what you are enrolled in now; the list changes during the term.",
    ),
    141: (
        "course_ambiguous",
        1,
        "More than one of your courses matches that name. `detail` lists them; "
        "name one by its numeric id instead.",
    ),
    142: (
        "moodle_unreachable",
        1,
        "Could not reach Moodle. Check the network and try again.",
    ),
    143: (
        "moodle_http_error",
        1,
        "Moodle answered with an error. Try again; if it keeps happening, "
        "report it as described by `iitb moodle --help`.",
    ),
    144: (
        "moodle_response_unexpected",
        1,
        "Moodle returned something this version of iitb does not understand. "
        "Retrying will not help. Report it as described by "
        "`iitb moodle --help`.",
    ),
    145: (
        "moodle_session_recovery_failed",
        1,
        "Could not establish a Moodle session. This is not something the "
        "operator needs to do by hand; report it as described by "
        "`iitb moodle --help`.",
    ),
    # Scoped to one course, which is what separates it from 144: a different
    # course may still work. It is also the only failure inside an enumeration
    # that fails the command, because per-activity failures are reported in-band.
    146: (
        "course_structure_unavailable",
        1,
        "Could not read the contents of that course. Other courses may still "
        "work. If it keeps happening, report it as described by "
        "`iitb moodle --help`.",
    ),
    147: (
        "activity_not_found",
        1,
        "No activity you can see has that id. Activity ids change when the "
        "institute rebuilds Moodle; run `iitb moodle course <course>` again "
        "and use an id from the fresh response.",
    ),
    # Exit 1 rather than a usage code on purpose: the argument was well formed
    # and the thing simply is not a file.
    148: (
        "activity_has_no_file",
        1,
        "That activity is not a file, so there is nothing to download. "
        "`iitb moodle course <course>` shows what each activity is.",
    ),
    149: (
        "grade_report_unavailable",
        1,
        "Could not read your grades. If it keeps happening, report it as "
        "described by `iitb moodle --help`.",
    ),
    # --- 170 to 189: browser --------------------------------------------
    # Deliberately not 103. A check that could not run is not a session that
    # ended, and reporting one as the other sends the operator to sign in for
    # nothing, which is the single wrong answer that costs a human real time.
    170: (
        "sso_check_failed",
        1,
        "Could not check the operator's IITB single sign-on, so its state is "
        "unknown. This is not the same as an ended session: do not ask the "
        "operator to sign in on this error. Try again.",
    ),
    # --- 190 to 199: config and downloads -------------------------------
    190: (
        "config_unreadable",
        1,
        "The iitb configuration under ~/.config/iitb/ exists but could not be "
        "read.",
    ),
    191: (
        "config_unwritable",
        1,
        "The setting could not be saved under ~/.config/iitb/.",
    ),
    # --- 200 to 219: usage. Exit 2. -------------------------------------
    200: (
        "unknown_command",
        2,
        "Unknown or missing command. Run `iitb --help` for the whole command "
        "tree.",
    ),
    201: (
        "missing_argument",
        2,
        "A required argument was not given. Run the command with --help for "
        "its usage.",
    ),
    202: (
        "invalid_argument",
        2,
        "An argument value is not valid. Run the command with --help for the "
        "accepted values.",
    ),
    203: (
        "output_path_required",
        2,
        "No default download directory is set, so --out is required. Either "
        "pass --out PATH, or set the default once with "
        "`iitb downloads set-default <path>`.",
    ),
    204: (
        "conflicting_options",
        2,
        "Those options cannot be used together. Run the command with --help "
        "for its usage.",
    ),
    # --- core. Exit 4 is structural and permanent, exit 1 is this run. ---
    498: (
        "core_missing",
        4,
        "iitb-core is missing, or present at a version this iitb does not "
        "understand. This is an install problem: running the command again "
        "will not fix it.",
    ),
    499: (
        "core_failed",
        1,
        "iitb-core failed in a way this version of iitb does not recognise. "
        "Report it as described by `iitb placements --help`.",
    ),
}

BY_NAME: dict[str, int] = {name: code for code, (name, _, _) in REGISTRY.items()}


class CliError(Exception):
    """A failure with a registry code, ready to be printed as the envelope.

    `detail` is the optional runtime string. It is what lets the public
    message stay portal-neutral without being useless: the message says what
    to do in CLI terms, the detail may say more, and the detail is never
    authored in this repo.
    """

    def __init__(self, code: int, detail: str | None = None) -> None:
        self.code = code
        self.name, self.exit_code, self.message = REGISTRY[code]
        self.detail = detail or None
        super().__init__(f"{code} {self.name}")

    def as_error(self) -> dict:
        error = {"code": self.code, "name": self.name, "message": self.message}
        if self.detail:
            error["detail"] = self.detail
        return error
