# 1EA7:0066 无线键盘驱动（libusb/WinUSB 接管）

用 Python + libusb（pyusb）直接读取这把 2.4G 无线键盘的 HID 报告，**扮演通用 HID 键盘类驱动**：
按 HID Usage Tables 把 usage 换成虚拟键码、按系统设置补发自动重复、把锁定键按原生方式转发，
并把系统锁定状态按描述符声明的 1 字节 Output 报告回写设备。

切层（字母区 ↔ 小键盘）由**固件**完成：它按主机回写的 Num Lock 灯位决定上报
`0x0D`（J）还是 `0x59`（小键盘 1）。主机侧没有任何"层表"或层状态机，
与 Windows 原生 HID 键盘类的分工完全一致。

> **验证状态（先看这条）**
> 仓库里有两条实现路线，实测证据不同，不要互相顶替：
>
> | 路线 | 层切换机制 | 实测情况 |
> |---|---|---|
> | **历史软切换方案**（tag `archive-soft-layer-switch`） | 主机软件重映射：只读报告，不读也不写 LED | Win7 上源码形态（python + venv）与打包 exe 均运行过，层切换 / 长按自动重复 / 媒体键三项实测通过（用户报告） |
> | **当前原生语义方案**（master） | 固件按 LED 灯位切层，主机必须写 LED 输出报告 | Win11 全部实测；**Win7 SP1 x64 上源码形态（登录会话 1 控制台）已实测通过**，exe 形态在 Win7 未验证 |
>
> 判定规则：验证结论**按方案、按版本、按形态**生效——只有明确写出"哪个版本、哪台机器、什么形态
> （源码/exe、在哪个会话运行）"的实测才算数，且只覆盖写出的范围。逐条记录见下方「验证记录」一节，
> 其它位置只引用它，不再各写一份。上表第一行只属于存档版本，**不**代表 master 的 exe 形态可用；
> 反过来，master 在 Win11 上通过也不代表存档版本通过。
>
> 结构重构（文件移动、拆分、改名、换入口）**不自动作废**已有实测：只要重构经核对是等价的
> （无算法或行为改动），已有结论继续适用于重构后的版本，只把入口命令与目录结构记为差异。
> 等价性依据见「验证记录」里的「重构等价性」。

## 验证记录

一条结论只覆盖"版本 + 形态 + 环境"这个组合，换任一项都要重新实测。

### 2026-11-10：master 源码形态 · Windows 7 SP1 x64 实机

| 项 | 内容 |
|---|---|
| 版本 | master 源码（实测时目录名是 `src\`，入口是 `src\keyboard.py`；之后只有结构重构，逻辑等价，见下「重构等价性」），不含任何打包产物 |
| 形态 | **源码形态**：用目标机旧 venv 的 Python 3.8.10（pyusb 1.2.1）直接运行 `src\keyboard.py`（当前入口是 `python -m keyboard_driver`，同一逻辑） |
| 环境 | Windows 7 SP1 x64；设备 `1EA7:0066`；接口已用 Zadig 绑 WinUSB；`libusb-1.0.dll` 取自系统 `C:\Windows\System32`（1.0.30 x64） |
| 会话 | **登录会话 1 的控制台窗口**（非 session 0 / 非系统服务） |
| 结论 | 打字、指示灯跟随系统锁定状态、灯位切层（灯亮时 J → `1`、灯灭时 J → `j`）、按住 A 两秒自动重复且松手即停、六个媒体键（静音 / 音量± / 播放暂停 / 上一首 / 下一首）全部生效——用户报告实测通过 |

配套探针证据（`tools\native_probe.py`，同一台机器、同一接管形态）：

- 键盘接口报告描述符 67 字节，解析为 `report_id=0: input=8, output=1, feature=0`；
- `led` 写 `01`（Num Lock 位）后的 60 秒窗口内按 J 全部上报 `0x59`（63 次，`0x0D` 0 次）；写 `00` 后 5 秒窗口内恢复 `0x0D`（4 次）；
- 写 `02`（Caps 位）后的 60 秒窗口内 J 仍为 `0x0D`（18 次）——切层只由 Num Lock 位驱动；
- 控制传输接受 1 字节、`report_id=0` 的 Output 报告。

以上只对**该机器、该固件、WinUSB 接管**成立，不外推到其它机型或固件版本。

**本条不覆盖的（仍按未验证对待）**：

- 当前版本**打包 exe** 在 Win7 上的运行；
- `libusb\<arch>` 项目目录方案（见 [INSTALL-WIN7.md](docs/INSTALL-WIN7.md) 3.4）——这次用的是系统已装的
  `C:\Windows\System32\libusb-1.0.dll`；
- 登录自启（`schtasks`）、断线重连、数小时以上长期驻留；
- Win7 驱动签名的**可重复安装**：该机的 WinUSB 是事前用 Zadig 装好的（`oem19.inf`），
  在这台机器上签名要求已通过，但重装系统或换 USB 口重装驱动仍需按
  [INSTALL-WIN7.md](docs/INSTALL-WIN7.md) 3.6 处置。

**入口与目录结构的变化不作废本条**：11-10 之后代码只经历了结构重构（拆出 `device_profile`、
`src\` 改造为 `keyboard_driver\` 包、模块改名、工具归位），主链路逻辑等价，依据见下节。
因此本条结论**继续适用于当前版本**；差异只有启动方式（`python -m keyboard_driver`）与目录名。
新入口尚未在这台机器上单独跑过一次，首次部署建议顺手做一次短跑确认（低成本，但这属于
“同一逻辑的另一种启动方式”，不是“未验证”）。

#### 重构等价性（为什么 11-10 的结论可以沿用）

- **重构提交的 diff 性质**：`git diff -M 2b9be7d d1381de` 里 `src\keyboard.py → keyboard_driver\driver.py`、
  `src\keyboard_utils.py → keyboard_driver\transport.py` 相似度均为 95%，差异只有导入方式
  （绝对导入 → 包内相对导入）与 docstring；`device_profile\`、`usage.py`、`win32_compat.py`、
  `paths.py` 也只改 import 与注释。纯文件移动/拆分/改名，无算法改动。
- **离线自检**：`python tools\check_device_profile.py` 62 项全过；`python -m compileall keyboard_driver tools` 通过。
- **行为抽查**：单实例互斥体名 `Local\KeyboardDriver_1EA7_0066` 逐字一致；接口识别常量 3/1/1 不变；
  `LED_BITS` 的 VK（0x90 / 0x14 / 0x91）不变；`parse_key_report`、`parse_consumer_report` 与注入路径
  （`simulate_key` / `simulate_modifiers` / `simulate_keys`）未改。
- **打桩回归**：采集侧 27 项、清单/判定 66 项全部通过，覆盖读取、解析与判定路径。
- **唯一一处真实行为差异**：`4407661` 让 `release_all_keys()` 连带释放消费类（媒体）按键并把
  `_consumer_usage` 归零，只影响退出/重连收尾路径，不改变正常输入路径。11-10 那轮只覆盖正常输入，
  因此这条差异不在等价性论证范围内，单独记在这里；除此之外没有其它行为差异。

### 历史条目

| 版本 / 形态 | 环境 | 结论 |
|---|---|---|
| 软切换版 tag `archive-soft-layer-switch`，源码 + 打包 exe 两种形态 | Win7 | 层切换 / 长按自动重复 / 媒体键三项通过（用户报告）；不覆盖 master，详见「存档版本」一节 |

## 用途与目标环境

| 项目 | 说明 |
|---|---|
| 设备 | USB `1EA7:0066`（复合设备：接口 0 = boot 键盘，接口 1 = 消费类/鼠标） |
| 目标系统 | Windows 11（全部行为的实测基准）；Windows 7 SP1 x64 上 master 的**源码形态**已实测通过（见「验证记录」），exe 形态未验证 |
| 运行前提 | 设备接口已绑定 WinUSB（见下节），程序独占读取该接口 |

Win7 与 Win11 差异：旧实现写死“接口 1”且只取第一个枚举结果，在 Win7 上可能拿错设备节点，
媒体键不工作；现在改为**按报告描述符角色 + 端点探测读**识别，不再依赖接口号和枚举顺序。
对当前版本而言这只是结构上的兼容改动，已在 Win7 SP1 x64 的实机回归（源码形态）中随 master 一起通过，
见「验证记录」；存档版本另有一套独立实测，两者不能互相顶替。

## 依赖与安装

- Python 3（本轮使用 MSYS2 clang64 Python 3.14，虚拟环境在 `.venv`）
- `pyusb`（本机 1.3.1；Win7 + Python 3.8 上 pip 会选 1.2.1，因为 1.3.x 要求 Python ≥ 3.9）
- `libusb-1.0.dll`（32/64 位需与 Python 一致）。来源按需选择：系统或 PATH 已有、
  `pip install "libusb-package<1.0.27"`（包内自带 DLL），或放到项目 `libusb\x86|x64\`
  （源码形态启动时按解释器位数自动搜索并加入 DLL 搜索路径，见 [INSTALL-WIN7.md](docs/INSTALL-WIN7.md) 3.4）。
  已跑通的 Win7 实机用的是系统 `C:\Windows\System32\libusb-1.0.dll`（1.0.30 x64），
  项目 `libusb\<arch>` 这条放法仍未在 Win7 实测。
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
   **64 位 Win7 另有驱动签名硬门槛**：要装的是 libwdi 生成的 WinUSB 驱动包（复用微软 `winusb.sys`），
   不是本项目自研驱动，见同文档 3.6。
2. 绑定后系统不再提供原生键盘/媒体键行为，一切按键由本程序注入。

**恢复系统原生驱动**（任选其一）：

- 设备管理器 → 找到该键盘 → 右键“卸载设备”并勾选“删除驱动程序软件” → 拔插接收器；
- 或以管理员运行：`pnputil /delete-driver oemXX.inf /uninstall /force`（旧版 `pnputil` 不支持
  `/uninstall`、`/force` 时去掉对应参数），然后拔插接收器
  （`oemXX.inf` 用 `pnputil /enum-drivers` 查 Provider 为 libwdi 的项）。

## 运行

```powershell
.\.venv\bin\python.exe -m keyboard_driver                 # 正常模式（指示灯回写默认开启）
.\.venv\bin\python.exe -m keyboard_driver --no-led        # 排障用：关闭灯位回写（Num Lock 切层会失效）
.\.venv\bin\python.exe tools\calibrate             # 向导：点名六个切层键 → 等按键 → 判定 → 汇总
.\.venv\bin\python.exe tools\calibrate --learn     # 单键采集：按一个记一个（发现未知键）
```

`tools\calibrate` 是个包（`tools\calibrate\`），只有这两种入口：项目根用 `python tools\calibrate`，
在 `tools` 目录下用 `python -m calibrate`（项目根没有包搜索路径，不能直接 `-m`）。

`tools\calibrate` 会独占键盘接口，**运行前先停掉 `python -m keyboard_driver`**；结果写到 `logs\calibrate_<时间戳>.txt`，
有失败项时退出码为 1。只测某几个键或调整等待时间见 [诊断脚本](#诊断脚本)。

目录划分：`keyboard_driver\` 驱动源码（键盘主程序与模块）、`tools\` 诊断脚本、`docs\` 说明文档
（`INSTALL-WIN7.md` 手工安装/卸载，`BUILD-WIN7.md` 手工打包）；`README.md` 为入口。
所有脚本都按自身文件位置解析路径，可从任意工作目录启动。

- **不需要管理员权限**：WinUSB 安装时已写入允许普通用户访问的权限，实测可 claim 并读取。
- 断线后每 5 秒自动重连；退出（Ctrl+C）前会抬起所有已注入的按键，避免残留。

### 打包为 exe（可选，需在目标机构建）

项目**不提供打包脚本**，改为手工执行 PyInstaller。目标机装好 Python 3.8.10 与
`"pyinstaller<6"` 后，在项目根执行（onedir；DLL 按 Python 位数选 `libusb\x64` 或 `x86`）：

```bat
python -m PyInstaller --noconfirm --clean --name KeyboardDriver --paths . ^
  --hidden-import usb.backend.libusb1 ^
  --add-binary "libusb\x64\libusb-1.0.dll;." ^
  --exclude-module tkinter --exclude-module unittest --exclude-module pydoc_data ^
  --console --onedir --distpath dist --workpath build ^
  keyboard_driver\run.py
```

单文件形态把 `--onedir` 换成 `--onefile`。打包后日志固定落在 **exe 同级**
`logs\keyboard.log`，不会写进临时解包目录；onedir 下 DLL 与 exe 同目录（PyInstaller 6.x 在
`_internal\`），onefile 下由 `keyboard_driver\paths.py` 的 `prepare_native_dlls()` 加入搜索路径。

版本建议（不写死）：`"pyinstaller<6"`（5.13.2 是最后一条 5.x 线，Win7 案例最多）。
完整步骤（版本选择理由、`libusb-1.0.dll` 的三种来源、onedir/onefile 取舍、自检清单、
在目标机构建的理由）见 [BUILD-WIN7.md](docs/BUILD-WIN7.md)。

**exe 不替代 Zadig 绑定**：仍需先把 `1EA7:0066` 绑到 WinUSB（整设备或两个接口均可），
否则 exe 只会报“设备未找到”。

## 键位映射：通用 usage → VK（无层表）

- 映射表在 `keyboard_driver\usage.py`，是**与设备无关**的 HID Usage Tables 对照表：
  Usage Page 0x07 → VK（字母、数字、符号、功能键、小键盘、锁定键…），
  Usage Page 0x0C → VK（媒体/浏览器/启动应用）。
- **没有"层"的概念**。设备固件在 Num Lock 灯位为 1 时会把字母区改报成小键盘 usage
  （实测 `J: 0x0D → 0x59`），主机只需通用映射：`0x0D → VK_J`、`0x59 → VK_NUMPAD1` 同时存在。
- **锁定键按原生方式转发**：`0x53 → VK_NUMLOCK`、`0x39 → VK_CAPITAL`、`0x47 → VK_SCROLL`，
  由系统切换锁定状态；系统状态一变就把 LED 位图回写设备（见下节）。
  锁定状态变化无论是外置键盘、笔记本键盘还是软件触发的，都会回写，因此灯、系统状态、
  固件层三者始终一致。
- 设备在两种锁定状态上报的 usage 不同，`tools\calibrate\` 会分「灯灭 / 灯亮」两轮逐键核对，属正常现象。
- **设备事实（实测，换键盘需重新确认）**：灯亮与否只影响 15 颗实体键——
  `7 8 9 0 U I O P J K L ; M . /`（与键帽上的小键盘副标注一一对应）；其余所有键（其他字母、
  数字行、F 键、控制键、编辑键、方向键、修饰键）在灯灭/灯亮两轮的 usage **必须完全相同**。
  这 15 颗的灯亮轮目标落在这 15 个小键盘 usage 内：`0x54` `/`、`0x55` `*`、`0x56` `-`、
  `0x57` `+`、`0x59`–`0x62` 小键盘 1–9/0、`0x63` `.`（HID Usage Tables 实际常量，不含
  `0x58` 小键盘 Enter——本键盘键帽上也没有该副标注）。实测配对见下表；`tools\calibrate\`
  的灯亮轮据此做双向断言，配对表可用 `--layer-pair` 覆盖、切层键集合可用 `--layer-key` 覆盖。

| 物理键 | 灯亮轮 usage | 物理键 | 灯亮轮 usage |
|---|---|---|---|
| `7` | `0x5F` 小键盘 7 | `J` | `0x59` 小键盘 1 |
| `8` | `0x60` 小键盘 8 | `K` | `0x5A` 小键盘 2 |
| `9` | `0x61` 小键盘 9 | `L` | `0x5B` 小键盘 3 |
| `0` | `0x55` `*` | `;` | `0x57` `+` |
| `U` | `0x5C` 小键盘 4 | `M` | `0x62` 小键盘 0 |
| `I` | `0x5D` 小键盘 5 | `.` | `0x63` `.` |
| `O` | `0x5E` 小键盘 6 | `/` | `0x54` `/` |
| `P` | `0x56` `-` | | |

> `'`（`0x34`）、`,`（`0x36`）实测**不切层**（3/3 两轮相同），不在 15 颗之内。
> 若实测出现 15 颗之外的键改报，按「不应切层却改报」记录并提示"可能为误按，请复核该次"，
> 不会静默当成设备行为。

### 长按自动重复

设备本身**不重发报告**（实测按住 2–3 秒只有一份报告），因此重复完全由主机侧补发，
参数取系统设置（`SPI_GETKEYBOARDDELAY` / `SPI_GETKEYBOARDSPEED`）：

- 首重复延迟：实测 505–514 ms（系统 500 ms，+1~3%）；本轮改动后复测 503 ms
- 重复间隔：实测平均 54.9 ms（系统 55.6 ms，−1.2%）；本轮复测平均 54.8 ms（52.3–57.1）
- 锁定键（Caps/Num/Scroll）不产生重复；修饰键按住同样按此节奏补发

Win7 SP1 x64 上（master 源码形态）用户实测：按住 A 两秒开始连发、松手即停；
那轮没有逐次计时，量化数据仍以上面的 Win11 钩子记录为准。见「验证记录」。

## 接入另一把键盘

设备专有内容**全部集中在 `keyboard_driver\device_profile\` 这个包里**，而且只保留**报告布局类事实**：
VID/PID、接口角色、键盘/消费类报告布局、指示灯输出报告格式。
`driver.py`、`transport.py`、`run.py` 只调用这个包，不含任何本键盘的
常量或分支——换键盘时**只改这个包**（保持包名与导出名不变，它是唯一的设备插槽）。

包内用**契约基类**约束"一把键盘设备应该提供什么"：

| 文件 | 作用 |
|---|---|
| `contract.py` | `KeyboardDevice`：五组能力契约，必需项为 `@abstractmethod` |
| `device.py` | `Wireless1EA7_0066`：当前键盘对契约的实现（只做装配） |
| `identity.py` / `reports.py` | 实测数据与算法（换键盘改这里的值） |

包内模块只依赖标准库与 `keyboard_driver\win32_compat.py` 的 VK 常量；`win32con` 不经过设备包转手导出
（通用 VK 常量统一从 `win32_compat` 取）。

`__init__.py` 实例化 `PROFILE = Wireless1EA7_0066()`（运行时单设备、单进程），再把契约成员
绑成模块级别名（`NAME` ← `name`、`KEY_REPORT_LENGTH` ← `key_report_length` …），因此通用代码
的导入与调用方式完全不变。

步骤：

1. 备份现有 `keyboard_driver\device_profile\` 目录（换回时可原样恢复）；
2. 按实测值改 `identity.py` / `reports.py`（`tools\calibrate\` 可逐键核对两种灯态下的 HID 码）；
3. 只有某组能力的**形状**与基类默认不同（报告带 Report ID、消费类取舍规则不同、
   有指示灯输出报告）时，才在 `device.py` 覆写对应成员；否则不用动它；
4. 跑 `python tools\check_device_profile.py`，确认 0 项失败；
5. 用 `tools\probe_keyboard.py`、`tools\enum_usb_nodes.py` 核对接口角色、报告长度与 Report ID，
   再运行 `python -m keyboard_driver` 上真机。

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

usage→VK 换算、自动重复语义不在契约里：它们是**通用 HID 知识**，见 `keyboard_driver\usage.py`。

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
- `usage` 覆盖字母区与小键盘 usage（`0x0D` 与 `0x59` 并存）、未映射返回 `None`、
  锁定键不重复、音量键可重复、`device_profile` 里不再有层概念；
- `led_report` 长度与 Report ID 处理正确、位图截断正确、位定义合法；
- 导出表自洽：`device_profile.__all__` / `transport.__all__` 里的名字都存在、
  没有公共名漏出、不含层相关旧符号；设备包不转手 `win32con`，键盘原语层不重复导出
  usage→VK 换算（归 `usage`）。

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

**Win7 侧**：同一实现（master 源码形态）在一台 Win7 SP1 x64 实机上，六个媒体键由用户实测全部生效
（未逐项记录播放器数值），见「验证记录」。该结论不外推到其它机器。

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
- Win7 SP1 x64 上同样成立：master 源码形态运行时用户目视确认灯跟随系统锁定状态，且灯位切层生效
  （灯亮 J → `1`、灯灭 J → `j`）；探针侧另有 `01` → 63 次全 `0x59`、`00` → 恢复 `0x0D` 的记录。
  范围与形态见「验证记录」，只对该机器、该固件、WinUSB 接管成立。
- 单次写入即生效，无需重发或初始化序列：`native_probe.py led --seconds 75 --num-only` 只在窗口开始写一次
  `01`，窗口内 34 次 J 全部上报 `0x59`（`0x0D` 0 次），控制传输返回 1 字节。
- 位定义：bit0 = Num Lock、bit1 = Caps Lock、bit2 = Scroll Lock。
- **可观测性**：这把外置键盘只有 Num Lock 一颗指示灯（Caps 灯在笔记本上，由笔记本自己控制）。
  因此只有 bit0 能肉眼验证；写 bit1/bit2 仍按描述符语义发送，但**没有可观测的反馈通道**，
  不能记为"失败"，也不能拿控制传输返回值当证据。实测中写 bit1 后 J 仍上报 `0x0D`，
  只说明 Caps 位不参与固件切层，不说明该位无效。
- 灯位**不只是显示**：设备按 Num Lock 灯位决定字母区上报 `0x0D`(J) 还是 `0x59`(小键盘 1)，
  所以 `driver.py` 默认启用灯同步（`--no-led` 只用于排障，关闭后切层不生效）。
- 回写的触发条件是**系统锁定状态发生变化**，与外置键盘、笔记本键盘还是软件触发无关：
  轮询 `GetKeyState` 后只要与上次不同就写一次，因此物理灯、系统状态、固件层三者始终一致。
- 轮询间隔见 `device_profile.LED_POLL_INTERVAL_S`（默认 0.01 s）。

## 诊断脚本

| 脚本 | 用途 |
|---|---|
| `tools\check_device_profile.py` | 离线一致性自检：验证当前设备实现是否完整满足 `KeyboardDevice` 契约（必需项、签名、报告长度、usage 映射覆盖、消费类过滤、LED 报告格式） |
| `tools\probe_keyboard.py` | HID 集合层枚举：接口/端点/包长/报告描述符、消费类集合与 Report ID、读权限自检；HidUsb 绑定下用 `ReadFile` 看原始报文。设备/驱动绑定交给 `enum_usb_nodes.py`，按键语义交给 `calibrate`（包）；键盘集合不可读时不再装钩子，改为提示用 `compare_native.py record` |
| `tools\calibrate\` | 键语义的核对/采集，四个入口：默认向导（点名六个切层键 → 等按下并抬起 → 判定 → 汇总）、`--learn` 单键采集（一次一个键，记录未知 usage、可起名、导出 `KEYMAP` 草稿）、`--learn --categories` 分类采集（先选 a-z/0-9 等类，再在类内逐项点名核对常规键）、`--watch` 纯被动翻译。分「灯灭 / 灯亮」两轮，结果落 `logs\` |
| `tools\native_probe.py` | 本次原理验证的**实验记录**：`info` 打印描述符原文与接口/端点、`capture` 只读记录原始报文、`led` 写灯位并按窗口内 J 的 usage 自判"写入是否落地"（`--seconds` / `--reassert` / `--num-only`） |
| `tools\compare_native.py` | `record` 用底层键盘钩子（本仓库唯一一处）记录原生/本实现的 VK 序列（含重复节奏），`compare` 输出差异清单 |
| `tools\enum_usb_nodes.py` | 只读枚举 `VID/PID` 的 USB 设备节点（父设备 + `MI_xx` 接口）：实例 ID、`SPDRP_SERVICE`、驱动键、问题码；`--classes` 另列键盘/鼠标/HID 类设备（原 `probe_keyboard.py --all` 的能力）。用于核对“Zadig 只显示一条，但 pyusb 能用两个接口”的展示差异 |

`tools\enum_usb_nodes.py` 只用标准库 + ctypes，不需 pyusb/pywin32，不安装也不改驱动绑定：

```powershell
python tools\enum_usb_nodes.py                    # 默认 VID=1EA7 PID=0066
python tools\enum_usb_nodes.py --vid 1EA7 --pid 0066 --all-nodes
python tools\enum_usb_nodes.py --classes          # 另列键盘/鼠标/HID 类设备
```

判读：两个 `MI_xx` 节点都在且 `service=WinUSB` → Zadig 条目数差异不影响运行（文档记录项）；
只有父节点且 `service=WinUSB` → 整设备被接管，Zadig 只列 1 条属正常。

`tools\compare_native.py` 用法：

```powershell
python tools\compare_native.py record --out native.jsonl --label 原生     # 记录，按 F8 结束
python tools\compare_native.py record --out ours.jsonl  --label 本实现
python tools\compare_native.py compare native.jsonl ours.jsonl
```

`tools\calibrate\` 有四个入口，场景不同，别混用：

| 入口 | 什么时候用 | 产出 |
|---|---|---|
| 默认向导 | 已知六个切层键（J/K/L/U/I/O）的映射核对，灯灭 / 灯亮两轮 | `logs\calibrate_<时间戳>.txt` 判定汇总 |
| `--learn` 单键采集 | 发现未知键：常规键、Fn 组合、厂商自定义键都可以，按一个记一个，可起名 | `logs\learn_<时间戳>_off.txt` / `_on.txt` 的 `KEYMAP` 草稿 |
| `--learn --categories` 分类采集 | 一般键盘的常规键按类全覆盖核对（先选类，再逐项点名；必要/可选项分开，汇总分一致/无此键/失败） | `logs\calibrate_<时间戳>.txt` 判定汇总 + 每类小结 |
| `--watch` | 只想看"刚按的键上报了什么"，不判定、不留档 | 屏幕输出 |

包内分工（一个模块只做一件事，改判定/改文案/改清单不必翻整个文件）：

| 文件 | 职责 |
|---|---|
| `__main__.py` | `python -m calibrate` / `python tools\calibrate` 的入口 |
| `cli.py` | 参数解析与模式分发 |
| `constants.py` | 参数默认值、向导键清单、HID 小键盘集合、切层集合与实测配对 |
| `text.py` | usage/VK/消费类与其他显示文案 |
| `console.py` | 非阻塞控制台上行队列（后台线程读 stdin） |
| `device.py` | 键盘 Reader、消费类监听线程、Num Lock 灯位写入 |
| `report.py` | `logs\calibrate_<时间戳>.txt` 落盘与屏幕汇总 |
| `wizard.py` | 默认向导 |
| `learn.py` | `--learn` 单键采集与草稿导出 |
| `watch.py` | `--watch` |
| `catalog.py` | `Target` 与内建九个类别（含 10 条 `fn`） |
| `catalog_file.py` | `--categories-file` 的读取、校验与注册 |
| `planning.py` | 选类、`--required/--optional`、`--layer-pair/--layer-key`、交互选类 |
| `judge.py` | 分类采集的判定口径（两轮断言、照实记录） |
| `range_mode.py` | 分类采集主流程（逐类逐项、`skip`/`stop`/`done`、类小结） |
| `paths.py` | 项目根与 `logs\` 目录 |

用法（下面用 `python tools\calibrate`；在 `tools` 目录下等价写法是 `python -m calibrate`）：

```powershell
python tools\calibrate                    # 向导：灯灭 + 灯亮两轮，核对 J/K/L/U/I/O
python tools\calibrate --keys J,K          # 向导：只核对指定键
python tools\calibrate --rounds off        # 只跑灯灭一轮
python tools\calibrate --timeout 20 --no-retry   # 放宽等待、失败不重试
python tools\calibrate --learn            # 单键采集：按一个记一个，可起名
python tools\calibrate --learn --categories a-z              # 分类采集：只采字母类
python tools\calibrate --learn --categories a-z 0-9 symbols  # 多类拼接
python tools\calibrate --learn --categories all              # 全部九类
python tools\calibrate --learn --categories                # 不带值：先交互选类
python tools\calibrate --learn --categories all --optional edit arrows
                                                # 把编辑键/方向键整体当可选项
python tools\calibrate --learn --categories all --required edit
                                                # 反过来：编辑键也是必要项
python tools\calibrate --learn --categories symbols 0-9
                                                # 补测符号区/数字行的切层归属
python tools\calibrate --learn --categories symbols --layer-pair "';'=0x57" ',=0x63'
                                                # 覆盖/增补灯亮轮的逐键配对
python tools\calibrate --learn --categories a-z --layer-key J K L
                                                # 覆盖"会切层"的键集合（换键盘时用）
python tools\calibrate --learn --categories fn   # Fn 组合（顶排 10 颗 F 键）：结果照实记
python tools\calibrate --learn --categories fn --categories-file tools\calibrate_keys.json
                                                # 类与键清单来自 JSON 文件（与内建类共存）
python tools\calibrate --learn --categories-file tools\calibrate_keys.json --categories-file-only
                                                # 只认文件里的类，忽略全部内建类
python tools\calibrate --watch            # 老用法：常驻打印每个键的 HID 码，不做判定
```

- 灯位由脚本自己写 HID Output 报告（接口绑 WinUSB 后 Windows 不再替这块键盘写灯），
  退出时恢复为 0；每轮开始前打印当前灯位，要求目视确认外置键盘的 Num Lock 指示灯状态
  （只是提示，不需要回车，直接开按）。
- **灯亮轮判定是双向断言**（依据见「键位映射」里的设备事实，实测得出、换键盘需重新确认）：
  1. 15 颗切层键必须改报：灯亮轮 usage 必须落在 15 个小键盘 usage（`0x54`–`0x57`、
     `0x59`–`0x63`）内且与灯灭轮不同；落在其中但与本键实测配对不符记
     「切层映射偏差（发现）」，单列且不计失败；不落其中、或仍报灯灭轮的 usage 记失败。
  2. 其余键必须不变：灯亮轮 usage 与灯灭轮相同记一致；不同记「不应切层却改报」并打出两轮 usage。
  3. 既不是本键常规 usage、也不在 15 个小键盘 usage 内的报文记「来源不明（需复测）」，
     原样落盘待真机复核（此前的 `0x13` 就属于这一类）。
- 配对表以实测为准，可用 `--layer-pair KEY=USAGE` 覆盖/增补（`usage` 必须在 15 个之内）；
  `--layer-key KEY…` 可整体替换"会切层"的键集合。默认向导仍只核对 J/K/L/U/I/O 六个键，
  灯亮轮对 `J` 按实测值精确比对，其余键要求"落在小键盘 usage 内且与灯灭轮不同"。
- 结果文件写到 `logs\calibrate_<时间戳>.txt`（`logs\` 已被 `.gitignore` 忽略），
  全部通过时退出码 0，有失败项时 1。
- 与 `native_probe.py` 一样用 pyusb 直读接口，**不能和 `python -m keyboard_driver` 同时运行**。

`--learn` 单键采集（发现未知映射时用）：

- 一次只针对一个键：常规键、这把键盘独有的键（Fn 组合、厂商自定义键）都可以；按下去就记录
  usage + 原始报文，**立刻回到等待下一个键**，不需要提前准备清单，也不需要回车推进。
- 同帧多个 usage 逐个记录并标注"同帧多键"；抬起事件只打印、不记录；修饰键位图变化单独记在
  草稿注释里（不进 `KEYMAP`）。
- **起名只属于这个模式**：在两次按键之间用另一把键盘（或屏幕键盘）输入 `VK_xxx` 回车，命名落到
  **最近记录的那个键**；空回车跳过命名，输入 `done` 结束一轮，或 Ctrl+C。控制台输入由后台线程读取，
  提示期间键盘仍在正常采集，不会漏按键。
- 灯灭 / 灯亮两轮分开采集，各写一份 `logs\learn_<时间戳>_off.txt` / `_on.txt`，
  两份草稿互相注明对照文件与该轮 usage 列表。
- 草稿正文是可直接粘贴进 `keyboard_driver\usage.py` 的 `KEYMAP.update({...})`：usage 去重、
  保留首次出现顺序，已命名的写成 `0x..: win32con.VK_xxx,`，未命名的留 `#` 占位注释。

`--learn --categories` 分类采集（一般键盘的常规键全覆盖）：

- **先选类，再在类内逐项点名。** 类是可勾选的最小单位，共九类：`a-z`（A–Z）、`0-9`（数字行）、
  `symbols`（符号行：`-` `=` `[` `]` `\` `;` `'` 反引号 `,` `.` `/`）、
  `control`（Esc/Tab/CapsLock/Enter/Backspace/Space/Menu）、`f1-f12`、
  `fn`（Fn 组合：顶排 10 颗 F 键的副标注 `F11`/`F12`/`♪`/`⏮`/`⏯`/`⏭`/`🔇`/音量−/音量+/Scroll Lock`）、
  `edit`（PrintScreen/ScrollLock/Pause/Insert/Home/PageUp/Delete/End/PageDown）、
  `arrows`（Up/Down/Left/Right）、`modifiers`（左右 Ctrl/Shift/Alt/Win）。
- 类名可组合：`--categories a-z 0-9`、`--categories a-z,0-9`、`--categories all` 都行；
  `--categories` 不带值时先打印菜单，用另一把键盘输入要采的类（回车确认），
  所以也可以只跑一类就结束，不必强制走完全部类。
- **必要项 / 可选项分开**：`a-z`、`0-9`、`symbols`、`control`、`f1-f12` 默认必要（超时记失败）；
  `edit`、`arrows`、`fn` 整类可选，`modifiers` 里只有右 Win 可选。可选项重试到上限仍收不到任何报告时
  自动记「无此键（该键盘可能没有这个键）」并进入下一项，**不计失败、不需要用户输入**。
  用 `--optional <类…>` / `--required <类…>` 可按类整体覆盖（支持 `all`，同一类同时出现时
  按必要项处理）；选中类时会打印每类是「必要 / 可选 / 部分可选」。
- **`fn` 类：Fn 组合按可选项处理，且只跑一轮。** 逐项点名顶排 10 颗 F 键的 Fn 副标注：
  `F1（Fn:F11）`、`F2（Fn:F12）`、`F3（Fn:♪）`、`F4（Fn:⏮）`、`F5（Fn:⏯）`、`F6（Fn:⏭）`、
  `F7（Fn:🔇）`、`F8（Fn:音量−）`、`F9（Fn:音量+）`、`F10（Fn:Scroll Lock）`——这把键盘顶排只有
  Esc + 10 颗 F 键，F11/F12 是 F1/F2 的 Fn 副标注，**没有独立的 F11/F12 实体键**；点名写
  "按住 Fn 再按顶排第 N 颗（主标注 Fx、Fn 副标注 …）"，类开头另行说明"本类必须按住 Fn；
  单独按只会出主功能键 F1..F10"。Fn 本身通常不上报，结果取决于固件，三类都照实记录：键盘接口收到 usage
  （改报，例如按 F1 的 Fn 副标注报成 F11 的 usage，按一致记并列出实收）、消费类接口收到 usage
  （记为「消费类 0x..（usage 名/未知）」，与键盘 usage、无上报三者可区分）、什么都没收到
  （记「无上报，可能由固件本地处理」，**不计失败**、自动进入下一项）。单轮的依据是实测：
  Fn 组合走的是消费类接口，与 Num Lock 灯位无关，灯灭/灯亮两轮结果完全一致。
  **消费类 usage 一收到就打印一行并推进下一项**，不必等 15 秒窗口到期；行内带相对本键开始
  等待的时间偏移（如 `+0.83s`）。同一帧出现多个键盘 usage 会全部列出，不按「多键同帧」判失败。
  键盘改报与消费类 usage 同帧出现时记在同一行，两类都不丢。`f1-f12` 类里 F11/F12 的点名同样
  改为"按住 Fn 按顶排第 2/3 颗"，因为这两颗在主标注层就是 F1/F2。
- **点名按物理位置描述**，不只给会随层变化的字符：例如「请按 字母区 J（副标注 1）」、
  「顶行数字 0（在 P 上方）」「符号键 ,（字母区 M 的右侧）」；`0-9` 指顶行数字键，不是小键盘。
  每轮开头说明一次"常规类不需要 Fn、不需要组合键"（选了 `fn` 类时改说明该类的按法）；
  灯亮轮同一颗键被固件改报为小键盘 usage（如 J → 0x59 = 小键盘 1）时，判定说明会写明
  "属于预期切换，不是按错"。
- **灯亮轮按双向断言判定**（设备事实见「键位映射」）：15 颗切层键必须改报、其余键必须与
  灯灭轮完全相同；切层键落在 15 个小键盘 usage 内但配对不符记「切层映射偏差（发现）」，
  不落其中或该改报没改报记失败，其余键改报记「不应切层却改报」；既非本键常规 usage、
  也不在 15 个小键盘 usage 内的报文记「来源不明（需复测）」并原样落盘。配对表用
  `--layer-pair KEY=USAGE` 增补/覆盖，切层键集合用 `--layer-key KEY…` 整体替换。
- **判据收敛的教训**：单次读数既不足以加进、也不足以踢出设备事实。`P → 0x56` 曾被当成误按
  移出集合，后经键帽副标注（小键盘 `-`）与实测 3/3 确认，重新并入 15 颗；因此 15 颗之外的键
  出现改报时只记「不应切层却改报」并提示"可能为误按，请复核该次"，重复确认后才允许改判。
  设备事实（只影响 15 颗）与配对表都以多次实测 + 键帽核对为准。
- 选中后按固定顺序逐项点名（"请按 A"），按一项收一项，**自动进入下一项**，不需要回车；
  每类结束打印该类小结（记录了几项、无此键/偏差/跳过/失败的是哪些键），并提示下一类的第一个键。
- 分类采集**不起名**：键名就是点名给出的名字；实收与预期不符时照实记录并标注
  （例如"点名 A，实收 0x0E"），不转起名流程，也不打断整类采集。
- 按错 / 超时只重试本键（`--attempts` 控制次数，`--no-retry` 关闭重试），重试用完记下结论
  继续下一项，一次按错不会让整类作废。
- **防误判**：连续 3 项完全收不到任何报告（且其中含必要项）时，不会默默记成"这些键都不存在"，
  而是提示更像设备没就绪或接口不对，可选择 `continue` 继续或 `abort` 中止（20 秒无输入按中止），
  中止后剩余项记「未采集」并照常汇总。
- **汇总分三类**：一致 / 无此键（可选项未采到）/ 失败（必要项超时、按错键、usage 不符、
  多键同帧、未按灯位改报、不应切层却改报、来源不明）；「切层映射偏差（发现）」单列发现项，
  「无上报」（`fn` 类未收到键盘报告）单列，两者都不计失败。分别计数并列出键名；
  跳过与未采集单列，不计失败。退出码仍是有失败项才为 1。
- 中途命令（后台线程读控制台，随时可用）：`skip` 跳过本键、`stop` 结束当前类并继续下一类、
  `done` 结束整次采集、Ctrl+C 退出；已完成的内容照常落盘并汇总。
- 默认分灯灭 / 灯亮两轮（`fn` 类例外，只跑一轮），`--rounds off` 只跑一轮。
- **配对表已定案**：15 颗的灯亮轮目标按键帽副标注定案 + 实测（见「键位映射」表）。
  2026-11-11 18:25 在 Win7 SP1 x64 实机（源码形态：目标机 venv 的 Python 3.8.10 直接运行
  `tools\calibrate`）用 `--learn --categories layer --rounds on` **一次跑全 15/15**：
  逐键 usage 与下表配对完全一致，`7` 0x5F、`8` 0x60、`9` 0x61、`0` 0x55、`U` 0x5C、`I` 0x5D、
  `O` 0x5E、`P` 0x56、`J` 0x59、`K` 0x5A、`L` 0x5B、`;` 0x57、`M` 0x62、`.` 0x63、`/` 0x54；
  日志 `logs\calibrate_20261111_182554.txt`（共 15 项，一致 15，失败 0）。
  `'`（0x34）与 `,`（0x36）实测不切层（3/3），不属于切层键。
  换键盘时用 `--layer-pair` 改配对、`--layer-key` 改集合。

**清单文件（`--categories-file`）**：类与键清单可以完全由 JSON 文件定义，适合"不是常规键"的组合
（Fn 副标注、厂商自定义键），清单随时可编辑，不必改脚本。

- 路径：随附示例在 `tools\calibrate_keys.json`（库内唯一一份）；自建清单放哪都行，
  用绝对路径或相对当前工作目录的路径传进去即可。
- 结构：顶层 `{"version": 1, "note": "整份说明（可省）", "categories": [...]}`；
  每个类 `{"name": "fn", "summary": "…", "note": "…", "optional": true, "fn": true,
  "keys": [...]}`；每个键 `{"label": "F1（Fn:F11）", "pos": "顶排第 2 颗…",
  "expect": "键盘 0x44 -> VK_F11", "note": "待复测", "optional": true, "fn": true}`。
  `label` 必填（也是点名与 `--layer-pair`/`--layer-key` 用的键名），其余字段可省；
  `optional`/`fn` 写在类上是该类的默认值，写在键上按项覆盖。`version` 必须为 `1`，
  类名不能是 `all`、不能含空格或逗号、不能重复。
- 语义：文件里的键**一律照实记录**——不比对 vks，`expect` 只在点名时作为提示打印
  （标注"仅提示，不参与判定"），`note` 作为「备注」打印；`optional: false` 的键超时记失败，
  `optional: true` 的键超时记「无上报」不计失败。`fn: true` 的键走 Fn 组合的判定口径
  （键盘 usage / 消费类 usage / 无上报三类，不按「多键同帧」判失败）。
  清单项没有结构化预期，因此**收到任意 usage 就立即记录并进入下一项**：键盘接口有报告立即推进，
  只有消费类接口有报告也立即推进，不会因为 `expect` 写的是自然语言就等满整个等待窗口。
- 与内建类的关系：**默认共存**，文件里的类追加到菜单末尾；**同名类整体替换**内建定义
  （会打印「清单文件覆盖内建类 X」）。加 `--categories-file-only` 则只认文件里的类，
  内建类不可选、`all` 也只展开文件里的类。文件解析失败（读不到、非法 JSON、缺字段、
  类名非法或重复、version 不符）时打印中文原因并以退出码 1 结束，不会带着半个清单继续跑。
- 示例清单 `tools\calibrate_keys.json` 含两类：`fn`（10 条，与内建 `fn` 同名，加载后覆盖内建）、
  `layer`（切层 15 颗 `7 8 9 0 U I O P J K L ; M . /`，`expect` 写灯灭/灯亮轮实收，与代码里的
  15 颗常量、配对表一致；`'`、`,` 实测不切层，只写在类备注里，不列条目）。跑法：

  ```powershell
  python tools\calibrate --learn --categories fn layer --categories-file tools\calibrate_keys.json
  python tools\calibrate --learn --categories-file tools\calibrate_keys.json   # 交互选类
  ```

**消费类接口监听（已接入）**：分类采集启动时会再起一条 daemon 线程读接口 1，把
`(时间, usage)` 放进队列。`0x00`（无键/释放帧）不入队，避免每个按下帧都跟一条「消费类 0x00 -> 未知」
把条目数翻倍。每颗键开始等待时先清掉队列里的旧事件（防止上一颗的 usage 被算进本键，出现"本键
窗口里没有自己的 usage 却判一致"的假阳性）；`fn` 类一收到消费类 usage 就打印并推进下一项，
行内带相对窗口起点的时间偏移。常规键仍按键盘事件前后约 200 ms 的窗口（`0.20 s` 窗口 +
`0.15 s` 回溯）把消费类 usage 合并进同一行，同帧的键盘改报与消费类 usage 都保留。
用到的后端是现成的 `find_consumer_endpoint()` / `read_consumer_report()` /
`parse_consumer_report()`（与 `keyboard_driver\driver.py` 同一套），**没有改动 50 ms 轮询节奏与
非阻塞控制台模型**。退出时置停止位并 join，确保不残留线程与接口占用；`find_consumer_endpoint`
找不到（含 Win7 上 claim/探测读失败）或读取报错时只降级为"只读键盘"，在轮次开头与日志里
如实写「消费类监听：未启动（原因）」，键盘侧采集照常进行。

工具边界（一个问题只归一个脚本）：

- **设备节点/驱动绑定**（WinUSB/HidUsb/usbccgp、问题码、Zadig 条数）→ `enum_usb_nodes.py`；
  需要键盘/鼠标/HID 类设备列表时加 `--classes`。
- **HID 集合/端点/包长/Report ID/可读性** → `probe_keyboard.py`；它不再装键盘钩子，
  键盘集合不可读时直接提示改用 `compare_native.py record`。
- **原始报文与描述符实验**（WinUSB 绑定下）→ `native_probe.py`（`info` / `capture` / `led`）；
  HidUsb 绑定下没有 pyusb 可用，用 `probe_keyboard.py` 的 `ReadFile` 抓包。
- **键语义**（usage ↔ 物理键 ↔ `usage`）→ `calibrate`，四个入口分工：
  单键采集 `--learn`（发现未知键，Fn 组合/自定义键也能按，可起名并产出草稿）→
  分类采集 `--learn --categories`（一般键盘常规键按类全覆盖核对）→
  默认向导（验证六个已知切层键）→ `--watch`（纯被动翻译，不判定）。
- **注入侧 VK 序列**（系统最终收到什么、注入标记、重复节奏）→ `compare_native.py record`；
  它是仓库里唯一安装 LL 键盘钩子的脚本。

`tools\native_probe.py` 只用于复盘实验：它直接 claim 接口，不能和 `python -m keyboard_driver` 同时运行；
日常排障优先用 `probe_keyboard.py`（HID 集合）、`enum_usb_nodes.py`（驱动绑定）、
`calibrate`（逐键核对 / 采集）、`check_device_profile.py`（离线自检）。

## 存档版本：软切换路线（tag `archive-soft-layer-switch`）

当前 master 的层切换交给**固件**，前提是主机能把 1 字节 LED 输出报告写进设备——这条路径已在
Win7 SP1 x64 的实机回归中验证（源码形态，见「验证记录」）。存档版本走另一条路线：**纯软件重映射**，
只读输入报告，不读也不写 LED，由程序内部的层表把同一个物理键翻译成字母键或小键盘键位
（层切换键不改变系统 Num Lock 状态）。它因此完全不依赖 LED 回路，代价是主机侧多一套层状态与层表。

**用户报告：Win7 上源码形态（python + venv）与打包 exe 两种形态都跑过，该方案的层切换 /
长按自动重复 / 媒体键三项均实测通过。** 这只覆盖存档版本；master 的源码形态已在 Win7 实测通过
（见「验证记录」），但 exe 形态仍未在 Win7 验证，两者的验证状态不能互相顶替。

推论：在 LED 写不通的目标机上，master 的切层不会生效，那台机器上该用的是存档这一版。
所以这个 tag 是**实现路线的备份**，不只是历史存档点。

取回方式（项目根执行，任选其一）：

```bat
rem 只看不改：切到 tag（分离头指针），看完用 git switch - 回来
git switch --detach archive-soft-layer-switch

rem 或从 tag 建一条分支，继续使用或继续改
git switch -c soft-layer-switch archive-soft-layer-switch
```

与当前 master 的主要差异：

| 项目 | 存档软切换版 | 当前 master（原生语义版） |
|---|---|---|
| 层切换 | 主机软件重映射（存档分支的 `device_profile\keys.py`，`LAYER_TOGGLE_HID`，不改系统 Num Lock） | 固件按 LED 灯位完成，主机回写 LED |
| 指示灯回写 | 默认关闭；`--led` 打开也标注“本设备无效果” | 默认开启（`--no-led` 可关），是切层的前提 |
| 映射表位置 | 存档分支的 `device_profile\keys.py`，按层维护 `C` / `XL` / `XN` 子集 | `keyboard_driver\usage.py`，通用 usage 表、无层概念 |
| 对 LED 回路的依赖 | 无 | 有（LED 写失败则切层失效） |

## 运行时风险与前提

| 风险 | 影响 | 触发条件 | 当前是否缓解 |
|---|---|---|---|
| Secure Desktop 下注入被丢弃 | UAC 提权框、锁屏、Ctrl+Alt+Del 界面上键盘完全无反应（不是丢键，是系统不接受注入） | 出现安全桌面 / 登录界面 / 锁屏 | **未缓解**：注入类方案的固有限制，要彻底解决需改成 HID 兼容驱动 |
| 注入事件带 `LLKHF_INJECTED` | 只接受物理输入的软件会忽略本程序注入的按键，表现为该程序内无输入、其它程序正常（"驱动没坏但按键无效"） | 游戏/反作弊、部分安全软件、安全输入框、远程运维工具、按注入标记过滤的程序 | **未缓解**：所有注入按键都走 `keybd_event`，事件必然带 `LLKHF_INJECTED`，无法去掉；自查用 `tools\compare_native.py record` 看事件标记，该工具在本机实测采不到事件时改用对照法（同一按键换原生键盘或另一程序各试一次） |
| 进程停止后无原生回退 | 程序退出、崩溃或被杀后接口仍绑在 WinUSB，这把键盘完全没有输入，系统不会自动恢复原生 HID 键盘 | 进程异常结束、任务被结束、注销后未重新登录 | **未缓解**：重新启动 `python -m keyboard_driver.run`（或计划任务）或拔插接收器后重启程序即可恢复；要彻底回到原生驱动，按 [INSTALL-WIN7.md](docs/INSTALL-WIN7.md) 第 5 节卸载 WinUSB 驱动 |
| 非美式布局下的符号键 | `usage` 是美式 usage 表，OEM 符号键在其它布局下 VK→扫描码可能不同，表现为键帽与字符不符 | 系统键盘布局不是美式（含 IME 切换布局） | 部分：字母、数字、功能键不受影响；符号键需在目标布局下用 `tools\calibrate\` 逐键核对，必要时扩展映射 |
| 独占接口 + 单实例 | 第二个实例会提示"已有另一个实例在运行"并退出；官方驱动或其它程序占用同一接口时按键无反应 | 重复启动、未卸载官方驱动、残留进程 | **已缓解**：启动时取命名互斥体（`Local\KeyboardDriver_1EA7_0066`），冲突即退出；接口被占时 claim 失败仍尝试读取并打印告警 |
| 消费类线程的恢复能力有限 | 拔插接收器后若设备节点被重新枚举，媒体键会一直失效，直到主循环整体重连 | 拔插接收器、接口重置 | 部分：读失败每 1 秒原地重试并只告警一次；不在消费线程里重开设备（同进程二次打开会互相干扰），节点被替换时靠主循环重连 |
| 断线重连期间的按键丢失 | 重连窗口（5 秒）内按键不生效；异常路径下可能来不及抬起已注入的键 | 接收器被拔、休眠唤醒、2.4G 丢连 | 部分：USBError 自动重连，退出/中断路径会 `release_all_keys()` |
| 线程与全局状态无锁 | 主线程与消费类线程共享 `_consumer_*`、重复计时等模块级变量，"读-判-写"可能交错，极端情况下多/漏一次重复注入 | 媒体键与普通键几乎同时操作 | 部分：GIL 保证单次赋值原子，影响面限于重复节奏，不会卡死或残留按键 |
| 需在交互式桌面会话中运行 | 以系统服务 / session 0 启动时注入无效，表现为"进程正常但不打字" | 用服务方式注册自启 | 已缓解：文档要求用 `schtasks` 注册**登录**自启（见 INSTALL-WIN7） |
| 长时间运行未测 | 只有空闲 60 秒的 CPU 采样与短时按键验证，数小时/过夜的内存与句柄增长没有实测数据 | 长期驻留 | **未测**：无实测结论，不建议在关键场合长期无人值守 |
| 层切换依赖固件行为 | 换键盘或固件升级后"按灯位切层"可能不成立，表现为 Num Lock 下字母区仍出字母 | 更换设备 / 固件变更 | 部分：`check_device_profile.py` 与 `tools\calibrate` 可快速复核，无运行时自动检测 |

未验证范围（不阻塞，但不要当成已验证）：**当前版本打包产物在 Win7 上的运行**
（存档版曾在 Win7 以 exe 形态运行过，但那是旧代码与旧构建，不能替当前版本验收）、
3.4 推荐的 `libusb\<arch>` 项目目录方案在 Win7 上的效果（已通过的实机回归用的是系统
`C:\Windows\System32\libusb-1.0.dll`）、登录自启（`schtasks`）与断线重连在 Win7 上的表现、
外置键盘 bit1/bit2 灯位的物理反馈（该键盘只有 Num Lock 一颗灯，无观测通道）。
master 源码形态在 Win7 上已实测通过；此后的结构重构经核对等价（见「验证记录」的「重构等价性」），
结论继续适用——入口命令与目录名不同，但逻辑相同。结论与边界见「验证记录」。

## 已知限制与故障排查

- 指示灯会随系统锁定状态回写（实测可见）；若灯不亮，先确认启动日志里没有
  `指示灯同步被 --no-led 关闭`，再用 `tools\native_probe.py led` 单独验证回写。
- **当前版本的 Win7 exe 形态未验证**：master 的源码形态已在 Win7 SP1 x64
  实测通过（打字、指示灯跟随、灯位切层、长按自动重复、六个媒体键，见「验证记录」）；
  源码形态的重构经核对逻辑等价，结论继续适用（入口由 `src\keyboard.py` 换成
  `python -m keyboard_driver`，尚未在 Win7 单独复跑，但不属于“未验证”）；打包产物、登录自启、`libusb\<arch>` 目录方案
  仍未在 Win7 验证。存档的软切换版另有源码与 exe 两种形态的 Win7 实测，但那是另一套实现，不能搬过来。
  若媒体键无效，先用 `tools\probe_keyboard.py` 看是否识别到消费类接口。
- **注入按键可能被“只认物理输入”的软件丢弃**：所有注入按键都走 `keybd_event`，事件带
  `LLKHF_INJECTED` 标记。部分游戏/反作弊、安全输入框、远程运维工具会直接忽略这类事件——
  表现是“驱动没坏（其它程序能打字），但目标程序里按键无效”。自查：用
  `tools\compare_native.py record` 看事件是否带注入标记；该工具在本机实测采不到事件，采不到时
  改用对照法（同一按键换原生键盘或换一个程序各试一次）。
- **离线依赖未随包提供**：`wheels\`、`installer\` 不再存在；离线安装请自备 pyusb 的 cp38 whl，
  用 `pip --no-index --find-links <目录>` 安装（见 `docs\INSTALL-WIN7.md` 3.3）。
- `tools\compare_native.py` 的“原生 vs 本实现”差异报告尚未执行（仅用合成数据自测过逻辑）。
- **当前版本的 exe 打包未实测**：frozen 路径代码（`keyboard_driver\paths.py`、`keyboard_driver\run.py`）已在本机验证，
  但本轮未执行真实打包；Python 3.8.10 + PyInstaller 5.x 的实际构建、onedir/onefile 的 DLL 加载
  与 Win7 日志位置仍需在目标机验证（见 [BUILD-WIN7.md](docs/BUILD-WIN7.md) 第 9 节）。
  存档软切换版曾在 Win7 以 exe 形态运行过，但那是旧代码与旧构建，不能作为当前版本的打包验收；
  master 在 Win7 上通过的只是源码形态，见「验证记录」。
- **`tools\compare_native.py record` 在本机未能采到事件**：钩子安装返回成功，但注入按键也收不到；
  本轮音量长按数据改用独立的全局钩子采集器取得。使用 `record` 前请先用一次按键自检，见上方用法。
- 报 “设备未找到”：确认 Zadig 绑定仍在（换电池/拔插会重新枚举，可能被系统绑回 HID 驱动），
  必要时重绑；用 `tools\probe_keyboard.py` 确认 `1EA7:0066` 是否可见。
- 按键无反应但进程正常：检查是否被别的程序（另一份 `python -m keyboard_driver`、官方驱动）占用了同一接口。
- 注入按键不重复：确认是外置键盘（本机键盘走的仍是原生路径，与本程序无关）。
- 性能实测（Win11，空闲 60 秒采样）：CPU 占用约 0%（旧版轮询式实现为单核 5.3%）。
