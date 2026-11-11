# device_profile —— 设备描述包

本包是项目里**唯一**允许出现「当前键盘（1EA7:0066）专有常量与分支」的地方。
通用代码（`keyboard_driver\driver.py`、`keyboard_driver\transport.py`、`tools\*`）只通过
`device_profile.X` 或 `from keyboard_driver.device_profile import X` 取值。

本包**只保存报告布局类事实**：设备身份、接口角色、键盘报告布局、消费类报告布局、
指示灯输出报告格式。键位映射（usage → VK）与自动重复语义是**通用 HID 知识**，
放在 `keyboard_driver\usage.py`，与本设备无关；"层"由固件按灯位自己切换，本包和通用代码里
都没有层表或层状态机。

包内用契约基类 `KeyboardDevice` 约束"一把键盘设备应该提供什么"：必需项是
`@abstractmethod`（缺一项就在实例化时 `TypeError`），可选能力有默认实现并在 docstring
里写明语义。当前这把键盘是它的子类 `Wireless1EA7_0066`；包入口实例化一份（`PROFILE`），
再把契约成员绑成模块级名字，所以现有导入方式与调用方式不变。
导出名清单、五组契约与最小骨架见仓库根 `README.md` 的「接入另一把键盘」一节。

## 文件划分

| 文件 | 内容 | 什么时候改 |
|---|---|---|
| `contract.py` | `KeyboardDevice`：五组能力契约（身份、接口角色、键盘报告、消费类报告、指示灯输出） | 只有新增能力或改通用语义时才动 |
| `device.py` | 当前键盘对契约的实现，只做装配，不含新数据 | 某组能力的**形状**与默认实现不同时覆写；换实测值不用动 |
| `identity.py` | `name` / `vid` / `pid` 的来源、`is_keyboard_interface`、`is_consumer_interface`、端点预期 | 换设备身份、接口类/子类/协议不同、端点不是中断 IN |
| `reports.py` | 键盘报告布局与 `parse_key_report` / `key_report_read_size`；消费类 Report ID、usage 位宽、字节序、取舍规则与解析；指示灯报告长度与位定义 | 报告长度/修饰键位置/键槽区间不同；消费类或 LED 输出格式不同 |
| `__init__.py` | 实例化 `PROFILE`、把契约成员绑成模块级别名、`__all__` | 新增导出名时同步更新 |

## 换一把键盘（新增设备实现）

1. 按实测值改 `identity.py` / `reports.py`；
2. 只有某组能力的**形状**与基类默认不同（报告带 Report ID、消费类取舍规则不同、
   有指示灯输出报告）时，才在 `device.py` 里覆写对应成员；其余继续复用默认实现；
3. 跑 `python tools\check_device_profile.py`，确认 0 项失败；
4. 用 `tools\calibrate` 逐键核对两种灯态下的 HID → VK（它会独占接口，先停 `python -m keyboard_driver`；
   未知键用 `--learn` 单键采集并导出 `KEYMAP` 草稿，常规键用
   `--learn --categories all` 按类逐项点名核对）、
   `tools\probe_keyboard.py` 核对接口角色与 Report ID（设备不可见时先用
   `tools\enum_usb_nodes.py --classes` 看驱动绑定），再运行 `python -m keyboard_driver` 上真机。

## 约束

- 依赖方向是单向的：`identity.py`、`reports.py` 只依赖标准库与 `keyboard_driver\win32_compat.py`
  （后者只提供 VK 常量）；`contract.py` 只用标准库；`device.py` 只向下装配；
  `__init__.py` 只实例化与导出。**不要**让子模块互相导入，也不要把 `win32con`
  经本包再导出（通用常量直接取 `win32_compat`）。
- 通用 HID 语义（usage → VK、哪些键会重复）**不要**放进本包，放 `keyboard_driver\usage.py`。
- 契约成员名（`name` / `vid` / `led_supported` …）与模块级导出名（`NAME` / `VID` / `LED_SUPPORTED` …）
  一一对应；`__all__` 是对外承诺，改它们要同步通用代码。
- `_` 开头的是私有名；通用代码只使用 `__init__.py` 导出清单里的名字。
- 自检覆盖：必需项是否存在、方法参数个数、报告长度与槽区间自洽、`usage` 映射覆盖、
  消费类 Report ID 过滤、重复语义、指示灯报告格式与位定义。
