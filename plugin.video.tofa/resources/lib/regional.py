"""Number formatting that follows Kodi's own regional settings.

Kodi HAS a per-region thousands separator and grouping rule, read from the
active language add-on's `langinfo.xml`:

    <region name="USA (12h)" locale="US">
      <thousandsseparator groupingformat="\\3">,</thousandsseparator>
      <decimalseparator>.</decimalseparator>
    </region>

and it does NOT expose them to add-ons. `xbmc.getRegion()` answers only
datelong, dateshort, datelongraw, dateshortraw, time, timeraw, meridiem,
tempunit and speedunit; the separator exists solely as a C++ locale facet
that `LangInfo.cpp` builds for its own use. Python's `locale` module is no
help either -- Kodi deliberately keeps the process locale's numeric facet as
"C" (its own comment says changing it "breaks atof() and others"), so
`locale.format_string` would silently give US grouping on a German box.

So the setting is read the only way it can be: find the language add-on, read
its langinfo.xml, and look up the region the user actually picked. Both halves
come from Kodi itself (`locale.language` and `locale.country`), which is what
makes this obey the regional setting rather than guess at it.

`groupingformat` is a Kodi-style escaped binary string: "\\3" means groups of
three, and a locale that groups differently after the first group (Indian
digit grouping, 1,00,000) spells it "\\3\\2". That is honoured rather than
assumed, because assuming groups of three is exactly the bug this is meant to
avoid on the locales where it matters.

Everything is cached after the first lookup: the answer cannot change without
a Kodi settings change, and this is called once per rendered row.
"""
from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET

import xbmc
import xbmcaddon
import xbmcvfs

from . import log

#: What Kodi itself falls back to when a region declares no separator
#: (LangInfo.cpp: `region.m_cThousandsSep = ','; region.m_strGrouping = "\3";`).
DEFAULT_SEPARATOR = ","
DEFAULT_GROUPING = (3,)
DEFAULT_DECIMAL = "."

#: (thousands separator, grouping, decimal separator). All three come from the
#: same <region> element, so they are looked up and cached as one.
_cached: tuple[str, tuple[int, ...], str] | None = None


def _setting(name: str) -> str:
    """One Kodi setting, via JSON-RPC. There is no Python API for reading
    Kodi's own settings -- xbmcaddon.Addon() reads OUR settings, not Kodi's."""
    try:
        raw = xbmc.executeJSONRPC(json.dumps({
            "jsonrpc": "2.0", "id": 1,
            "method": "Settings.GetSettingValue",
            "params": {"setting": name},
        }))
        return str(json.loads(raw).get("result", {}).get("value") or "")
    except Exception as exc:
        log.debug(f"regional: could not read {name}: {exc}")
        return ""


def _parse_grouping(spec: str | None) -> tuple[int, ...]:
    """Kodi's `groupingformat` into group sizes.

    The attribute holds escaped bytes, "\\3" or "\\3\\2". A value that parses
    to nothing at all falls back rather than producing zero-width groups,
    which would loop forever downstream."""
    if not spec:
        return DEFAULT_GROUPING
    sizes = tuple(int(n) for n in re.findall(r"\\(\d+)", spec) if int(n) > 0)
    return sizes or DEFAULT_GROUPING


def _lookup() -> tuple[str, tuple[int, ...], str]:
    fallback = (DEFAULT_SEPARATOR, DEFAULT_GROUPING, DEFAULT_DECIMAL)
    language = _setting("locale.language")
    region = _setting("locale.country")
    if not language or not region:
        return fallback
    try:
        # Resolved through the add-on rather than by building a path: a
        # language add-on may live in the Kodi install OR in userdata, and
        # getAddonInfo("path") is right either way.
        base = xbmcvfs.translatePath(xbmcaddon.Addon(language).getAddonInfo("path"))
    except Exception as exc:
        log.debug(f"regional: language add-on {language} not readable: {exc}")
        return fallback

    path = base.rstrip("/") + "/resources/langinfo.xml"
    if not xbmcvfs.exists(path):
        log.debug(f"regional: no langinfo.xml at {path}")
        return fallback
    try:
        handle = xbmcvfs.File(path)
        try:
            text = handle.read()
        finally:
            handle.close()
        root = ET.fromstring(text)
    except Exception as exc:
        log.debug(f"regional: could not parse {path}: {exc}")
        return fallback

    for element in root.iter("region"):
        if element.get("name") != region:
            continue
        point = element.find("decimalseparator")
        decimal_mark = (point.text or DEFAULT_DECIMAL)[0] if point is not None else DEFAULT_DECIMAL
        node = element.find("thousandsseparator")
        if node is None or not (node.text or ""):
            # A region that declares none gets Kodi's own default, not "no
            # grouping" -- matching LangInfo.cpp's else branch.
            return DEFAULT_SEPARATOR, DEFAULT_GROUPING, decimal_mark
        return node.text[0], _parse_grouping(node.get("groupingformat")), decimal_mark
    log.debug(f"regional: region {region!r} not in {path}")
    return fallback


def _region() -> tuple[str, tuple[int, ...], str]:
    global _cached
    if _cached is None:
        _cached = _lookup()
        log.debug("regional: thousands %r grouping %r decimal %r" % _cached)
    return _cached


def separator_and_grouping() -> tuple[str, tuple[int, ...]]:
    separator, grouping, _ = _region()
    return separator, grouping


def group_digits(value: int, separator: str, grouping: tuple[int, ...]) -> str:
    """`value` with `separator` inserted per `grouping`, which is pure and so
    testable without Kodi. The last group size repeats, as it does in C."""
    digits = str(abs(int(value)))
    out: list[str] = []
    index = 0
    while digits:
        size = grouping[min(index, len(grouping) - 1)]
        out.append(digits[-size:])
        digits = digits[:-size]
        index += 1
    return ("-" if value < 0 else "") + separator.join(reversed(out))


def number(value) -> str:
    """An integer formatted the way this Kodi's region would write it.

    Anything that is not a whole number is returned unchanged: this exists for
    counts, and quietly reformatting something unexpected would be worse than
    leaving it be."""
    if isinstance(value, bool) or not isinstance(value, int):
        return "" if value is None else str(value)
    separator, grouping = separator_and_grouping()
    return group_digits(value, separator, grouping)


# ------------------------------------------------------------- decimals --

def decimal_separator() -> str:
    """The region's decimal mark. Same langinfo lookup as the thousands one;
    they come from the same <region> element and are cached together."""
    return _region()[2]


def decimal(value, places: int = 1) -> str:
    """A number with `places` decimals, grouped and pointed the way this
    region writes it: 42.0 GB in the US, 42,0 GB in Germany.

    Rounded BEFORE grouping, so 999.96 at one place becomes 1,000.0 and not
    999.10 -- rounding after would carry into a group that had already been
    split."""
    try:
        number_value = float(value)
    except (TypeError, ValueError):
        return ""
    rounded = round(number_value, places)
    whole = int(abs(rounded))
    separator, grouping = separator_and_grouping()
    head = group_digits(whole, separator, grouping)
    sign = "-" if rounded < 0 else ""
    if places <= 0:
        return sign + head
    frac = abs(rounded) - whole
    tail = ("%.*f" % (places, frac))[2:]
    return sign + head + decimal_separator() + tail


# ---------------------------------------------------------------- dates --

#: Kodi's own localized names, so a German box says "Jan"/"Montag" without us
#: shipping a translation table. 21-32 long months, 51-62 short months,
#: 11-17 long weekdays, 41-47 short weekdays (verified in Kodi's strings.po).
def _month(index: int, short: bool) -> str:
    return xbmc.getLocalizedString((51 if short else 21) + index - 1)


def _weekday(index: int, short: bool) -> str:
    return xbmc.getLocalizedString((41 if short else 11) + index)


#: Longest token first: Python's alternation takes the first branch that
#: matches at a position, so "D" listed before "DDDD" would eat one letter of
#: a four-letter token and leave "DDD" as literal text.
_DATE_TOKEN = re.compile(r"DDDD|DDD|DD|D|MMMM|MMM|MM|M|YYYY|YY")


def _render_date(fmt: str, value) -> str:
    """Kodi's date tokens against a date. Kodi does NOT pre-convert these to
    strftime the way it does for time formats, so this is the renderer."""
    def one(match: "re.Match[str]") -> str:
        token = match.group(0)
        if token == "DDDD":
            return _weekday(value.weekday(), short=False)
        if token == "DDD":
            return _weekday(value.weekday(), short=True)
        if token == "DD":
            return "%02d" % value.day
        if token == "D":
            return str(value.day)
        if token == "MMMM":
            return _month(value.month, short=False)
        if token == "MMM":
            return _month(value.month, short=True)
        if token == "MM":
            return "%02d" % value.month
        if token == "M":
            return str(value.month)
        if token == "YYYY":
            return "%04d" % value.year
        return "%02d" % (value.year % 100)
    return _DATE_TOKEN.sub(one, fmt)


def _date_format(long: bool) -> str:
    fmt = xbmc.getRegion("datelongraw" if long else "dateshortraw")
    return fmt or ("DDDD, MMMM D, YYYY" if long else "DD/MM/YYYY")


def date(value, long: bool = False) -> str:
    """A full date, in this region's order and language."""
    parsed = _as_date(value)
    return _render_date(_date_format(long), parsed) if parsed else ""


def day_and_month(value) -> str:
    """"Jul 28", or "28. Jul" where the region puts the day first.

    Not a short date: the design wants a compact month+day with no year
    ("Airs Jul 28"), which is not one of Kodi's formats. Only the ORDER is
    taken from the region, by asking whether its short format puts D before
    M. That keeps the design's shape while not writing a German date
    backwards."""
    parsed = _as_date(value)
    if not parsed:
        return ""
    fmt = _date_format(long=False)
    day_first = fmt.find("D") < fmt.find("M") if "D" in fmt and "M" in fmt else False
    month = _month(parsed.month, short=True)
    return f"{parsed.day}. {month}" if day_first else f"{month} {parsed.day}"


def _as_date(value):
    import datetime
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    text = str(value or "")[:10]
    try:
        return datetime.datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


# ---------------------------------------------------------------- clock --

#: Kodi hands back a ready strftime string here (ModuleXbmc.cpp converts its
#: own tokens for "time" but NOT for the date ids), so this needs no renderer
#: -- only the seconds removed, since a clock shows hours and minutes.
_SECONDS = re.compile(r"[:.\s]?%S")


def clock(when=None) -> str:
    """The time of day as this Kodi writes it: 22:41, or 10:41 PM on a region
    set to 12-hour. Follows Kodi's regional setting, which is the one thing
    the user can actually change; the tofa API has no say (its `region` drives
    ratings and age restrictions, not clocks)."""
    import time as _time
    fmt = xbmc.getRegion("time") or "%H:%M"
    fmt = _SECONDS.sub("", fmt)
    try:
        return _time.strftime(fmt, when or _time.localtime())
    except Exception:
        return _time.strftime("%H:%M", when or _time.localtime())
