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

`iitb downloads fetch` reuses all five and adds 192, 193 and 194 for the three
conditions none of them covers: the service is unreachable, the link is dead,
and a session that could not be established. They are in the 190 block rather
than a portal's, because the command belongs to no portal.

Block reservations::

    100-109  shared: session, browser, runtime, and the shell itself
    110-139  placements
    140-149  moodle
    150-169  mail             (150-157 defined, 158-169 free)
    170-189  browser          (170-171 defined, 172-189 free)
    190-199  shared: config and downloads (190-194 defined, 195-199 free)
    200-219  shared usage
    220-239  placements usage (reserved, none needed yet)
    240-269  moodle usage     (reserved; examined and deliberately empty)
    270-289  mail usage       (reserved; examined and deliberately empty)
    497-499  core

Moodle was reserved 140-169 and defined 140-149. Mail took 150-169 out of the
tail of that reservation rather than opening a block further out, because a
reservation is a promise about collisions and moodle has none to make in a
range it did not use. Every moodle code that exists keeps its number, which is
the only guarantee the table actually gives.

Neither moodle nor mail needs a usage code of its own. Every shape error either
can produce is already 201, 202, 203 or 204. Moodle's three candidates (an
ambiguous course, a fetch target that is not a file, an activity type with no
reader) and mail's three (an unknown folder, a UID that names no message, a
message with nothing attached) are existence questions rather than shape ones,
which are exit 1 by the standing rule: shape is usage, existence is
operational. A cancelled `iitb mail login` is the one that looks like a new
code and is not: nothing was given where something was required, which is 201.
Recorded rather than left silent, so an implementer finding an empty reserved
block knows it was examined.
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
    # The exit 3 for everything that rides the browser, which is every surface
    # but mail. A `iitb browser login` that ran and ended with no session is
    # this, not a code of its own: the state it leaves behind is exactly the
    # state this describes. Mail adds 150 and 151 rather than reusing this,
    # because the remedy is a different command; the rule an agent branches on
    # is unchanged, since it is the exit code that says "go and get the
    # operator" and `error.name` that says which door to send them to.
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
    # --- 150 to 169: mail -----------------------------------------------
    # The first surface with two exit 3 codes, and the only one that can have
    # them. Everywhere else a dead sign-on is one condition with one remedy, so
    # 103 covers it. Mail runs on a credential the operator issues by hand and
    # that nothing here can renew, so "there is none yet" and "the one there
    # stopped working" are two conditions, both of which only a human can end.
    # They stay two codes because the sentence to read out differs (set it up,
    # versus set it up again), and they are both exit 3 because the rule an
    # agent runs on must not change: exit 3 means go and get the operator.
    # Neither message may tell them to run `iitb browser login`, which would
    # send them to the wrong place and leave mail exactly as broken.
    150: (
        "mail_not_configured",
        3,
        "No IITB mail credential is stored on this machine, and only the "
        "operator can store one. Ask them to run `iitb mail login`, which "
        "prompts them for their own access token, then run this command "
        "again. Do not ask them for that token and do not offer to type it.",
    ),
    151: (
        "mail_token_rejected",
        3,
        "The stored IITB mail credential was refused, which normally means "
        "the operator's access token has expired. Only they can replace it: "
        "ask them to run `iitb mail login` again with a fresh token, then run "
        "this command again. Nothing this CLI can do will renew it, and "
        "retrying will not help.",
    ),
    152: (
        "mail_unreachable",
        1,
        "Could not reach the IITB mail server. Check the network and try "
        "again.",
    ),
    153: (
        "mail_protocol_error",
        1,
        "The IITB mail server answered something this version of iitb does "
        "not understand. Report it as described by `iitb mail --help`.",
    ),
    154: (
        "mailbox_not_found",
        1,
        "This account has no folder with that name. Run `iitb mail mailboxes` "
        "to see the folders it does have; `detail` lists them too.",
    ),
    # Exit 1, not a usage code: the UID was a well formed number and simply
    # names nothing. Shape is usage, existence is operational.
    155: (
        "message_not_found",
        1,
        "No message with that UID in that folder. UIDs are per folder, so a "
        "UID from one folder is not found in another: check --mailbox. Run "
        "`iitb mail list` again and use a UID from the fresh response.",
    ),
    156: (
        "message_unreadable",
        1,
        "That message could not be read. Every other message in the folder is "
        "unaffected. Report it as described by `iitb mail --help`.",
    ),
    # Mirrors 148: the argument was fine and the message simply has nothing on
    # it, which is a fact about the mail rather than about the command line.
    157: (
        "message_has_no_attachments",
        1,
        "That message has nothing attached, so nothing was written. "
        "`iitb mail list` reports \"hasAttachments\" for each message, and "
        "`iitb mail read` lists what one carries.",
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
    # Not 104, and the distinction is the whole reason this code exists. 104
    # means there is a Chrome and it would not start, which is a bug to
    # report; this means the machine has no Chrome at all, which is a five
    # minute download and the only thing standing between a new operator and
    # a working CLI. Told as 104 it reads "report it", which is the one
    # instruction that leaves them exactly as stuck.
    #
    # Exit 1, not exit 3, even though a human does have to act. Exit 3 keeps
    # its single meaning across this CLI, which is that the operator's own
    # sign-on needs them; a missing application is not that, and the remedy
    # rides in the message where an agent reads it out either way.
    #
    # `google.com/chrome` with no scheme in front of it, on purpose. The leak
    # guard in the checks bans every scheme-and-slashes prefix in this repo's
    # source by shape rather than by a list of hosts, which is the only form
    # of that guard that can live in a public file. This message is not what
    # it is aimed at, and the guard is worth more than four characters: do not
    # "fix" this into a full URL. (This comment cannot spell one either.)
    171: (
        "chrome_not_found",
        1,
        "Google Chrome is not installed on this machine, or iitb could not "
        "find it. This CLI drives its own Chrome, so it needs one: install "
        "Google Chrome from google.com/chrome and run the command again. "
        "If Chrome is already installed somewhere unusual, "
        "set IITB_CHROME_BIN to the full path of its binary instead. "
        "`detail` says where iitb looked.",
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
    # `iitb downloads fetch` finally uses the rest of the block the setting was
    # given. It is not a portal command, so its failures are not in a portal's
    # block: it takes a url from wherever the operator found it, and numbering
    # it under one surface would be wrong the first time it covers a second.
    192: (
        "download_source_unreachable",
        1,
        "Could not reach the service that url points at. Check the network and "
        "try again.",
    ),
    # A fact about the link rather than about iitb, which is why it is not 121:
    # 121 is worth another attempt and this is not.
    193: (
        "download_not_found",
        1,
        "There is no file behind that link. Links to shared files expire and "
        "are withdrawn, so ask the operator for a current one. Retrying will "
        "not help, and neither will signing in again.",
    ),
    194: (
        "download_session_recovery_failed",
        1,
        "Could not establish a session with the service that url points at. "
        "This is not something the operator needs to do by hand; report it as "
        "described by `iitb downloads --help`.",
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
    # 497 and 498 split "the install is wrong" by remedy: 498 means there is
    # no core to speak to, 497 means there is one and the two halves do not
    # fit together. Only 497 can say which side to update, so folding them
    # into one code would cost exactly the sentence the consumer needs.
    497: (
        "core_incompatible",
        4,
        "The installed iitb and iitb-core do not fit together. This is an "
        "install problem: running the command again will not fix it, and "
        "`detail` says which of the two to update.",
    ),
    498: (
        "core_missing",
        4,
        "iitb-core is not installed, or could not be imported. This is an "
        "install problem: running the command again will not fix it.",
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
