# 厂商游戏调试工具

独立网页服务，使用从 Panda 项目提取的 JWT 签发规则。只依赖 Python 3.10+ 标准库，启动时不连接数据库，也不需要启动 Panda 游戏服务。

## 启动

在 `/Users/allenflux/PycharmProjects/platgames-tools` 目录运行：

```sh
python3 vendor_debug_server.py
```

浏览器打开 <http://127.0.0.1:9100>。按 `Ctrl+C` 停止。

需要在内部测试网络提供服务时，可以指定监听地址和端口：

```sh
python3 vendor_debug_server.py --host 0.0.0.0 --port 9100
```

服务没有内置登录系统，默认仅监听本机。部署到团队环境时，应放在现有内部鉴权代理后，保留原始 Host；代理域名通过 `--allow-host tools.example.internal` 指定。不要向公网直接开放签发接口。

## 签名配置

签名密钥优先从 `PANDA_JWT_SECRET` 环境变量读取；也可用 `PANDA_JWT_SECRET_FILE` 指定密钥文件路径，默认读取项目根目录 `.panda_signing_key`。当前开发环境已从原 Panda 项目配置该本地文件，权限为 600，并由 `.gitignore` 排除。密钥仅在后端使用，不发送到浏览器。迁移到其他机器时配置对应测试环境的密钥即可，不依赖原 `platgames/server/share` 目录。

## Docker Compose 部署

项目中的 `docker-compose.yml` 使用 **9100:9100** 端口映射，包含健康检查和自动重启。

将整个独立项目放到部署机器，例如 `/opt/platgames-tools`，并单独带上隐藏文件 `.panda_signing_key`（上传工具不要漏掉点文件）。该文件不能进入镜像或版本库。

```sh
cd /opt/platgames-tools
chmod 600 .panda_signing_key
docker compose config --quiet
docker compose up -d --build
docker compose ps
docker compose logs -f --tail=100 platgames-tools
```

浏览器打开 `http://服务器IP:9100`。本机 Docker 部署则打开 <http://127.0.0.1:9100>。

更新代码后重新执行 `docker compose up -d --build`。停止服务：

```sh
docker compose down
```

如使用域名反向代理，在同目录 `.env` 中配置 `PANDA_TOOL_ALLOWED_HOSTS=tools.example.internal`（多个域名以逗号分隔），并保留 Host 请求头。直接用服务器 IP 访问无需配置此项。

密钥通过 [Docker Compose secrets](https://docs.docker.com/compose/how-tos/use-secrets/) 只读挂载到 `/run/secrets/panda_jwt_secret`，不会写入镜像。此部署完全不依赖游戏主体项目或它的数据库。

## 使用

1. 选择 **Panda**，打开“自然免费调试 Token”工具。
2. 从当前能正常进入的游戏页面复制完整 URL，粘贴到输入框。支持普通 URL、Markdown 链接和聊天中转义的链接。
3. 选择有效期。默认“长期”到 **9999-12-31 23:59:59 UTC**，也支持 30 天、90 天。
4. 点击“生成调试链接”，复制完整的新 URL 或单独的 token，也可以直接打开游戏。

每次生成都会验证原 token 签名和测试商户，并从本次输入保留账号、游戏 ID、登录时间和会话签名，再添加新的自然免费声明。输出 URL 仅替换 `token` 参数值，原有参数顺序、编码、游戏路径和 fragment 均保留。不会把其他参数中恰好相同的 token 文本一起替换。

普通旋转会选取自然触发免费局的结果包，购买免费玩法仍按原流程处理；没有自然免费结果包的游戏不适用。只有当前 Panda 服务允许的测试商户可以生成。

**长期调试有效期不等于登录会话永远有效。** 重新登录、会话轮换或缓存清理后，需要从最新有效游戏链接重新生成。此工具只进行本地签名校验和签发，不主动访问输入 URL、不查询钱包、不下注，也不能恢复已失效的登录会话。页面生成成功不代表线上会话已经验证。

URL 和 token 不保存在浏览器存储或服务访问日志中；结果只保留在当前页面内存，刷新即清除。结果接口使用 `Cache-Control: no-store`。

## 接口

- `GET /api/health`：本地服务状态。
- `GET /api/vendors`：已支持的厂商和工具。
- `POST /api/generate`：生成新 URL。请求头需要 `Content-Type: application/json` 和 `X-Debug-Tool: 1`。

```json
{
  "vendor": "panda",
  "tool": "natural-free-token",
  "url": "https://your-panda-test-host/smash-fury/index.html?token=YOUR_CURRENT_TOKEN",
  "validity": "long_term"
}
```

响应包含 `url`、`token`、`game`、`expires_at`、`expires_label`、`session_note` 和 `session_verified: false`。错误响应使用 `error` 字段。

## 文件与扩展

- `vendor_debug_server.py`：HTTP 服务、静态文件和接口。
- `vendor_debug_tokens.py`：厂商注册、URL 解析和生成逻辑。
- `make_panda_natural_free_token.py`：Panda token 签发器。
- `panda_jwt.py`：独立 HS256 签名实现及本地密钥配置。
- `vendor_debug_web/`：网页和图标。
- `test_vendor_debug_tools.py`：使用合成账号的生成逻辑和 HTTP 回归测试。

添加其他厂商时，在 `VENDORS` 添加工具说明，在 `TOOL_HANDLERS` 注册对应处理函数，并为该厂商实现独立的 token 校验和转换。不要让其他厂商复用 Panda 的签名规则。

## 验证

```sh
python3 -m unittest test_vendor_debug_tools test_panda_jwt -v
```

覆盖签名校验、会话字段保留、URL 精确替换、有效期、Markdown 输入、错误处理、接口访问限制和敏感信息日志检查。HTTP 测试使用随机本地端口，不访问线上游戏。

## 界面参考

布局和样式参考用户指定的[运维工具页面](http://216.176.194.30:18080/p0-batch-callback?lang=zh-CN)：白底、深灰按钮、浅灰细边框、步骤式表单和就地结果反馈。按本工具的实际操作简化步骤。
