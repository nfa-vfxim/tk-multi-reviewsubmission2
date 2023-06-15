import hou

import sgtk

HookBaseClass = sgtk.get_hook_baseclass()


class Progress(HookBaseClass):
    """
    Progress hook implementation for the tk-houdini engine.
    """

    def __init__(self, *args, **kwargs):
        super(Progress, self).__init__(*args, **kwargs)
        self.__app = self.parent

        self.name = ""
        self.long_name = ""
        self.total_items = 1
        self.current_item = 0
        self.current_description = ""

        self.operation = None

    def start(self, callback):
        """
        Start the progress

        :param function callback: Callback on update

        :returns:               If progress succeeded
        :rtype:                 bool
        """
        with hou.InterruptableOperation(
            self.name,
            long_operation_name=self.long_name,
            open_interrupt_dialog=True,
        ) as operation:
            self.operation = operation
            callback(self)

    def __update(self):
        """
        Call an update on the progress
        """
        if self.operation is not None:
            self.operation.updateLongProgress(
                self.current_item / self.total_items,
                "{} ({}/{})".format(self.current_description, self.current_item + 1, self.total_items + 1)
            )
