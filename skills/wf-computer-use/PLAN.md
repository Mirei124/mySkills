# Wayfire Computer Use Skill 实现计划

日期：2026-11-14  
状态：计划完成，尚未实现或安装 skill。

## 1. 目标和范围

创建 `wayfire-computer-use` skill，让 Codex 通过截图观察、鼠标及键盘操作控制**当前已有的 Wayfire 桌面会话**。优先复用当前已打开、已登录的应用。

- 截图通过 XDG Desktop Portal；连续任务优先建立 ScreenCast + PipeWire 会话并按需取帧。
- 鼠标通过 `zwlr_virtual_pointer_manager_v1`；键盘通过 `zwp_virtual_keyboard_manager_v1`。
- 对模型暴露与公开 OpenAI computer use actions 尽量一致的操作名、JSON 参数和行为。
- 前台执行，与用户共享光标和键盘焦点。串行操作同一个桌面。
- 第一版不实现 nested/headless 会话、独立 seat、后台操作现有窗口或跨操作系统执行后端。
- 本次交付是计划文件；后续按本计划创建实现、skill 和验证记录。

## 2. 已知条件与待验证项

已检查本机：

- `XDG_SESSION_TYPE=wayland`、`XDG_CURRENT_DESKTOP=Wayfire`、`WAYLAND_DISPLAY=wayland-1`。
- 已安装 `/usr/bin/wlrctl` 和 `/usr/bin/wayland-info`；未发现 `wtype`、`ydotool`。
- `/usr/share/xdg-desktop-portal/portals/wlr.portal` 仅声明 Screenshot 与 ScreenCast，没有 RemoteDesktop。
- 当前 Codex 执行沙箱连接 Wayland socket 时返回 `Operation not permitted`。这不是 Wayfire 不支持协议的证据；当前尚未执行键鼠实测。

实施前通过只读 doctor 检查实际会话：协议 globals 及版本、output 名称/尺寸/缩放/旋转、portal 后端路由、D-Bus/PipeWire 连通性、依赖和 socket 访问。不硬编码上述环境值。

如果运行环境不允许访问 socket，返回明确错误；不能通过改 socket 权限、sudo 或换输入后端绕过限制。真实桌面测试须在允许访问该桌面的执行环境内进行。

## 3. 兼容策略

兼容基准是 OpenAI **公开 computer action schema**，不是尚未完整公开的 Codex Windows/macOS 桌面插件内部 schema。

模型层保持动作对象稳定；Wayfire 特有设置放在 session/config 中。将来取得真实桌面工具 schema 后增加薄适配器，不改底层输入和捕获实现。不得宣称与原生 Windows/macOS 插件逐字段兼容。

Skill 本身是指令与本地程序，不会自动给 Codex 注册原生 `computer` 工具：

1. 第一版通过 CLI 的 JSON 输入调用相同动作，并用图片查看工具呈现返回截图。
2. 若宿主需要原生工具调用，提供可选 MCP stdio 适配层，将同一 schema 暴露为 `computer`；此层返回图片 content block。
3. 不要求购买 API、创建 API key 或让 helper 自己调用模型。现有 Codex 负责推理循环。

## 4. 操作接口 v1

以下为拟定本地动作契约；实施时以锁定版本的官方 schema 核对按钮枚举、可选 `keys` 等细节，并保存来源版本。未知或不支持的字段/动作显式报错，不静默忽略。

| type | 参数 | 行为 |
|---|---|---|
| `screenshot` | 无 | 返回当前选定显示区域的新截图 |
| `move` | `x`, `y`, 可选 `keys` | 移到绝对坐标；可在动作期间保持修饰键 |
| `click` | `x`, `y`, `button`, 可选 `keys` | 定位后按下并松开按钮 |
| `double_click` | `x`, `y`, 可选 `keys` | 定位后左键双击 |
| `drag` | `path: [{x,y}, ...]`, 可选 `keys` | 从首点按下左键，依次移动，末点释放 |
| `scroll` | `x`, `y`, `scroll_x`, `scroll_y`, 可选 `keys` | 先定位，再发送横纵滚动 |
| `keypress` | `keys: string[]` | 执行组合键并释放；不是逐个输入字符 |
| `type` | `text` | 将 UTF-8 文本输入当前焦点控件 |
| `wait` | 无 | 按会话配置短暂等待，再观察状态 |

默认按钮先支持 `left/right/middle`；其他公开枚举逐项实现或报告 `UNSUPPORTED_BUTTON`。键名支持 `CTRL/SHIFT/ALT/SUPER/ENTER/TAB/ESC/BACKSPACE`、方向键、功能键及字符，提供显式别名表。不能未经配置把 macOS 的 `CMD` 等同于 Linux 的 CTRL。

示例动作保持跨后端形式：

```json
{"type":"click","x":640,"y":360,"button":"left"}
{"type":"keypress","keys":["CTRL","A"]}
{"type":"type","text":"你好，Wayfire"}
{"type":"scroll","x":800,"y":500,"scroll_x":0,"scroll_y":480}
{"type":"drag","path":[{"x":100,"y":100},{"x":140,"y":130},{"x":200,"y":180}]}
```

### 调用与返回封装

CLI 计划提供 `doctor`、`start`、`act`、`stop`。`act` 从 stdin/文件读取 JSON，不将文本拼接进 shell 命令。以下请求外壳是本项目扩展，不是 OpenAI 原生 schema：

```json
{
  "request_id":"r-002",
  "session_id":"s-001",
  "observation_id":"o-001",
  "action":{"type":"click","x":640,"y":360,"button":"left"}
}
```

成功返回包含 `request_id`、`status`、`observation_id`、截图路径、图片尺寸、output、布局版本和时间戳。错误返回结构化 `code/message/retryable` 及动作是否已执行；执行后截图失败不能伪装为动作未执行，更不能自动重放点击。

每个动作完成后取得新截图；`screenshot` 只捕获一次。模型必须实际接收图片，而不是只收到路径。CLI 由 skill 指导调用图片查看工具；MCP 返回 image content block。

管理接口包含 session 状态、capabilities 和紧急停止；`release_all` 是恢复机制，不混入标准动作集合。第一版不开放跨调用保持按键，也不开放任意 shell 执行接口。

## 5. 实现架构

```text
Codex + SKILL.md
        |
        | 标准动作 JSON
        v
CLI / 可选 MCP adapter
        |
        v
单会话常驻 helper：校验、串行队列、坐标、状态、错误处理
        |                                  |
        v                                  v
virtual pointer / virtual keyboard    Portal ScreenCast
        |                                  |
        v                                  v
Wayfire 当前 seat                     PipeWire → PNG
```

建议使用 Python 管理 CLI、JSON 和 portal/PipeWire 工作流，以 C + libwayland-client/libxkbcommon 实现小型常驻输入 helper；若现有 Python Wayland 绑定经验证完整支持所需协议，也可统一 Python。先完成依赖探测和最小验证再锁定方案，避免同时维护两套输入实现。

`wlrctl` 仅用于基础冒烟验证：本机版本的 `pointer move` 是相对移动，不能冒充标准绝对坐标接口。正式实现直接调用协议，维持虚拟设备和 keymap。

## 6. 截图与坐标契约

- 第一版一个 session 选择一个明确 output。使用截图左上角为 `(0,0)`，坐标单位为交给模型的图片像素。
- 优先在 start 时创建 ScreenCast session，用户通过 portal 选择来源，PipeWire 持续供帧；每次观察获取动作之后的新帧，避免返回缓存旧画面。
- Screenshot portal 可作为单次截图备选，但必须确认实际捕获区域和坐标映射，不能假设总是单屏；不采用可能反复弹出选择器的循环作为默认实现。
- 记录原始帧尺寸、裁剪、缩放、旋转、output 身份及逻辑几何，建立完整转换。若无法可靠识别 stream 对应 output，要求明确选择或返回映射错误，不猜测。
- virtual-pointer v2 可提出 output 绑定建议；验证 compositor 的实际映射。v1 或绑定不生效时仅在已验证全局布局映射后降级。
- 支持绝对定位；处理屏幕缩放、旋转和非零 output 原点。边界外坐标拒绝，不静默 clamp。
- 分辨率变化、显示器断开、捕获会话结束使旧 observation 失效；重新捕获并建立映射后才能继续。
- 第一版不支持任意窗口裁剪截图直接驱动点击；后续加入时必须增加窗口到 output 的几何映射。

## 7. 输入行为

- 指针：`motion_absolute`、`button`、`axis` 与 `frame`；拖拽保持同一个虚拟设备，完整发送 press/motion/release。
- 滚动：对外维持 `scroll_x/scroll_y` 的方向和像素式语义，后端明确换算为 Wayland axis 单位；记录校准结果，不承诺所有应用实际滚动像素完全一致。
- 键盘：上传有效 XKB keymap，发送 keycode 和 modifiers；区分字符输入、快捷键和键位，不靠英文键盘布局猜测。
- Unicode：优先采用受控 keymap/Unicode keysym 路径，验证中文及常用符号。IME、emoji 和不同 toolkit 的兼容性单独测试，不能仅凭协议存在宣称全部支持。
- 剪贴板粘贴仅作为显式启用的文本策略，记录对剪贴板的影响与可恢复范围；不默认覆盖用户剪贴板，也不使用逐字输入失败后的静默粘贴降级。
- 组合键、拖拽均在 `finally` 路径释放；动作超时、取消、断连时清理输入状态。异常退出由设备销毁与会话恢复共同验证。
- 虚拟输入共享当前桌面焦点。虚拟设备不是独立 seat，不声称不抢鼠标。

## 8. 运行控制与故障处理

- 每个 Wayland display 同时只允许一个控制任务；请求串行处理。
- helper 使用当前用户私有 runtime socket，不监听网络端口；设置空闲退出并在正常 stop 时关闭 portal session。
- 会话开始和结束时使用 `notify-send` 发送桌面通知，提醒用户避免与 agent 同时操作。通知属于 session 生命周期，不在每次点击或截图时重复发送。
  - 开始：取得会话控制锁并完成准备后、首次键鼠输入前发送“Computer Use 正在使用桌面”，正文为“正在控制鼠标和键盘，请暂时不要操作；结束后会再次通知。”
  - 结束：释放按键、按钮及控制锁后发送“Computer Use 已结束”，正文为“已停止控制鼠标和键盘，可以继续操作桌面。”
  - 正常 stop、取消、空闲超时及可捕获异常统一走清理流程，每个已开始会话只发送一次结束通知；异常结束注明“任务中断，桌面控制已停止”。若清理结果不确定，不发送保证已释放控制的文案，改为提示检查会话状态。
  - helper 由监督进程管理，以便 helper 崩溃时清理并通知；整个进程组被 SIGKILL、会话总线断开或系统关机时无法保证通知送达，在文档中明确这一边界。
  - doctor 检查 `notify-send` 是否存在及通知服务可用性。通过参数数组调用，不拼接 shell；通知不包含输入文本或截图内容。
  - 开始通知调用失败时不进入键鼠控制，返回 `NOTIFICATION_FAILED`；结束通知失败时仍必须完成清理，并在调用结果中报告。`notify-send` 成功只代表通知请求提交，不代表用户已看到或确认；勿扰模式可能隐藏通知，通知不能替代会话互斥。
- 配置动作超时、拖拽最大路径长度、文本长度上限和等待上限；返回明确错误。
- 同一 session 内按 `request_id` 去重。连接中断导致结果未知时先观察，不自动重试有副作用的动作。
- 提供可从独立终端执行的 stop；按能力验证可选全局停止快捷键，未实现前不写成保证。
- 不因每次普通点击另加确认；沿用用户当前任务授权和宿主已有权限规则。Skill 不能赋予 helper 沙箱外权限。
- 默认不记录输入正文或长期保存截图；输出临时文件有明确清理策略。
- `doctor` 区分 `WAYLAND_ACCESS_DENIED`、`PROTOCOL_UNAVAILABLE`、`PORTAL_UNAVAILABLE`、`CAPTURE_CANCELLED`、`STALE_OBSERVATION`、`LAYOUT_CHANGED`、`UNSUPPORTED_KEY` 等错误。

## 9. Skill 交付结构

在当前可写目录开发，计划结构如下；仅在需要时创建实际资源：

```text
wf-computer-use/
  PLAN.md
  wayfire-computer-use/
    SKILL.md
    agents/openai.yaml
    scripts/                 # CLI、session/capture 编排
    native/                  # 虚拟键鼠 helper 源码和构建定义
    references/
      actions.md             # 参数、键名、结果和兼容性
      troubleshooting.md     # doctor 错误及有证据的修复步骤
  tests/                     # schema、映射和受控端到端验证
```

SKILL.md 保持简洁：触发条件、doctor/start/观察/动作/验证/stop 工作流、开始与结束通知、图片展示要求、共享焦点限制及参考链接。触发范围是 Wayfire 原生桌面交互，不接管普通文件编辑或纯浏览器自动化。

默认允许自动发现；不凭空设为 explicit-only。安装到用户 skill 目录是后续部署步骤，先完成可审查的工作区版本。当前 `~/.agents`/`~/.codex` 等路径的写入权限必须单独遵守。

## 10. 分阶段实施与验收

### P0：环境与接口冻结

- [ ] doctor 输出实际协议版本、桌面访问、portal/PipeWire 状态和 output 信息。
- [ ] 锁定官方 action schema 来源/版本，生成本地校验定义和兼容映射表。
- [ ] 验证所选技术栈能捕获一帧并建立持久虚拟设备；明确当前环境权限阻塞。

验收：能力报告区分“源码支持”“本机暴露”“实测可用”，不混淆。

### P1：最小闭环

- [ ] 单 output 捕获、绝对移动、左右键、ASCII 输入和组合键。
- [ ] JSON CLI、session 生命周期、串行化及结构化错误。
- [ ] 接入 `notify-send` 开始/结束通知；验证通知先于首次输入、结束通知晚于控制释放，且每个会话各发送一次。
- [ ] 每次操作后截图，并实际呈现给模型。

验收：在专用测试窗口中完成“截图 → 点击输入框 → 输入 → 截图确认”，不向其他应用发送字符。

### P2：完整动作与可靠性

- [ ] 双击、拖拽、横纵滚动、修饰键、Unicode、wait。
- [ ] 坐标缩放/旋转/多屏映射、布局变化检测、过期截图处理。
- [ ] 取消、超时、重复请求、断连与清理；验证没有卡住的按键/按钮。
- [ ] 验证取消、超时及 helper 崩溃后的结束通知，以及开始通知失败时不执行输入、结束通知失败不阻塞清理。

验收：九种标准动作逐项通过或明确记录不支持项，不能以空操作充当成功。

### P3：Skill 包装与使用验证

- [ ] 创建 SKILL.md、UI metadata、参考文档；运行 skill-creator 的 quick_validate。
- [ ] 用真实任务验证 skill 能选择正确工具、展示截图、依据结果继续或停止。
- [ ] 记录依赖、复现步骤、已通过项目及尚未解决的限制。
- [ ] 如果需要原生 tool call，增加 MCP stdio adapter，复用同一 action dispatcher。

验收：用户在工作区可按文档调用，模型无需重新编写桌面操作脚本；打包版本完成后再部署。

## 11. 测试矩阵

自动测试重点放在易损坏的行为：坐标转换、旋转/缩放/负 output 原点、键名与 modifiers、事件顺序、请求去重和失败清理。使用事件记录的 fake backend 验证语义，但不将其当作真实桌面通过证据。

真实桌面使用单独测试窗口，覆盖：

1. 点击多个已知坐标目标；双击、框选拖拽、横纵滚动。
2. ASCII/中文/符号输入、CTRL+A、SHIFT+方向键及释放后的正常输入。
3. 缩放和多屏配置；布局改变后拒绝旧坐标。
4. portal 取消、PipeWire 结束、helper 中断、动作成功但截图失败。
5. 三个 skill 场景：编辑测试文本、拖拽测试对象、根据错误停止并报告。
6. 通知生命周期：正常开始/结束、重复 stop、取消、超时、helper 崩溃、缺少 notify-send、通知服务失败；检查通知次数、顺序、文案与实际控制状态一致。真实桌面验证通知显示，自动测试验证调用顺序与失败分支。

桌面操作测试串行运行，不让多个评估 agent 同时控制同一 seat。若当前沙箱限制仍在，完成离线测试并标记真实桌面验证受阻，不以 mock 替代验收。

## 12. 参考资料

- [OpenAI computer use action handlers](https://developers.openai.com/api/docs/guides/tools-computer-use-integration)：公开动作集合与后端转换方式。
- [OpenAI ComputerDriver contract](https://developers.openai.com/api/docs/guides/tools-computer-use-sdk-drivers)：方法参数和截图返回契约。
- [OpenAI Python action types](https://github.com/openai/openai-python/blob/main/src/openai/types/responses/response_computer_tool_call.py)：实施时锁定版本的 schema 基准。
- [Wayfire core API](https://github.com/WayfireWM/wayfire/blob/master/src/api/wayfire/core.hpp)：虚拟输入管理器与 single-seat 限制。
- [Virtual pointer protocol](https://github.com/swaywm/wlr-protocols/blob/master/unstable/wlr-virtual-pointer-unstable-v1.xml)：绝对坐标、按钮、滚动及 output 绑定。
- [xdg-desktop-portal-wlr](https://github.com/emersion/xdg-desktop-portal-wlr)：Screenshot/ScreenCast 支持范围。
- [RemoteDesktop portal](https://flatpak.github.io/xdg-desktop-portal/docs/doc-org.freedesktop.portal.RemoteDesktop.html)：未来可选 libei 后端，不作为当前前提。
- [wayvnc](https://github.com/any1/wayvnc)、[wtype](https://github.com/atx/wtype)：虚拟设备与文字输入的实现参考；复用代码前核对许可证。
