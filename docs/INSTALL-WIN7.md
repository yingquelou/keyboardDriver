# Windows 7 安装 / 卸载（手工步骤）

本项目**不再提供安装脚本**（`install\` 目录已删除）。本文从零开始给出可照做的命令行步骤：
装 Python、建虚拟环境、装依赖、用 Zadig 绑定驱动、启动程序、注册登录自启、卸载并恢复原生驱动。

所有命令都在**项目根目录**（含 `src\`、`tools\`、`docs\` 的那一级）执行。PowerShell 与 cmd 均可，
下面统一用 `cmd` 语法；PowerShell 里反斜杠路径同样可用。

## 1. 分发目录里需要有什么

```
keyboard-driver-win7\
├─ README.md
├─ src\                       # 运行期代码：keyboard.py / keyboard_utils.py / device_profile\（设备包）
│  ├─ win32_compat.py         # pywin32 缺失时的兼容层
│  ├─ app_paths.py            # 源码与打包两种形态的路径处理
│  └─ run_keyboard.py         # 写日志后启动 keyboard.main()（计划任务入口）
├─ tools\                     # 诊断脚本（可选）：probe_keyboard.py / calibrate.py / compare_native.py / enum_usb_nodes.py
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
| libusb-1.0.dll | 1.0.26 线优先 | pyusb 通过 `ctypes` 加载它，**必须与 Python 位数一致**；Win7 上建议使用仍支持 Win7 的 1.0.26 系列 |
| pywin32 | 可选 | 缺省时程序自动退回 `src\win32_compat.py`（ctypes 版 `keybd_event`），行为等价 |
| Zadig | 2.9 | **只负责内核驱动绑定，不提供 `libusb-1.0.dll`**；两者是两件事 |

### libusb-1.0.dll 从哪里来

按优先级任选一种：

1. **系统 / PATH 中已有** —— 零配置，但不可控；常见于装过 QEMU、其它 USB 工具链的机器。
2. **libusb-package（pip 安装）** —— `python -m pip install "libusb-package<1.0.27"`，
   包内自带对应位数的 DLL。注意：源码运行**不会自动**使用包内 DLL（`src\keyboard_utils.py`
   直接调用 `usb.backend.libusb1.get_backend()`，未传 `find_library`），仍需把 DLL 放到系统目录
   或 PATH；打包时可用 `--add-binary` 显式取包内文件。
3. **随包放置** —— 从 libusb 官方 Windows 二进制包解压后放到
   `libusb\x86\libusb-1.0.dll`（32 位 Python）或 `libusb\x64\libusb-1.0.dll`（64 位 Python），
   运行前把该目录加入 PATH（见 3.5）。**不要放进 `C:\Windows`**，避免与其它工具冲突。

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

### 3.4 准备 libusb DLL（若系统/PATH 没有）

```bat
:: 以 64 位 Python 为例；32 位改成 libusb\x86
set "PATH=%CD%\libusb\x64;%PATH%"
.venv\Scripts\python.exe -c "import usb.backend.libusb1 as b;print(b.get_backend())"
```

输出 `None` 说明 DLL 没被找到；检查位数、路径拼写，或改放到系统目录。

### 3.5 用 Zadig 绑定驱动

**先记住恢复方法**（第 5 节），再执行绑定。Interface 1 同时承载鼠标/系统控制等输入，
绑定后这部分输入交给 libusb，请用笔记本自带键盘/触控板完成操作。

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

### 3.6 先试跑（不注册任务）

```bat
set "PATH=%CD%\libusb\x64;%PATH%"
.venv\Scripts\python.exe src\keyboard.py
```

出现 `找到设备`、`中断端点: 0x81`、`媒体键使用接口 1，端点 0x82`、`开始监听键盘` 即正常；
Ctrl+C 退出，退出前会抬起所有注入按键。

计划任务入口是 `src\run_keyboard.py`：它在项目根写 `logs\keyboard.log` 后调用 `keyboard.main()`。
手动验证日志可运行：

```bat
.venv\Scripts\python.exe src\run_keyboard.py
```

**日志位置**：`<项目根>\logs\keyboard.log`（超过 1 MB 滚动为 `keyboard.log.1`）。
直接运行 `src\keyboard.py` 只输出到控制台，不写日志。

### 3.7 注册登录自启（手工 schtasks）

**源码形态**（依赖 `.venv`，路径必须写绝对路径；移动项目目录后要重建任务）：

```bat
schtasks /Create /TN KeyboardDriver /TR "\"%CD%\.venv\Scripts\pythonw.exe\" \"%CD%\src\run_keyboard.py\"" /SC ONLOGON /RL HIGHEST /F
```

- `pythonw.exe`：无控制台窗口；日志由 `run_keyboard.py` 写入文件。
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

## 4. 运行前提与行为

- **不需要管理员权限**：WinUSB 绑定后已写入允许普通用户访问的权限，实测可 claim 并读取接口。
- 程序独占读取接口；同一时间只能有一个实例（另一份 `keyboard.py`、官方驱动都会抢接口）。
- 断线后每 5 秒自动重连；退出（Ctrl+C / 结束任务）前会抬起所有已注入按键。
- 绑定后系统不再提供原生键盘/媒体键行为，一切按键由本程序注入。

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
| `libusb` 后端为 `None` | `libusb-1.0.dll` 位数与 Python 不符或不在 PATH/系统目录；按 3.4 处理 |
| `Access denied` / 访问被拒 | 已有另一个实例占用接口：先结束旧进程；或确认任务以最高权限运行 |
| 媒体键无效 | 先用 `tools\probe_keyboard.py` 看是否识别到消费类接口（端点 0x82、Report ID 1） |
| 登录后没启动 | `schtasks /Query /TN KeyboardDriver /V /FO LIST` 看状态；看 `logs\keyboard.log` |
| 指示灯不亮 | WinUSB 接管后本设备指示灯不可控，属已知限制，不是故障 |

## 7. 验证状态（如实标注）

本文档的命令在开发机（Windows 11）上做过静态核对（文件与参数真实存在）；下列内容
**未在 Windows 7 实机验证**，首次部署请按顺序逐项确认：

- Python 3.8.10 安装、`pip<24.1` 升级与 pyusb 安装；
- `libusb-1.0.dll` 位数匹配与 PATH 生效；
- Zadig 两种绑定形态后的设备枚举；
- `schtasks /SC ONLOGON /RL HIGHEST` 登录后确实以最高权限运行；
- `logs\keyboard.log` 正常写入、卸载后原生 HID 键盘恢复。
