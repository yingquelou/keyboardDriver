# 在目标系统上手工打包为 exe（PyInstaller）

> **未实机验证（针对 exe 形态）**：本文是打包步骤与版本建议，不是当前版本打包产物在 Win7 上的验证结论。
> 已知的 Win7 实测只有两条，且都不覆盖 exe 形态：**当前版本的源码形态**已在一台 Win7 SP1 x64 实机上跑通
> （登录会话 1 控制台，见 [README](../README.md)「验证记录」）；**存档版本曾在 Win7 以 exe 形态运行过**
> （tag `archive-soft-layer-switch`，用户报告层切换 / 长按自动重复 / 媒体键均通过），但那是旧代码与旧构建。
> **当前版本的打包产物未在 Win7 验证**，本文命令也未在 Win7 执行过；当前版本的实测基准是 Windows 11 + WinUSB 接管。

项目**不提供打包脚本**。本文给出可直接复制执行的 PyInstaller 命令，以及入口、隐藏导入、
libusb DLL 放置和版本建议。产物不随仓库分发；建议**在目标系统上构建**（理由见第 8 节）。

**前提（不可省略）**：exe 只是把 Python 与依赖封进可执行文件，**不能替代驱动绑定**。
目标机仍需先用 Zadig 把 `1EA7:0066` 绑到 WinUSB（按接口或整设备均可），否则 exe 找不到设备。
绑定、运行、自启与恢复步骤见 [INSTALL-WIN7.md](INSTALL-WIN7.md) 第 3、5 节。

## 1. 版本建议（只是建议，不写死）

| 组件 | 建议 | 理由 |
|---|---|---|
| Python | **3.8.10** | 最后一个官方支持 Windows 7 的 Python；产物依赖它自带的 `python38.dll`。**位数决定 exe 位数** |
| PyInstaller | `"pyinstaller<6"`（当前解析到 5.13.2） | 5.13.2 是最后一条 5.x 稳定线，Win7 成功案例最多。**不加约束时** 3.8 上 pip 会装 6.x：6.x 换过 bootloader，对 Win7 没有任何兼容承诺 |
| pyusb | 不指定 | 3.8 上 pip 会选 1.2.1（1.3.x 要求 ≥3.9）。程序用到的 API 两版一致 |
| libusb-1.0 | 1.0.26 线优先 | 与 Win7 兼容的版本线；已跑通的 Win7 源码形态用的是系统 `C:\Windows\System32` 的 1.0.30 x64，打包形态未验证（见第 9 节）；来源见第 3 节 |

PyInstaller 5.x 与 6.x 的官方文档都只写 **Windows 8 及以上**
（5.13.2：<https://pyinstaller.org/en/v5.13.2/requirements.html>），Win7 不在官方承诺内。
5.x 的实际成功案例远多于 6.x，因此建议 5.x——这是工程建议，不是保证。

## 2. 准备构建环境

在目标机（或与目标机同位数、同 Python 版本的构建机）上：

```bat
python -c "import sys,struct;print(sys.version, 8*struct.calcsize('P'))"
python -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade "pip<24.1" setuptools wheel
.venv\Scripts\python.exe -m pip install pyusb
.venv\Scripts\python.exe -m pip install "pyinstaller<6"
.venv\Scripts\python.exe -m PyInstaller --version
```

`--version` 应打印 5.x。若装成了 6.x，可回退：`.venv\Scripts\python.exe -m pip install "pyinstaller<6"`。

## 3. libusb-1.0.dll 的来源与取路径

三选一，拿到 DLL 的**绝对路径**后填进第 4 节的 `--add-binary`：

1. **随包放置**（推荐，显式可审计）：把官方 Windows 二进制解压到
   `libusb\x86\libusb-1.0.dll` 或 `libusb\x64\libusb-1.0.dll`（按 Python 位数选）。
2. **libusb-package**：`.venv\Scripts\python.exe -m pip install "libusb-package<1.0.27"`，
   然后打印包内 DLL 路径：

   ```bat
   .venv\Scripts\python.exe -c "import libusb_package;print(libusb_package.get_library_path())"
   ```

3. **系统 / PATH 中已有**：零配置，但会把系统 DLL 复制进产物；libusb 为 LGPL-2.1，
   再分发前请自行确认许可与位数。

**位数必须与 Python 一致**（64 位 Python → 64 位 DLL）。位数不符时 PyInstaller 会照常打包，
但运行时 `usb.backend.libusb1.get_backend()` 返回 `None`、程序报“libusb 后端不可用”。

## 4. 手工打包命令

都在项目根目录执行。命令较长，建议整行复制。`--distpath dist --workpath build` 与默认值相同，
写出来只是为了明确产物位置（两者都已加入 `.gitignore`）。

**执行前先按第 3 节准备好 DLL**，把文件放到 `libusb\x64\libusb-1.0.dll`（32 位 Python 用
`libusb\x86\`），或把命令里的路径换成第 3 节取得的实际路径；否则 PyInstaller 会报找不到该文件。

### 4.1 onedir（推荐）

```bat
python -m PyInstaller --noconfirm --clean --name KeyboardDriver --paths . ^
  --hidden-import usb.backend.libusb1 ^
  --add-binary "libusb\x64\libusb-1.0.dll;." ^
  --exclude-module tkinter --exclude-module unittest --exclude-module pydoc_data ^
  --console --onedir --distpath dist --workpath build ^
  keyboard_driver\run.py
```

- 32 位 Python 把 `libusb\x64\...` 改成 `libusb\x86\...`；用 libusb-package 时换成它打印出的绝对路径。
- `--add-binary` 的 `源;目标` 分隔符在 Windows 上是分号（其它平台是冒号），目标 `.` 表示贴在 exe 同级。

### 4.2 onefile（单文件）

```bat
python -m PyInstaller --noconfirm --clean --name KeyboardDriver --paths . ^
  --hidden-import usb.backend.libusb1 ^
  --add-binary "libusb\x64\libusb-1.0.dll;." ^
  --exclude-module tkinter --exclude-module unittest --exclude-module pydoc_data ^
  --console --onefile --distpath dist --workpath build ^
  keyboard_driver\run.py
```

### 4.3 参数说明（每一项都对应真实选项）

| 参数 | 作用 |
|---|---|
| `keyboard_driver\run.py` | 入口：写 `logs\keyboard.log` 后调用 `driver.main()`。直接 `python -m keyboard_driver` 也可运行，但不会写日志 |
| `--paths .` | 把项目根加入模块搜索路径，让 PyInstaller 的静态分析找到 `keyboard_driver` 包（`run.py` 以脚本形态运行时也按这个路径导入） |
| `--hidden-import usb.backend.libusb1` | pyusb 的后端是运行时动态选择，静态分析看不到，必须显式声明 |
| `--add-binary "...;."` | 把 libusb DLL 放进产物（onedir 落在 exe 同级；onefile 落进 `_MEIPASS`） |
| `--exclude-module tkinter` 等 | 排除用不到的大模块，减小产物 |
| `--console` | 控制台程序；`keyboard_driver\run.py` 会同时写日志与屏幕。不想要登录时的控制台窗口可改 `--windowed`，日志仍写入文件 |
| `--onedir` / `--onefile` | 产物形态（区别见第 6 节） |
| `--name` | 产物名（`KeyboardDriver`） |
| `--noconfirm --clean` | 覆盖旧产物、清空缓存 |

仓库里**没有安装器/卸载器 exe**：安装与卸载改为手工命令，见 [INSTALL-WIN7.md](INSTALL-WIN7.md)
第 3.8、5 节（`schtasks` 注册自启、设备管理器/`pnputil` 恢复原生驱动）。

## 5. libusb DLL 在两种形态下的放置

| 形态 | DLL 位置 | 运行时如何找到 |
|---|---|---|
| onedir（5.x） | 与 `KeyboardDriver.exe` 同目录 | Windows 默认搜索顺序即可命中 |
| onedir（6.x） | `_internal\libusb-1.0.dll` | 同上 |
| onefile | 被解包到 `%TEMP%\_MEIxxxx\` | `keyboard_driver\paths.py: prepare_native_dlls()` 在导入 pyusb **之前**把 `sys._MEIPASS` 加入 `PATH` 并调用 `os.add_dll_directory()` |

`prepare_native_dlls()` 在两种形态下都生效：打包形态按上表查找（它同时尝试
`resource_dir()`、`app_dir()` 及其下的 `libusb\` 子目录）；源码形态按解释器位数加入项目根的
`libusb\x64` 或 `libusb\x86`。源码分支是为登录自启准备的——`schtasks` 拉起的进程不继承
交互 shell 的 PATH，所以不能靠手工 `set PATH`。

## 6. 产物结构与自检

onedir：

```
dist\KeyboardDriver\
├─ KeyboardDriver.exe
├─ python38.dll
├─ libusb-1.0.dll
├─ _internal\?（仅 PyInstaller 6.x；5.13.2 无此目录）
└─ ...（pyusb 等）
```

onefile：`dist\KeyboardDriver.exe`（单文件，运行时自解包到临时目录）。

在目标机上自检：

1. **启动**：运行 `dist\KeyboardDriver\KeyboardDriver.exe`，控制台应依次出现
   `启动正常模式...`、`找到设备: ...`、`中断端点: 0x81`、`媒体键使用接口 1，端点 0x82`、
   `开始监听键盘，按 Ctrl+C 退出。`。
2. **日志位置**：exe 同级出现 `logs\keyboard.log`，内容与控制台一致（超过 1 MB 滚动为 `.1`）。
   若日志出现在 `%TEMP%\_MEIxxxx` 或 `_internal\` 下，说明 frozen 路径处理失效，应视为构建失败。
3. **设备枚举**：日志出现“设备未找到”＝Zadig 未绑定、绑定被系统还原，或 libusb DLL 缺失/位数不符；
   出现 `USB 错误: [Errno 13] Access denied`＝已有另一个实例占用接口，先结束旧进程。
4. **按键**：Num Lock 切换后字母区改出小键盘字符（固件按灯位切层）、长按重复、音量±（含长按连续调节）、静音、播放/暂停、上下曲；外置键盘的 Num Lock 灯随系统 Num Lock 状态亮灭（该键盘只有这一颗灯，Caps 状态无法在它上面肉眼验证）。
5. **自启（可选）**：按 [INSTALL-WIN7.md](INSTALL-WIN7.md) 3.8 节创建任务，`/TR` 指向 exe 绝对路径；
   onedir 必须连同整个产物目录一起移动。

## 7. onedir 与 onefile 的取舍

| 维度 | onedir（推荐） | onefile |
|---|---|---|
| DLL 定位 | 与 exe 同目录（6.x 在 `_internal\`），默认搜索即可 | 解包到 `%TEMP%\_MEIxxxx`，靠 `prepare_native_dlls()` 显式加路径 |
| 启动速度 | 快（无解包） | 每次启动解包，通常慢 1–3 秒 |
| 诊断/替换 | 可直接看到 `python38.dll`、libusb DLL，便于核对位数 | 全部隐藏，排查困难 |
| 杀软误报 | 概率较低 | 单文件自解包更容易被误报/拦截 |
| 临时目录依赖 | 无 | 依赖 `%TEMP%` 可写且不被清理 |
| 分发 | 必须整目录拷贝，漏文件即失败 | 单文件，拷贝方便 |

结论：**默认 onedir**；只有“必须单文件分发”时才用 onefile，并在目标机实测冷启动与杀软拦截。

## 8. 为什么建议在目标系统上构建

- **不能交叉编译**：PyInstaller 会把当前解释器与它加载的原生 DLL 一起封装，产物位数/依赖由
  **构建机上的 Python** 决定；用 64 位 Python 构建就只能产出 64 位 exe。
- **Win7 兼容性取决于构建环境**：PyInstaller 官方只承诺 Windows 8+。在 Win7 上用 5.13.2
  构建的成功案例最多；若在 Win7 上构建失败，可改在 Win8.1/10 主机上用 **Python 3.8.10** 构建，
  产物仍可运行在 Win7（bootloader 与运行库都以 3.8 为准）。
- **便于当场自检**：构建完立刻在同一台机器上验证 Zadig 绑定、DLL 加载、日志落点与自启，
  避免“构建机能跑、目标机不能跑”的来回拷贝。
- 开发机（Windows 11 + 更高版本 Python）无法产出 Win7 可用包，因此不作为构建环境。

## 9. 验证状态（如实标注）

- 本文所有命令均为**静态核对**：入口文件 `keyboard_driver\run.py`、包 `keyboard_driver`、
  `usb.backend.libusb1` 与 PyInstaller 选项（`--paths`、`--hidden-import`、`--add-binary`、
  `--exclude-module`、`--console`、`--onedir`、`--onefile`、`--distpath`、`--workpath`、
  `--name`、`--noconfirm`、`--clean`）均真实存在。
- `keyboard_driver/`、`tools/` 下脚本 `py_compile` 通过。
- **未执行真实打包**（本机未安装 PyInstaller）：Python 3.8.10 + PyInstaller 5.x 的实际构建、
  onedir/onefile 的 DLL 加载、frozen 分支（`sys.executable` / `sys._MEIPASS`）与日志落点、
  杀软拦截与冷启动耗时，都必须在目标机实测。以上针对当前版本的 exe 形态；当前版本的**源码形态**
  已在一台 Win7 SP1 x64 实机上跑通（见 [README](../README.md)「验证记录」），存档软切换版也曾在 Win7
  以 exe 形态运行并跑通三项行为，但两者都不构成当前版本的打包验收。
