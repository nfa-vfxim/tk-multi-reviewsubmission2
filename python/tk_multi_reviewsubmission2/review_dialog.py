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
import tempfile
import time

from PySide2 import QtGui
from PySide2 import QtWidgets
from PySide2.QtWidgets import QMessageBox

from .create_slate import CreateSlate
from .submit_version import SubmitVersion


class ReviewDialog(QtWidgets.QDialog):
    def __init__(self, app, parent=None):
        QtWidgets.QDialog.__init__(self, parent)
        self.app = app
        self.current_engine = self.app.engine
        self.logger = self.app.logger
        self.sg = self.current_engine.shotgun
        self.current_context = self.current_engine.context
        self.entity = self.current_context.entity

        # Get task and project info
        self.fields = {
            "cut_in": self.app.get_setting("cut_in_field"),
            "cut_out": self.app.get_setting("cut_out_field"),
            "fps": self.app.get_setting("fps_field"),
        }

        cut_data = self.sg.find_one(
            self.entity["type"],
            [["id", "is", self.entity["id"]]],
            [self.fields.get("cut_in"), self.fields.get("cut_out")],
        )

        project_name = self.current_context.project["name"]
        fps = self.sg.find_one(
            "Project", [["name", "is", project_name]], [self.fields.get("fps")]
        ).get(self.fields.get("fps"))

        self.cut_data = {
            "cut_in": cut_data.get(self.fields.get("cut_in")),
            "cut_out": cut_data.get(self.fields.get("cut_out")),
            "fps": float(fps),
        }

        self.work_file_template = self.app.get_template("work_file_template")
        review_file_template = self.app.get_template("review_file_template")

        fields = self.work_file_template.get_fields(
            self.app.execute_hook_method(
                key="helper_hook",
                method_name="get_file_path",
            )
        )
        self.file_fields = fields
        self.review_file_path = review_file_template.apply_fields(self.file_fields)

        # Create a temporary directory for the JPG files
        temp_dir = tempfile.mkdtemp()
        self.render_file_path = os.path.join(temp_dir, "temporary.####.jpg")
        if self.current_engine.name == "tk-houdini":
            self.render_file_path = os.path.join(temp_dir, "temporary.$F4.jpg")

        # Format temporary path for importing in Nuke
        self.nuke_render_file_path = os.path.join(temp_dir, "temporary.####.jpg")

        #
        # --- DIALOG ---
        #
        self.setWindowTitle("ShotGrid Review")

        # Define general layout
        layout = QtWidgets.QVBoxLayout()
        group_layout = QtWidgets.QVBoxLayout()

        # Set label
        self.output_label = QtWidgets.QLabel(
            "Rendering to: %s" % (os.path.basename(self.review_file_path))
        )

        # description widget
        self.description_label = QtWidgets.QLabel("Description")
        self.description = QtWidgets.QLineEdit()

        #
        # --- FRAME RANGE ---
        #
        # frame range widget
        self.frame_range = QtWidgets.QGroupBox("Frame range")
        frame_range_group_layout = QtWidgets.QHBoxLayout()

        # frame range start sub-widget
        self.frame_range_start = QtWidgets.QWidget()
        frame_range_start_layout = QtWidgets.QVBoxLayout()
        self.frame_range_start_label = QtWidgets.QLabel("Start")
        self.frame_range_start_line = QtWidgets.QDoubleSpinBox()
        self.frame_range_start_line.setDecimals(0)
        self.frame_range_start_line.setRange(0, 1000000)
        self.frame_range_start_line.setValue(self.__get_frame_range()[0])
        frame_range_start_layout.addWidget(self.frame_range_start_label)
        frame_range_start_layout.addWidget(self.frame_range_start_line)
        self.frame_range_start.setLayout(frame_range_start_layout)
        frame_range_group_layout.addWidget(self.frame_range_start)

        # frame range end sub-widget
        self.frame_range_end = QtWidgets.QWidget()
        frame_range_end_layout = QtWidgets.QVBoxLayout()
        self.frame_range_end_label = QtWidgets.QLabel("End")
        self.frame_range_end_line = QtWidgets.QDoubleSpinBox()
        self.frame_range_end_line.setDecimals(0)
        self.frame_range_end_line.setRange(0, 1000000)
        self.frame_range_end_line.setValue(self.__get_frame_range()[1])
        frame_range_end_layout.addWidget(self.frame_range_end_label)
        frame_range_end_layout.addWidget(self.frame_range_end_line)
        self.frame_range_end.setLayout(frame_range_end_layout)
        frame_range_group_layout.addWidget(self.frame_range_end)

        # fps sub-widget
        self.fps_widget = QtWidgets.QWidget()
        fps_widget_layout = QtWidgets.QVBoxLayout()
        self.fps_widget_label = QtWidgets.QLabel("FPS")
        self.fps_widget_line = QtWidgets.QDoubleSpinBox()
        self.fps_widget_line.setRange(0, 1000000)
        self.fps_widget_line.setValue(self.__get_default_fps())
        fps_widget_layout.addWidget(self.fps_widget_label)
        fps_widget_layout.addWidget(self.fps_widget_line)
        self.fps_widget.setLayout(fps_widget_layout)
        frame_range_group_layout.addWidget(self.fps_widget)

        # frame range widget finalizing
        self.frame_range.setLayout(frame_range_group_layout)

        #
        # --- RESOLUTION ---
        #
        # resolution sub-widgets x
        self.resolution_x = QtWidgets.QWidget()
        self.resolution_x.default = 1920
        resolution_x_layout = QtWidgets.QVBoxLayout()
        self.resolution_x_label = QtWidgets.QLabel("Width")
        self.resolution_x_line = QtWidgets.QDoubleSpinBox()
        self.resolution_x_line.setDecimals(0)
        self.resolution_x_line.setRange(0, 1000000)
        self.resolution_x_line.setValue(self.resolution_x.default)
        resolution_x_layout.addWidget(self.resolution_x_label)
        resolution_x_layout.addWidget(self.resolution_x_line)
        self.resolution_x.setLayout(resolution_x_layout)

        # resolution sub-widgets y
        self.resolution_y = QtWidgets.QWidget()
        self.resolution_y.default = 1080
        resolution_y_layout = QtWidgets.QVBoxLayout()
        self.resolution_y_label = QtWidgets.QLabel("Height")
        self.resolution_y_line = QtWidgets.QDoubleSpinBox()
        self.resolution_y_line.setDecimals(0)
        self.resolution_y_line.setRange(0, 1000000)
        self.resolution_y_line.setValue(self.resolution_y.default)
        resolution_y_layout.addWidget(self.resolution_y_label)
        resolution_y_layout.addWidget(self.resolution_y_line)
        self.resolution_y.setLayout(resolution_y_layout)

        # resolution group
        self.resolution_group = QtWidgets.QGroupBox("Resolution")
        resolution_group_layout = QtWidgets.QHBoxLayout()
        resolution_group_layout.addWidget(self.resolution_x)
        resolution_group_layout.addWidget(self.resolution_y)
        self.resolution_group.setLayout(resolution_group_layout)

        #
        # --- OPTIONS ---
        #
        # Houdini specific settings
        if self.current_engine.name == "tk-houdini":
            self.output_to_mplay = QtWidgets.QCheckBox("MPlay Output", self)
            self.output_to_mplay.setChecked(True)
            self.beauty_pass_only = QtWidgets.QCheckBox("Beauty Pass", self)
            group_layout.addWidget(self.output_to_mplay)
            group_layout.addWidget(self.beauty_pass_only)
        elif self.current_engine.name == "tk-maya":
            self.use_antialiasing = QtWidgets.QCheckBox("Anti-aliasing", self)
            self.show_ornaments = QtWidgets.QCheckBox("Show ornaments", self)
            self.show_ornaments.setChecked(True)
            group_layout.addWidget(self.use_antialiasing)
            group_layout.addWidget(self.show_ornaments)

        self.use_motionblur = QtWidgets.QCheckBox("Motion Blur", self)
        group_layout.addWidget(self.use_motionblur)

        # save new version widget
        self.save_new_version_checkbox = QtWidgets.QCheckBox("Save New Version", self)
        self.save_new_version_checkbox.setChecked(True)

        # publish to ShotGrid
        self.publish_to_shotgrid_checkbox = QtWidgets.QCheckBox(
            "Publish to ShotGrid", self
        )

        # copy to path widget
        self.copy_path_button = QtWidgets.QPushButton("Copy Path to Clipboard")

        # options group
        self.options_group = QtWidgets.QGroupBox("Render options")
        group_layout.addWidget(self.save_new_version_checkbox)
        group_layout.addWidget(self.publish_to_shotgrid_checkbox)
        group_layout.addWidget(self.copy_path_button)
        self.options_group.setLayout(group_layout)

        #
        # --- DIALOG ---
        #
        # button box buttons
        self.cancel_button = QtWidgets.QPushButton("Cancel")
        self.start_button = QtWidgets.QPushButton("Start Render")

        # lower right button box
        button_box = QtWidgets.QDialogButtonBox()
        button_box.addButton(self.start_button, QtWidgets.QDialogButtonBox.ActionRole)
        button_box.addButton(self.cancel_button, QtWidgets.QDialogButtonBox.ActionRole)

        # widgets additions
        layout.addWidget(self.output_label)
        layout.addWidget(self.description_label)
        layout.addWidget(self.description)
        layout.addWidget(self.frame_range)
        layout.addWidget(self.resolution_group)
        layout.addWidget(self.options_group)
        layout.addWidget(button_box)

        # connect button functionality
        self.cancel_button.clicked.connect(self.close_window)
        self.start_button.clicked.connect(self.start_render)
        self.copy_path_button.clicked.connect(self.copy_path_to_clipboard)

        # finally, set layout
        self.setLayout(layout)

    def close_window(self):
        self.close()

    def start_render(self):
        publish_to_shotgrid = self.validate_shotgrid()
        save_new_version = self.validate_save_new_version()

        def run(progress):
            self.close_window()

            # Validation of inputs
            progress.set_progress(0, "Collecting render data")
            input_settings = {}
            engine_settings = {}

            input_settings["render_file_path"] = self.render_file_path
            input_settings["review_file_path"] = self.review_file_path
            input_settings["frame_range"] = self.validate_frame_range()
            input_settings["fps"] = self.validate_fps()
            input_settings["resolution"] = self.validate_resolution()
            input_settings["description"] = self.validate_description()
            input_settings["version"] = self.file_fields.get("version")

            if self.current_engine.name == "tk-houdini":
                engine_settings["mplay"] = self.validate_mplay()
                engine_settings["beauty_pass"] = self.validate_beauty()
            elif self.current_engine.name == "tk-maya":
                engine_settings["use_antialiasing"] = self.validate_antialiasing()
                engine_settings["show_ornaments"] = self.validate_show_ornaments()
            engine_settings["motion_blur"] = self.validate_motionblur()

            input_settings["engine_settings"] = engine_settings

            self.logger.debug("Using the following settings, %s" % input_settings)

            # Render
            progress.next_progress("Executing the render hook")
            self.app.execute_hook_method(
                key="render_media_hook",
                method_name="render",
                base_class=None,
                **input_settings
            )

            # Slate
            progress.next_progress("Rendering slate")

            project_file = os.path.basename(
                self.app.execute_hook_method(
                    key="helper_hook",
                    method_name="get_file_path",
                )
            ).lower()
            try:
                slate = CreateSlate(self.app)
                slate.run_slate(
                    self.nuke_render_file_path,
                    self.review_file_path,
                    project_file,
                    input_settings,
                )
            except Exception as err:
                progress.finish()
                QMessageBox.question(
                    self,
                    "Error",
                    "Something went wrong while rendering the slate:\n\n{}".format(err),
                    QMessageBox.Ok,
                    QMessageBox.Ok
                )
                return False

            # Check if created slate
            if not pathlib.Path(self.review_file_path).is_file():
                self.logger.error('Something went wrong while creating the slate!')
                progress.finish()
                QMessageBox.question(
                    self,
                    "Error",
                    "Something went wrong while creating the slate! Please check if the app is configured properly and "
                    "try again.",
                    QMessageBox.Ok,
                    QMessageBox.Ok
                )
                return False

            # Publish
            if publish_to_shotgrid:
                progress.next_progress("Creating Shotgun Version and uploading movie")
                SubmitVersion(
                    self.app,
                    self.review_file_path,
                    self.validate_frame_range(),
                    self.validate_description(),
                ).submit_version()

            # Save
            if save_new_version:
                progress.next_progress("Saving file")
                new_file = self.file_fields
                new_file["version"] += 1
                self.app.execute_hook_method(
                    key="helper_hook",
                    method_name="save_file",
                    path=self.work_file_template.apply_fields(new_file),
                )

            # Close window
            progress.finish()
            self.logger.info("Review successful")

        # Start progress bar
        progress = self.app.execute_hook_method(
            key="progress_hook",
            method_name="create_progress",
            name="{}ing".format(self.app.get_setting("display_name")),
            long_name="Creating a review",
            total_items=4 + int(publish_to_shotgrid) + int(save_new_version),
        ).start(run)

        if progress:
            # Show completed dialog
            QMessageBox.question(
                self,
                "Completed",
                "Rendering preview completed.",
                QMessageBox.Ok,
                QMessageBox.Ok
            )

    def copy_path_to_clipboard(self):
        """
        copyPathButton callback
        Copy the output path to the clipboard.
        """
        self.logger.debug("Copying path to clipboard: %s" % self.review_file_path)
        QtGui.QGuiApplication.clipboard().setText(self.review_file_path)
        return

    def validate_shotgrid(self):
        # validating the publish to ShotGrid checkbox
        return self.publish_to_shotgrid_checkbox.isChecked()

    def validate_save_new_version(self):
        # save_new_version validation
        # check if the save new version option is ticked
        return self.save_new_version_checkbox.isChecked()

    def validate_frame_range(self):
        """Format the frame range"""

        cut_in = self.__get_frame_range()[0]
        if self.frame_range_start_line.hasAcceptableInput():
            cut_in = int(self.frame_range_start_line.text())

        self.logger.debug("Setting start of frame range to %s" % cut_in)

        cut_out = self.__get_frame_range()[1]
        if self.frame_range_end_line.hasAcceptableInput():
            cut_out = int(self.frame_range_end_line.text())

        self.logger.debug("Setting end of frame range to %s" % cut_out)

        return tuple(sorted([cut_in, cut_out]))

    def validate_fps(self):
        """Format the fps"""

        fps = self.__get_default_fps()
        if self.fps_widget_line.hasAcceptableInput():
            fps = self.fps_widget_line.value()

        self.logger.debug("Setting fps to %s" % fps)

        return fps

    def validate_resolution(self):
        """Format the resolution"""

        width = int(self.resolution_x.default)
        if self.resolution_x_line.hasAcceptableInput():
            width = int(self.resolution_x_line.text())

        self.logger.debug("Setting width resolution to %s" % width)

        height = int(self.resolution_y.default)
        if self.resolution_y_line.hasAcceptableInput():
            height = int(self.resolution_y_line.text())

        self.logger.debug("Setting height resolution to %s" % height)

        return tuple([width, height])

    def validate_mplay(self):
        # validating the mplay checkbox

        return self.output_to_mplay.isChecked()

    def validate_beauty(self):
        # validating the beauty pass checkbox

        return self.beauty_pass_only.isChecked()

    def validate_motionblur(self):
        # validating the motion blur checkbox

        return self.use_motionblur.isChecked()

    def validate_antialiasing(self):
        # validating the anti-aliasing checkbox

        return self.use_antialiasing.isChecked()

    def validate_show_ornaments(self):
        # validating the show ornaments checkbox

        return self.show_ornaments.isChecked()

    def validate_description(self):
        return str(self.description.text())

    def __get_frame_range(self):
        """Get the configured frame range integers."""

        frame_range = []

        frame_start = self.cut_data.get("cut_in")
        frame_end = self.cut_data.get("cut_out")

        if frame_start is None:
            cut_data = self.app.execute_hook_method(
                key="helper_hook",
                method_name="get_cut_data",
            )
            if cut_data:
                frame_range.append(int(cut_data.get("cut_in")))
                frame_range.append(int(cut_data.get("cut_out")))
            else:
                frame_range.append(1001)
                frame_range.append(1240)
        else:
            frame_range.append(int(frame_start))
            frame_range.append(int(frame_end))

        return frame_range

    def __get_default_fps(self):
        """Get the configured fps integer."""

        try:
            fps = self.cut_data.get("fps")

            if fps is None:
                cut_data = self.app.execute_hook_method(
                    key="helper_hook",
                    method_name="get_cut_data",
                    base_class=None,
                )
                if cut_data:
                    fps = cut_data.get("fps")
                else:
                    fps = 24

            return fps

        except Exception as e:
            self.logger.error(
                "An error occurred while getting the default configured frame range. Make sure the configuration for "
                "tk-multi-reviewsubmission2 is correct. %s" % str(e)
            )
