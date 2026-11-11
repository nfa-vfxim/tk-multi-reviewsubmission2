# MIT License

# Copyright (c) 2020 Netherlands Film Academy

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import datetime
import json
import os
import struct
import sys
import time

import nuke

input_path = sys.argv[1]
output_path = sys.argv[2]
company_name = sys.argv[3]
project_name = sys.argv[4]
file_name = sys.argv[5]
first_frame = int(float(sys.argv[6]))
last_frame = int(float(sys.argv[7]))
app_path = sys.argv[8]
version = int(sys.argv[9])
resolution = sys.argv[10]
user_name = sys.argv[11]
task_name = sys.argv[12]
description = sys.argv[13]
fps = float(sys.argv[14])
logo_path = sys.argv[15]
sound_path = sys.argv[16]
sound_offset = int(float(sys.argv[17])) if sys.argv[17] != "None" else None
output_node = None

version_padding = 3
_burnin_nk = os.path.join(app_path, "resources", "slate.nk")


def __get_srgb_colorspace():
    """Get the correct sRGB namespace"""
    # setting output colorspace
    colorspace = nuke.root().knob("colorManagement").getValue()

    # If OCIO is set, Output - sRGB
    if colorspace:
        return "Output - sRGB"

    # If no OCIO is set, use sRGB
    else:
        return "sRGB"

# create group
group = nuke.nodes.Group()

# general metadata
today = datetime.date.today()
date_formatted = time.strftime("%d/%m/%Y %H:%M")
colorspace = __get_srgb_colorspace()

# operate in group
group.begin()


def __create_output_node(path):
    # get the Write node settings we'll use for generating the Quicktime
    wn_settings = __get_quicktime_settings()

    node = nuke.nodes.Write(file_type=wn_settings.get("file_type"))

    # apply any additional knob settings provided by the hook. Now that the knob has been
    # created, we can be sure specific file_type settings will be valid.
    for knob_name in wn_settings.keys():
        knob_value = wn_settings.get(knob_name)
        if knob_name != "file_type":
            if node.knob(knob_name) is None:
                continue  # knob not in this Nuke version (e.g. mov64_write_timecode)
            node.knob(knob_name).setValue(knob_value)

    root_node = nuke.root()
    is_proxy = root_node["proxy"].value()
    if is_proxy:
        node["proxy"].setValue(path.replace(os.sep, "/"))
    else:
        node["file"].setValue(path.replace(os.sep, "/"))

    return node


def __get_quicktime_settings():
    settings = {}
    settings["file_type"] = "mov"
    if nuke.NUKE_VERSION_MAJOR >= 9:
        # Nuke 9.0v1 changed the codec knob name to meta_codec and added an encoder knob
        # (which defaults to the new mov64 encoder/decoder).
        settings["mov64_codec"] = 14
        settings["mov64_quality_max"] = "3"
        settings["mov64_fps"] = fps
        if os.path.isfile(sound_path):
            settings["mov64_audiofile"] = sound_path
            settings["mov64_audio_offset"] = sound_offset - (first_frame - 1)
        settings["mov64_units"] = "Frames"
        # NFA: start timecode = frame number, so other tools know where the movie starts
        settings["mov64_write_timecode"] = True

        # setting output colorspace
        settings["colorspace"] = colorspace

    else:
        settings["codec"] = "jpeg"

    return settings


try:
    # create read node
    read = nuke.nodes.Read(
        name="source", file_type="jpg", file=input_path.replace(os.sep, "/")
    )
    read["on_error"].setValue("checkerboard")
    read["first"].setValue(first_frame)
    read["last"].setValue(last_frame)
    if colorspace:
        read["colorspace"].setValue(colorspace)

    # now create the slate/burnin node
    burn = nuke.nodePaste(_burnin_nk)
    burn.setInput(0, read)

    # format the burnins
    version_padding_format = "%%0%dd" % version_padding
    version_str = version_padding_format % version

    if task_name:
        version_label = "%s, v%s" % (task_name, version_str)
    else:
        version_label = "v%s" % version_str

    burn.knob("project").setValue(project_name)
    burn.knob("company").setValue(company_name)
    burn.knob("file").setValue(file_name)
    burn.knob("date").setValue(date_formatted)

    burn.knob("first_frame").setValue(first_frame)
    burn.knob("last_frame").setValue(last_frame)
    burn.knob("artist").setValue(user_name)
    burn.knob("task").setValue(task_name)
    burn.knob("description").setValue(description)
    burn.knob("version").setValue(str(version))
    burn.knob("fps").setValue(fps)
    burn.knob("colorspaceIDT").setValue("Output - sRGB")
    burn.knob("colorspaceODT").setValue("Output - sRGB")
    burn.knob("logo_path").setValue(logo_path)

    # NFA: timecode that counts frames (slate = first_frame - 1), written into the movie
    last_node = burn
    try:
        base = int(round(fps))
        start = first_frame - 1
        timecode = nuke.nodes.AddTimeCode(inputs=[burn])
        timecode["startcode"].setValue(
            "%02d:%02d:%02d:%02d"
            % (start // (3600 * base), (start // (60 * base)) % 60, (start // base) % 60, start % base)
        )
        timecode["metafps"].setValue(False)
        timecode["fps"].setValue(base)
        timecode["useFrame"].setValue(True)
        timecode["frame"].setValue(start)
        last_node = timecode
    except Exception as error:
        print("NFA metadata: no timecode (%s)" % error)

    # Create the output node
    output_node = __create_output_node(output_path)
    output_node.setInput(0, last_node)

finally:
    group.end()

if output_node:
    # Render the outputs, first view only
    nuke.executeMultiple(
        [output_node], ([first_frame - 1, last_frame, 1],), [nuke.views()[0]]
    )



def __write_nfa_metadata(path):
    """NFA: frame range and playblast settings inside the movie file, for tools that have to
    line the movie up with its plate (NFA VFX Edit in Resolve). Nuke cannot write custom
    QuickTime keys, so this is a 'free' atom at the end of the file: every player skips it,
    readers look for the NFAMETA1 marker. Never lets the review submission fail."""
    try:
        width, height = [int(x) for x in resolution.lower().split("x")]
    except Exception:
        width = height = 0
    data = {
        "first_frame": first_frame,
        "last_frame": last_frame,
        "slate_frames": 1,
        "fps": fps,
        "width": width,
        "height": height,
        "version": version,
        "project": project_name,
        "task": task_name,
        "artist": user_name,
        "source": file_name,
        "camera": os.environ.get("NFA_REVIEW_CAMERA", ""),
        "created": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    for key in ("overscan", "film_fit", "focal_length"):
        value = os.environ.get("NFA_REVIEW_%s" % key.upper())
        if value not in (None, ""):
            try:
                data[key] = float(value)
            except ValueError:
                data[key] = value
    payload = b"NFAMETA1" + json.dumps(data, sort_keys=True).encode("utf-8")
    with open(path, "ab") as handle:
        handle.write(struct.pack(">I4s", 8 + len(payload), b"free") + payload)


if output_node and os.path.isfile(output_path):
    try:
        __write_nfa_metadata(output_path)
    except Exception as error:
        print("NFA metadata not written: %s" % error)

# Cleanup after ourselves
nuke.delete(group)
