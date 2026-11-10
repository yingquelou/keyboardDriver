# device_profile —— 设备描述包

本包是项目里**唯一**允许出现「当前键盘（1EA7:0066）专有常量与分支」的地方。
通用代码（`src\keyboard.py`、`src\keyboard_utils.py`、`tools\*`）只通过
`device_profile.X` 或 `from device_profile import X` 取值。

包内用契约基类 `KeyboardDevice` 约束"一把键盘设备应该提供什么"：必需项是
`@abstractmethod`（缺一项就在实例化时 `TypeError`），可选能力有默认实现并在 docstring
里写明语义。当前这把键盘是它的子类 `Wireless1EA7_0066`；包入口实例化一份（`PROFILE`），
再把契约成员绑成模块级名字，所以现有导入方式与调用方式不变。
导出名清单、七组契约与最小骨架见仓库根 `README.md` 的「接入另一把键盘」一节。

## 文件划分

| 文件 | 内容 | 什么时候改 |
|---|---|---|
| `contract.py` | `KeyboardDevice`：七组能力契约（身份、接口角色、键盘报告、消费类报告、键表与层、重复策略、指示灯） | 只有新增能力或改通用语义时才动 |
| `device.py` | 当前键盘对契约的实现，只做装配，不含新数据 | 某组能力的**形状**与默认实现不同时覆写；换实测值不用动 |
| `identity.py` | `name` / `vid` / `pid` 的来源、`is_keyboard_interface`、`is_consumer_interface`、端点预期 | 换设备身份、接口类/子类/协议不同、端点不是中断 IN |
| `reports.py` | 键盘报告布局与 `parse_key_report` / `key_report_read_size`；消费类 Report ID、usage 位宽、字节序、取舍规则与解析 | 报告长度/修饰键位置/键槽区间不同；消费类格式不同 |
| `keys.py` | `C` / `XL` / `XN` / `CONSUMER` 四张映射表、`LAYERS`、层顺序与默认层、层切换键与切层策略 | **最常见的改动**：键位映射、层名与顺序、层切换键的 HID 码 |
| `policy.py` | 免重复 VK 集合、消费类重复集合、指示灯能力与位序 | 重复规则或指示灯结论不同 |
| `_win32.py` | 私有：`win32con` 获取（pywin32 / ctypes 兼容层）与 VK 补全 | 一般不动 |
| `__init__.py` | 实例化 `PROFILE`、把契约成员绑成模块级别名、`__all__` | 新增导出名时同步更新 |

## 换一把键盘（新增设备实现）

1. 按实测值改 `identity.py` / `reports.py` / `keys.py` / `policy.py`；
2. 若报告带 Report ID、层切换语义或消费类取舍规则与基类默认不同，在 `device.py` 里覆写
   对应成员（其余成员继续复用默认实现）；
3. 跑 `python tools\check_device_profile.py`，确认 0 项失败；
4. 用 `tools\calibrate.py` 逐键核对 HID → VK、`tools\probe_keyboard.py` 核对接口角色与
   Report ID，再运行 `src\keyboard.py` 上真机。

## 约束

- 依赖方向是单向的：`keys.py` / `policy.py` → `_win32.py`；`identity.py`、`reports.py`
  不依赖其它模块；`contract.py` 只用标准库；`device.py` 只向下装配；`__init__.py` 只实例化
  与导出。**不要**让子模块互相导入。
- 映射表体量大且频繁变动，必须留在 `keys.py`，不要塞回 `__init__.py`。
- 契约成员名（`name` / `vid` / `layers` …）与模块级导出名（`NAME` / `VID` / `LAYERS` …）
  一一对应；`__all__` 的 49 项是对外承诺，改它们要同步通用代码。
- `_` 开头的是私有名；通用代码只使用 `__init__.py` 导出清单里的名字。
- 自检覆盖：必需项是否存在、方法参数个数、报告长度与槽区间自洽、层顺序与子表覆盖、
  层切换键不出现在映射表中、消费类 Report ID 过滤、重复策略与指示灯默认语义。
