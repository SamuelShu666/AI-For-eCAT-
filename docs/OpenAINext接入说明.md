# OpenAINext 本机接入

服务地址为 https://api.openai-next.com/v1，模型按用户指定为 claude-opus-5-5。

2026 年 10 月 18 日实测状态：项目端已经通过 Anthropic 原生 Messages 接口接通，后端调用模块返回 OK。模型及协议保存在当前 Windows 用户环境中：OPENAINEXT_MODEL=claude-opus-5-5，OPENAINEXT_PROTOCOL=anthropic。

Codex 桌面端尚未切换。该模型的 Responses 接口虽然返回 HTTP 成功和 completed 状态，但实测输出为空，没有所请求的 function_call；普通文本请求也未产生文本。使用字符串和结构化消息内容分别检查后，工具调用仍未通过。当前 Codex 原配置保持不变。

随后已按平台指南再次测试：在隔离 CODEX_HOME 内使用 requires_openai_auth=true 和仅包含 OPENAI_API_KEY 的 auth.json，运行本机 codex-cli 0.163.0-alpha.10.2。客户端识别到 openai-next 服务与 claude-opus-5-5 模型，但最终消息仍为空；进程退出码为 0 不代表成功收到回复。测试使用空目录和固定 OK 提示，不包含项目文件。正式桌面 config.toml 和 auth.json 的文件哈希均保持不变。

### 恢复到本次重试前的桌面状态

已创建独立备份，位置保存在 .local/desktop-rollback.json，备份内容是桌面 config.toml 与 auth.json，并附 SHA-256 校验清单。恢复路径经过校验，备份含登录信息，应留在本机。

运行工作目录中的“恢复Codex原配置.ps1”，会先保存恢复前的两份文件，再恢复快照并校验。恢复逻辑已使用临时配置与虚构认证文件测试，能逐字节恢复原内容；没有为测试覆盖正式登录文件。

恢复范围为桌面配置及登录文件，不改聊天历史、项目资料或当前已接通的项目端 Claude 配置。当前桌面文件尚未切换，已经处于本次重试前状态，无需立即运行恢复。以后若实际切换，再用此脚本恢复并重启 Codex。

完成桌面接入的前提是平台修复该模型的 POST /v1/responses 路由，使其能返回非空文本、标准函数调用和工具结果后的最终回复，并提供匹配的 Codex 模型目录元数据。仅支持 Anthropic Messages 或出现在模型列表中，不足以证明 Codex 兼容性。

scripts/接入OpenAINext.ps1 提供本机密码输入框；当前密钥已保存，无需重复填写。接入脚本会检查标准工具调用及回传，不发送项目文件。测试会有少量 Token 费用，不代表开启批量实验或自动评测。

密钥已存入当前 Windows 用户的 OPENAINEXT_API_KEY 环境变量，未写入项目源码。只有 Responses 工具循环测试通过，脚本才会备份并合并 Codex 配置，不修改 auth.json。当前测试未通过，尚未进行此桌面配置步骤，也无需为此次接入重启 Codex。

项目端通过 backend/model_gateway.py 的 ModelGateway 调用。它从环境变量读取密钥；Windows 下也可以直接读取当前用户环境配置，因此当前进程尚未重启时仍可调用。

```python
from backend.model_gateway import ModelGateway
reply = ModelGateway().respond("请用一句话描述实验反馈的作用。", max_output_tokens=512)
print(reply.text)
print(reply.usage)
```

连接状态写入 .local/connection-status.json，只含状态、用量及配置状态，不含密钥。项目没有前端、Agent 工作流或批量费用控制器；本次只提供可复用的后端接入模块。

恢复原桌面配置时，将状态文件记录的备份 config.toml 复制回用户 .codex/config.toml，再重启 Codex。若项目仍需调用 OpenAINext，可以保留用户环境变量。任何真实密钥都不应写入 .env.example 或提交到版本库。

### WorkBuddy 客户端接入（2026 年 10 月 18 日完成，可复原）

已按 https://credits.openai-next.com/guide/cli/workbuddy 完成 WorkBuddy 客户端接入：

- 配置文件：`C:\Users\Stellan\.workbuddy\models.json`（应用监听此文件，改动即时生效，无需重启）。
- 模型：claude-opus-5-5，协议 anthropic-messages，Base URL `https://api.openai-next.com`（不含 /v1），密钥引用环境变量 `${OPENAINEXT_API_KEY}`，明文不落盘。
- 实测：当日用该密钥分别通过 /v1/messages 与 /v1/chat/completions 均返回正常文本；应用日志显示配置加载成功、无无效条目。在对话框模型列表选择「Claude Opus 5.5 (OpenAINext)」即可使用。
- 协议选择依据：此前 Responses 接口输出为空，故未采用 openai-responses。

**复原方法**：原 models.json 内容为 `[]`，备份在 `C:\Users\Stellan\.workbuddy\models.json.bak-20261018`（SHA-256 `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945`，两文件哈希一致）。恢复任选其一：把备份复制回 `models.json`；或在 设置 → 模型 中删除该自定义模型；或直接删除 models.json。文件改动会被应用自动同步。此操作不涉及 auth.json、Codex 配置及项目端 backend/model_gateway.py。

来源：

- https://credits.openai-next.com/guide/cli/workbuddy
- https://credits.openai-next.com/guide/cli/codex-desktop
- https://credits.openai-next.com/guide/quickstart
- https://learn.chatgpt.com/docs/enterprise/connect-to-a-gateway
- https://learn.chatgpt.com/docs/auth
