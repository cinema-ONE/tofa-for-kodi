"""Centralized logging -- every xbmc.log() call in this add-on routes
through here, so a secret can never reach kodi.log just because a call site
forgot to scrub it.

This is a chokepoint, not a per-call-site convention: a new log line added
anywhere later gets redaction for free. Doesn't touch Kodi's own core C++
logging (CCurlFile::Open etc. still print the resolved stream_url verbatim
when debug logging is on) -- nothing at the Python level can reach that,
this only closes the half we do control.
"""
from __future__ import annotations

import re

import xbmc

PREFIX = "[plugin.video.tofa]"

# `st`/`token` as URL query params (covers stream/image URLs). Scoped to
# right after `?`/`&`: these names are short/generic enough that matching
# them anywhere risks mangling unrelated text.
_QUERY_SECRET_RE = re.compile(r"(?<=[?&])(st|token)=[^&\s]+", re.IGNORECASE)
# `access_token`/`refresh_token` wherever they appear -- unambiguous enough
# to redact anywhere, not just in a URL: covers query-string shape
# (`access_token=xyz`) and Python repr/dict shape (`refresh_token='xyz'`,
# `"refresh_token": "xyz"`) in case a whole Tokens object gets logged.
_NAMED_TOKEN_RE = re.compile(r"""(access_token|refresh_token)['"]?\s*[:=]\s*['"]?[^'",&\s)]+""", re.IGNORECASE)
# Bare JWTs (header.payload.signature, base64url, header always starts
# `eyJ` -- base64 of `{"`) -- catches an access token even without a
# recognisable key name nearby.
_JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")


def _redact(message: str) -> str:
    message = _QUERY_SECRET_RE.sub(lambda m: f"{m.group(1)}=***", message)
    message = _NAMED_TOKEN_RE.sub(lambda m: f"{m.group(1)}=***", message)
    message = _JWT_RE.sub("***", message)
    return message


def debug(message: str) -> None:
    xbmc.log(f"{PREFIX} {_redact(message)}", xbmc.LOGDEBUG)


def info(message: str) -> None:
    """For the few events worth seeing WITHOUT debug logging switched on --
    a display mode change being the case that added this. Kept rare on
    purpose; `debug` is the default for tracing.

    It exists at all because its absence was a silent trap: calling a level
    this module did not define raised AttributeError at the call site, and in
    the one place it happened the exception was swallowed by a broad handler,
    so refresh-rate switching failed quietly for a day.
    """
    xbmc.log(f"{PREFIX} {_redact(message)}", xbmc.LOGINFO)


def warning(message: str) -> None:
    xbmc.log(f"{PREFIX} {_redact(message)}", xbmc.LOGWARNING)


def error(message: str) -> None:
    xbmc.log(f"{PREFIX} {_redact(message)}", xbmc.LOGERROR)
