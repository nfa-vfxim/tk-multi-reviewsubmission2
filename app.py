# Copyright (c) 2013 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

"""
Sgtk Application for handling Quicktime generation and review submission
"""

import os
import pathlib

import sgtk.templatekey

try:
    from PySide2 import QtCore
    from PySide2.QtWidgets import QMessageBox
except ModuleNotFoundError:
    from PySide6 import QtCore
    from PySide6.QtWidgets import QMessageBox


class MultiReviewSubmissionApp(sgtk.platform.Application):
    """
    Main Application class
    """

    def init_app(self):
        """
        App initialization

        Note, this app doesn't register any commands at the moment as all it's functionality is
        provided through it's API.
        """

        self.reviewsubmission2 = self.import_module("tk_multi_reviewsubmission2")

        display_name = self.get_setting("display_name")

        # Only register the command to the engine if the display name is explicitly added to the config.
        # There's cases where someone would want to have this app in his environment without the menu item.
        if display_name:
            menu_caption = "%s..." % display_name
            menu_options = {
                "short_name": "create_review",
                "description": "Render a version for review",
                # dark themed icon for engines that recognize this format
                "icons": {
                    "dark": {
                        "png": os.path.join(self.disk_location, "icon_256_dark.png")
                    }
                },
            }

            self.engine.register_command(menu_caption, self.__show_dialog, menu_options)

    def __show_dialog(self):
        """
        Launch the UI for the flipbook settings.
        """
        main_window = self.execute_hook_method(
            key="helper_hook",
            method_name="get_main_window",
            base_class=None,
        )

        if main_window is not None:
            work_file_template = self.get_template("work_file_template")
            review_file_template = self.get_template("review_file_template")

            file_path = self.execute_hook_method(
                key="helper_hook",
                method_name="get_file_path",
            )

            # The work file has to follow the work file template, otherwise we
            # can't work out where the review file should go. This happens when
            # a scene was never saved, or saved outside of ShotGrid (e.g. Maya's
            # own File > Save As). Tell the user how to fix it instead of
            # raising a TankError traceback.
            fields = None
            if file_path:
                try:
                    fields = work_file_template.get_fields(file_path)
                except sgtk.TankError as error:
                    self.logger.debug(
                        "Work file does not match template: %s" % error
                    )

            if fields is None:
                if file_path:
                    problem = (
                        "The file <b>%s</b> was not saved through ShotGrid, "
                        "so its name does not match the pipeline."
                    ) % os.path.basename(file_path)
                else:
                    problem = "This scene has not been saved yet."

                QMessageBox.warning(
                    main_window,
                    "Can't create review",
                    problem + "<br><br>Please save the scene through "
                    "<b>ShotGrid &gt; File Save...</b> first and try again.",
                )
                return

            self.review_file_path = review_file_template.apply_fields(fields)

            # Check if review file already exists
            if pathlib.Path(self.review_file_path).is_file():
                reply = QMessageBox.question(
                    main_window,
                    "Override preview",
                    "A preview for this file already exists, do you want to override it?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if reply == QMessageBox.No:
                    return

            review_dialog = self.reviewsubmission2.ReviewDialog(self)
            review_dialog.setParent(main_window, QtCore.Qt.Window)
            review_dialog.setModal(True)
            review_dialog.show()
        else:
            self.logger.error("Can't find main window.")
