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

Codes 121, 122, 123 and 124, and usage code 203, describe downloading. No v1
command downloads a file, so only 123 can currently fire (from `downloads
set-default`). They stay because a code never changes meaning and because
downloads are the next surface: deleting them would free numbers that must
never be reused, and re-adding them later is exactly what the permanence rule
exists to prevent.

Block reservations::

    100-109  shared: session, browser, runtime, and the shell itself
    110-139  placements
    140-169  moodle          (reserved, undefined)
    170-189  browser
    190-199  shared: config and downloads
    200-219  shared usage
    220-239  placements usage (reserved, none needed yet)
    240-269  moodle usage     (reserved)
    498-499  core
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
    # The one code in the whole registry that asks a human for anything.
    103: (
        "sso_session_ended",
        3,
        "The operator's IITB single sign-on session has ended, and only they "
        "can restore it. Ask them to sign in to IITB SSO in the iitb browser "
        "window, then run this command again. Do not attempt to sign in on "
        "their behalf.",
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
