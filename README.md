# AI 订阅用量监控器 · Chrome 扩展版

当前版本使用你日常 Chrome 已有的登录状态，读取 Codex / Work（Plus）和 Claude（Pro）的官方用量页，发送到本机 Windows 悬浮窗。无需在独立浏览器再次登录。

## 首次连接

1. 下载或构建程序后，双击 `dist/AIUsageMonitor/AIUsageMonitor.exe`。右上角菜单选择“连接 Chrome 扩展 / 复制配对码”。
2. 在你已登录两个平台的 Chrome 打开 `chrome://extensions`，开启右上角“开发者模式”。
3. 点击“加载已解压的扩展程序”，选择程序目录内的 `ChromeExtension` 文件夹。可在悬浮窗连接窗口复制目录路径。
4. 点击 Chrome 工具栏的拼图图标，打开“AI 订阅用量助手”。从悬浮窗复制配对码，粘贴到扩展，点击“保存配对码并连接”。
5. 在扩展中分别点击“打开 Codex / Work 监控页”和“打开 Claude 监控页”。它会创建两个独立的固定标签页，复用该 Chrome 配置现有登录状态。
6. 首次读数请与官方页面核对。悬浮窗显示的是“剩余”；Claude 网页的“已用”会换算为剩余。

安装扩展是一次性步骤，不需要每次加载。不要删除或移动已加载的扩展文件夹；更新后在扩展管理页点击重新加载。

## 日常使用

- Chrome、扩展创建的两个监控标签页和悬浮窗需保持运行。标签页可以放在后台，Chrome 可以最小化。
- 扩展约每 60 秒重载自己的监控页。Chrome 休眠/节能可能延后刷新，并非硬实时。
- 不会刷新你的原有标签页。关闭监控页或把它导航到其他页面会停止对应平台读取；在扩展中重新打开即可。
- 扩展中的“立即刷新”立即触发；悬浮窗刷新按钮会发送请求，扩展通常在下次 30 秒检查时执行。
- 扩展支持暂停。超过 150 秒未成功获取、页面无法识别或发生错误时，悬浮窗保留旧值并灰显。
- 到达重置时间不会自行假定额度补满。OpenAI 页面提供精确时间时显示倒计时；Claude 只有相对/星期文案时原样显示，不猜日期。
- 鼠标移入展开，空白处可拖动，菜单可固定展开、隐藏、退出及设置开机启动。开机启动默认关闭。

## 权限和数据

扩展会申请 ChatGPT、Claude 两站的网页访问权限及本机地址权限。Chrome 对站点权限的提示可能覆盖整个站点，但代码仅在用量路径/设置弹窗中、且仅在扩展自建的监控标签页读取标注清晰的额度仪表。Claude 当前地址会从 `/settings/usage` 跳转到 `/new#settings/usage`。

扩展没有 cookies、debugger、webRequest 或浏览历史权限。不读取密码、Cookie、令牌或对话内容，不点击充值、购买、额度重置等操作。

传输仅包含平台、额度周期、使用率、重置时间/文案和读取时间。仅发送到 `http://127.0.0.1:18765`，不会上传第三方。悬浮窗只监听本机回环地址，使用随机配对码校验请求，拒绝普通网页来源及旧数据。

配对码只用于连接本机悬浮窗，不是 Google/OpenAI/Claude 凭据；仍请不要分享。它保存在程序 `runtime/extension-bridge.json` 和 Chrome 扩展本地存储中。`runtime/` 限制为当前 Windows 用户和 SYSTEM，管理员仍可接管。

如果曾使用旧版独立浏览器，原有 `runtime/profiles/` 不参与新版运行。升级时请保留 `runtime/`，其中还有扩展配对码和最近用量缓存。

## 验证边界

已针对当前实测的中文 OpenAI 额度卡片和英文 Claude 额度仪表做 DOM 解析测试，并测试来源限制、本机配对校验、旧数据、重复窗口、标签页归属和导航保护。网页结构或语言变化可能导致“页面未识别”，不会用其他百分比填充。

最终真实账号连通性要在扩展由用户加载并配对后核验；测试数据不代表真实额度。当前界面仅识别实际核验过的五小时与每周总额度，其他模型专项额度不会擅自归类。

## 开发

需要 Windows 11、Python 3.12、Node.js 和 Chrome。先创建虚拟环境并安装依赖；测试通过后构建 EXE，再把扩展复制到发布目录。

```powershell
py -3.12 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
npm install --prefix build/test-tools --no-audit --no-fund jsdom@30.1.3
.venv/Scripts/python.exe -m unittest -q
node test_extension.js
node test_extension_background.js
.venv/Scripts/python.exe -m PyInstaller --noconfirm AIUsageMonitor.spec
Copy-Item -LiteralPath chrome-extension -Destination dist/AIUsageMonitor/ChromeExtension -Recurse
```

HTTP 桥接测试只访问本机回环地址。

使用提供的 `.spec` 构建，它排除了构建机 PATH 中与 Qt 不兼容的 ICU DLL，运行时使用 Windows 11 自带 ICU。不要直接用 PyInstaller 覆盖含用户登录数据的旧发布目录。将源码 `chrome-extension/` 复制为发布目录的 `ChromeExtension/`。

`--demo` 使用明确标注的示意数据，不连接扩展、不写用量缓存。`--screenshot PATH` 导出窗口图后退出。`--show-extension-setup` 启动时打开连接说明。旧版 Playwright 适配器未收入此仓库，发布包也不携带浏览器控制驱动。
