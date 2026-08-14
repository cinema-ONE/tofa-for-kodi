"""Minimal stand-ins for the Kodi modules the add-on imports.

Enough to import resources.lib.* outside Kodi and exercise pure logic.
Importing this module installs the stubs and puts the add-on on sys.path.
"""
import os, sys, tempfile, types, pathlib

PLUGIN = pathlib.Path(__file__).resolve().parent.parent / "plugin.video.tofa"

NOTIFICATIONS = []

#: Every window property ever SET, in order, as (key, value). A plain
#: getProperty() cannot see a transient one: our own toast clears itself
#: from a timer thread, and `sleep` here is a no-op, so the clear can win
#: the race against the assertion. The history records that it was raised
#: at all, which is what a test about "is the viewer told" actually means.
PROPERTY_WRITES = []


def _stub(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m


class _Player:
    def __init__(self, *a, **k): pass


class _Monitor:
    def __init__(self, *a, **k): pass
    def abortRequested(self): return False
    def waitForAbort(self, t=0): return True


class _Addon:
    def getAddonInfo(self, k):
        # "profile" has to be a special:// path, not a bare name. It used to
        # answer "tofa" for everything, so any code that builds a path under
        # the profile directory wrote into the CURRENT DIRECTORY -- which
        # created tests/tofa/avatar_presets.json and got it committed. The
        # vfs stub maps special:// into a temp root, so this keeps writes out
        # of the working tree entirely.
        if k == "profile":
            return "special://profile/addon_data/plugin.video.tofa"
        if k == "path":
            return str(PLUGIN)
        return "tofa"
    def getLocalizedString(self, i): return f"<string {i}>"
    def getSetting(self, k): return ""
    def getSettingBool(self, k): return False
    def getSettingInt(self, k): return 0
    def setSetting(self, k, v): pass


class _Dialog:
    def notification(self, heading, message, icon=None, *a, **k):
        NOTIFICATIONS.append((heading, message, icon))
    def ok(self, *a, **k): return True
    def yesno(self, *a, **k): return True


class _Window:
    _props = {}
    def __init__(self, *a, **k): pass
    def getProperty(self, k): return _Window._props.get(k, "")
    def setProperty(self, k, v):
        _Window._props[k] = v
        PROPERTY_WRITES.append((k, v))
    def clearProperty(self, k): _Window._props.pop(k, None)


class _ListItem:
    def __init__(self, *a, **k): pass
    def __getattr__(self, name): return lambda *a, **k: None


class _WindowBase:
    """Distinct from `object` on purpose: the add-on's window classes
    inherit (WindowXML, BaseFunctions), and object-as-a-base breaks the MRO."""
    def __init__(self, *a, **k): pass
    def getProperty(self, k): return ""
    def setProperty(self, k, v): pass
    def setFocusId(self, i): pass
    def getFocusId(self): return 0


class _WindowXML(_WindowBase): pass
class _WindowXMLDialog(_WindowBase): pass
class _Control:
    def __init__(self, *a, **k): pass
    def __getattr__(self, name): return lambda *a, **k: None


class _RequestException(Exception): pass
class _Timeout(_RequestException): pass


# --- a working xbmcvfs, rooted in a temp directory -----------------------
_VFS_ROOT = os.path.join(tempfile.gettempdir(), "tofa-test-vfs")


def _vfs_path(path):
    """special:// -> a real temp directory; anything else passes through."""
    if path.startswith("special://"):
        return os.path.join(_VFS_ROOT, path[len("special://"):])
    return path


def _vfs_mkdirs(path):
    os.makedirs(_vfs_path(path), exist_ok=True)
    return True


def _vfs_delete(path):
    try:
        os.remove(_vfs_path(path))
    except OSError:
        return False
    return True


class _VfsFile(object):
    """Kodi's File: read()/write()/close(), and write MAKES the directory.

    Kodi's own does that last part too, which is why add-on code gets away
    with opening a file in a profile directory it never created."""

    def __init__(self, path, mode="r"):
        self._path = _vfs_path(path)
        if "w" in mode:
            os.makedirs(os.path.dirname(self._path) or ".", exist_ok=True)
        self._handle = open(self._path, mode)

    def read(self):
        return self._handle.read()

    def write(self, data):
        return self._handle.write(data)

    def close(self):
        self._handle.close()


def install():
    _stub("xbmc", Player=_Player, Monitor=_Monitor, log=lambda *a, **k: None,
          LOGINFO=1, LOGWARNING=2, LOGERROR=3, LOGDEBUG=0, LOGFATAL=4,
          executebuiltin=lambda *a, **k: None, getInfoLabel=lambda *a: "",
          # Answers with a well-formed empty result. Suites that care what
          # Kodi replies replace this attribute; the default exists so an
          # unrelated import cannot blow up on a missing symbol.
          executeJSONRPC=lambda payload: '{"jsonrpc":"2.0","id":1,"result":{}}',
          getCondVisibility=lambda *a: False, getLocalizedString=lambda i: "",
          sleep=lambda ms: None, getRegion=lambda k: "", translatePath=lambda p: p,
          Keyboard=lambda *a, **k: None, PlayList=lambda *a, **k: None,
          getSkinDir=lambda: "skin.estuary", getLanguage=lambda *a, **k: "English")
    _stub("xbmcaddon", Addon=lambda *a, **k: _Addon())
    _stub("xbmcgui", Dialog=_Dialog, Window=_Window, ListItem=_ListItem,
          WindowXML=_WindowXML, WindowXMLDialog=_WindowXMLDialog,
          ControlButton=_Control, ControlLabel=_Control, ControlImage=_Control,
          ControlList=_Control, ControlGroup=_Control, ControlProgress=_Control,
          ControlTextBox=_Control, ControlEdit=_Control, ControlSlider=_Control,
          NOTIFICATION_WARNING="warn", NOTIFICATION_ERROR="error",
          NOTIFICATION_INFO="info",
          getCurrentWindowId=lambda: 13001, getCurrentWindowDialogId=lambda: 13002)
    # A REAL filesystem, rooted in a temp directory. The old stub answered
    # exists() with a flat False and handed out `object` for File, which
    # meant any code that writes something and reads it back could not be
    # tested at all -- and that is exactly the shape of a
    # survives-a-restart marker. Nothing escapes the temp root: paths that
    # are already absolute and real are passed through untouched, and
    # special:// is mapped in.
    _stub("xbmcvfs", translatePath=_vfs_path, exists=os.path.exists,
          mkdirs=_vfs_mkdirs, listdir=lambda p: ([], []), File=_VfsFile,
          delete=_vfs_delete, copy=lambda a, b: True)
    _stub("xbmcplugin", setResolvedUrl=lambda *a, **k: None,
          addDirectoryItem=lambda *a, **k: None, endOfDirectory=lambda *a, **k: None,
          setContent=lambda *a, **k: None)
    _stub("requests",
          Session=lambda: types.SimpleNamespace(headers={}, request=lambda *a, **k: None),
          RequestException=_RequestException,
          exceptions=types.SimpleNamespace(Timeout=_Timeout,
                                           RequestException=_RequestException),
          get=lambda *a, **k: None, post=lambda *a, **k: None)
    if str(PLUGIN) not in sys.path:
        sys.path.insert(0, str(PLUGIN))


install()
