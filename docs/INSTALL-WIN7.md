# Windows 7 安装 / 卸载（手工步骤）

> **验证状态**：同一份代码在 **Windows 7 SP1 x64** 实机上以**源码形态**跑通——旧 venv 的
> Python 3.8.10 直接运行 `src\keyboard.py`（实测时的入口）、登录会话 1 控制台、WinUSB 接管；
> 打字、指示灯跟随、灯位切层、长按自动重复、六个媒体键全部通过。此后代码只做了结构重构
> （拆包、改名、换入口），主链路逻辑等价，因此**该结论对当前版本继续适用**；入口命令现在是
> `python -m keyboard_driver`，目录结构也不同，但那是同一逻辑的另一种启动方式，不是“未验证”。
> 等价性依据见 [README](../README.md) 的「重构等价性」；首次部署仍建议做一次短跑确认。
> 记录与边界见 [README](../README.md) 的「验证记录」。
>
> **本文仍有未在 Win7 实机执行过的步骤**：3.4 推荐的 `libusb\<arch>` 项目目录方案（已通过的实机用的是
> 系统 `C:\Windows\System32\libusb-1.0.dll`）、3.8 的 `schtasks` 登录自启、以及打包 exe 形态
> （见 [BUILD-WIN7.md](BUILD-WIN7.md)）。判定规则按方案、版本、形态生效：除非某次提交或文档明确写出
> 哪个版本、哪台机器、什么形态的实测，否则按未验证对待；结构重构若经核对等价，不作废已有实测。

本项目**不再提供安装脚本**（`install\` 目录已删除）。本文从零开始给出可照做的命令行步骤：
装 Python、建虚拟环境、装依赖、用 Zadig 绑定驱动、启动程序、注册登录自启、卸载并恢复原生驱动。

所有命令都在**项目根目录**（含 `keyboard_driver\`、`tools\`、`docs\` 的那一级）执行。PowerShell 与 cmd 均可，
下面统一用 `cmd` 语法；PowerShell 里反斜杠路径同样可用。

## 1. 分发目录里需要有什么

```
keyboard-driver-win7\
├─ README.md
├─ keyboard_driver\           # 驱动包（可执行模块）：__main__.py 入口，device_profile\ 内为设备包
│  ├─ driver.py               # 运行期编排：主读取循环、线程、断线重连
│  ├─ transport.py            # HID 运输与原语：枚举、claim、读取解析、按键注入
│  ├─ usage.py                # 通用 HID usage → Windows VK 映射
│  ├─ win32_compat.py         # pywin32 缺失时的兼容层
│  ├─ paths.py                # 源码与打包两种形态的路径处理
│  └─ run.py                  # 写日志后启动 driver.main()（计划任务/打包入口）
├─ tools\                     # 诊断脚本（可选）：probe_keyboard.py / calibrate\（包） / compare_native.py / enum_usb_nodes.py
├─ docs\                      # 本文与 BUILD-WIN7.md
├─ zadig-2.9.exe              # 驱动绑定工具（只做绑定，不含 libusb DLL）
├─ libusb\x86\libusb-1.0.dll  # 可选：32 位 Python 用
├─ libusb\x64\libusb-1.0.dll  # 可选：64 位 Python 用
├─ logs\                      # 运行时生成
└─ .venv\                     # 手工创建
```

`Zadig` 与 `libusb-1.0.dll` 都可以从官方站点单独下载，不必随包。

## 2. 依赖与版本

| 组件 | 版本口径 | 说明 |
|---|---|---|
| Python | **3.8.10** | 最后一个官方支持 Windows 7 的 Python；**位数决定后续一切**（32/64 位） |
| pyusb | 不指定 | 纯 Python。3.8 上 pip 会选 **1.2.1**（1.3.x 要求 Python ≥ 3.9）。本项目用到的 `find_all`、`ctrl_transfer`、`read(timeout=)` 等 API 两个版本语义一致，无需锁版本 |
| libusb-1.0.dll | 1.0.26 线优先 | pyusb 通过 `ctypes` 加载它，**必须与 Python 位数一致**；建议用仍支持 Win7 的 1.0.26 系列。已跑通的 Win7 实机用的是系统自带的 1.0.30 x64（见 README「验证记录」），所以 1.0.26 这个建议本身仍未在 Win7 实测 |
| pywin32 | 可选 | 缺省时程序自动退回 `keyboard_driver\win32_compat.py`（ctypes 版 `keybd_event`），行为等价 |
| Zadig | 2.9 | **只负责内核驱动绑定，不提供 `libusb-1.0.dll`**；两者是两件事 |

### libusb-1.0.dll 从哪里来

按优先级任选一种：

1. **系统 / PATH 中已有** —— 零配置，但不可控；常见于装过 QEMU、其它 USB 工具链的机器。
   **已跑通的 Win7 实机用的就是这一种**（`C:\Windows\System32\libusb-1.0.dll`，1.0.30 x64）。
2. **libusb-package（pip 安装）** —— `python -m pip install "libusb-package<1.0.27"`，
   包内自带对应位数的 DLL。注意：源码运行**不会自动**使用包内 DLL（`keyboard_driver\transport.py`
   直接调用 `usb.backend.libusb1.get_backend()`，未传 `find_library`），需要把包里的 DLL
   复制到项目 `libusb\x64`（或 `x86`）、系统 PATH 或 venv 目录，见 3.4；打包时可用
   `--add-binary` 显式取包内文件。
3. **随包放置** —— 从 libusb 官方 Windows 二进制包解压后放到
   `libusb\x86\libusb-1.0.dll`（32 位 Python）或 `libusb\x64\libusb-1.0.dll`（64 位 Python）。
   **推荐这种放法**：源码形态启动时会自动搜索该目录（见 3.4）。**不要放进 `C:\Windows`**，
   避免与其它工具冲突。

位数对照：64 位 Python → 64 位 DLL；64 位系统上的 32 位 Python → 仍要 32 位 DLL。
DLL 加载失败时补装 VC++ 2015-2019 运行库。

## 3. 手工安装（在目标机）

### 3.1 安装 Python 3.8.10

1. 安装 `python-3.8.10.exe`（32 位）或 `python-3.8.10-amd64.exe`（64 位），勾选
   **Add Python 3.8 to PATH**。
2. 确认版本与位数：

   ```bat
   python -c "import sys,struct;print(sys.version, 8*struct.calcsize('P'))"
   ```

   应输出 `3.8.10 ... 64`（或 `32`）；位数必须与准备使用的 `libusb-1.0.dll` 一致。

### 3.2 创建虚拟环境（可选但推荐）

```bat
python -m venv .venv
.venv\Scripts\python.exe -c "import sys;print(sys.version)"
```

不用虚拟环境也可以，后续命令把 `.venv\Scripts\python.exe` 换成 `python` 即可。
（在 MSYS/Git Bash 里创建的虚拟环境可执行文件在 `.venv\bin\python.exe`。）

### 3.3 安装依赖

```bat
.venv\Scripts\python.exe -m pip install --upgrade "pip<24.1" setuptools wheel
.venv\Scripts\python.exe -m pip install pyusb
```

- `pip<24.1`：旧 pip 在 Win7 上常因 TLS 失败，先升级这一层；若仍报 SSL/TLS 错误，
  安装 Win7 补丁 `KB3140245`，或改用国内镜像
  `-i https://pypi.tuna.tsinghua.edu.cn/simple`。
- 完全离线时用 `-m pip install --no-index --find-links <离线 whl 目录> pyusb`。
- `pywin32` 可不装；确需安装时 `.venv\Scripts\python.exe -m pip install pywin32`。

### 3.4 准备 libusb DLL（源码形态推荐放项目目录）

**推荐：把 DLL 放到项目的 `libusb\x64`（64 位 Python）或 `libusb\x86`（32 位 Python），
文件名保持 `libusb-1.0.dll`。**

> **这条推荐方案尚未在 Win7 实机验证过。** 目前唯一跑通的 Win7 实机（master 源码形态，见
> [README](../README.md)「验证记录」）用的是系统已有的 `C:\Windows\System32\libusb-1.0.dll`
> （1.0.30 x64），项目目录里没有放 DLL。所以下面的自查命令在 Win7 上仍属"待验证"，
> 只是逻辑与 Win11 上一致；首次部署请先看它是否输出非 `None`。

源码形态启动时，`keyboard_driver\paths.py` 的 `prepare_native_dlls()` 会按解释器位数把该目录加入
DLL 搜索路径。这条机制专门为登录自启准备：`schtasks` 拉起的进程不继承交互 shell 里的 PATH。
打包形态的行为不变，仍从 exe 同级、`_internal` 或 `_MEIPASS` 找 DLL。

自查（不依赖当前 shell 的 PATH）：

```bat
.venv\Scripts\python.exe -c "from keyboard_driver import paths;paths.prepare_native_dlls();import usb.backend.libusb1 as b;print(b.get_backend())"
```

输出一个 `<pyusb ...>` 对象表示生效；输出 `None` 表示没找到，先核对位数（3.1）与文件名。

另外两种放法可用，但各有代价：

- **系统 PATH**：把 DLL 所在目录加入系统 PATH（不要直接丢进 `C:\Windows`）。所有程序都能用，
  但全局生效、需要管理员权限，且位数错误时更难发现。
- **`python.exe` 同目录**：把 DLL 放到 `.venv\Scripts\`（与 `python.exe` 同级）。
  LoadLibrary 会先在可执行文件目录里找；缺点是重建虚拟环境或升级 Python 后要重放，
  且只对这一个 venv 有效。

### 3.5 用 Zadig 绑定驱动

**先记住恢复方法**（第 5 节），再执行绑定。Interface 1 同时承载鼠标/系统控制等输入，
绑定后这部分输入交给 libusb，请用笔记本自带键盘/触控板完成操作。

**64 位 Windows 7 要先过 3.6 节的驱动签名硬门槛**，否则这一步只会得到带黄色感叹号的设备。

Zadig 2.9 只有图形界面，没有命令行参数。勾选 `Options → List All Devices` 后，有两种等效形态，
**任选一种**：

- **形态 A：按接口绑定（推荐）**
  1. 选中 `1EA7:0066` 的 `Interface 0` → 驱动选 `WinUSB` → `Replace Driver`；
  2. 选中 `Interface 1` → 同样 `Replace Driver`；
  3. 两次都完成后拔插接收器。
  绑完后系统里有两个 `MI_00` / `MI_01` 节点，服务名均为 `WinUSB`。
- **形态 B：整设备绑定**
  选中列表中不带 `Interface` 后缀的 `1EA7:0066` 父设备 → `WinUSB` → `Replace Driver`。
  绑定后 Windows 不再枚举 `MI_xx` 子节点，但 pyusb 仍能看到该设备的两个接口。

两种形态程序都能工作；只想确认当前是哪种，用只读诊断脚本：

```bat
.venv\Scripts\python.exe tools\enum_usb_nodes.py
```

- 两个 `MI_xx` 都在且 `service=WinUSB` → 按接口绑定；
- 只有父节点且 `service=WinUSB` → 整设备绑定；
- 都没有 → 未绑定，或设备未插好。

### 3.6 Win7 x64 驱动签名（硬门槛，先读）

**先弄清对象：本项目不写内核驱动。** 全部代码在用户态（pyusb/libusb + `keybd_event`），仓库里
没有任何 `.sys`、`.inf` 或 catalog。签名要求针对的不是“我们的驱动”，而是 **`1EA7:0066` 的设备
绑定包**：Zadig（libwdi）生成 `oemXX.inf` + `.cat`，复用微软自带的 `winusb.sys`，把这个设备从
`HidUsb` 换绑到 `WinUSB`。问题因此是“**这个安装包能不能被系统接受**”，而不是“我们自研的驱动
有没有签名”。不换绑，就不存在这条要求。

64 位 Windows 7 内核对这个驱动包强制要求**受信任的签名链**：

- 受信任的含义是证书能追溯到系统信任的根（WHQL 或受信任的发布者证书）；
- 未签名、或签名链断在不受信任的根证书上的驱动会被拒绝加载，设备管理器里显示黄色感叹号、
  错误码 52（“Windows 无法验证此设备所需的驱动程序的数字签名”）；
- 32 位 Win7 不强制内核驱动签名，所以“同一个 Zadig 包在 32 位能用、64 位不能用”是正常现象。

libwdi/Zadig 的常规做法是**自签名**：生成一张自签名证书去签 catalog，并把证书装进本机的
“受信任的根证书颁发机构”与“受信任的发布者”，让签名链在本机闭环。这个组合在 Win7 x64 上
**通常**能通过校验：已知一台 Win7 SP1 x64 实机上用它装出的 `oem19.inf` 通过校验并正常工作
（见本节末尾）。但 Zadig 2.9 的具体行为（是否默认自签、是否提示导入证书、证书装到哪个存储）
本项目没有逐项记录，装不上时按表中 B/C 处理，不要假设“Zadig 装完就能用”。

三条可选路径，按能接受的代价选一条：

| 做法 | 操作 | 代价 / 风险 |
|---|---|---|
| **A. 使用已签名驱动（首选，若拿得到）** | 向设备/驱动提供方索取已签名的 WinUSB 驱动包；或在有代码签名证书的机器上用 `Inf2Cat` + `signtool` 对 libwdi 生成的 INF 重新签名后再安装 | 最干净、可长期使用，安装后与其他驱动无异；但需要受信任的代码签名证书（个人环境通常没有）。仓库**未附任何已签名驱动** |
| **B. 测试签名模式** | 管理员执行 `bcdedit /set testsigning on` → 重启 → 给驱动包签一张自签名证书并将证书装入“受信任的根证书颁发机构”“受信任的发布者” → 再按 3.5 安装 | 桌面右下角常驻“测试模式”水印；系统对驱动签名的校验被削弱，任何自签名驱动都能装，安全边界由本机使用者承担；不适合长期生产机 |
| **C. 临时禁用签名强制（仅调试）** | 开机时按 F8 → 选“禁用驱动程序签名强制” → 本次启动内完成 3.5 的安装 | 只对本次启动有效，重启后驱动无法再加载；无法与 3.8 的登录自启配合；不建议作为长期方案 |

判读与操作要点：

- 先确认是不是 64 位：`wmic os get osarchitecture`。只有 64 位 Win7 受这条约束。
- 当前策略可查：`bcdedit /enum {current}`，看 `testsigning` 是否为 `Yes`。
- 装完回 3.5 用 `tools\enum_usb_nodes.py` 复核 `service=WinUSB`；装不上时先看设备管理器
  属性页的“数字签名”页签与错误码，再决定换哪条路径。
- 本节只写要求与操作路径。**Win7 x64 上“签名方式 + 安装结果”的组合未在本项目实机复现过**，
  不要按“已验证可用”理解。
- 已知的一台 Win7 SP1 x64 实机上，WinUSB 是事前用 Zadig 装好的（生成 `oem19.inf`），签名这一关
  **在那台机器上已通过**——master 源码形态随后跑通（见 [README](../README.md)「验证记录」）。
  这只说明"该机器上的既成绑定可用"，不构成"Win7 x64 一律可用"的证据：重装系统、换 USB 口重装驱动、
  或换另一台机器，都要重新按本节处置。

**替代路径：不绑 WinUSB，就完全不碰签名。** 保持 `HidUsb` 原生驱动时，`tools\probe_keyboard.py`
只走 Windows HID API（不需要 Zadig、不需要签名），可以枚举集合、端点、包长并做诊断。代价是：
键盘/消费类集合由系统 HID 类驱动独占，用户态打不开、读不到原始报告，也无法代替系统向设备写
那 1 字节 LED 输出报告——而这正是固件按 Num Lock 灯位切层的唯一手段。所以在 Win7 x64 上，
“省掉签名”与“用本项目的用户态实现接管、并保住切层”是**互斥**的：要么满足签名要求换绑
WinUSB，要么放弃本项目、回到原生 HID 行为。

### 3.7 先试跑（不注册任务）

```bat
.venv\Scripts\python.exe -m keyboard_driver
```

DLL 不需要在这里手工 `set PATH`：`keyboard_driver\paths.py` 的 `prepare_native_dlls()` 在源码形态下
会按解释器位数自动加入项目 `libusb\x64` 或 `libusb\x86`（见 3.4）。这一步与计划任务启动的
搜索路径完全一致，所以这里能跑通，3.8 的自启也能跑通。

出现 `找到设备`、`中断端点: 0x81`、`媒体键使用接口 1，端点 0x82`、`开始监听键盘` 即正常；
Ctrl+C 退出，退出前会抬起所有注入按键。

这一步就是已经实测通过的那条路径（Win7 SP1 x64、登录会话 1 控制台、源码形态），区别只在于
那台机器没有放项目 `libusb\<arch>`，用的是系统 `C:\Windows\System32\libusb-1.0.dll`。
若你把 DLL 放在项目目录，启动行完全一样，DLL 由 `prepare_native_dlls()` 自动找到（见 3.4）。

计划任务入口是 `keyboard_driver\run.py`：它在项目根写 `logs\keyboard.log` 后调用 `driver.main()`。
手动验证日志可运行：

```bat
.venv\Scripts\python.exe keyboard_driver\run.py
```

**日志位置**：`<项目根>\logs\keyboard.log`（超过 1 MB 滚动为 `keyboard.log.1`）。
直接运行 `python -m keyboard_driver` 只输出到控制台，不写日志。

### 3.8 注册登录自启（手工 schtasks）

**源码形态**（依赖 `.venv`，路径必须写绝对路径；移动项目目录后要重建任务）：
任务拉起的进程不继承交互 shell 的 PATH，DLL 由 `prepare_native_dlls()` 从项目
`libusb\x64`（或 `x86`）自动加入搜索路径（见 3.4、3.7），因此**不需要**把 DLL 目录写进系统 PATH。

```bat
schtasks /Create /TN KeyboardDriver /TR "\"%CD%\.venv\Scripts\pythonw.exe\" \"%CD%\keyboard_driver\run.py\"" /SC ONLOGON /RL HIGHEST /F
```

- `pythonw.exe`：无控制台窗口；日志由 `run.py` 写入文件。
- `/SC ONLOGON`：当前用户登录时触发；`/RL HIGHEST`：以最高权限运行（WinUSB 已允许普通用户访问，
  但最高权限可避免个别机器上的访问被拒）。
- 创建任务可能需要管理员：在“以管理员身份运行”的命令行里执行。

**打包形态**（见 [BUILD-WIN7.md](BUILD-WIN7.md)；onedir 必须整目录一起移动）：

```bat
schtasks /Create /TN KeyboardDriver /TR "\"<exe 所在目录>\KeyboardDriver.exe\"" /SC ONLOGON /RL HIGHEST /F
```

差异：源码形态多一层 Python 与 `.venv`，升级依赖后无需重建任务，但目录变动必须重建；
打包形态只指向 exe，启动更快，但 onedir 漏拷文件、onefile 依赖 `%TEMP%` 可写都会导致启动失败。

**验证 / 撤销**：

```bat
rem 立即运行一次
schtasks /Run /TN KeyboardDriver
rem 查看状态与上次结果
schtasks /Query /TN KeyboardDriver /V /FO LIST
rem 撤销自启
schtasks /Delete /TN KeyboardDriver /F
```

注销重登后确认进程在跑，并查看 `logs\keyboard.log`。

自查“登录自启这条路径是否真的能加载 DLL”（登录后、任务已运行时执行）：

```bat
findstr /C:"找到设备" logs\keyboard.log
```

有命中＝DLL 在无 shell 环境下确实被找到；日志里出现 `无法加载 libusb 后端` 或在
`发生未预期错误` 之间反复重试，则按 3.4 与第 6 节故障排查处理，不要去改系统 PATH 掩盖问题。

## 4. 运行前提与行为

- **不需要管理员权限**：WinUSB 绑定后已写入允许普通用户访问的权限，在 Win11 上实测可 claim 并读取接口；
  Win7 SP1 x64 上也已实测（master 源码形态，普通用户账户、登录会话 1 控制台）。
- 程序独占读取接口；同一时间只能有一个实例（另一份 `python -m keyboard_driver`、官方驱动都会抢接口）。
- 断线后每 5 秒自动重连；退出（Ctrl+C / 结束任务）前会抬起所有已注入按键。
- 绑定后系统不再提供原生键盘/媒体键行为，一切按键由本程序注入。
- 当前版本的切层依赖 LED 回写成功。已实测的那台 Win7 上回写可用（写 `01` 后 J 全报 `0x59`，
  驱动进程运行时的灯跟随与灯位切层也通过）；换机器/固件仍应先用 `tools\native_probe.py led` 复核，
  若确实写不通，切层不会生效，应改用存档的软切换版（tag `archive-soft-layer-switch`，见
  [README](../README.md) 的“存档版本”一节）。

## 5. 卸载与恢复原生驱动

1. 撤销自启：

   ```bat
   schtasks /Delete /TN KeyboardDriver /F
   ```

2. 结束正在运行的驱动进程（任务管理器里结束 `python.exe` / `pythonw.exe` / `KeyboardDriver.exe`）。
3. 设备管理器（`devmgmt.msc`）→ 在“键盘 / 人体学输入设备”下找到 `1EA7:0066` 的
   Interface 子设备（看不到时勾选“查看 → 显示隐藏的设备”）→ 右键“卸载设备” →
   勾选“删除此设备的驱动程序软件” → 确定 → **拔插接收器**，Windows 会自动装回 HID 驱动。
   整设备绑定（形态 B）时，父设备可能显示为单一 `1EA7:0066` 设备，卸载它即可。
4. 可选等效命令（删除驱动包，需管理员）：

   ```bat
   rem 找到 Provider 为 libwdi 的 oemXX.inf
   pnputil /enum-drivers
   pnputil /delete-driver oemXX.inf /uninstall /force
   ```

   说明：`/uninstall`、`/force` 在旧版 `pnputil`（含部分 Win7 版本）可能不被识别，去掉对应参数即可；
   `pnputil /scan-devices` 只在 Windows 10 及以上提供，Win7 用设备管理器“操作 → 扫描检测硬件改动”。
   删除驱动包后仍需在设备管理器卸载设备并拔插，否则设备不会立即还原。
5. 可选：删除 `.venv` 与 `logs\`。

## 6. 故障排查

| 现象 | 处理 |
| --- | --- |
| `pip` 报 SSL 错误 | Win7 默认未启用 TLS 1.2：装 `KB3140245`，或改用国内镜像，或离线 whl |
| 找不到设备 | 确认接收器已插好；Zadig 勾选 `List All Devices` 后按 3.5 重绑；用 `tools\enum_usb_nodes.py` 与 `tools\probe_keyboard.py` 核对 |
| `libusb` 后端为 `None` | 先跑 3.4 的自查命令：它按位数直接加项目 `libusb\x64`/`x86`，不走 shell PATH。输出仍为 `None` 时核对目录名、`libusb-1.0.dll` 文件名与位数（3.1），以及是否误装成 32 位 Python |
| 驱动安装被拒 / 设备黄色感叹号 | 64 位 Win7 的签名策略不满足：按 3.6 检查 `bcdedit /enum {current}` 的 `testsigning` 与设备属性页“数字签名”页签；32 位 Win7 不受此限 |
| `Access denied` / 访问被拒 | 已有另一个实例占用接口：先结束旧进程；或确认任务以最高权限运行 |
| 媒体键无效 | 先用 `tools\probe_keyboard.py` 看是否识别到消费类接口（端点 0x82、Report ID 1） |
| 登录后没启动 | `schtasks /Query /TN KeyboardDriver /V /FO LIST` 看状态；看 `logs\keyboard.log` |
| 指示灯不亮 | 确认启动日志里没有 `指示灯同步被 --no-led 关闭`（灯位回写默认开启，且是 Num Lock 切层的必要条件）；可用 `tools\native_probe.py led` 单独验证按 1 字节 Output 报告回写。已实测的那台 Win7 上回写可用；若你的机器回写确实无效，master 的切层不会生效，改用存档软切换版 |

## 7. 验证状态（如实标注）

本文档的命令在开发机（Windows 11）上做过静态核对（文件与参数真实存在）。

已成事实的部分（一台 Win7 SP1 x64 实机，详见 [README](../README.md)「验证记录」）：
Python 3.8.10 + pyusb 1.2.1 的 venv 可用；Zadig 事前的 WinUSB 绑定（`oem19.inf`）在该机器上签名过关；
实测时的入口 `src\keyboard.py` 在登录会话 1 控制台、普通用户权限下跑通全部行为。此后只有结构重构
（逻辑等价，见 [README](../README.md)「重构等价性」），当前入口 `python -m keyboard_driver` 尚未在该机
单独复跑，但这不改变已实测的行为结论。

**仍未在 Win7 实机执行、首次部署请逐项确认**：

- 3.4 推荐的 `libusb\<arch>` 项目目录方案与它的自查命令（已通过的实机用的是系统
  `C:\Windows\System32\libusb-1.0.dll`）；
- `schtasks /SC ONLOGON /RL HIGHEST` 登录后确实以最高权限运行；
- 计划任务启动后能读到设备（日志出现 `找到设备`）而不是 `未找到设备`，即 DLL 路径在无 shell 环境下确实生效；
- `logs\keyboard.log` 正常写入、卸载后原生 HID 键盘恢复；
- 打包 exe 形态（见 [BUILD-WIN7.md](BUILD-WIN7.md)）。
