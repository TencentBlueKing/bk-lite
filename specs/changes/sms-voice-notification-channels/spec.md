# 短信与语音通知渠道

Status: implemented

## Problem Statement

重要告警需要通过短信或电话主动通知到人。平台已有统一通知渠道，业务模块选择渠道后发送，但渠道里没有短信和语音。客户已经在腾讯云或阿里云申请并审核了签名和模板，平台需要按这些已审核模板发送，而不是再做一套模板申请流程。

## Solution

系统管理新增短信、语音两种通知渠道。管理员可以配置多个实例，每个实例对接腾讯云或阿里云之一。凭证加密保存，页面只显示脱敏值。实例上填写客户已在云厂商审核通过的签名和模板标识，并把本次通知的标题、正文或固定文字对应到模板参数。告警和流程仍按现有方式选择渠道并提交标题、正文和平台用户。手机号从平台用户资料读取。没有可用手机号，或请求还没交给厂商就因配置失败时，该次发送停止并给出原因。请求已经交给厂商后，同一次投递不再自动重发。操作人员之后再次分派、执行流程或测试发送，会重新检查并调用厂商。

## User Stories

1. As a 系统管理员, I want to create and edit Tencent Cloud and Alibaba Cloud SMS and voice channel instances, so that approved signatures and templates can be used without the platform applying for them.
2. As a 系统管理员, I want stored secrets to appear only as a masked value, so that opening the configuration page does not reveal the cloud credential.
3. As a 系统管理员, I want a test send from a saved instance to use the current user's phone and the configured template, so that I can confirm a real SMS or voice call before business traffic uses the channel.
4. As a 告警值班人, I want an alert to reach me by SMS or voice through the existing notification channel, so that the alert module does not integrate with a cloud vendor itself.
5. As a 告警处理人, I want a recipient without a usable phone number to fail with a visible reason while other recipients continue, so that I know who was skipped.
6. As a 告警处理人, I want the same alert delivery to stop automatically once the request has been handed to the vendor or has failed before leaving the platform, so that a retry does not send another SMS or place another call.
7. As a 操作人员, I want a later manual assignment, workflow run, or test send to call the vendor again, so that fixing a phone number or repeating a notification still works.
8. As a 流程设计者, I want to choose an SMS or voice channel on the existing notification step, so that workflow messages use the same channel instances.

## Implementation Decisions

- 渠道类型新增 `sms` 与 `voice`，仍是系统管理的普通通知渠道。社区版和企业版使用同一套渠道，不放到企业版模块，也不做许可开关。
- 云厂商模板的申请、提交和审核不由平台执行，平台也不查询模板审核状态。实例只保存厂商、已审核签名、模板标识和参数对应。一个实例对应一套云模板。告警通知模板仍负责把告警字段渲染成标题和正文；短信和语音在那里是纯文本渠道。流程节点直接使用已有的标题和正文。
- `provider` 只有 `tencent` 和 `aliyun`。短信腾讯云保存 SecretId、SecretKey、SdkAppId、签名、模板 ID。短信阿里云保存 AccessKeyId、AccessKeySecret、签名、模板 Code。语音腾讯云保存 SecretId、SecretKey、语音 SdkAppId、模板 ID。语音阿里云保存 AccessKeyId、AccessKeySecret、模板 ID，被叫显号可空；为空时走厂商公共号码池。
- `parameters` 最多 20 项。每项来源是标题、正文或固定文字。固定文字最长 200 字。腾讯云按数组顺序生成位置参数，阿里云用参数名生成 JSON。换行在填入前改为空格。语音同一次通话的播放次数固定为 1。
- 腾讯云短信和语音的接口地域固定为 `ap-guangzhou`，阿里云使用国内短信和语音的默认域名。地域不出现在配置页。
- 密钥沿用渠道现有加密。读出时显示为掩码加末四位。提交掩码或空值时保留原密文。列表和详情都不返回可解密的密钥。
- 腾讯云使用仓库已有 SDK 的短信 `SendSms` 和语音 `SendTtsVoice`，重试器保持不重试。阿里云增加官方短信与语音 SDK 的 `SendSms` 和 `SingleCallByTts`，并关闭 SDK 自带重试。厂商签名和请求只留在系统管理的渠道适配器中。
- 发送仍走现有的渠道发送入口，每个接收人单独请求一次。手机号只接受大陆 11 位数字。腾讯云发送时加上 `+86`，阿里云使用裸号。
- 不新增发送账本，也不用历史结果拦截下一次调用。一次调用的返回包含整单是否全部受理、`retryable`、失败原因，以及每个接收人的状态、请求号、回执号和原因。接收人状态为已受理、厂商拒绝、结果未知或未发出。
- 未发出指请求没有交给厂商。渠道配置不完整、密钥解不开或参数对应不合法时，整次发送在调用前结束。某个接收人没有可用手机号，或号码不能用于该厂商时，只跳过这个人，其余接收人继续。只要有人未受理，整单结果为失败，原因写明是谁、为什么。
- 已发出指请求已经交给厂商。已受理是腾讯云短信号码状态 `Ok`、语音返回通话标识，或阿里云返回成功码。厂商拒绝是响应里有错误码或请求号。结果未知是请求已提交给 HTTP 客户端，但没有可判定的受理或拒绝；腾讯云 SDK 把连接失败和读超时都报成同一类网络错误，这类按结果未知处理。
- 未发出和已发出的 `retryable` 都是 false。告警现有投递据此停止自动重试。短信和语音适配器捕获厂商异常并返回该结构，不把异常抛回发送入口。流程通知原子在短信和语音返回不可重试时，把投递结果作为原子输出正常返回，避免该原子现有的一次失败重试再打厂商。人工再次分派、再次执行流程或再次测试发送是新的一次调用。
- 进程在请求交给厂商之后、结果写回告警投递之前被杀掉时，现有租约仍可能再投一次。这一版不另做记录来关闭这个窗口。
- 告警分派继续按渠道类型要求对应的通知内容。流程通知类型增加短信和语音，渠道、收件人、标题和正文的要求与邮件一致。对外通知目录把这两种类型纳入现有目录和发送接口，接收人仍是平台用户 ID。
- 测试发送使用已保存实例，向当前登录用户的手机号发送页面上的标题和正文。每次点击都是新的一次调用。未保存的掩码不能当作密钥送出。
- 成功日志只记录渠道、受理人数和未知人数。失败只在适配器边界记一条错误，带失败阶段和错误类型。日志不包含密钥、手机号、标题、正文和厂商响应体。

## Testing Decisions

测试观察渠道配置接口的保存与回读、渠道发送入口的返回、告警投递是否停止重试，以及流程通知原子是否把不可重试结果当作完成。厂商 HTTP 用假的适配器替换，不访问腾讯云或阿里云。

- 渠道配置：创建和再次读取后，密钥是掩码加末四位；用掩码或空值更新后，原密文仍能解密出发送所需的值。缺少模板标识、厂商不匹配或参数超过 20 项时拒绝保存。
- 渠道发送：没有手机号的接收人不触发厂商调用，并在返回原因中出现；其他接收人仍得到假适配器的受理结果。整单在存在未受理接收人时为失败，且 `retryable` 为 false。假适配器报告受理、厂商拒绝、网络错误时，分别对应已受理、厂商拒绝和结果未知，并带上请求号或回执号。
- 告警投递：发送结果 `retryable` 为 false 时，该次投递进入终态，不再安排下一次自动重试。
- 流程通知原子：短信或语音返回不可重试时，原子输出包含失败原因，并且不以抛出异常的方式完成。
- 对外目录：短信和语音实例出现在现有目录中，发送说明仍使用标题、正文和平台用户 ID。
- 先验是现有渠道序列化测试、对外通知渠道目录测试、告警通知投递测试和流程通知原子测试。

## Out of Scope

- 不建立、不提交、不查询云厂商模板审核。
- 不把告警字段直接映射为云模板参数。
- 不从一个实例挂多套云模板。
- 不接收送达回执，也不判断电话是否接听。
- 不配置接口地域，不发送非大陆 11 位号码。
- 不新增发送账本，不用历史发送结果拦截人工再次发送。
- 不关闭进程被杀掉后、结果尚未写回时现有租约再次投递的窗口。

## Further Notes

腾讯云短信和语音产品的接口地域只有广州。阿里云国内短信和语音使用固定服务域名。因此地域保持厂商默认值，不增加配置项。

渠道类型、加密脱敏和发送结果在 `server/apps/system_mgmt/services/cloud_notify/`。告警模板把短信和语音当作带标题的纯文本渠道。流程通知原子在短信或语音返回 `retryable: false` 时正常返回投递结果。对外目录沿用现有通知渠道接口。真实短信和语音需要客户自己的已审核模板，不在自动化测试里拨打。
