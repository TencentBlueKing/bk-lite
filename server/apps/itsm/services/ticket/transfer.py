from typing import Annotated, Literal

from django.db.models.functions import Length
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, TypeAdapter, ValidationError

from apps.itsm.models import HandlerGroup, TicketTask
from apps.system_mgmt.models import User

ASSIGNEE_MAX_LENGTH = TicketTask._meta.get_field("assignee").max_length
Username = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=ASSIGNEE_MAX_LENGTH)]
GroupId = Annotated[int, Field(strict=True, gt=0, le=2**63 - 1)]


class UserTransferScope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["users"]
    users: list[Username] = Field(min_length=1)


class GroupTransferScope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["handler_groups"]
    group_ids: list[GroupId] = Field(min_length=1)


_scope_adapter = TypeAdapter(Annotated[UserTransferScope | GroupTransferScope, Field(discriminator="type")] | None)


def _active_users(domain):
    return (
        User.objects.filter(domain=domain, disabled=False)
        .alias(assignee_length=Length("username"))
        .filter(assignee_length__range=(1, ASSIGNEE_MAX_LENGTH))
    )


def transfer_users(domain, node):
    users = _active_users(domain)
    try:
        scope = _scope_adapter.validate_python(node.get("transfer_scope"))
    except ValidationError:
        return users.none()
    if isinstance(scope, UserTransferScope):
        return users.filter(username__in=scope.users)
    if isinstance(scope, GroupTransferScope):
        membership = HandlerGroup.objects.filter(domain=domain, id__in=scope.group_ids).values_list("members", flat=True)
        names = {name for members in membership if isinstance(members, list) for name in members if isinstance(name, str)}
        return users.filter(username__in=names)
    return users


def require_transfer_target(users, raw_target):
    target = raw_target.strip() if isinstance(raw_target, str) else ""
    if not target or len(target) > ASSIGNEE_MAX_LENGTH:
        raise ValueError("需要转单目标")
    if not users.filter(username=target).exists():
        raise PermissionError()
    return target


def validate_transfer_scopes(design, domain):
    for node in design.get("nodes", []):
        config = node.get("transfer_scope")
        actions = node.get("actions")
        if config is None or (isinstance(actions, list) and "transfer" not in actions):
            continue
        label = node.get("name") or node.get("id")
        try:
            scope = _scope_adapter.validate_python(config)
        except ValidationError as exc:
            raise ValueError(f"节点「{label}」的转交范围配置无效，请选择人员或处理组") from exc
        if isinstance(scope, UserTransferScope):
            selected = set(scope.users)
            if _active_users(domain).filter(username__in=selected).count() != len(selected):
                raise ValueError(f"节点「{label}」的转交范围含有不可用的人员")
        elif isinstance(scope, GroupTransferScope):
            selected = set(scope.group_ids)
            if HandlerGroup.objects.filter(domain=domain, id__in=selected).count() != len(selected):
                raise ValueError(f"节点「{label}」的转交范围含有不可用的处理组")
