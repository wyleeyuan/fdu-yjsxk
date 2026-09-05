# fdu-yjsxk · 复旦大学研究生选课脚本

一个用于复旦大学研究生选课系统（`yjsxk.fudan.edu.cn`）的自动抢课脚本，2026 版协议重写。

## 文件结构

仓库已按用途分目录整理：

```
fdu-yjsxk/
├── src/                  Python 源码
│   ├── grab.py           抢课脚本（自检 / 登录 / 抢课都在这里）
│   └── preselect.py      预选课脚本（拉课程列表 → 生成 config.json）
├── scripts/              Windows(.bat) + macOS(.command) 一键双击脚本
│   └── 选课助手.command / .bat   三合一菜单：1 自检 / 2 预选课 / 3 抢课
├── config.example.json   配置模板（入库，给首次使用者参考）
├── requirements.txt      Python 依赖
└── README.md
```

> `config.json`（你的实际配置）与 `cookie.txt`（登录态）在你本机的仓库根目录，
> 由脚本自动读写，已加入 `.gitignore` 不会误提交。

## 环境要求

- **Python 3.9+**（推荐 3.10 ~ 3.13，3.13 实测可用）
- 依赖包只有两个：`requests`、`browser-cookie3`，见 `requirements.txt`
- **浏览器：macOS 上请用 Edge 或 Chrome，不要用 Safari**（原因见下）

```bash
pip install -r requirements.txt
```

> **为什么 Safari 不行**：脚本靠 `browser-cookie3` 直接读浏览器的本地 Cookie 库取
> `JSESSIONID` / `_WEU`。Safari 是沙盒应用，Cookie 存在
> `~/Library/Containers/com.apple.Safari/Data/Library/Cookies/Cookies.binarycookies`，
> 该路径受 macOS 隐私保护（TCC）管辖，终端 / Python 默认无权读取，实测直接报
> `PermissionError: Operation not permitted`——除非单独给终端授予「完全磁盘访问权限」。
> Edge / Chrome 的 Cookie 库（`~/Library/Application Support/.../Default/Cookies`）没有
> 这层沙盒，脚本可以直接读。所以**登录和抢课全程用 Edge 或 Chrome 即可**。

## 快速开始

脚本自己管理登录态：自动读取浏览器 Cookie 并固化到本地 `cookie.txt`（文件优先），
失效时引导现场重登。**正常使用不需要先手动登录**，只在首次使用或登录态过期时
才需要走一次第 0 步。

### 第 0 步：登录选课系统（首次使用 / Cookie 失效时）

跑 `python src/grab.py --login`（或双击选课助手选 **1 自检**，发现 Cookie 失效时按提示
选 Y 现场登录），脚本会自动打开选课页：

```
http://yjsxk.fudan.edu.cn/yjsxkapp/sys/xsxkappfudan/xsxkHome/gotoChooseCourse.do
```

> ⚠️ **macOS 注意**：这里打开的是你的**系统默认浏览器**。若默认是 Safari，请把网址
> 复制到 **Edge 或 Chrome** 里登录——脚本读不到 Safari 的 Cookie（见上方「环境要求」）。
> **在哪个浏览器登录，脚本就得从哪个浏览器读**，两边必须一致。

未登录时会自动跳到复旦统一身份认证（UIS），登录成功后自动回到选课页面。
在浏览器里完成登录后回到终端**回车确认**，脚本会自动等待 Cookie 落盘并验证保存
（写入有延迟，回车后自动重读——进度条倒计时，最多 1 分钟、约 20 次机会，**不用自己掐时间**）。

> 登录态有时效（几小时到一天）。之后自检或抢课时若提示「Cookie 已失效」，跑一次
> `--login`（或按提示选 Y 现场登录）即可，不用手动折腾。

### 一键双击（推荐）

双击对应平台的入口脚本，会弹出菜单，输入编号回车即可随时切换三个功能：

| 平台 | 双击入口 |
|---|---|
| macOS | `scripts/选课助手.command` |
| Windows | `scripts/选课助手.bat` |

菜单选项：

- **1 自检**：检查登录态与课程配置，不发任何选课请求（可反复跑）
- **2 预选课**：拉出全部课程让你挑选，自动生成 / 更新 `config.json`（每次换课都用这个）
- **3 开始抢课**：按 `config.json` 自动抢（会等到 `start_time` 再开抢）
- **0 退出**

> 建议顺序：先 1 自检 → 2 预选课 → 3 抢课。
> macOS 首次双击 `.command` 若被系统拦截，右键 →「打开」即可。
> Windows 的 `.bat` 会先自动检测并安装依赖，再显示菜单。
> 自检若发现 Cookie 已失效，会问你是否打开浏览器重新登录，选 Y 即可。

### 命令行

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 自检（不会提交任何选课请求；无登录态或已失效会引导现场登录）
python src/grab.py --dry-run

# 3. 抢课（会等到 config.json 里的 start_time 再开始）
python src/grab.py
```

## 命令行参数

```bash
python src/grab.py             # 正常跑，等到 start_time 开始
python src/grab.py --dry-run   # 环境自检，不发请求（Cookie 失效时会引导现场登录）
python src/grab.py --login     # 现场登录：自动打开浏览器 → 你登录后回车 → 自动等待 Cookie 落盘并验证保存
python src/grab.py --now       # 忽略 start_time，立即开始
python src/grab.py --probe     # 链路演练：发 1 次真实请求看服务器回什么
```

## 预选课：生成 / 更新 config.json

不想手动一条条填 `courses` / 抓 `bjdm`？可以先把课选好、自动生成 `config.json`：

双击 `scripts/选课助手.command / .bat` 并在菜单里选
**2 预选课**（或命令行运行 `python3 src/preselect.py`），脚本会：

1. 自动读取并验证登录态（失效时会引导现场登录）
2. 若 `config.json` 里已有上一轮预选的课程，先列出它们，并询问是否覆盖更新：
   **回车 = 覆盖、重新挑选**；输 `n` = 保留现有课程、跳过挑选，直接进入第 6 步
3. 从选课系统拉取全部可抢类别（自动带对 lx / bqmc），列出类别菜单让你**循环挑**：
   每轮输入一个类别编号去挑该类里的课，挑完**回到菜单**继续挑下一个，想挑几类就挑几类；
   输 `0` 或直接回车 = 结束挑选，进入第 5 步。先挑的类别先进入待抢列表
4. 每个类别里让你输入编号挑选要抢的课（可多选，**输入顺序 = 抢课优先级**，先输的先抢；
   直接回车 = 跳过该类；先挑的类别先进入待抢列表）。每门含课程代码、班号、学分、教师、
   时间地点、校区、余量，已满或与已选课冲突会标出来
5. 确认开抢窗口（自动取**当天最近一场还没开始的放号**：每天 10:00 与 13:00 两场放退课名额，
   提前 5 秒起跑、放号后 30 分钟收工；窗口始终锚定在当天，当天两场都过了就回退到今天 13:00
   （已过期，脚本会立即开始），不会顺延到明天。可直接回车接受，也可手动改成别的时间）
6. 写回 `config.json`

其他约定：

- 已存在 `config.json` 时**只重建课程和时间**，浏览器、请求间隔、满课阈值等其它设置
  原样保留；旧文件先自动备份为 `config.json.preselect.bak`（已 gitignore，不会误提交）
- 全程**只读**课程列表，不会提交任何选课请求，可放心反复运行
- 同一门课有多个班（如 `.01` / `.02`）会各占一行，可以都选上：第一个班抢到后，
  第二个班会被判定"已选过"自动跳过
- 按编号挑课覆盖三大页签全部可抢类别：学位公共课（lx=7，bqmc=1/2/3）、学科专业课
  （lx=8，bqmc=4/5/6）、公共选修课（lx=9，bqmc=9），lx / bqmc 按所在页签自动写好，
  不需要手动指定

## 配置

`config.json` 由**预选课**自动生成与维护，正常使用**不需要手动编辑**——
脚本每次写回前都会把旧文件备份为 `config.json.preselect.bak`（已 gitignore）。
`bjdm`（班级代码）、`lx` / `bqmc`（分类编码）、开抢窗口都由脚本自动抓好写入。

首次运行（直接跑 `grab.py` 或 `preselect.py`）若发现没有 `config.json`，会拿
`config.example.json` 当模板自动创建一份**课程列表为空**的配置，并把开抢窗口设成
**当天**最近一场放号（每天 10:00 / 13:00），无需手动 `cp`。之后用 `preselect.py` 预选课即可。

少数情况才需要打开文件微调：

- `enabled: false` —— 某门课这轮不抢（例如已经选上），预选课会原样保留这个开关
- `browser` —— 从哪些浏览器读登录 Cookie，默认 `["edge", "chrome"]` 按顺序尝试。
  目前只支持 Edge / Chrome（macOS 上 Safari 受系统沙盒限制读不到，见「环境要求」）
- `full_max_tries` —— 满课放弃阈值：一门课连续满员 N 次自动放弃（默认 3），`0` = 永不放弃
- `serial_mode` —— 务必保持 `true`（结果轮询是单例的，并发会丢结果）

### 课满了怎么办（自动行为）

- 课程在 `courses` 里的顺序即优先级，排前面的先试（预选课里先输的编号排前面）。
- 某门课满员被拒**不会卡住后面的课**：打印一行"满员"提示后立刻试下一门。
- 满员失败的课每轮会自动**挪到本轮末尾**再试（有人退课 / 每天放号时能第一时间接住），不会挡在能抢的课前面。
- 一门课被**连续**判满 `full_max_tries` 次后自动放弃，结尾汇总里会单独列出；想重点盯某门课，把它单独设 `"full_max_tries": 0`（永不放弃）即可。

## 为什么是一门一门选

选课系统的结果轮询在网页里是**单例**的（全局一个"正在查询"标志）。如果一下把几门课都提交
出去，后一次会覆盖前一次的轮询，导致前面那门的结果收不到。所以 `serial_mode` 必须保持
`true`：提交一门 → 等结果 → 再提交下一门。课程在 `courses` 数组里的顺序即优先级，建议把
容量最小、最难抢的课排在前面。

## 免责声明

- 本程序仅供学习交流，功能仅为辅助选课，**存在抢课失败的可能**。
- 请控制请求频率、及时停止程序，**避免给学校服务器带来过大压力**。
- 请遵守学校相关规定，使用本程序产生的任何后果由使用者自行承担。

