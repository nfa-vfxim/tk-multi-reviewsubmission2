# Copyright (c) 2019 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.


import os
import re
import tempfile

import hou
import sgtk
from hou import SceneViewer

HookBaseClass = sgtk.get_hook_baseclass()


class RenderMedia(HookBaseClass):
    """
    Base class of the RenderMedia hook. It implements the hook interface and helper methods.
    """

    def render(
        self,
        render_file_path,
        review_file_path,
        frame_range,
        fps,
        resolution,
        description,
        version,
        engine_settings,
    ):
        """
        Render the media

        :param str render_file_path:    Path to render the frames of the movie to
        :param str review_file_path:    Path to the output movie that will be rendered
        :param int[] frame_range:       Frame range of the output movie
        :param int fps:                 FPS of the output movie
        :param int[] resolution:        Resolution of the output movie
        :param str description:         Description to use in the slate for the output movie
        :param int version:             Version number to use for the output movie slate and burn-in
        :param dict engine_settings:    Engine specific settings to use for rendering

        :returns:               Location of the rendered media
        :rtype:                 str
        """
        scene = hou.ui.paneTabOfType(hou.paneTabType.SceneViewer)

        settings = scene.flipbookSettings().stash()

        # standard settings
        settings.outputToMPlay(engine_settings["mplay"])
        settings.output(render_file_path)
        settings.useResolution(True)
        settings.resolution(resolution)
        settings.cropOutMaskOverlay(True)
        settings.frameRange(frame_range)
        settings.beautyPassOnly(engine_settings["beauty_pass"])
        settings.antialias(hou.flipbookAntialias.HighQuality)
        settings.sessionLabel(review_file_path)
        settings.useMotionBlur(engine_settings["motion_blur"])

        SceneViewer.flipbook(scene, settings=settings)

