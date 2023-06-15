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
import pathlib
import subprocess

import sgtk


class CreateSlate(object):
    def __init__(self, app):
        # initialize and set paths
        self.app = app
        if sgtk.util.is_linux():
            self.nuke_path = "{}".format(app.get_setting("nuke_path_linux"))
        elif sgtk.util.is_macos():
            self.nuke_path = "{}".format(app.get_setting("nuke_path_mac"))
        elif sgtk.util.is_windows():
            self.nuke_path = "{}".format(app.get_setting("nuke_path_windows"))

        # set slate script path
        __location__ = os.path.realpath(
            os.path.join(os.getcwd(), os.path.dirname(__file__))
        )
        self.slatePath = os.path.join(__location__, "slate.py")

    def run_slate(self, inputFile, outputFile, projectFile, settings):
        # setup environment
        custom_env = os.environ.copy()

        if custom_env.get("PYTHONPATH") is not None:
            del custom_env["PYTHONPATH"]

        if custom_env.get("PYTHONHOME") is not None:
            del custom_env["PYTHONHOME"]

        # setup arguments for call
        context = self.app.context
        company_name = self.app.get_setting("company_name")
        project_name = context.project["name"]
        user_name = context.user["name"]
        file_name = projectFile
        first_frame = settings["frame_range"][0]
        last_frame = settings["frame_range"][1]
        task_name = context.step["name"]
        description = settings["description"]
        fps = settings["fps"]
        app_path = self.app.disk_location

        logo_path = self.app.get_setting("slate_logo")
        if sgtk.util.is_windows():
            logo_path = logo_path.replace(os.sep, "/")

        # ensure output path exists
        self.app.ensure_folder_exists(os.path.dirname(os.path.abspath(outputFile)))

        version = settings["version"]

        resolution = "%d x %d" % (
            settings["resolution"][0],
            settings["resolution"][1],
        )

        # call subprocess of nuke and convert
        process = subprocess.Popen(
            [
                self.nuke_path,
                "-t",
                self.slatePath,
                inputFile,
                outputFile,
                company_name,
                project_name,
                file_name,
                str(first_frame),
                str(last_frame),
                app_path,
                str(version),
                resolution,
                user_name,
                task_name,
                description,
                str(fps),
                logo_path,
            ],
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=custom_env,
        )

        stdout, stderr = process.communicate()
        self.app.logger.debug(stdout.decode("utf-8"))

        if "A license for nuke was not found" in stdout.decode("utf-8"):
            raise Exception(stdout.decode("utf-8"))

        if stderr:
            self.app.logger.error(stderr)
            raise Exception(stderr)
