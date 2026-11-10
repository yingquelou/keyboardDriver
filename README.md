# 1EA7:0066 无线键盘驱动（libusb/WinUSB 接管）

用 Python + libusb（pyusb）直接读取这把 2.4G 无线键盘的 HID 报告，**扮演通用 HID 键盘类驱动**：
按 HID Usage Tables 把 usage 换成虚拟键码、按系统设置补发自动重复、把锁定键按原生方式转发，
并把系统锁定状态按描述符声明的 1 字节 Output 报告回写设备。

切层（字母区 ↔ 小键盘）由**固件**完成：它按主机回写的 Num Lock 灯位决定上报
`0x0D`（J）还是 `0x59`（小键盘 1）。主机侧没有任何"层表"或层状态机，
与 Windows 原生 HID 键盘类的分工完全一致。

## 用途与目标环境

| 项目 | 说明 |
|---|---|
| 设备 | USB `1EA7:0066`（复合设备：接口 0 = boot 键盘，接口 1 = 消费类/鼠标） |
| 目标系统 | Windows 11（**本轮全部实测**）；Windows 7 为历史目标，本轮未重新实测 |
| 运行前提 | 设备接口已绑定 WinUSB（见下节），程序独占读取该接口 |

Win7 与 Win11 差异：旧实现写死“接口 1”且只取第一个枚举结果，在 Win7 上会拿错设备节点，
媒体键不工作；现在改为**按报告描述符角色 + 端点探测读**识别，不再依赖接口号和枚举顺序。
Win7 上是否同样可用**未验证**，仅保留了结构上的兼容。

## 依赖与安装

- Python 3（本轮使用 MSYS2 clang64 Python 3.14，虚拟环境在 `.venv`）
- `pyusb`（本机 1.3.1；Win7 + Python 3.8 上 pip 会选 1.2.1，因为 1.3.x 要求 Python ≥ 3.9）
- `libusb-1.0.dll`（32/64 位需与 Python 一致）。来源按需选择：系统或 PATH 已有、
  `pip install "libusb-package<1.0.27"`（包内自带 DLL），或放到项目 `libusb\x86|x64\`。
  **Zadig 只负责内核驱动绑定，不提供这个 DLL**；详见 [BUILD-WIN7.md](docs/BUILD-WIN7.md) 第 3 节
- `pywin32` **可选**：缺省时自动退回 `win32_compat.py`（ctypes 版 `keybd_event` + VK 常量），
  行为等价，无需强装

项目内安装示例（PowerShell）：

```powershell
python -m venv .venv
.\.venv\bin\python.exe -m pip install pyusb
```

**Windows 7 目标机**没有安装脚本，全部按手工步骤执行：安装 Python 3.8.10、建虚拟环境、
装依赖、Zadig 绑定（整设备或按接口两种形态）、启动、`schtasks` 注册登录自启与卸载恢复，
逐条命令见 [INSTALL-WIN7.md](docs/INSTALL-WIN7.md)。

### 驱动绑定（Zadig）与恢复

1. 运行 `zadig-2.9.exe`，勾选 Options → List All Devices，选中 `1EA7:0066` 的 **Interface 0 与 Interface 1**，
   目标驱动选 WinUSB，逐个 Replace Driver。
   也可对整个 `1EA7:0066` 父设备（不带 `Interface` 后缀）执行一次 Replace Driver；两种形态程序都能用，
   判读与操作细节见 [INSTALL-WIN7.md](docs/INSTALL-WIN7.md) 3.5。
2. 绑定后系统不再提供原生键盘/媒体键行为，一切按键由本程序注入。

**恢复系统原生驱动**（任选其一）：

- 设备管理器 → 找到该键盘 → 右键“卸载设备”并勾选“删除驱动程序软件” → 拔插接收器；
- 或以管理员运行：`pnputil /delete-driver oemXX.inf /uninstall /force`（旧版 `pnputil` 不支持
  `/uninstall`、`/force` 时去掉对应参数），然后拔插接收器
  （`oemXX.inf` 用 `pnputil /enum-drivers` 查 Provider 为 libwdi 的项）。

## 运行

```powershell
.\.venv\bin\python.exe src\keyboard.py             # 正常模式（指示灯回写默认开启）
.\.venv\bin\python.exe src\keyboard.py --no-led    # 排障用：关闭灯位回写（Num Lock 切层会失效）
.\.venv\bin\python.exe tools\calibrate.py          # 校准：打印每个键的 HID 码与映射结果
```

目录划分：`src\` 驱动源码（键盘主程序与模块）、`tools\` 诊断脚本、`docs\` 说明文档
（`INSTALL-WIN7.md` 手工安装/卸载，`BUILD-WIN7.md` 手工打包）；`README.md` 为入口。
所有脚本都按自身文件位置解析路径，可从任意工作目录启动。

- **不需要管理员权限**：WinUSB 安装时已写入允许普通用户访问的权限，实测可 claim 并读取。
- 断线后每 5 秒自动重连；退出（Ctrl+C）前会抬起所有已注入的按键，避免残留。

### 打包为 exe（可选，需在目标机构建）

项目**不提供打包脚本**，改为手工执行 PyInstaller。目标机装好 Python 3.8.10 与
`"pyinstaller<6"` 后，在项目根执行（onedir；DLL 按 Python 位数选 `libusb\x64` 或 `x86`）：

```bat
python -m PyInstaller --noconfirm --clean --name KeyboardDriver --paths src ^
  --hidden-import usb.backend.libusb1 --hidden-import app_paths ^
  --add-binary "libusb\x64\libusb-1.0.dll;." ^
  --exclude-module tkinter --exclude-module unittest --exclude-module pydoc_data ^
  --console --onedir --distpath dist --workpath build ^
  src\run_keyboard.py
```

单文件形态把 `--onedir` 换成 `--onefile`。打包后日志固定落在 **exe 同级**
`logs\keyboard.log`，不会写进临时解包目录；onedir 下 DLL 与 exe 同目录（PyInstaller 6.x 在
`_internal\`），onefile 下由 `src\app_paths.py` 的 `prepare_native_dlls()` 加入搜索路径。

版本建议（不写死）：`"pyinstaller<6"`（5.13.2 是最后一条 5.x 线，Win7 案例最多）。
完整步骤（版本选择理由、`libusb-1.0.dll` 的三种来源、onedir/onefile 取舍、自检清单、
在目标机构建的理由）见 [BUILD-WIN7.md](docs/BUILD-WIN7.md)。

**exe 不替代 Zadig 绑定**：仍需先把 `1EA7:0066` 绑到 WinUSB（整设备或两个接口均可），
否则 exe 只会报“设备未找到”。

## 键位映射：通用 usage → VK（无层表）

- 映射表在 `src\hid_usage.py`，是**与设备无关**的 HID Usage Tables 对照表：
  Usage Page 0x07 → VK（字母、数字、符号、功能键、小键盘、锁定键…），
  Usage Page 0x0C → VK（媒体/浏览器/启动应用）。
- **没有"层"的概念**。设备固件在 Num Lock 灯位为 1 时会把字母区改报成小键盘 usage
  （实测 `J: 0x0D → 0x59`），主机只需通用映射：`0x0D → VK_J`、`0x59 → VK_NUMPAD1` 同时存在。
- **锁定键按原生方式转发**：`0x53 → VK_NUMLOCK`、`0x39 → VK_CAPITAL`、`0x47 → VK_SCROLL`，
  由系统切换锁定状态；系统状态一变就把 LED 位图回写设备（见下节）。
  锁定状态变化无论是外置键盘、笔记本键盘还是软件触发的，都会回写，因此灯、系统状态、
  固件层三者始终一致。
- 设备在两种锁定状态上报的 usage 不同，`tools\calibrate.py` 会如实显示，属正常现象。

### 长按自动重复

设备本身**不重发报告**（实测按住 2–3 秒只有一份报告），因此重复完全由主机侧补发，
参数取系统设置（`SPI_GETKEYBOARDDELAY` / `SPI_GETKEYBOARDSPEED`）：

- 首重复延迟：实测 505–514 ms（系统 500 ms，+1~3%）；本轮改动后复测 503 ms
- 重复间隔：实测平均 54.9 ms（系统 55.6 ms，−1.2%）；本轮复测平均 54.8 ms（52.3–57.1）
- 锁定键（Caps/Num/Scroll）不产生重复；修饰键按住同样按此节奏补发

## 接入另一把键盘

设备专有内容**全部集中在 `src\device_profile\` 这个包里**，而且只保留**报告布局类事实**：
VID/PID、接口角色、键盘/消费类报告布局、指示灯输出报告格式。
`keyboard.py`、`keyboard_utils.py`、`run_keyboard.py` 只调用这个包，不含任何本键盘的
常量或分支——换键盘时**只改这个包**（保持包名与导出名不变，它是唯一的设备插槽）。

包内用**契约基类**约束"一把键盘设备应该提供什么"：

| 文件 | 作用 |
|---|---|
| `contract.py` | `KeyboardDevice`：五组能力契约，必需项为 `@abstractmethod` |
| `device.py` | `Wireless1EA7_0066`：当前键盘对契约的实现（只做装配） |
| `identity.py` / `reports.py` | 实测数据与算法（换键盘改这里的值） |
| `_win32.py` | 私有：`win32con` 入口与 VK 补全 |

`__init__.py` 实例化 `PROFILE = Wireless1EA7_0066()`（运行时单设备、单进程），再把契约成员
绑成模块级别名（`NAME` ← `name`、`KEY_REPORT_LENGTH` ← `key_report_length` …），因此通用代码
的导入与调用方式完全不变。

步骤：

1. 备份现有 `src\device_profile\` 目录（换回时可原样恢复）；
2. 按实测值改 `identity.py` / `reports.py`（`tools\calibrate.py` 会打印每个键的 HID 码）；
3. 只有某组能力的**形状**与基类默认不同（报告带 Report ID、消费类取舍规则不同、
   有指示灯输出报告）时，才在 `device.py` 覆写对应成员；否则不用动它；
4. 跑 `python tools\check_device_profile.py`，确认 0 项失败；
5. 用 `tools\probe_keyboard.py`、`tools\enum_usb_nodes.py` 核对接口角色、报告长度与 Report ID，
   再运行 `src\keyboard.py` 上真机。

### 契约（五组能力）

子类只需覆写与实测值有关的成员；"默认"列是基类给出的语义，等价于"该设备没有这项能力"。
带 ★ 的是必需项，缺一个就在实例化时直接 `TypeError`（`abc` 的运行时强制，不是注释约定）。

| 组 | 契约成员 | 必需 | 默认 / 说明 |
|---|---|---|---|
| 身份 | `name` / `vid` / `pid` | ★ | 设备显示名与枚举过滤条件 |
| 接口角色 | `is_keyboard_interface(setting)` | ★ | 按描述符判定，不按接口号 |
| | `is_consumer_interface(setting)` | | HID 类且非键盘接口 |
| | `endpoint_direction` / `endpoint_type` | | `'in'` / `'interrupt'` |
| 键盘报告 | `key_report_length` / `parse_key_report(raw)` / `key_report_read_size(n)` | ★ | 报告长度、解析（残包返回 `(0, None)`）、单次读取长度 |
| | `modifier_byte_index` / `key_slot_start` / `key_slot_end` / `key_report_has_id` | | `0` / `2` / 报告长度 / `False`（仅描述布局，供自检核对） |
| 消费类报告 | `choose_consumer_report(items)` / `parse_consumer_report(raw)` / `consumer_report_read_size(n)` | | 恒 `None` / 恒 `None` / 覆盖 Report ID + usage；本键盘按 Report Size ≥ 16 位取舍、按 Report ID 1 过滤 |
| | `consumer_usage_page` / `consumer_report_id` / `consumer_report_id_size` / `consumer_usage_size` / `consumer_usage_bits` / `consumer_usage_byte_order` | | `0x0C` / `1` / `1` / `2` / `16` / `'little'` |
| 指示灯输出 | `led_supported` / `led_report_id` / `led_report_length` / `led_poll_interval_s` / `led_bits` / `led_report(bitmap)` | | `False`（不声明）/ `0` / `1` / `0.2` / `()` / 按长度小端截断；本键盘为 `True` / `0` / `1` / `0.01` / (Num/Caps/Scroll) |

模块级导出名与契约成员一一对应（通用代码用 `NAME`、`KEY_REPORT_LENGTH`、`LED_SUPPORTED` … 取值，
分别对应 `name`、`key_report_length`、`led_supported`）——**调用方不需要改**。
`KeyboardDevice` 与 `PROFILE` 可以直接导入，但不进 `__all__`。

usage→VK 换算、自动重复语义不在契约里：它们是**通用 HID 知识**，见 `src\hid_usage.py`。

### 最小骨架

只实现三个必需方法 + 三个必需属性就能实例化，其余能力走基类默认（无消费类、无指示灯）：

```python
from .contract import KeyboardDevice

class ExampleKeyboard(KeyboardDevice):
    name = "示例键盘"
    vid, pid = 0x1234, 0x5678
    key_report_length = 8

    def is_keyboard_interface(self, setting):
        return (setting.bInterfaceClass == 3
                and setting.bInterfaceSubClass == 1
                and setting.bInterfaceProtocol == 1)

    def parse_key_report(self, raw):
        data = bytes(raw or b'')
        if len(data) < self.key_report_length:
            return 0, None
        return data[0], [b for b in data[2:8] if b]

    def key_report_read_size(self, max_packet_size):
        return max(self.key_report_length, max_packet_size)
```

要声明消费类或指示灯输出报告时，覆写上表对应成员即可——默认实现都在
`contract.py` 里，docstring 写明了各自语义。

### 一致性自检

`python tools\check_device_profile.py` 纯离线（不打开设备），检查：

- 基类不可直接实例化、实现类没有残留 abstract 成员；
- 身份字段类型与范围；每个方法的参数个数与契约一致；
- 报告长度为正、修饰键与键槽区间自洽、残包返回 `(0, None)`、读取长度覆盖报告；
- 消费类 Report ID/usage 布局自洽，Report ID 不符或长度不足的报文被丢弃；
- `hid_usage` 覆盖字母区与小键盘 usage（`0x0D` 与 `0x59` 并存）、未映射返回 `None`、
  锁定键不重复、音量键可重复、`device_profile` 里不再有层概念；
- `led_report` 长度与 Report ID 处理正确、位图截断正确、位定义合法。

退出码 0 表示全部通过；新增/更换键盘后必须先跑它，再上真机。

## 媒体键

由接口 1（消费类集合，Usage Page `0x0C`，Report ID 1，16 位 usage 小端）上报，
独立线程读取后注入对应 VK：

| usage | 按键 | 注入 VK |
|---|---|---|
| 0xE2 | 静音 | `VK_VOLUME_MUTE` |
| 0xE9 | 音量+ | `VK_VOLUME_UP` |
| 0xEA | 音量− | `VK_VOLUME_DOWN` |
| 0xCD | 播放/暂停 | `VK_MEDIA_PLAY_PAUSE` |
| 0xB5 | 下一曲 | `VK_MEDIA_NEXT_TRACK` |
| 0xB6 | 上一曲 | `VK_MEDIA_PREV_TRACK` |

同一 usage 连续上报不会重复触发；长按期间由主机侧按系统节奏补发，抬起（usage=0）即停。
该端点同时混有厂商报文（首字节非 1），解析时以 `data[0]==1` 过滤。

**端到端实测（Win11 + 网易云音乐）**：六项全部通过——静音（标志 NO→YES、音量不变）、
音量+（84.0%→86.0%，每步 2%）、音量−（86.0%→84.0%）、播放/暂停、上一首、下一首均在播放器中生效。

**音量键长按实测（Win11、外置键盘、WinUSB 接管单实例）**：用全局键盘钩子记录注入事件
（VK 175/174），系统音量先重置为基线 20.0%，系统 typematic 为延迟 500 ms、间隔约 55.6 ms。
每轮操作顺序为“点按 +、按住 +、按住 −”，共做两轮：

| 实测项 | 音量+（两次按住） | 音量−（两次按住） |
|---|---|---|
| 注入按下次数 | 8 / 5 | 7 / 7 |
| 首延迟（第 1→第 2 次按下） | 504.7 / 515.8 ms | 514.8 / 510.6 ms |
| 重复间隔均值 | 55.67 / 50.60 ms | 53.36 / 53.22 ms |
| 间隔标准差（抖动） | 7.33 / 2.18 ms | 5.77 / 5.56 ms |
| 间隔范围 | 45.1–61.1 / 47.6–52.7 ms | 44.8–64.4 / 44.8–59.8 ms |

- **点按单步 2%**：单次点按只注入 1 次按下；整轮共 15 次音量+ 按下、16 次音量− 按下（各另有 4 次抬起），
  系统音量 20.0%→18.0%，等于 (15−16)×2%，说明每次按下正好一步、无漏发也无翻倍。
- **抬起即停**：末次注入到抬起 17–52 ms，抬起后到下一次人为按压之前没有任何同方向注入。
- **无重复翻倍**：同方向相邻注入最短 44.8 ms，未出现 <20 ms 的双发；每次长按都存在约 505 ms 的首延迟，
  不是“松开后直接连发”。
- 实测按住时长约 0.7–0.9 s（受人工操作影响），注入次数随按住时长线性增加。

## 指示灯

- 键盘接口声明 5 位 LED（Num/Caps/Scroll，另有 Compose/Kana 位），输出报告为
  **1 字节、无 Report ID**；回写方式为 `Set_Report(bmRequestType=0x21, wValue=0x0200, wIndex=0, 1 字节)`。
- **实测结论：按描述符声明的 1 字节 Output 报告回写可正常驱动物理指示灯**（Win11 + WinUSB 接管，
  用户目视确认）。驱动进程与 `tools\native_probe.py` 单独直写两条路径都已验证；早期"接管下灯不可控"
  的结论作废，原因是当时发送的是 2–3 字节裸包，与描述符声明不符，设备虽然返回成功但不会执行。
- 单次写入即生效，无需重发或初始化序列：`native_probe.py led --seconds 75 --num-only` 只在窗口开始写一次
  `01`，窗口内 34 次 J 全部上报 `0x59`（`0x0D` 0 次），控制传输返回 1 字节。
- 位定义：bit0 = Num Lock、bit1 = Caps Lock、bit2 = Scroll Lock。
- **可观测性**：这把外置键盘只有 Num Lock 一颗指示灯（Caps 灯在笔记本上，由笔记本自己控制）。
  因此只有 bit0 能肉眼验证；写 bit1/bit2 仍按描述符语义发送，但**没有可观测的反馈通道**，
  不能记为"失败"，也不能拿控制传输返回值当证据。实测中写 bit1 后 J 仍上报 `0x0D`，
  只说明 Caps 位不参与固件切层，不说明该位无效。
- 灯位**不只是显示**：设备按 Num Lock 灯位决定字母区上报 `0x0D`(J) 还是 `0x59`(小键盘 1)，
  所以 `keyboard.py` 默认启用灯同步（`--no-led` 只用于排障，关闭后切层不生效）。
- 回写的触发条件是**系统锁定状态发生变化**，与外置键盘、笔记本键盘还是软件触发无关：
  轮询 `GetKeyState` 后只要与上次不同就写一次，因此物理灯、系统状态、固件层三者始终一致。
- 轮询间隔见 `device_profile.LED_POLL_INTERVAL_S`（默认 0.01 s）。

## 诊断脚本

| 脚本 | 用途 |
|---|---|
| `tools\check_device_profile.py` | 离线一致性自检：验证当前设备实现是否完整满足 `KeyboardDevice` 契约（必需项、签名、报告长度、usage 映射覆盖、消费类过滤、LED 报告格式） |
| `tools\probe_keyboard.py` | 无侵入枚举：接口/端点/包长/报告描述符，核对消费类集合与 Report ID |
| `tools\calibrate.py` | 逐个按键打印 HID 码 → VK 名，核对通用 usage 映射 |
| `tools\native_probe.py` | WinUSB 接管下的真机探针：`info` 打印描述符原文与接口/端点、`capture` 只读记录原始报文，`led` 写入灯位并观察 |
| `tools\compare_native.py` | `record` 用底层键盘钩子记录原生/本实现的 VK 序列（含重复节奏），`compare` 输出差异清单 |
| `tools\enum_usb_nodes.py` | 只读枚举 `VID/PID` 的 USB 设备节点（父设备 + `MI_xx` 接口）：实例 ID、`SPDRP_SERVICE`、驱动键、问题码；用于核对“Zadig 只显示一条，但 pyusb 能用两个接口”的展示差异 |

`tools\enum_usb_nodes.py` 只用标准库 + ctypes，不需 pyusb/pywin32，不安装也不改驱动绑定：

```powershell
python tools\enum_usb_nodes.py                    # 默认 VID=1EA7 PID=0066
python tools\enum_usb_nodes.py --vid 1EA7 --pid 0066 --all-nodes
```

判读：两个 `MI_xx` 节点都在且 `service=WinUSB` → Zadig 条目数差异不影响运行（文档记录项）；
只有父节点且 `service=WinUSB` → 整设备被接管，Zadig 只列 1 条属正常。

`tools\compare_native.py` 用法：

```powershell
python tools\compare_native.py record --out native.jsonl --label 原生     # 记录，按 F8 结束
python tools\compare_native.py record --out ours.jsonl  --label 本实现
python tools\compare_native.py compare native.jsonl ours.jsonl
```

## 已知限制与故障排查

- 指示灯会随系统锁定状态回写（实测可见）；若灯不亮，先确认启动日志里没有
  `指示灯同步被 --no-led 关闭`，再用 `tools\native_probe.py led` 单独验证回写。
- **Win7 实机回归整体未做**：层切换（由固件按灯位完成）、长按重复、媒体键、断线重连在 Win11 均已实测通过，
  Win7 仅保留结构兼容，未重新验证；若媒体键无效，先用 `tools\probe_keyboard.py` 看是否识别到消费类接口。
- **离线依赖未随包提供**：`wheels\`、`installer\` 不再存在；离线安装请自备 pyusb 的 cp38 whl，
  用 `pip --no-index --find-links <目录>` 安装（见 `docs\INSTALL-WIN7.md` 3.3）。
- `tools\compare_native.py` 的“原生 vs 本实现”差异报告尚未执行（仅用合成数据自测过逻辑）。
- **exe 打包未实测**：frozen 路径代码（`src\app_paths.py`、`src\run_keyboard.py`）已在本机验证，
  但本轮未执行真实打包；Python 3.8.10 + PyInstaller 5.x 的实际构建、onedir/onefile 的 DLL 加载
  与 Win7 日志位置仍需在目标机验证（见 [BUILD-WIN7.md](docs/BUILD-WIN7.md) 第 9 节）。
- **`tools\compare_native.py record` 在本机未能采到事件**：钩子安装返回成功，但注入按键也收不到；
  本轮音量长按数据改用独立的全局钩子采集器取得。使用 `record` 前请先用一次按键自检，见上方用法。
- 报 “设备未找到”：确认 Zadig 绑定仍在（换电池/拔插会重新枚举，可能被系统绑回 HID 驱动），
  必要时重绑；用 `tools\probe_keyboard.py` 确认 `1EA7:0066` 是否可见。
- 按键无反应但进程正常：检查是否被别的程序（另一份 `src\keyboard.py`、官方驱动）占用了同一接口。
- 注入按键不重复：确认是外置键盘（本机键盘走的仍是原生路径，与本程序无关）。
- 性能实测（Win11，空闲 60 秒采样）：CPU 占用约 0%（旧版轮询式实现为单核 5.3%）。
