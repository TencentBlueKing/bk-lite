from apps.node_mgmt.models import Controller

CONTROLLER = [
    {
        "os": "linux",
        "name": "Controller",
        "description": "The Controller is primarily used to manage various types of collectors, composed of Sidecarand NAS Executor, enabling automated deployment, resource coordination, and task execution on servers.",
    },
    {
        "os": "windows",
        "name": "Controller",
        "description": "The Controller is primarily used to manage various types of collectors, composed of Sidecarand NAS Executor, enabling automated deployment, resource coordination, and task execution on servers.",
    },
]

def controller_init():
    old_controller = Controller.objects.all()
    old_controller_map = {(i.os, i.name): i for i in old_controller}

    create_controllers, update_controllers = [], []

    for controller_info in CONTROLLER:

        if (controller_info["os"], controller_info["name"]) in old_controller_map:
            obj = old_controller_map[(controller_info["os"], controller_info["name"])]
            obj.description = controller_info["description"]
            update_controllers.append(obj)
        else:
            create_controllers.append(controller_info)

    if create_controllers:
        Controller.objects.bulk_create([Controller(**i) for i in create_controllers])

    if update_controllers:
        Controller.objects.bulk_update(update_controllers, ["description"])