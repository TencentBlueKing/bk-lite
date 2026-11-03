# 通知渠道标签

Status: implemented

## Problem Statement

通知渠道目前只能整条启用或停用，同一条渠道上的不同消息用途无法区分。用户若要把 ITSM 和测试环境的消息走不同处理，只能复制渠道，或者放弃按用途筛选。

## Solution

管理员在配置通知渠道时，用与 CMDB 实例标签相同的两级选择为渠道打上 `key:value` 标签。标签候选全局一份，不按组织拆分，邮箱渠道和 IM 应用通知渠道共用。保存后，渠道列表展示这条渠道选中的标签；对外渠道目录用同样的字符串数组返回，并可以按这些整串筛选。

## User Stories

1. As a 系统管理员, I want to pick existing `key:value` tags and add a new pair while configuring a notification channel, so that one channel can be distinguished by message purpose.
2. As a 系统管理员, I want a tag added on an email channel to appear the next time I open an IM notification channel, so that I do not maintain a separate vocabulary per channel type.
3. As a 系统管理员, I want a channel saved with no tags to stay empty, so that the initial enterprise WeChat channel is not given a tag it never selected.
4. As an 外部调用方, I want `GET /openapi/v1/system-mgmt/notification-channels` to return each channel's selected tags as `tag: ["用途:ITSM"]`, so that I can see the purpose without reading channel credentials.
5. As an 外部调用方, I want to filter that directory by one or more `key:value` strings, so that a channel matches when it has any requested tag, and a channel with no tags is left out only when a tag filter is present.
6. As a 系统管理员, I want deleting or editing a channel to change only that channel's selected tags, so that a tag removed from one channel remains available for the others.

## Implementation Decisions

- 标签候选是一张全局表，一行一对 `key` 与 `value`，`(key, value)` 唯一。表上没有组织字段。沿用系统管理现有的维护人与时间字段；其中 `domain` 是操作者域，不是组织。
- `key` 与 `value` 去掉首尾空格后保存，长度各不超过 64。两者都不能包含冒号、空格、换行或逗号。逗号也排除，是因为对外目录的筛选参数只能以单个查询字符串传入，多条标签用逗号分隔。
- 初始化命令插入 `system` / `itsm`。已有渠道不自动关联任何标签。
- 邮箱、企微、机器人、Webhook 等 `Channel`，以及 IM 应用通知渠道，各自用关联表保存选中的标签行。删除渠道时删除关联，不删除候选行。同一 `key` 的不同 `value` 是不同行，一条渠道可以同时选中。
- 配置页的两级选择不读渠道列表。打开配置时单独读取全部候选，按 `key` 分组；左列是 key，右列是 value。加号填写一对后先进入当前表单，当前下拉立即可见。保存时把新的一对写入候选表，并替换这条渠道的选用。保存成功后刷新渠道列表，列表行展示该渠道的 `tag`。
- 渠道创建、修改和读取使用字段名 `tag`，值是字符串数组，例如 `["用途:ITSM", "用途:测试环境"]`。未选为 `[]`。顺序按候选行 `id` 升序。IM 应用通知渠道的配置接口使用同一个字段。
- 对外目录 `GET /openapi/v1/system-mgmt/notification-channels` 默认同时返回当前组织内的普通渠道和 IM 应用通知。两者都用已有的 `channel_type` 区分，IM 应用通知的值是 `im_notification`。每条结果的 `tag` 都是同样的字符串数组。查询参数 `tag` 为逗号分隔的整串；传入时渠道命中其中任意一条即返回，没有标签的渠道不返回。不传 `tag` 时，空标签渠道仍按原有组织范围返回。NATS 仍不在这个目录里。
- 发送接口 `POST /openapi/v1/system-mgmt/notification-channels/send` 不接收标签，也不按标签选择渠道。`channel_type` 必填，取目录返回的原值。`im_notification` 只查找 IM 应用通知并发送，其他值只查找对应的普通渠道，因为两边的数字 `id` 可能相同。

## Testing Decisions

测试只观察接口的请求和响应，不断言关联表的内部列名。

- 渠道配置接口：创建和修改后再次读取，`tag` 与提交的整串一致；新的一对出现在候选读取结果中；删除渠道后候选仍在，另一条渠道仍能选到。非法字符、空 key 或空 value 被拒绝。已有无标签渠道返回 `[]`。
- IM 应用通知渠道配置接口：同一套保存、回读和候选共享行为。
- 对外目录：双租户下只返回本组织渠道，默认同时包含普通渠道和 IM 应用通知，并用 `channel_type` 区分；`tag` 为字符串数组；按逗号分隔的整串筛选时命中任意一条，无标签渠道在传入筛选时不出现，不传筛选时仍出现。发送接口的请求体和响应不出现 `tag`。`channel_type` 缺失时请求被拒绝；传入 `im_notification` 时投递 IM 渠道，传入普通渠道类型时只投递该类型。
- 先验是现有渠道配置接口测试、IM 应用通知渠道接口测试，以及对外通知渠道目录的双租户测试。

## Out of Scope

- 不按组织拆分标签候选。
- 不自动推荐或生成标签。
- 不按标签做消息路由或分发。
- 不提供 CMDB 的严格模式。
- 不改变发送接口。

## Further Notes

CMDB 实例上的已选标签也是 `key:value` 字符串数组；候选则按模型存放。通知渠道的候选改成全局表，是因为邮箱渠道和 IM 应用通知渠道不是同一个模型，仍要共用一份下拉。

## Completion

渠道配置、IM 应用通知配置和对外目录的保存、回读、候选共享与逗号筛选已有接口测试覆盖。发送接口仍拒绝 `tag`。
