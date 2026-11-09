# 1EA7:0066 无线键盘驱动（libusb/WinUSB 接管）

用 Python + libusb（pyusb）直接读取这把 2.4G 无线键盘的 HID 报告，在主机侧重放键序，
补齐原版固件/驱动缺少的**长按自动重复**与**媒体键**，并把层切换键改成数字锁定键位。

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
.\.venv\bin\python.exe src\keyboard.py          # 正常模式（指示灯同步默认关闭）
.\.venv\bin\python.exe src\keyboard.py --led    # 额外启用指示灯回写（本设备无效果，见下）
.\.venv\bin\python.exe tools\calibrate.py       # 校准：打印每个键的 HID 码与映射结果
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

## 键位映射与层切换

- 映射表在 `keymap.py`：`letter`（字母层）与 `number`（数字层）。
- **层切换键 = HID `0x53`（数字锁定键位）**，与原始驱动一致：
  - 只在“上一份报告未按下 → 本次按下”时切换一次；
  - 本身不注入任何按键，**不改变系统 Num Lock 状态**，也不参与自动重复；
  - 按住期间跨层，松开时按按下时记录的 VK 抬起。
- **Scroll Lock = HID `0x47`**：普通键，注入 `VK_SCROLL` 并切换系统锁定状态；锁定键不参与自动重复。
- 常量统一在 `keyboard_utils.LAYER_TOGGLE_HID`，不要在别处写死。

### 长按自动重复

设备本身**不重发报告**（实测按住 2–3 秒只有一份报告），因此重复完全由主机侧补发，
参数取系统设置（`SPI_GETKEYBOARDDELAY` / `SPI_GETKEYBOARDSPEED`）：

- 首重复延迟：实测 505–514 ms（系统 500 ms，+1~3%）
- 重复间隔：实测平均 54.9 ms（系统 55.6 ms，−1.2%）；单次间隔有 40–70 ms 抖动
- 锁定键（Caps/Num/Scroll）不产生重复；修饰键按住同样按此节奏补发

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

- 键盘接口声明 5 位 LED（Num/Caps/Scroll/Compose/Kana，1 字节输出报告）。
- **实测结论：在 WinUSB 接管模式下指示灯不可控**——1 字节与 2 字节 `Set_Report` 均返回成功，
  但物理灯毫无反应；该接口也只有 IN 端点（无中断 OUT）。原生 HID 驱动下灯正常。
- 因此 `keyboard.py` **默认不启用**灯同步（无流量、无日志噪音），仅 `--led` 时按系统锁定状态写入，
  供其它设备或后续验证使用。本设备只有一颗指示灯，接管后它不亮属已知限制，不是故障。

## 诊断脚本

| 脚本 | 用途 |
|---|---|
| `tools\probe_keyboard.py` | 无侵入枚举：接口/端点/包长/报告描述符，核对消费类集合与 Report ID |
| `tools\calibrate.py` | 逐个按键打印 HID 码 → VK 名，核对映射与层切换 |
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

- 指示灯在接管模式下不可控（见上节）。
- **Win7 实机回归整体未做**：层切换、长按重复、媒体键、断线重连在 Win11 均已实测通过，
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
