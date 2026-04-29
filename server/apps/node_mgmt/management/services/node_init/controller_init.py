from apps.node_mgmt.constants.controller import ControllerConstants
from apps.node_mgmt.models import Controller
from apps.core.logger import node_logger as logger


def controller_init():
    try:
        old_controller = Controller.objects.all()
        old_controller_map = {(i.os, i.cpu_architecture, i.name): i for i in old_controller}

        create_controllers, update_controllers = [], []

        for controller_info in ControllerConstants.CONTROLLER:
            key = (
                controller_info["os"],
                controller_info.get("cpu_architecture", ""),
                controller_info["name"],
            )

            if key in old_controller_map:
                obj = old_controller_map[key]
                obj.description = controller_info["description"]
                obj.version_command = controller_info["version_command"]
                obj.cpu_architecture = controller_info.get("cpu_architecture", "")
                update_controllers.append(obj)
            else:
                create_controllers.append(controller_info)

        if create_controllers:
            Controller.objects.bulk_create([Controller(**i) for i in create_controllers])

        if update_controllers:
            Controller.objects.bulk_update(update_controllers, ["description", "version_command", "cpu_architecture"])
    except Exception as e:
        logger.exception(e)
