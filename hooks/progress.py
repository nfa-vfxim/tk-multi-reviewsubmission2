import sgtk
from typing import Callable

HookBaseClass = sgtk.get_hook_baseclass()


class Progress(HookBaseClass):
    """
    Base class of the Progress hook.
    """

    def __init__(self, *args, **kwargs):
        super(Progress, self).__init__(*args, **kwargs)
        self.__app = self.parent

        self.name = ""
        self.long_name = ""
        self.total_items = 1
        self.current_item = 0
        self.current_description = ""

    def create_progress(self, name, long_name, total_items):
        """
        Create the progress instance

        :param str name:        Short progress name
        :param str long_name:   Long progress name
        :param int total_items: Total items in progress

        :returns:               Progress object
        :rtype:                 Progress
        """
        self.name = name
        self.long_name = long_name
        self.total_items = total_items
        return self

    def set_progress(self, current_item, description):
        """
        Set the current item index and description

        :param int current_item:    Progress item index
        :param str description:     Progress item description
        """
        self.current_item = current_item
        self.current_description = description

        self.__update()

    def next_progress(self, description):
        """
        Go to the next progress item

        :param str description: Progress item description
        """
        self.current_item += 1
        self.current_description = description

        self.__update()

    def finish(self):
        """
        Complete the progress
        """
        self.current_item = self.total_items

        self.__update()

    def start(self, callback):
        """
        Start the progress

        :param function callback: Callback on update

        :returns:               If progress succeeded
        :rtype:                 bool
        """
        callback(self)

    def __update(self):
        """
        Call an update on the progress
        """
        pass
