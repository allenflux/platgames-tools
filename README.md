# 厂商游戏调试工具

独立的开发辅助网页项目，当前提供 Panda 自然免费调试 Token 生成。Python 3.10+ 标准库实现，无第三方依赖。可部署在另一台机器，不需要原游戏项目、数据库、Redis 或游戏服务进程。

## Docker Compose 部署

完整上传本项目（包含整个 `config/` 目录及其中的 `private/panda_signing.key`）到服务器，例如 `/opt/platgames-tools`，然后执行：

```sh
cd /opt/platgames-tools
docker compose up -d --build --force-recreate
docker compose ps
docker compose logs -f --tail=100 platgames-tools
```

浏览器访问 `http://服务器IP或域名:9100`，例如 <http://allenflux.tech:9100>。端口映射为主机 **9100** 到容器 **9100**。任意访问域名均可使用，无需配置域名列表。

本机预览可运行：

```sh
TOOLS_BIND_IP=127.0.0.1 docker compose up -d --build
```

然后打开 <http://127.0.0.1:9100>。停止服务：

```sh
docker compose down
```

更新代码或厂商配置后重新构建镜像：

```sh
docker compose up -d --build --force-recreate
```

本版本已取消 Host 域名校验、Origin 来源校验、专用请求头要求、页面 CSP/嵌入限制及容器只读/权限限制；支持跨域请求和 OPTIONS 预检。JSON 与游戏链接格式校验仍用于返回可用的结果。

## 厂商配置

Panda 所需的配置已经复制到本项目 **`config/vendors/panda.json`**：

- `signing_key_file`：项目内签名密钥文件路径，默认 `config/private/panda_signing.key`。
- `test_app_keys`：游戏服务支持自然免费调试的测试商户标识。
- `natural_free_mode`、`game_scope`：免费调试模式和游戏范围。
- `default_days`、`max_days`、`no_expiry_timestamp`：Token 有效期设置。
- `games`：51 个 Panda 游戏的编号、英文路径名和中文名称。

普通配置由 `vendor_config.py` 读取并复制到镜像。签名密钥已经单独复制到本项目 `config/private/panda_signing.key`，由 Compose 自动挂载，且不会进入 Git 或镜像。部署时复制整个项目目录即可；如果用 Git 拉取代码，需要另外传输 `config/private/`。**不再需要根目录 `.panda_signing_key`、Docker secrets 或任何原游戏项目目录。** 网页静态接口不会返回这些配置文件。

如果目标游戏环境改了签名密钥或测试商户，请更新对应配置；修改商户或模式配置后重新构建，修改密钥文件后重新创建容器。仍兼容 `PANDA_JWT_SECRET` 环境变量或 `PANDA_JWT_SECRET_FILE` 文件路径覆盖签名密钥；普通部署无需设置。

## 本地 Python 启动

```sh
cd /Users/allenflux/PycharmProjects/platgames-tools
python3 vendor_debug_server.py --host 0.0.0.0 --port 9100
```

只在本机使用可省略参数，默认地址 <http://127.0.0.1:9100>。按 `Ctrl+C` 停止。

## 使用

1. 选择 **Panda**，打开自然免费调试 Token 工具。
2. 粘贴当前能正常进入游戏的完整 URL，支持普通链接或 Markdown 链接。
3. 选择有效期，默认至 9999 年，也支持 30 天或 90 天。
4. 生成后复制完整新链接、复制 Token，或直接打开游戏。

工具验证输入 Token 的签名，保留本次输入的账号、游戏 ID、登录时间和会话签名，仅更新调试声明和到期时间。URL 只替换 `token` 参数值，保留其他参数、编码、顺序和 fragment。

测试商户和模式要求来自 Panda 游戏服务本身。普通旋转选取自然触发免费局的结果包，购买免费仍走原流程；游戏必须具备自然免费结果包。

长期调试有效期不会延长原登录会话。重新登录或会话被清理后，需要用最新游戏链接重新生成。工具不访问输入链接、不查询钱包、不下注，也不能恢复已失效的登录会话。生成成功表示本地签发完成，不代表线上会话已验证。

链接和 Token 不写入浏览器本地存储或服务访问日志。接口使用 `Cache-Control: no-store`，避免重复使用缓存的生成结果。

## 接口

- `GET /api/health`：服务状态。
- `GET /api/vendors`：支持的厂商和工具。
- `POST /api/generate`：生成新 URL，仅需 `Content-Type: application/json`。
- `OPTIONS /api/generate`：跨域预检。

```json
{
  "vendor": "panda",
  "tool": "natural-free-token",
  "url": "https://your-panda-test-host/smash-fury/index.html?token=YOUR_CURRENT_TOKEN",
  "validity": "long_term"
}
```

响应包含 `url`、`token`、`game`、`game_name`、`expires_at`、`expires_label`、`session_note` 和 `session_verified: false`。错误信息在 `error` 字段。

## 验证与扩展

```sh
python3 -m unittest discover -v
```

测试使用合成账号和临时本地端口，覆盖配置加载、Panda 签名兼容、会话字段保留、URL 精确替换、有效期、任意域名访问、跨域请求及错误处理。

新增其他厂商时，复制其所需配置到 `config/vendors/`，在 `vendor_debug_tokens.py` 的 `VENDORS` 和 `TOOL_HANDLERS` 中注册独立的生成逻辑。

## 页面与图标

布局参考用户指定的[运维工具页面](http://216.176.194.30:18080/p0-batch-callback?lang=zh-CN)：白底、灰色边框、深灰按钮、步骤式表单和就地结果反馈。

页面资源位于 `vendor_debug_web/`。图标为内置 image_gen 生成的 `icon.png`，提示词保存在 `ICON_PROMPT.md`。
