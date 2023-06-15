import sgtk

HookBaseClass = sgtk.get_hook_baseclass()


class Helper(HookBaseClass):
    """
    Base class of the Helper hook.
    """

    def get_main_window(self):
        """
        Get the main window of the application
        """
        pass

    def get_file_path(self):
        """
        Get the file path of the currently opened file
        """
        pass

    def get_cut_data(self):
        """
        Get the frame range and fps of the currently opened file
        """
        pass

    def save_file(self, path):
        """
        Save the file, optionally with a new path

        :param str path:    Path to save the workfile to
        """
        pass
