# MIT License
# Copyright (c) 2026 Netherlands Film Academy

"""
Default playblast resolution for Maya.

The first source that gives an answer wins:
1. the backplate in the scene (image plane, preferably on a shot camera);
2. the plate on disk: 02_source/sc<seq>/<shot>/p###/plates/<ext>/ (newest p,
   EXR first) - the same place Shot Setup reads;
3. otherwise always 1920 x 1080 (the scene's render resolution is not used).

Image sizes come from the EXR header (displayWindow) or from Qt for other
formats, so nothing heavy is loaded. Everything here is defensive: a failing
source is skipped, never raised.
"""

import glob
import os
import re
import struct

DEFAULT = (1920, 1080)
MAYA_DEFAULTS = {(960, 540), (640, 480), (320, 240)}
IMAGE_EXT = (".exr", ".dpx", ".tif", ".tiff", ".png", ".jpg", ".jpeg")
STARTUP_CAMERAS = ("persp", "top", "front", "side", "bottom", "back", "left")


class Result(object):
    def __init__(self, width, height, source):
        self.width = int(width)
        self.height = int(height)
        self.source = source  # short text for the dialog, e.g. "plate_0040_0160 (image plane)"

    def __iter__(self):
        return iter((self.width, self.height))

    def __repr__(self):
        return "Result(%d x %d, %s)" % (self.width, self.height, self.source)


# --------------------------------------------------------------------------- image sizes
def _read_cstr(fh, limit=256):
    out = b""
    while len(out) < limit:
        c = fh.read(1)
        if not c or c == b"\0":
            break
        out += c
    return out.decode("ascii", "replace")


def exr_size(path):
    """(width, height) from an OpenEXR header (displayWindow, else dataWindow)."""
    with open(path, "rb") as fh:
        if struct.unpack("<i", fh.read(4))[0] != 20000630:
            return None
        fh.read(4)
        display = data = None
        for _ in range(500):
            name = _read_cstr(fh)
            if not name:
                break
            atype = _read_cstr(fh)
            size = struct.unpack("<i", fh.read(4))[0]
            raw = fh.read(size)
            if atype == "box2i" and name in ("displayWindow", "dataWindow"):
                x0, y0, x1, y1 = struct.unpack("<iiii", raw)
                if name == "displayWindow":
                    display = (x1 - x0 + 1, y1 - y0 + 1)
                else:
                    data = (x1 - x0 + 1, y1 - y0 + 1)
        return display or data


def image_size(path):
    """(width, height) of an image file, or None."""
    if not path or not os.path.isfile(path):
        return None
    if path.lower().endswith(".exr"):
        try:
            return exr_size(path)
        except Exception:
            return None
    try:
        try:
            from PySide6 import QtGui
        except ImportError:
            from PySide2 import QtGui
        s = QtGui.QImageReader(path).size()
        if s.isValid() and s.width() > 0:
            return s.width(), s.height()
    except Exception:
        pass
    return None


def _sane(wh):
    return bool(wh) and 16 <= wh[0] <= 16384 and 16 <= wh[1] <= 16384


_FRAME_RE = re.compile(r"^(?P<head>.*?)(?P<num>\d+|#+|%0\dd|<f>|<UDIM>)(?P<ext>\.[A-Za-z0-9]+)$")


def first_existing_frame(path):
    """The file itself, or another frame of the same sequence when this one doesn't exist."""
    if not path:
        return None
    path = os.path.expandvars(path)
    if os.path.isfile(path):
        return path
    folder, name = os.path.split(path)
    m = _FRAME_RE.match(name)
    if not m or not os.path.isdir(folder):
        return None
    pattern = os.path.join(folder, glob.escape(m.group("head")) + "*" + m.group("ext"))
    frames = sorted(glob.glob(pattern))
    return frames[0] if frames else None


# --------------------------------------------------------------------------- 1. backplate in the scene
def from_image_planes(cmds):
    """Size of the backplate: image planes on shot cameras first, then any image plane."""
    planes = cmds.ls(type="imagePlane") or []
    if not planes:
        return None

    def camera_of(ip):
        for attr in (".message",):
            for dest in cmds.listConnections(ip + attr, destination=True, source=False, type="camera") or []:
                return dest.split("|")[-1]
        parents = cmds.listRelatives(ip, parent=True, fullPath=True) or []
        for p in parents:
            if cmds.nodeType(p) in ("camera", "transform"):
                return p.split("|")[-1]
        return ""

    def rank(ip):
        cam = camera_of(ip).lower()
        on_shot_cam = bool(cam) and not any(cam.startswith(s) for s in STARTUP_CAMERAS)
        try:
            visible = cmds.getAttr(ip + ".displayMode") != 0
        except Exception:
            visible = True
        return (0 if on_shot_cam else 1, 0 if visible else 1)

    for ip in sorted(planes, key=rank):
        label = ip.split("|")[-1]
        try:
            itype = cmds.getAttr(ip + ".type")  # 0 = image file, 1 = texture, 2 = movie
        except Exception:
            itype = 0
        if itype == 0:
            try:
                name = cmds.getAttr(ip + ".imageName")
            except Exception:
                name = ""
            wh = image_size(first_existing_frame(name))
            if _sane(wh):
                return Result(wh[0], wh[1], "backplate %s" % _short(label))
        # Maya fills coverage with the image size when it loads the plate (also for movies)
        try:
            wh = (int(cmds.getAttr(ip + ".coverageX")), int(cmds.getAttr(ip + ".coverageY")))
            if _sane(wh) and wh not in MAYA_DEFAULTS:
                return Result(wh[0], wh[1], "backplate %s" % _short(label))
        except Exception:
            pass
    return None


def _short(name, n=40):
    name = name.split(":")[-1]
    return name if len(name) <= n else name[: n - 1] + "…"


# --------------------------------------------------------------------------- 2. plate on disk
def _natural_key(text):
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", text or "")]


def _sequence_folders(seq):
    names = {seq}
    if re.match(r"^sc(?=[A-Z0-9])", seq or ""):
        names.add(seq[2:])
    elif seq:
        names.add("sc" + seq)
    return [n for n in names if n]


def plate_folders(root, seq, shot):
    """Plate folders of a shot, newest p-version first, EXR before other formats."""
    found = []
    for s in _sequence_folders(seq):
        for pdir in glob.glob(os.path.join(root, "02_source", s, shot, "p*")):
            if not os.path.isdir(pdir):
                continue
            for ext_dir in glob.glob(os.path.join(pdir, "plates", "*")):
                if not os.path.isdir(ext_dir) or os.path.basename(ext_dir).lower() in ("ref", "mov"):
                    continue
                found.append((pdir, ext_dir))
    found.sort(key=lambda t: (_natural_key(os.path.basename(t[0])), os.path.basename(t[1]).lower() == "exr"),
               reverse=True)
    return [ext_dir for _, ext_dir in found]


def from_plate_on_disk(root, seq, shot):
    if not (root and shot):
        return None
    for folder in plate_folders(root, seq, shot):
        try:
            names = sorted(n for n in os.listdir(folder) if n.lower().endswith(IMAGE_EXT))
        except OSError:
            continue
        for name in names[:3]:
            wh = image_size(os.path.join(folder, name))
            if _sane(wh):
                pversion = os.path.basename(os.path.dirname(os.path.dirname(folder)))
                return Result(wh[0], wh[1], "plate %s (%s)" % (pversion, os.path.basename(folder)))
    return None


# --------------------------------------------------------------------------- all together
def find(cmds=None, root=None, seq=None, shot=None, logger=None):
    """The default playblast resolution as a Result (never None)."""
    steps = []
    if cmds is not None:
        steps.append(lambda: from_image_planes(cmds))
    steps.append(lambda: from_plate_on_disk(root, seq, shot))
    for step in steps:
        try:
            result = step()
        except Exception as error:
            if logger:
                logger.debug("Resolution lookup step failed: %s" % error)
            result = None
        if result:
            return result
    return Result(DEFAULT[0], DEFAULT[1], "default")
