import hou

import sgtk

HookBaseClass = sgtk.get_hook_baseclass()


class Helper(HookBaseClass):
    """
    Helper hook implementation for the tk-houdini engine.
    """

    def get_main_window(self):
        """
        Get the main window of the application
        """
        return hou.qt.mainWindow()

    def get_file_path(self):
        """
        Get the file path of the currently opened file
        """
        return hou.hipFile.path()

    def get_cut_data(self):
        """
        Get the frame range and fps of the currently opened file
        """
        return {
            "cut_in": hou.hscriptExpression("$FSTART"),
            "cut_out": hou.hscriptExpression("$FEND"),
            "fps": hou.hscriptExpression("$FPS"),
        }

    def save_file(self, path):
        """
        Save the file, optionally with a new path

        :param str path:    Path to save the workfile to
        """
        if path is not None:
            hou.hipFile.setName(path)
        hou.hipFile.save()
