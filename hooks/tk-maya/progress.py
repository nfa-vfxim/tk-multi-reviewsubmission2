import maya.cmds as cmds
import sgtk

HookBaseClass = sgtk.get_hook_baseclass()


class Progress(HookBaseClass):
    """
    Progress hook implementation for the tk-maya engine.
    """

    def start(self, callback):
        """
        Start the progress

        :param function callback: Callback on update

        :returns:               If progress succeeded
        :rtype:                 bool
        """
        cmds.progressWindow(
            title=self.name,
            progress=0,
            status=self.long_name,
            isInterruptable=True,
            maxValue=self.total_items,
        )
        callback(self)

    def __update(self):
        """
        Call an update on the progress
        """
        cmds.progressWindow(
            edit=True,
            progress=self.current_item,
            status="{} ({}/{})".format(
                self.current_description, self.current_item + 1, self.total_items + 1
            ),
        )

        if self.current_item == self.total_items:
            cmds.progressWindow(endProgress=1)
