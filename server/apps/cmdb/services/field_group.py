# -- coding: utf-8 --
# @File: field_group.py
# @Time: 2026/1/4
# @Author: windyzhao

import json
from typing import List, Dict

from django.db import transaction
from django.db.models import Max

from apps.cmdb.constants.constants import MODEL
from apps.cmdb.graph.drivers.graph_client import GraphClient
from apps.cmdb.models.field_group import FieldGroup
from apps.cmdb.services.model import ModelManage
from apps.core.exceptions.base_app_exception import BaseAppException


class FieldGroupService:
    """字段分组服务层"""

    @staticmethod
    def _ensure_groups_for_model(model_id: str, attrs: List[Dict], created_by: str = "system") -> None:
        """确保模型存在与 attrs.attr_group 一致的 FieldGroup 记录。

        说明：
        - 前端模型属性页依赖 /field_groups/full_info 返回的 groups[].attrs。
        - 若模型已有 attrs 但 FieldGroup 缺失，或 FieldGroup 的 group_name 与 attrs 中 attr_group 不一致，
          页面会显示“空”，但新增属性又会因为 attr_id 已存在而报重复。
        - 这里按 attrs 中出现过的 attr_group 自动补齐缺失分组（仅创建缺失分组，不修改已有 attrs）。
        """

        if not attrs:
            return

        existing_group_names = set(
            FieldGroup.objects.filter(model_id=model_id).values_list("group_name", flat=True)
        )

        # 收集 attrs 中出现过的分组名（保持顺序，去重）
        group_names: List[str] = []
        seen = set()
        for attr in attrs:
            g = attr.get("attr_group")
            if not g:
                continue
            if g in seen:
                continue
            seen.add(g)
            group_names.append(g)

        # 如果 attrs 全都没有 attr_group，至少给一个默认分组，避免 full_info 为空
        if not group_names:
            group_names = ["default"]

        missing = [g for g in group_names if g not in existing_group_names]
        if not missing:
            return

        max_order = (
            FieldGroup.objects.filter(model_id=model_id).aggregate(max_order=Max("order"))["max_order"]
            or 0
        )

        for idx, group_name in enumerate(missing, start=1):
            group_attr_orders = [
                a.get("attr_id")
                for a in attrs
                if a.get("attr_group") == group_name and a.get("attr_id")
            ]
            FieldGroup.objects.create(
                model_id=model_id,
                group_name=group_name,
                order=max_order + idx,
                is_collapsed=False,
                description="auto created",
                created_by=created_by,
                attr_orders=group_attr_orders,
            )

    @staticmethod
    def create_group(
            model_id: str, group_name: str, created_by: str, **kwargs
    ) -> FieldGroup:
        """
        创建字段分组

        Args:
            model_id: 模型ID
            group_name: 分组名称（必填）
            created_by: 创建人
            **kwargs: 其他可选参数（description, is_collapsed）

        Returns:
            FieldGroup: 创建的分组实例

        Raises:
            BaseAppException: 名称为空或模型不存在
        """
        # 1. 校验名称必填
        if not group_name or not group_name.strip():
            raise BaseAppException("分组名称不能为空")

        # 2. 校验模型是否存在
        model_info = ModelManage.search_model_info(model_id)
        if not model_info:
            raise BaseAppException("模型不存在")

        # 3. 检查分组名称是否已存在
        if FieldGroup.objects.filter(model_id=model_id, group_name=group_name.strip()).exists():
            raise BaseAppException(f"分组名称'{group_name}'已存在")

        # 4. 获取当前最大order值
        max_order = (
                FieldGroup.objects.filter(model_id=model_id).aggregate(
                    max_order=Max("order")
                )["max_order"]
                or 0
        )

        # 5. 创建分组
        group = FieldGroup.objects.create(
            model_id=model_id,
            group_name=group_name.strip(),
            order=max_order + 1,
            created_by=created_by,
            description=kwargs.get("description", ""),
            is_collapsed=kwargs.get("is_collapsed", False),
        )

        return group

    @staticmethod
    def update_group(group, new_group_name: str = None, **kwargs) -> FieldGroup:
        """
        修改字段分组

        Args:
            group: 要更新的分组实例
            new_group_name: 新的分组名称
            **kwargs: 其他可选参数（description, is_collapsed）

        Returns:
            FieldGroup: 更新后的分组实例

        Raises:
            BaseAppException: 名称为空、分组不存在
        """

        # 2. 更新字段
        update_fields = ["updated_at"]
        need_update_falkordb = False
        old_name = group.group_name
        model_id = group.model_id

        if new_group_name is not None:
            new_group_name = new_group_name.strip()
            if not new_group_name:
                raise BaseAppException("分组名称不能为空")

            # 检查新名称是否已存在
            if new_group_name != old_name:
                if FieldGroup.objects.filter(model_id=model_id, group_name=new_group_name).exists():
                    raise BaseAppException(f"分组名称'{new_group_name}'已存在")

                need_update_falkordb = True
                group.group_name = new_group_name
                update_fields.append("group_name")

        if "description" in kwargs and kwargs["description"] is not None:
            group.description = kwargs["description"]
            update_fields.append("description")

        if "is_collapsed" in kwargs and kwargs["is_collapsed"] is not None:
            group.is_collapsed = kwargs["is_collapsed"]
            update_fields.append("is_collapsed")

        group.save(update_fields=update_fields)

        # 3. 如果修改了分组名称，需要同步更新FalkorDB中所有字段的attr_group
        if need_update_falkordb:
            model_info = ModelManage.search_model_info(model_id)
            if model_info:
                attrs = ModelManage.parse_attrs(model_info.get("attrs", "[]"))
                updated = False
                for attr in attrs:
                    if attr.get("attr_group") == old_name:
                        attr["attr_group"] = group.group_name
                        updated = True

                if updated:
                    with GraphClient() as ag:
                        ag.set_entity_properties(
                            MODEL,
                            [model_info["_id"]],
                            {"attrs": json.dumps(attrs)},
                            {},
                            [],
                            False,
                        )

        return group

    @staticmethod
    def delete_group(group) -> Dict[str, any]:
        """
        删除字段分组

        Args:
            group: 实例对象

        Returns:
            dict: {"success": bool, "message": str}

        Raises:
            BaseAppException: 只有一个分组时禁止删除、分组不存在
        """
        model_id = group.model_id
        group_name = group.group_name

        # 查询模型下的分组总数
        group_count = FieldGroup.objects.filter(model_id=model_id).count()

        #  校验：只有一个分组时不允许删除
        if group_count <= 1:
            raise BaseAppException("至少保留一个分组，无法删除")

        #  查询分组下的属性，并迁移到第一个分组
        model_info = ModelManage.search_model_info(model_id)
        if not model_info:
            raise BaseAppException("模型不存在")

        attrs = ModelManage.parse_attrs(model_info.get("attrs", "[]"))
        attrs_in_group = [attr for attr in attrs if attr.get("attr_group") == group_name]

        # 5. 执行删除
        with transaction.atomic():
            if attrs_in_group:
                # 获取第一个分组（迁移目标）
                first_group = FieldGroup.objects.filter(model_id=model_id).order_by("order").first()
                target_group_name = first_group.group_name

                # 迁移属性到第一个分组
                for attr in attrs_in_group:
                    attr["attr_group"] = target_group_name

                # 更新模型属性
                with GraphClient() as ag:
                    ag.set_entity_properties(
                        MODEL,
                        [model_info["_id"]],
                        {"attrs": json.dumps(attrs)},
                        {},
                        [],
                        False,
                    )

            # 删除分组
            group.delete()

            # 重新排序（填补空隙）
            FieldGroupService.reorder_after_delete(model_id)

        return {"success": True, "message": "删除成功"}

    @staticmethod
    def reorder_after_delete(model_id: str):
        """删除后重新排序，消除order间隙"""
        groups = FieldGroup.objects.filter(model_id=model_id).order_by("order")
        for index, group in enumerate(groups, start=1):
            if group.order != index:
                group.order = index
                group.save(update_fields=["order"])

    @staticmethod
    def move_group(model_id: str, group_name: str, direction: str) -> Dict[str, any]:
        """
        移动分组顺序（向上/向下）

        Args:
            model_id: 模型ID
            group_name: 要移动的分组名称
            direction: 移动方向 "up" 或 "down"

        Returns:
            dict: {
                "success": bool,
                "message": str,
                "new_orders": List[{"group_name": str, "order": int}]
            }

        Raises:
            BaseAppException: 无法移动（已在边界位置）
        """
        # 1. 查询所有分组（按order排序）
        groups = list(FieldGroup.objects.filter(model_id=model_id).order_by("order"))

        if len(groups) <= 1:
            raise BaseAppException("只有一个分组，无法调整顺序")

        # 2. 找到当前分组的索引
        try:
            current_index = next(
                i for i, g in enumerate(groups) if g.group_name == group_name
            )
        except StopIteration:
            raise BaseAppException("分组不存在")

        # 3. 校验边界
        if direction == "up" and current_index == 0:
            raise BaseAppException("已经是第一个分组，无法上移")

        if direction == "down" and current_index == len(groups) - 1:
            raise BaseAppException("已经是最后一个分组，无法下移")

        # 4. 交换order
        if direction == "up":
            swap_index = current_index - 1
        else:  # down
            swap_index = current_index + 1

        current_group = groups[current_index]
        swap_group = groups[swap_index]

        # 临时存储order
        temp_order = current_group.order
        current_group.order = swap_group.order
        swap_group.order = temp_order

        # 5. 批量更新数据库
        try:
            with transaction.atomic():
                current_group.save(update_fields=["order"])
                swap_group.save(update_fields=["order"])

            # 6. 返回新的顺序列表
            new_orders = [
                {"group_name": g.group_name, "order": g.order}
                for g in sorted(groups, key=lambda x: x.order)
            ]

            return {"success": True, "message": "修改成功", "new_orders": new_orders}

        except Exception as e:
            raise BaseAppException(f"修改失败：{str(e)}")

    @staticmethod
    def list_groups(model_id: str) -> List[FieldGroup]:
        """
        获取模型的所有分组

        Args:
            model_id: 模型ID

        Returns:
            List[FieldGroup]: 分组列表（按order排序）
        """
        return list(FieldGroup.objects.filter(model_id=model_id).order_by("order"))

    @staticmethod
    def get_model_with_groups(model_id: str, language: str = "zh-Hans") -> Dict:
        """
        获取模型完整信息（包含分组和属性）

        Args:
            model_id: 模型ID
            language: 语言

        Returns:
            dict: {
                "model_id": str,
                "model_name": str,
                "groups": [
                    {
                        "group_name": str,
                        "order": int,
                        "is_collapsed": bool,
                        "attrs": [...],  # 该分组下的属性列表
                        "attrs_count": int,
                        "can_move_up": bool,
                        "can_move_down": bool,
                        "can_delete": bool
                    }
                ],
                "total_groups": int,
                "total_attrs": int
            }
        """
        # 1. 获取模型基本信息
        model_info = ModelManage.search_model_info(model_id)
        if not model_info:
            raise BaseAppException("模型不存在")

        # 2. 解析属性
        attrs = ModelManage.parse_attrs(model_info.get("attrs", "[]"))

        # 3. 获取所有分组（若缺失/不匹配则自动补齐，避免前端属性页显示为空）
        groups = FieldGroup.objects.filter(model_id=model_id).order_by("order")
        if attrs:
            FieldGroupService._ensure_groups_for_model(model_id=model_id, attrs=attrs)
            groups = FieldGroup.objects.filter(model_id=model_id).order_by("order")

        groups_count = groups.count()

        # 4. 按分组组织属性
        groups_data = []
        for idx, group in enumerate(groups):
            group_attrs = [
                attr for attr in attrs if attr.get("attr_group") == group.group_name
            ]

            # 按FieldGroup中存储的attr_orders排序分组内的属性
            if group.attr_orders:
                # 创建排序映射
                order_map = {attr_id: order for order, attr_id in enumerate(group.attr_orders)}
                # 排序：在attr_orders中的排在前面，不在的排在后面
                group_attrs.sort(key=lambda x: order_map.get(x.get("attr_id"), 9999))

            groups_data.append(
                {
                    "id": group.id,
                    "group_name": group.group_name,
                    "order": group.order,
                    "is_collapsed": group.is_collapsed,
                    "description": group.description,
                    "attrs": group_attrs,
                    "attrs_count": len(group_attrs),
                    # 用于前端判断是否显示上下移动按钮
                    "can_move_up": idx > 0,
                    "can_move_down": idx < groups_count - 1,
                    "can_delete": groups_count > 1,  # 只有一个分组时不能删除
                }
            )

        return {
            "model_id": model_info["model_id"],
            "model_name": model_info["model_name"],
            "groups": groups_data,
            "total_groups": len(groups_data),
            "total_attrs": len(attrs),
        }

    @staticmethod
    def validate_group_exists(model_id: str, group_name: str):
        """
        校验分组是否存在

        Args:
            model_id: 模型ID
            group_name: 分组名称

        Returns:
            bool: 是否存在

        Raises:
            BaseAppException: 分组不存在
        """
        exists = FieldGroup.objects.filter(
            model_id=model_id, group_name=group_name
        ).exists()
        if not exists:
            raise BaseAppException(f"分组'{group_name}'不存在")

    @staticmethod
    def batch_update_attrs_group(model_id: str, updates: List[Dict]) -> Dict:
        """
        批量更新字段分组

        Args:
            model_id: 模型ID
            updates: 更新列表 [{"attr_id": "xxx", "group_name": "yyy"}, ...]

        Returns:
            dict: {
                "success": bool,
                "message": str,
                "updated_count": int
            }

        Raises:
            BaseAppException: 模型不存在、分组不存在、字段不存在
        """
        # 1. 获取模型信息
        model_info = ModelManage.search_model_info(model_id)
        if not model_info:
            raise BaseAppException("模型不存在")

        # 2. 校验所有目标分组是否存在
        unique_group_names = set(item["group_name"] for item in updates)
        for group_name in unique_group_names:
            FieldGroupService.validate_group_exists(model_id, group_name)

        # 3. 解析属性
        attrs = ModelManage.parse_attrs(model_info.get("attrs", "[]"))

        # 4. 批量更新
        updated_count = 0
        for update in updates:
            attr_id = update["attr_id"]
            new_group_name = update["group_name"]

            # 查找并更新属性
            for attr in attrs:
                if attr.get("attr_id") == attr_id:
                    attr["attr_group"] = new_group_name
                    updated_count += 1
                    break
            else:
                raise BaseAppException(f"字段'{attr_id}'不存在")

        # 5. 保存到FalkorDB
        with GraphClient() as ag:
            ag.set_entity_properties(
                MODEL, [model_info["_id"]], {"attrs": json.dumps(attrs)}, {}, [], False
            )

        # 6. 更新各个分组的attr_orders（添加新属性到末尾）
        for group_name in unique_group_names:
            group = FieldGroup.objects.get(model_id=model_id, group_name=group_name)
            group_attr_ids = [attr.get("attr_id") for attr in attrs if attr.get("attr_group") == group_name]

            # 保留原有顺序，添加新的到末尾
            existing_orders = group.attr_orders or []
            new_orders = [aid for aid in existing_orders if aid in group_attr_ids]
            for aid in group_attr_ids:
                if aid not in new_orders:
                    new_orders.append(aid)

            group.attr_orders = new_orders
            group.save(update_fields=["attr_orders"])

        return {
            "success": True,
            "message": f"成功更新{updated_count}个字段的分组",
            "updated_count": updated_count,
        }

    @staticmethod
    def update_attr_group(model_id: str, attr_id: str, new_group_name: str, order_id: int = None) -> Dict:
        """
        修改单个属性的分组（支持跨分组移动）

        Args:
            model_id: 模型ID
            attr_id: 属性ID
            new_group_name: 新的分组名称
            order_id: 新分组内的排序位置（可选，默认为None时插入到末尾）

        Returns:
            dict: {
                "success": bool,
                "message": str,
                "attr_id": str,
                "old_group": str,
                "new_group": str
            }

        Raises:
            BaseAppException: 模型不存在、分组不存在、字段不存在
        """
        # 1. 获取模型信息
        model_info = ModelManage.search_model_info(model_id)
        if not model_info:
            raise BaseAppException("模型不存在")

        # 2. 校验目标分组是否存在
        FieldGroupService.validate_group_exists(model_id, new_group_name)

        # 3. 解析属性
        attrs = ModelManage.parse_attrs(model_info.get("attrs", "[]"))

        # 4. 查找并更新属性
        old_group = None
        found = False
        for attr in attrs:
            if attr.get("attr_id") == attr_id:
                old_group = attr.get("attr_group", "")
                attr["attr_group"] = new_group_name
                found = True
                break

        if not found:
            raise BaseAppException(f"字段'{attr_id}'不存在")

        # 5. 保存到FalkorDB
        with GraphClient() as ag:
            ag.set_entity_properties(
                MODEL, [model_info["_id"]], {"attrs": json.dumps(attrs)}, {}, [], False
            )

        # 6. 更新分组的attr_orders
        # 从旧分组移除
        if old_group:
            try:
                old_group_obj = FieldGroup.objects.get(model_id=model_id, group_name=old_group)
                if old_group_obj.attr_orders and attr_id in old_group_obj.attr_orders:
                    old_group_obj.attr_orders.remove(attr_id)
                    old_group_obj.save(update_fields=["attr_orders"])
            except FieldGroup.DoesNotExist:
                pass

        # 添加到新分组的指定位置
        new_group_obj = FieldGroup.objects.get(model_id=model_id, group_name=new_group_name)
        if not new_group_obj.attr_orders:
            new_group_obj.attr_orders = []
        
        # 如果属性已存在,先移除(避免重复)
        if attr_id in new_group_obj.attr_orders:
            new_group_obj.attr_orders.remove(attr_id)
        
        # 插入到指定位置
        if order_id is None:
            # 未指定位置,插入到末尾
            new_group_obj.attr_orders.append(attr_id)
        else:
            # 指定了位置,插入到对应位置(如果超出范围,则插入到末尾)
            if order_id < 0:
                insert_position = 0
            elif order_id >= len(new_group_obj.attr_orders):
                insert_position = len(new_group_obj.attr_orders)
            else:
                insert_position = order_id
            new_group_obj.attr_orders.insert(insert_position, attr_id)
        new_group_obj.save(update_fields=["attr_orders"])

        return {
            "success": True,
            "message": f"成功将属性'{attr_id}'从'{old_group}'移动到'{new_group_name}'",
            "attr_id": attr_id,
            "new_group": new_group_name,
        }

    @staticmethod
    def reorder_group_attrs(model_id: str, group_name: str, attr_orders: List[str]) -> Dict:
        """
        调整分组内属性的顺序

        Args:
            model_id: 模型ID
            group_name: 分组名称
            attr_orders: 属性ID列表（按新顺序排列），例如 ["c", "a", "b"]

        Returns:
            dict: {
                "success": bool,
                "message": str,
                "group_name": str,
                "attr_orders": List[str]
            }

        Raises:
            BaseAppException: 模型不存在、分组不存在、属性不在该分组中
        """
        # 1. 获取模型信息
        model_info = ModelManage.search_model_info(model_id)
        if not model_info:
            raise BaseAppException("模型不存在")

        # 2. 查询分组
        try:
            group = FieldGroup.objects.get(model_id=model_id, group_name=group_name)
        except FieldGroup.DoesNotExist:
            raise BaseAppException("分组不存在")

        # 3. 解析属性，获取该分组下的所有属性
        attrs = ModelManage.parse_attrs(model_info.get("attrs", "[]"))
        group_attr_ids = {attr.get("attr_id") for attr in attrs if attr.get("attr_group") == group_name}

        # 4. 校验：attr_orders中的属性必须都属于该分组
        for attr_id in attr_orders:
            if attr_id not in group_attr_ids:
                raise BaseAppException(f"属性'{attr_id}'不属于分组'{group_name}'")

        # 5. 校验：attr_orders必须包含该分组的所有属性
        if set(attr_orders) != group_attr_ids:
            missing = group_attr_ids - set(attr_orders)
            raise BaseAppException(f"缺少属性：{', '.join(missing)}")

        # 6. 更新分组的attr_orders字段
        group.attr_orders = attr_orders
        group.save(update_fields=["attr_orders"])

        return {
            "success": True,
            "message": f"成功调整分组'{group_name}'的属性顺序",
            "group_name": group_name,
            "attr_orders": attr_orders,
        }
