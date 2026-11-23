# BK-Lite 通知渠道包开发指南

通知渠道包注册一种渠道类型。上传并加载成功后，通知渠道首页多一张卡片，卡片下的实例是 `Channel`。告警、流程和其他调用方按渠道实例发送，不直接调用包。

企业版在集成类型页上传 zip，请求带用途 `notification_channel`。社区版没有上传入口。包在服务进程内导入执行，加载时不会安装新依赖，上传前必须审查。

## 1. 目录结构

推荐单层目录，目录里就是包：

```text
acme_sms/
├── __init__.py
├── manifest.py
├── language/
│   ├── en.yaml
│   └── zh-Hans.yaml
└── adapters/
    ├── __init__.py
    └── send.py
```

zip 也可以把 `__init__.py` 放在根上，不要再套一层。压缩前体积和解压后总体积都不能超过 10MB。路径必须是相对路径，不能含 `..`。不要包含 `__pycache__`、`.pyc`。

加载器只强制这两个文件：

```text
__init__.py
adapters/send.py
```

另外必须有：

```text
language/en.yaml
language/zh-Hans.yaml
```

包内不要放页面、密钥或依赖声明。出现以下任一文件都会拒绝入库：

- 目录名 `pages`，或路径中含 `pages`
- 后缀 `.tsx`、`.jsx`、`.vue`、`.html`
- `requirements.txt`、`pyproject.toml`、`setup.py`、`setup.cfg`、`Pipfile`、`package.json`、`poetry.lock`
- `.env` 及以 `.env` 开头的文件
- `credentials.json`、`secrets.json`、`secrets.yaml`、`id_rsa`
- 后缀 `.pem`、`.key`

`__init__.py` 只导出 Manifest：

```python
from .manifest import PROVIDER_MANIFEST

__all__ = ["PROVIDER_MANIFEST"]
```

不要在包入口执行网络请求、数据库查询、启动线程或其他有副作用的逻辑。包内模块互相引用用相对导入。可以 import `apps.system_mgmt.providers.schemas`。这是宿主提供的契约，不是包内代码。

## 2. Manifest

`key` 会成为渠道类型，写入 `Channel.channel_type`。长度不超过 30。创建实例之后不要更换。

`key` 不能使用内置渠道类型，也不能与镜像里的内置 Provider 目录名相同，也不能是 `im_notification`。当前内置渠道类型是：

```text
email
enterprise_wechat
enterprise_wechat_bot
nats
feishu_bot
dingtalk_bot
custom_webhook
sms
voice
```

Manifest 只能有一条能力，键为 `notification_channel`。`delivery` 决定这条渠道怎么发，先看第 3 节再填。模板类写 `template`，并写 `parameter_mode`。正文类写 `body`，不要写 `parameter_mode`。

`adapter_key` 以 `{key}.` 开头。`adapter_path` 指向包内发送适配器，并且以 `adapters.send` 开头，例如 `adapters.send.AcmeSmsSendAdapter`。

渠道配置字段放在 `instance_templates`。页面把其中所有分组字段展平后渲染。不要把配置字段放进能力的 `connection_template`：发送前会丢掉实例模板以外的键。不要使用字段名 `parameters`，模板类用这个键保存变量声明。

模板类示例：

```python
from apps.system_mgmt.providers.schemas import ProviderManifest


PROVIDER_MANIFEST = ProviderManifest.model_validate(
    {
        "key": "acme_sms",
        "name": "Acme SMS",
        "description": "Acme template notification channel.",
        "instance_templates": {
            "connection": {
                "title": "Connection",
                "groups": [
                    {
                        "key": "main",
                        "title": "Main",
                        "fields": [
                            {
                                "key": "endpoint",
                                "label": "Endpoint",
                                "field_type": "string",
                                "required": True,
                            },
                            {
                                "key": "api_secret",
                                "label": "API Secret",
                                "field_type": "password",
                                "required": True,
                                "secret": True,
                            },
                            {
                                "key": "template_id",
                                "label": "Template ID",
                                "field_type": "string",
                                "required": True,
                            },
                        ],
                    }
                ],
            }
        },
        "capabilities": [
            {
                "key": "notification_channel",
                "name": "Notify",
                "adapter_key": "acme_sms.send",
                "adapter_path": "adapters.send.AcmeSmsSendAdapter",
                "delivery": "template",
                "parameter_mode": "named",
            }
        ],
    }
)
```

正文类把上面的 `delivery` 改成 `body`，删掉 `parameter_mode`。连接地址和密钥仍放在 `instance_templates`。对方没有模板 ID 时，不要保留 `template_id` 字段。

字段类型支持 `string`、`password`、`number`、`boolean`、`select`、`textarea`。`secret=True` 的字段加密存储，读出时脱敏；提交空值或当前掩码会保留原密文。`send` 收到的是解密后的明文。`select` 用 `options`，每项包含 `value` 和 `label`。

## 3. 模板类和正文类

一个包只做一种投递。`delivery` 决定平台交给 `send` 的内容，也决定渠道配置页上有没有参数表。已经有渠道实例时，不能从一种换成另一种。

### 模板类

对方系统里已经有一条审核过的消息模板，平台不能把告警标题和正文直接送过去。短信、语音属于这类：正文在对方那里，每次发送只填变量，例如验证码、告警名称。渠道上配置的是对方的地址、密钥、模板 ID。

平台按接收人各调用一次。接收人是平台用户，传给包的是该用户资料里的电话原值。平台不校验是不是大陆 11 位号码。没有电话的人跳过并写明原因，其他人继续。包认为这个号码不能用时，返回 `rejected`，并在 `reason` 里说明。

`send` 收不到标题和正文。正式发送用的是调用方这次带来的 `template_params`，不用渠道上保存的测试值。

变量怎么排列由 `parameter_mode` 决定：

- `named`：变量有名字。调用方传对象，例如 `{"code": "123456", "minutes": "5"}`。配置页登记参数名，每行可以填一个测试值。调用方省略参数时，平台传 `{}`。
- `ordered`：变量按位置对应模板槽位。调用方传字符串数组，例如 `["123456", "5"]` 表示第 1、第 2 个槽位。配置页只显示槽位和测试值，不显示参数名。调用方省略参数时，平台传 `[]`。

调用方传来的对象或字符串数组会原样进入包。平台不检查键是否齐全、槽位是否够、值是否为空，这些由包拒绝并写明原因。既不是对象也不是字符串数组时，平台不调用包。变量最多登记 20 条。配置页上的测试值只给页面里的测试发送使用。

### 正文类

对方接受一段已经写好的标题和正文。Webhook、机器人和自建邮件网关属于这类：上游先把通知渲染成文字，包负责送出。配置页只有地址、密钥这类连接字段，没有参数表。

一次发送只调用一次 `send`，参数是解密后的配置、标题和正文。包收不到接收人，也收不到电话；收件地址写在渠道配置里，例如 Webhook 地址。调用方即使带了 `template_params`，包也看不到。标题或正文不是字符串，或者正文是空白时，平台不调用包。

页面上的测试发送会忽略请求里填写的标题和正文，改用一段固定英文，用来确认地址和密钥是否可用。

## 4. `send`

推荐类方法。平台按 `adapter_key` 取出对象；对象有 `send` 就调用它。

模板类：

```python
class AcmeSmsSendAdapter:
    @classmethod
    def send(cls, config, phone, template_params):
        # config: 解密后的实例字段，不含 parameters
        # phone: 用户资料中的电话原值
        # template_params: named 为 dict，ordered 为字符串 list
        return {"status": "accepted", "request_id": "req-1", "reason": ""}
```

正文类：

```python
class AcmeHookSendAdapter:
    @classmethod
    def send(cls, config, title, content):
        return {"status": "accepted", "request_id": "req-1", "reason": ""}
```

`status` 只能是 `accepted`、`rejected`、`unknown`。

- `accepted`：对方已受理。
- `rejected`：对方明确拒绝。`reason` 要让调用方能看懂，例如号码不可用、模板变量缺失。
- `unknown`：已经发出但不知道对方是否受理。抛异常时平台也记为 `unknown`。

`request_id` 保留前 128 个字符。`reason` 必须是字符串，保留前 500 个字符。返回值不是这个结构，或 `status` 不在上述三个值里，平台记为 `unknown`。

任一接收人未被受理，整次结果为失败。`retryable` 为 false。已受理或未知不会自动重发，手动重发会再次调用包。

## 5. 语言文件

两个文件都必须存在，根级 `description` 不能为空：

```yaml
name: Acme SMS
description: Acme SMS notification channel.

templates:
  connection:
    title: Connection
    groups:
      main:
        title: Main
        fields:
          endpoint:
            label: Endpoint
          api_secret:
            label: API Secret
          template_id:
            label: Template ID
```

文案覆盖顺序是请求语言、`en.yaml`、Manifest 原始文案。语言文件只覆盖展示文案，不声明字段类型、是否必填或默认值。中文文件名固定为 `zh-Hans.yaml`。`templates` 的键对应 `instance_templates` 的模板名、分组 `key` 和字段 `key`。help text 里出现 ASCII 冒号时加引号。

## 6. 上传、更换、卸载

上传字段是 `file` 或 `archive`，并带 `purpose=notification_channel`。试加载失败不入库。加载失败的包留在列表里，用途为空，不能用来新建渠道。

同 key 再次上传且不带确认时返回 409。确认更换后覆盖包体，已有渠道的配置保持不变。能读出旧包用途时，本次用途必须与它一致，同一个标识不能改成集成包。已有渠道实例时，`delivery` 必须保持不变；读不出旧包则拒绝更换，返回 409，`reason` 为 `delivery_changed`。没有渠道实例、且旧包读不出来时，按本次选择的用途校验后可以更换。

卸载时只要还有 `channel_type` 等于该标识的渠道，就返回 409。

渠道首页用包的 `name` 作为卡片名，表单渲染实例字段。模板类再显示参数表：具名模式显示参数名，顺序模式显示槽位，每行有测试值。正文类不显示参数表。

页面测试发送忽略请求里的标题和正文。正文类使用固定英文：标题是 `[{渠道名}] Test Message`，正文是 `This is a test message from channel '{渠道名}'. Receiver: {接收人}`。模板类用渠道上已保存的 `test_value` 组装 `template_params`；没有登记变量时，具名模式传空对象，顺序模式传空数组。正式发送不看这次测试的结果。

告警模板和流程通知的渠道类别仍是各自写死的列表，上传新包不会自动出现在那些列表里。

## 7. 安全和日志

包在服务进程内执行，能够接触解密后的渠道配置。上传前按受信任代码审查：

- 导入阶段不得产生副作用。
- 不在日志中记录密码、token、电话号码、完整请求 URL 或响应正文。
- 使用 `from apps.system_mgmt.providers.log import logger`。不要使用 `print`、`loguru` 或 `apps.core.logger`。
- 第三方错误转换成 `rejected` 或 `unknown`，带短原因和必要的 `request_id`。
- 不直接修改渠道、用户或发送结果；平台负责持久化和结果汇总。
- 数据库访问只能使用 Django ORM，禁止 raw SQL、`.raw()`、`RawSQL` 和 `cursor.execute`。

## 8. 常见错误

- 上传时用途选成集成，或未带用途。未带用途按集成包校验，渠道包会失败且不入库。
- `key` 使用了 `email`、`sms` 等内置渠道，或与内置 Provider 目录名相同。
- 声明了 `login_auth` 等第二条能力，或正文类写了 `parameter_mode`。
- `adapter_path` 没有指向 `adapters.send`。
- 把地址或密钥放在能力的 `connection_template`，页面不渲染，发送时也会丢掉。
- 把实例字段命名为 `parameters`。
- 缺少 `language/en.yaml` 或 `language/zh-Hans.yaml`，或 `description` 为空。
- 包内放入 `requirements.txt`、`.env`、页面文件或私钥。
- `send` 返回第三方原始响应，而不是 `status`、`request_id`、`reason`。
- 在具名模式里改写调用方传入的键，或在顺序模式里把数组渲染成带 `name` 的对象。键和槽位不符时直接 `rejected` 并写明原因。
- 在日志中输出密钥、电话或响应正文。

## 9. 代码依据

```text
server/apps/system_mgmt/services/notification_channel_pack.py
server/apps/system_mgmt/providers/loader.py
server/apps/system_mgmt/providers/schemas.py
server/apps/system_mgmt/providers/pack_i18n.py
server/apps/system_mgmt/viewset/channel_viewset.py
server/apps/system_mgmt/models/channel.py
server/apps/system_mgmt/tests/test_notification_channel_packs.py
```
