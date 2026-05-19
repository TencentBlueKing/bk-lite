from collections import defaultdict

from apps.system_mgmt.models import Menu


class RoleManage(object):
    def get_all_menus(self, client_id, user_menus=None, username="", is_superuser=False):
        if user_menus is not None:
            user_menus.sort()
        if not is_superuser and not user_menus:
            menus = []
        else:
            menus = list(Menu.objects.filter(app=client_id).values())
            if user_menus:
                menus = [i for i in menus if i["name"] in user_menus]
        all_menus = self.transform_data(menus)
        return all_menus

    @staticmethod
    def transform_data(data):
        if not data:
            return []
        data = [
            {
                "name": i["name"],
                "type": i["menu_type"],
                "display_name": i["display_name"],
                "index": i["order"],
            }
            for i in data
        ]
        data.sort(key=lambda i: i["index"])
        transformed = defaultdict(lambda: defaultdict(lambda: {"display_name": "", "operation": []}))
        for item in data:
            type_ = item["type"]
            name_operation = item["name"].split("-")
            name = name_operation[0]
            operation = name_operation[1] if len(name_operation) > 1 else ""
            display_name = " ".join(item["display_name"].split("-")[:-1])

            if transformed[type_][name]["display_name"] == "":
                transformed[type_][name]["display_name"] = display_name

            transformed[type_][name]["operation"].append(operation)

        result = []
        for type_, names in transformed.items():
            children = []
            for name, details in names.items():
                children.append(
                    {
                        "name": name,
                        "display_name": details["display_name"],
                        "operation": details["operation"],
                    }
                )
            result.append({"name": type_, "display_name": type_, "children": children})

        return result
