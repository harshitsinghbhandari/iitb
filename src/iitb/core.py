"""The one seam between this public shell and the private implementation core.

Everything portal-specific lives in `iitb_core`. This module does three
things and nothing else:

1. imports a core module, turning a missing or unimportable one into 498;
2. calls a core function with the arguments the shell parsed;
3. turns whatever the core raised into a registry code.

Step 3 never inspects a core exception's contents and never imports a core
exception class. It reads the exception's *name*, mapped to a registry slug
(`PortalUnreachable` -> `portal_unreachable` -> 110), or an explicit `code`
attribute if the core sets one. Anything unrecognised becomes 499 with the
core's own string as `detail`.

That indirection is the point. The shell stays blind to what the core does,
the two repos share a vocabulary rather than an import graph, and a new
typed exception in the core is wired up by naming it after its code.

The pinned core seams, one function per command::

    iitb_core.browser.start()
    iitb_core.browser.attach()
    iitb_core.browser.status()
    iitb_core.browser.sso_status()
    iitb_core.browser.stop()

    iitb_core.placements.jobs(status=..., eligible=..., company=...)
    iitb_core.placements.job(job_id=..., company=..., job_code=..., text=...)
    iitb_core.placements.deadlines(within=..., eligible=..., include_applied=...)
    iitb_core.placements.applications()
    iitb_core.placements.blog(post_id=..., blog=..., page=..., since=...,
                             max_pages=..., text=...)

Each returns the `data` payload for its command. The shell wraps it in the
envelope and prints it; it does not reshape it.
"""

from __future__ import annotations

import importlib
import re

from .errors import BY_NAME, REGISTRY, CliError

# CamelCase -> snake_case, splitting before an uppercase that starts a word
# and after a lowercase or digit. Keeps acronyms whole: SSOCheckFailed
# becomes sso_check_failed rather than s_s_o_check_failed.
_WORD_BOUNDARY = re.compile(r"(?<!^)(?=[A-Z][a-z])|(?<=[a-z0-9])(?=[A-Z])")


def _slug(class_name: str) -> str:
    return _WORD_BOUNDARY.sub("_", class_name).lower()


def code_for(exc: Exception) -> int:
    """The registry code for a core exception, or 499 if it cannot be read."""
    code = getattr(exc, "code", None)
    if isinstance(code, int) and code in REGISTRY:
        return code
    return BY_NAME.get(_slug(type(exc).__name__), 499)


def load(module: str):
    """Import a core module. A core that is absent or broken is 498, exit 4.

    An ImportError raised *inside* the core (a missing runtime dependency,
    say) lands here too, and 498 is the right answer for it: both are an
    install that needs fixing rather than an operation that can be retried.
    """
    try:
        return importlib.import_module(module)
    except ImportError as exc:
        raise CliError(498, detail=str(exc)) from exc


def call(module: str, function: str, **kwargs):
    """Call a pinned core seam and return its `data` payload."""
    mod = load(module)
    fn = getattr(mod, function, None)
    if not callable(fn):
        raise CliError(
            498, detail=f"{module}.{function} is missing from the installed core"
        )
    try:
        return fn(**kwargs)
    except CliError:
        raise
    except TypeError as exc:
        # "jobs() got an unexpected keyword argument ..." is an incompatible
        # core, not a bad command line: the shell validated the arguments
        # before it got here. A TypeError from anywhere else inside the core
        # is just a core failure, so match the signature shape narrowly.
        if str(exc).startswith(f"{function}("):
            raise CliError(498, detail=str(exc)) from exc
        raise CliError(code_for(exc), detail=str(exc)) from exc
    except Exception as exc:
        raise CliError(code_for(exc), detail=str(exc) or type(exc).__name__) from exc
