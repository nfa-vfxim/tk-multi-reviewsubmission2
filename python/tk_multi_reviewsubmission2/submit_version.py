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

import os

import sgtk
from PySide2 import QtCore


class SubmitVersion(object):
    def __init__(self, app, file_path, frame_range, description):
        self.app = app
        self.file = file_path
        self.frame_range = frame_range
        self.description = description

    def submit_version(self):
        """Submit file to ShotGrid"""
        # Bind user
        user = sgtk.util.get_current_user(self.app.sgtk)

        # Calculate name for version
        # Get file path and strip it of path and extension
        name = os.path.splitext(os.path.basename(self.file))[0]

        # Get the current context
        ctx = self.app.context

        # Update data object for submission
        data = {"code": name, "sg_status_list": "rev", "entity": ctx.entity, "sg_task": ctx.task,
                "sg_first_frame": self.frame_range[0], "sg_last_frame": self.frame_range[1],
                "sg_frames_have_slate": False, "created_by": user, "user": user, "description": self.description,
                "sg_movie_has_slate": True, "project": ctx.project,
                "frame_count": self.frame_range[1] - self.frame_range[0] + 1,
                "frame_range": "%s-%s" % (self.frame_range[0], self.frame_range[1]), "sg_path_to_movie": self.file}

        # Calculate frame count and range and update accordingly

        # Link movie file

        # Create the version in ShotGrid
        try:
            version = self.app.sgtk.shotgun.create("Version", data)

            self.app.logger.debug("Created version in ShotGrid: %s" % str(data))

            # upload the movie files to ShotGrid
            self.__upload_version(version)
            self.app.logger.debug("Uploaded version in ShotGrid")
        except Exception as err:
            self.app.logger.debug(
                "An error occurred while creating a new version: {}".format(err)
            )

    def __upload_version(self, version):
        """Upload files to ShotGrid"""
        # Create a new event loop to upload files
        event_loop = QtCore.QEventLoop()

        # Open new thread and wait for thread to finish
        thread = UploaderThread(self.app, version, self.file)
        thread.finished.connect(event_loop.quit)
        thread.start()
        event_loop.exec_()

        if thread.get_errors():
            for e in thread.get_errors():
                self.app.logger.error(e)


class UploaderThread(QtCore.QThread):
    def __init__(self, app, version, filePath):
        QtCore.QThread.__init__(self)

        self.app = app
        self.version = version
        self.file = filePath
        self._errors = []

    def get_errors(self):
        """Function to retrieve errors"""
        return self._errors

    def run(self):
        """Run the upload thread"""
        try:
            self.app.sgtk.shotgun.upload(
                "Version", self.version["id"], self.file, "sg_uploaded_movie"
            )
        except Exception as e:
            self._errors.append("Movie upload to ShotGrid failed: %s" % e)
