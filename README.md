# fdu-yjsxk · 复旦大学研究生选课脚本

一个用于复旦大学研究生选课系统（`yjsxk.fudan.edu.cn`）的自动抢课脚本，2026 版协议重写。

本项目基于 [JarynWong/fdu_course_enrollment](https://github.com/JarynWong/fdu_course_enrollment) 重写。
原脚本基于 2024 年的选课协议，在 2026 年的系统上已多处失效，本仓库按当前系统的真实接口逻辑
重新实现，并补上了原版缺失的一键 Cookie 读取、串行选课、链路自检等能力。

## 与原版的区别

| | 原版 course.py | 本仓库 grab.py |
|---|---|---|
| csrfToken 提取 | `value='...'` 单引号，已失效 | 兼容单/双引号，实测可用 |
| 选课结果判定 | `code!=0` 就当成功 | 两步异步：提交拿 `xid` → 轮询 `code==1` 才算选上 |
| Cookie | 手动 F12 复制 | 自动读浏览器本地库（含 HttpOnly） |
| 多门课 | 一轮全提交 | 串行（系统轮询是单例，并发会丢结果） |
| 配置 | 改源码里的全局变量 | 独立 `config.json`，不用动代码 |
| 自检 | 无 | `--dry-run` 环境自检 |

## 环境要求

- **Python 3.9+**（推荐 3.10 ~ 3.13，3.13 实测可用）
- 依赖包只有两个：`requests`、`browser-cookie3`，见 `requirements.txt`

```bash
pip install -r requirements.txt
```

## 快速开始

### 一键双击（推荐）

先在浏览器（Edge 或 Chrome）登录一次选课系统，然后：

| 平台 | 自检（先跑） | 抢课 |
|---|---|---|
| macOS | 双击 `先跑自检.command` | 双击 `一键抢课.command` |
| Windows | 双击 `先跑自检.bat` | 双击 `一键抢课.bat` |

> macOS 首次双击 `.command` 若被系统拦截，右键 →「打开」即可。
> Windows 的 `.bat` 会先自动检测并安装依赖，再运行。

### 命令行

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 在浏览器登录一次选课系统（Edge 或 Chrome）

# 3. 自检（不会提交任何选课请求）
python grab.py --dry-run

# 4. 抢课（会等到 config.json 里的 start_time 再开始）
python grab.py
```

## 命令行参数

```bash
python grab.py             # 正常跑，等到 start_time 开始
python grab.py --dry-run   # 环境自检，不发请求
python grab.py --now       # 忽略 start_time，立即开始
python grab.py --probe     # 链路演练：发 1 次真实请求看服务器回什么
```

## 配置

所有配置都在 `config.json` 里，关键项：

```jsonc
{
  "target": "yjsxk.fudan.edu.cn",        // 选课系统域名
  "start_time": "2026-09-02 09:59:55",   // 开抢时间（提前几秒起跑）
  "end_time": "2026-09-02 10:30:00",     // 到点强制收工
  "browser": "edge",                     // 从哪个浏览器读 Cookie
  "serial_mode": true,                   // 一门一门来，务必保持 true
  "courses": [
    // name / bjdm / lx / bqmc / enabled
  ]
}
```

- `bjdm`（班级代码）格式为 `学年学期 + 课程代码 + .班号`，需要到选课系统抓取，不同年级前缀不同。
- `lx` / `bqmc` 是选课系统的分类编码，已在脚本内说明对应关系。
- `enabled: false` 的课程不参与抢课。

## 为什么是一门一门选

选课系统的结果轮询在网页里是**单例**的（全局一个"正在查询"标志）。如果一下把几门课都提交
出去，后一次会覆盖前一次的轮询，导致前面那门的结果收不到。所以 `serial_mode` 必须保持
`true`：提交一门 → 等结果 → 再提交下一门。课程在 `courses` 数组里的顺序即优先级，建议把
容量最小、最难抢的课排在前面。

## 免责声明

- 本程序仅供学习交流，功能仅为辅助选课，**存在抢课失败的可能**。
- 请控制请求频率、及时停止程序，**避免给学校服务器带来过大压力**。
- 请遵守学校相关规定，使用本程序产生的任何后果由使用者自行承担。

## 许可

本项目为重写实现，代码可自由参考。原项目 [JarynWong/fdu_course_enrollment](https://github.com/JarynWong/fdu_course_enrollment)
未附带 LICENSE，如需使用原版代码请自行联系原作者。
