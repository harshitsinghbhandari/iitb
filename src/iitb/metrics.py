"""A local count of how many times each command has been run.

One number per command path, in one file on the operator's own laptop.
`iitb moodle courses` adds one to `moodle.courses`, and that is the whole
feature. There is no session, no event, no schema and no framework here; a
dict of names to integers is the entire model and is meant to stay that way.

Three properties are the point of it, and each is a constraint rather than a
nicety:

**Local only. It is not telemetry and it must never become any.** Nothing in
this module opens a socket, resolves a name, or hands a byte to another
process, and nothing anywhere in this CLI reads this file except the command
that prints it. What this CLI tells the institute about itself is that it
reads the operator's own portals and sends nothing anywhere, and that claim
is load-bearing: spending it on an analytics number nobody makes a decision
on would be a bad trade at any price. If a later reader thinks these counts
could usefully be collected somewhere, the answer is no.

**It records what was run, never what was asked.** A count is keyed by the
command path argparse resolved, which is a name out of this repo's own
command tree. No argument, no flag value, no search text, no folder name, no
address, no filename, nothing the operator typed and nothing that came back.
The file is safe to hand to anyone, and that is the test to hold any edit
here to.

**It never changes what a command answers.** Counting is a side effect on the
way past, so every failure it can have is swallowed: a read-only config
directory, a full disk, a file somebody replaced with a directory, a home
directory that cannot be found. A command prints the same object on stdout
and exits the same code whether the counter was written, could not be
written, or was switched off.

`IITB_NO_METRICS` in the environment switches the counting off. The readout
still answers with it set, because reading a file is not counting.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from .config import config_dir
from .errors import CliError

FILENAME = "metrics.json"

# Any non-empty value switches counting off. Read at call time rather than at
# import time, so exporting it takes effect on the next command rather than on
# the next shell.
OPT_OUT = "IITB_NO_METRICS"


def path() -> Path:
    return config_dir() / FILENAME


def counting() -> bool:
    return not os.environ.get(OPT_OUT, "")


def read() -> dict[str, int]:
    """The counts on disk, or an empty dict for anything that is not counts.

    Tolerant on purpose, and this is the one place that has to be: nobody
    asked for a counter file, so a corrupt one must cost them nothing. A
    truncated write, a hand edit, a file left by a version that stored
    something else, all read as "no counts yet" rather than as a failure of
    whatever command happened to be running.

    Keys are stripped and then merged, so a file that already holds
    `"moodle.courses"` beside `"moodle.courses "` comes back as one command
    with the two counts added together. That is a repair rather than a
    tolerance: a file like that has one command's runs split across two rows,
    and adding them is the only reading that does not throw some of them away.
    It heals in memory here and reaches disk on the next run that records
    anything, because reading the counts must never write to them.

    Whitespace cannot get into a key from here on, so this is for files
    already on disk. It stays because the alternative is asking the operator
    to reset a counter they never asked for to fix damage they did not do.
    """
    try:
        stored = json.loads(path().read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - missing, unreadable, or not JSON
        return {}
    if not isinstance(stored, dict):
        return {}
    counts: dict[str, int] = {}
    for name, count in stored.items():
        if not isinstance(name, str) or not isinstance(count, int):
            continue
        name = name.strip()
        if not name:
            continue
        counts[name] = counts.get(name, 0) + count
    return counts


def record(command_path: str | None) -> None:
    """Add one to a command's count. Raises nothing, ever.

    Called on the way to the handler rather than after it, because the
    question is how often a command was run and a command that then failed
    was still run. `command_path` is what the parser resolved, so it is one of
    this repo's own command names and cannot carry anything the operator
    typed; passing anything else in would break the promise in the docstring
    above.

    The name is stripped before it is used. The parser cannot produce a name
    that needs it, which is exactly why the strip is here: this is the single
    line through which every key in the file passes, so normalising it once
    makes "a key never carries surrounding whitespace" a property of the
    module rather than a property of every caller being careful. A name that
    is nothing but whitespace is dropped rather than stored under "".
    """
    command_path = (command_path or "").strip()
    if not command_path or not counting():
        return
    # ponytail: read, add one, write. Two commands finishing in the same
    # instant can lose one count. A lock would cost every invocation something
    # to protect a number nobody makes a decision on; add one if these counts
    # ever have to be exact.
    try:
        counts = read()
        counts[command_path] = counts.get(command_path, 0) + 1
        directory = config_dir()
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / FILENAME
        target.write_text(
            json.dumps(counts, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        target.chmod(0o600)
    except Exception:  # noqa: BLE001 - a count is never worth a failed command
        pass


def clear() -> int:
    """Delete the counter file. Returns how many runs were forgotten.

    The one operation here that reports its failures, and the reason is the
    difference between a side effect and a request: nobody asked for the
    write in `record`, so its failure is nobody's problem, and somebody did
    ask for this, so a reset that silently did not happen would be a lie.
    """
    forgotten = sum(read().values())
    try:
        path().unlink(missing_ok=True)
    except OSError as exc:
        raise CliError(192, detail=f"{path()}: {exc}") from exc
    return forgotten


def summary() -> dict:
    """The readout payload: the counts, the total, the file, and the switch."""
    counts = read()
    return {
        "commands": counts,
        "total": sum(counts.values()),
        "file": str(path()),
        "counting": counting(),
    }
