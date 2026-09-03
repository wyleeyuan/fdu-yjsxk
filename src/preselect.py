#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
复旦研究生选课 · 预选课助手（自动生成 config.json）

功能：复用 grab.py 的登录态，从选课系统拉取全部可抢类别并逐类展示挑选——
      学科专业课（学位基础课 / 学位专业课 / 专业选修课）、学位公共课（政治
      理论课 / 第一外国语 / 专业外语）、公共选修课；在命令行里按编号把
      想抢的课挑出来（选择顺序 = 抢课优先级，先选的先抢），自动生成
      config.json，之后用「选课助手」菜单里的 3 开始抢课（或 python3
      src/grab.py）开抢即可。

用法：
    python3 src/preselect.py
或双击 macOS 的 scripts/选课助手.command / Windows 的 scripts/选课助手.bat
   （菜单选 2 预选课）

说明：
    · 全程只读选课列表，不会提交任何选课请求
    · 已存在 config.json 时，只重建 courses / start_time / end_time，
      其余设置（浏览器、间隔、阈值等）原样保留；原文件先备份一份
      config.json.preselect.bak
    · Cookie 失效时会引导现场登录（同 grab.py --login）
    · 各列表里看不到的课（如还没获得选课资格、但教学大纲能搜到）可在
      末尾「手工补充」：粘贴 fdjwgl 教学大纲详情链接，自动解析课程名与
      课程序号、按当前学期前缀拼好 bjdm 补进待抢列表
"""
from __future__ import annotations

import datetime as dt
import html as _html
import json
import os
import re
import shutil
import sys
import time

import requests

import grab  # 复用 grab.py 的 Cookie 获取/验证、UA、常量

BASE_DIR = grab.BASE_DIR
CONFIG_PATH = grab.CONFIG_PATH
CONFIG_BAK = os.path.join(BASE_DIR, "config.json.preselect.bak")

# 拉取范围与抢课参数（口径与选课页一致）：
#   lx   = 大页签编码：7=学位公共课，8=学科专业课，9=公共选修课
#   bqmc = 课程所在页签编号，页面提交 choiceCourse.do 时把它连同 lx 一起传。
#          学位公共课：1政治理论课 / 2第一外国语 / 3专业外语
#          学科专业课：4学位基础课 / 5学位专业课 / 6专业选修课
#          公共选修课：页面只有单列表、无子页签，页签编号即 9
# 注意行内字段不能当 bqmc：KCLBDM 是「培养方案课程类别码」（政治理论课=5，
# 与页签编号 1 不同）；TABSZWID 仅部分列表行有，公选课行甚至是 5/6/空。
# 所以拉课时必须记住自己用的页签编号（=下方 LISTS 的 bqmc 列），写进
# config.json 才不会错 —— 与页面闭包提交的 bqmc 完全同源。
LISTS = [
    # (大页签名, lx, 子分类展示名, 列表接口, 页签参数名, 页签编号=bqmc)
    ("学科专业课", 8, "学位基础课", "loadXwzykCourseInfo.do", "query_tabszwid", 4),
    ("学科专业课", 8, "学位专业课", "loadXwzykCourseInfo.do", "query_tabszwid", 5),
    ("学科专业课", 8, "专业选修课", "loadXwzykCourseInfo.do", "query_tabszwid", 6),
    ("学位公共课", 7, "政治理论课", "loadXwggkCourseInfo.do", "query_tabszwid", 1),
    ("学位公共课", 7, "第一外国语", "loadXwggkCourseInfo.do", "query_tabszwid", 2),
    ("学位公共课", 7, "专业外语",   "loadXwggkCourseInfo.do", "query_tabszwid", 3),
    ("公共选修课", 9, "公共选修课", "loadGgxxkCourseInfo.do", "lx", 9),
]

QUERY_URL = (
    f"http://{grab.DOMAIN}/yjsxkapp/sys/xsxkappfudan/"
    "xsxkCourse/{endpoint}?_={ts}"
)
QUERY_BODY = (
    "query_keyword=&query_kclb=&query_kkyx=&query_xqdm1=&query_sfct="
    "&query_sfym=&fixedAutoSubmitBug=&{tab}={val}&pageIndex=1"
    "&pageSize=500&sortField=&sortOrder="
)

# 首次运行（无 config.json）时的默认设置，与 grab.py / config.example 对齐
DEFAULT_CFG = {
    "target": grab.DOMAIN,
    "cookie_source": "auto",
    "browser": "edge",
    "cookie_refresh_secs": 240,
    "request_interval": 0.8,
    "poll_interval": 0.6,
    "poll_max": 15,
    "http_timeout": 12,
    "serial_mode": True,
    "full_max_tries": 3,
}


def log(msg: str = "") -> None:
    print(msg, flush=True)


def ensure_cookie(cfg: dict) -> str:
    """取一份现场验证过的 Cookie；全失效时引导现场登录。"""
    try:
        return grab._obtain_verified(cfg)
    except grab.CookieError as exc:
        log(f"✗ 登录态不可用：{exc}")
        log("")
        interactive = False
        try:
            interactive = sys.stdin.isatty()
        except Exception:
            pass
        try:
            ans = input("要现在打开浏览器现场登录一次吗？[Y/n]：").strip()
        except EOFError:
            ans = "EOF"  # 非交互/输入流已断：不弹浏览器，直接退出
        if ans.lower() in ("y", "yes") or (not ans and interactive):
            log("")
            return grab.cmd_login(cfg)  # 自带：弹浏览器→登录→回车→验证→固化 cookie.txt
        raise SystemExit("未登录，无法拉取课程列表。可先运行 python src/grab.py --login")


def fetch_lists(cookie: str, timeout: float = 12.0) -> list[tuple[str, int, str, int, list[dict]]]:
    """拉取全部可抢类别。返回 [(大页签名, lx, 子分类名, bqmc, 课程列表), ...]。

    bqmc 即拉取所用的页签编号（LISTS 末列），与页面提交给 choiceCourse.do
    的 bqmc 同源 —— 用它写 config.json 才不会错（行内字段不可靠，见 LISTS 注释）。
    """
    headers = {
        "Cookie": cookie,
        "User-Agent": grab.UA,
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": f"http://{grab.DOMAIN}{grab.APP_ENTRY}",
    }
    s = requests.Session()
    out: list[tuple[str, int, str, int, list[dict]]] = []
    last_group = None
    for group, lx, label, endpoint, tab, val in LISTS:
        if group != last_group:
            log(f"◆ {group}（lx={lx}）")
            last_group = group
        url = QUERY_URL.format(endpoint=endpoint, ts=int(time.time() * 1000))
        body = QUERY_BODY.format(tab=tab, val=val)
        try:
            r = s.post(url, headers=headers, data=body, timeout=timeout)
        except requests.RequestException as exc:
            raise SystemExit(f"✗ 请求课程列表失败（{group}·{label}）：{exc}")
        if r.status_code != 200:
            raise SystemExit(f"✗ 课程列表接口返回 HTTP {r.status_code}（{group}·{label}）")
        try:
            j = r.json()
        except Exception:
            raise SystemExit(f"✗ 课程列表响应不是 JSON（{group}·{label}），可能登录态失效")
        rows = j.get("datas") or []
        if not isinstance(rows, list):
            raise SystemExit(f"✗ 课程列表接口返回结构异常（{group}·{label}），可能登录态失效或系统改版")
        out.append((group, lx, label, val, rows))
        log(f"  · {label}：{len(rows)} 门")
    return out


def _fmt_course(c: dict) -> str:
    """把接口的一行课程格式化成可读文本。"""
    kx = int(c.get("KXRS") or 0)
    dq = int(c.get("DQRS") or 0)
    if kx > 0 and dq >= kx:
        state = "已满"
    elif kx > 0:
        state = f"余{kx - dq}"
    else:
        state = ""
    bjdm = c.get("BJDM", "")
    ban = bjdm.rsplit(".", 1)[-1] if bjdm else "?"
    parts = [
        f"{state:>5}" if state else "     ",
        c.get("KCDM", ""),
        f"{c.get('KCMC', '')}（班 .{ban}）",
        f"{c.get('KCXF') or c.get('XF') or '?'}学分",
        c.get("RKJS", ""),
    ]
    td = c.get("PKSJ") or ""
    loc = c.get("PKDD") or ""
    xq = c.get("XQMC") or ""
    seg = " ".join(x for x in (td, loc, xq) if x)
    if seg:
        parts.append(seg)
    if int(c.get("IS_CONFLICT") or 0):
        parts.append("⚠时间冲突")
    return "  ".join(x for x in parts if x)


def pick_group(title: str, rows: list[dict]) -> list[int]:
    """展示一类课程，返回用户选中的行下标列表（顺序 = 优先级）。"""
    log("")
    log("=" * 60)
    log(f"  {title}（共 {len(rows)} 门）")
    log("=" * 60)
    if not rows:
        log("（没有可选课程）")
        return []
    for i, c in enumerate(rows, 1):
        log(f"[{i:2d}] {_fmt_course(c)}")
    while True:
        log("")
        raw = input(
            f"要抢哪些？输入编号，多个用空格或逗号分隔（越靠前越优先，回车跳过）："
        ).strip()
        if not raw:
            return []
        tokens = re.split(r"[,\s，、]+", raw)
        picked: list[int] = []
        bad = False
        for t in tokens:
            if not t.isdigit():
                log(f"  ✗ 无法识别「{t}」，请输入纯编号")
                bad = True
                break
            i = int(t)
            if not (1 <= i <= len(rows)):
                log(f"  ✗ 编号 {i} 超出范围（1~{len(rows)}）")
                bad = True
                break
            if i in picked:
                log(f"  ✗ 编号 {i} 重复了")
                bad = True
                break
            picked.append(i)
        if not bad:
            return picked


def to_course(lx: int, bqmc: int, row: dict) -> dict:
    """接口行 → config.json 的 course 条目。

    lx / bqmc 来自行所在页签（fetch_lists 携带），不是行内字段 —— 与页面
    提交 choiceCourse.do 的参数同源，保证抢课时不会因类别写错被服务器拒收。
    """
    return {
        "name": row.get("KCMC", ""),
        "kcdm": row.get("KCDM", ""),
        "bjdm": row.get("BJDM", ""),
        "lx": lx,
        "bqmc": bqmc,
        "enabled": True,
    }


def ask_time(label: str, default: str) -> str:
    while True:
        raw = input(f"{label} [{default}]：").strip()
        if not raw:
            return default
        try:
            dt.datetime.strptime(raw, "%Y-%m-%d %H:%M:%S")
            return raw
        except ValueError:
            log("  ✗ 格式应为 YYYY-MM-DD HH:MM:SS，例如 2026-09-04 12:59:55")


# 每天放退课名额的时间点：10:00 与 13:00 两场。
# 默认起跑时刻 = 放号时间提前 5 秒；收工 = 放号后 30 分钟。
SLOT_HOURS = (10, 13)   # 放号整点
SLOT_LEAD = 5           # 起跑提前秒数
SLOT_RUN_MIN = 30       # 放号后收工分钟数


def slot_window(release: dt.datetime) -> tuple[dt.datetime, dt.datetime]:
    """放号时刻 → (起跑时刻, 收工时刻)。"""
    start = release - dt.timedelta(seconds=SLOT_LEAD)
    end = release + dt.timedelta(minutes=SLOT_RUN_MIN)
    return start, end


def next_slot(now: dt.datetime | None = None) -> tuple[dt.datetime, dt.datetime]:
    """找「最近一场还没开始放号」的开抢窗口。

    依次看 今天 10:00 → 今天 13:00 → 明天 10:00 → 明天 13:00，返回
    第一个放号时刻晚于 now 的场次；已经开始/已经过去的场次不回头。
    """
    now = now or dt.datetime.now()
    base = now.replace(hour=0, minute=0, second=0, microsecond=0)
    for day_offset in range(2):
        day = base + dt.timedelta(days=day_offset)
        for hh in SLOT_HOURS:
            release = day.replace(hour=hh, minute=0, second=0)
            if release > now:
                return slot_window(release)
    raise AssertionError("两天内必有一场未开始的放号")  # 逻辑上不可达


def default_window(now: dt.datetime | None = None) -> tuple[str, str]:
    """默认开抢窗口：取最近一场还没开始的放号（每天 10:00 / 13:00 两场）。

    当天两场都过了就自动顺延到明天第一场（10:00），保证生成的窗口永远
    落在未来，不会给出一份已经过期的 config。
    """
    start, end = next_slot(now)
    return start.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S")


# ------------------------------------------------------------ 手工补充 ----
# 有些课因为还没有选课资格，上面的三类列表里根本看不到，但能通过
# fdjwgl「教学大纲」公开查询搜到。这里在流程末尾给一次手工补充的机会：
# 只支持贴一份教学大纲详情链接（fdjwgl.fudan.edu.cn/.../teaching-syllabus/...），
# 自动解析出「课程名称 + 课程序号（课程代码.班号）」，再按当前学期前缀拼出
# bjdm 补进待抢列表。其余信息一律不额外询问，保持简单。

FDJWGL_URL_RE = re.compile(r"^https?://", re.I)
CODE_RE = re.compile(r"^([A-Za-z][A-Za-z0-9]*)$")
CODE_BAN_RE = re.compile(r"^([A-Za-z][A-Za-z0-9]*)\.([0-9]+)$")

# 手工补充时可选的全部子分类（选项数字恰好等于 bqmc，与 config.json 的
# _字段含义 一致，方便对照）：1/2/3 属学位公共课(lx=7)，4/5/6 属学科专业课
# (lx=8)，9 属公共选修课(lx=9)。主要用于「暂无选课资格、列表里看不到」的课；
# 列表里能看到的课建议直接在上面按编号挑，脚本会自动带对 lx/bqmc。
CATEGORIES = [
    # (选项数字, bqmc, lx, 类别名)
    ("1", "1", "7", "政治理论课"),
    ("2", "2", "7", "第一外国语"),
    ("3", "3", "7", "专业外语"),
    ("4", "4", "8", "学位基础课"),
    ("5", "5", "8", "学位专业课"),
    ("6", "6", "8", "专业选修课"),
    ("9", "9", "9", "公共选修课"),
]


def _label_value(page: str, label: str) -> str:
    """fdjwgl 大纲页里某 label 后面 value div 的文本（该页为服务端渲染，结构稳定）。"""
    pat = (
        r'<div[^>]*class="[^"]*base-info-label[^"]*"[^>]*>\s*'
        + re.escape(label)
        + r'.*?<div[^>]*class="[^"]*base-info-value[^"]*"[^>]*>\s*(.*?)\s*</div>'
    )
    m = re.search(pat, page, re.S)
    if not m:
        return ""
    return _html.unescape(re.sub(r"<[^>]+>", "", m.group(1)).strip())


def parse_fdjwgl(url: str, timeout: float) -> tuple[dict | None, str]:
    """抓取并解析一份 fdjwgl 教学大纲公开页，返回 {name,kcdm,ban}。

    大纲页无需登录；失败返回 (None, 原因)。
    """
    try:
        r = requests.get(url, headers={"User-Agent": grab.UA}, timeout=timeout)
    except requests.RequestException as exc:
        return None, f"请求失败：{exc}"
    if r.status_code != 200:
        return None, f"页面返回 HTTP {r.status_code}"
    page = r.text
    name = _label_value(page, "课程名称（中文）")
    lesson = _label_value(page, "课程序号")
    m = CODE_BAN_RE.fullmatch(lesson) or CODE_RE.fullmatch(lesson)
    if not name or not m:
        return None, (
            "页面里没找到「课程名称 / 课程序号」，可能页面结构已改版或链接不是教学大纲详情页，"
            "请核对链接后重试"
        )
    ban = m.group(2) if m.lastindex and m.lastindex >= 2 else ""
    return {"name": name, "kcdm": m.group(1), "ban": ban}, ""


def parse_manual_input(raw: str, timeout: float) -> tuple[dict | None, str]:
    """把用户在手工补充里输入的一行转成候选课程，只认 fdjwgl 大纲详情链接。

    返回 {"name","kcdm","ban"}（课程名 + 课程序号解析自页面）。
    """
    raw = raw.strip()
    if not FDJWGL_URL_RE.match(raw):
        return None, (
            "只支持 fdjwgl「教学大纲」详情页链接，例如\n"
            "    https://fdjwgl.fudan.edu.cn/manager/teaching-syllabus/open-info/1053822"
        )
    return parse_fdjwgl(raw, timeout)


def detect_term_prefix(lists_: list, old: dict) -> str | None:
    """取当前学期前缀（bjdm 前 10 位）：优先看本次拉到的课程，再看旧 config。"""
    counts: dict[str, int] = {}
    for _group, _lx, _label, _bqmc, rows in lists_:
        for r in rows:
            m = re.match(r"^(\d{10})", str(r.get("BJDM") or ""))
            if m:
                counts[m.group(1)] = counts.get(m.group(1), 0) + 1
    if counts:
        return max(counts, key=counts.get)
    for c in (old.get("courses") or []):
        m = re.match(r"^(\d{10})", str(c.get("bjdm") or ""))
        if m:
            return m.group(1)
    return None


def ask_category(default: str = "5") -> tuple[str, str] | None:
    """问手工补充课程的子分类，返回 (bqmc, lx)；取消返回 None。"""
    log("")
    log("  这门课属于哪个子分类？（编号 = config 里的 bqmc）")
    for num, _bqmc, _lx, cname in CATEGORIES:
        log(f"    [{num}] {cname}")
    log("    [7] 其它（手动输入 lx / bqmc，如其它类别 lx=10）")
    log("    [0] 取消，不加这门")
    while True:
        raw = input(f"  子分类 [{default}]：").strip() or default
        if raw == "0":
            return None
        for num, bqmc, lx, _cname in CATEGORIES:
            if raw == num:
                return bqmc, lx
        if raw == "7":
            lx = input("    lx（课程大类编码，如 7/8/9/10）：").strip()
            bqmc = input("    bqmc（页签编号，如 5）：").strip()
            if lx and bqmc:
                return bqmc, lx
            log("    ✗ lx / bqmc 不能为空")
            continue
        log("    ✗ 请输入 0~9 的数字")


def ask_position(total: int, what: str) -> int:
    """问插入位置（1..total+1），回车默认排最后（优先级最低）。"""
    while True:
        raw = input(
            f"  「{what}」排在待抢列表第几位？（1=最先抢；直接回车=第 {total + 1} 位排最后）："
        ).strip()
        if not raw:
            return total + 1
        if raw.isdigit() and 1 <= int(raw) <= total + 1:
            return int(raw)
        log(f"  ✗ 请输入 1~{total + 1} 的整数")


def _compose_entry(cand: dict, prefix: str | None) -> tuple[dict | None, str]:
    """按解析结果 + 当前学期前缀拼 course 条目，只再问一次子分类。

    cand 必含 name/kcdm/ban（均来自大纲页面）；缺班号或前缀时直接报错返回，
    不再追问细节，保持简单。
    """
    kcdm, ban = cand["kcdm"], cand["ban"]
    name = (cand.get("name") or "").strip() or kcdm
    if not ban:
        return None, "页面课程序号里没有班号（形如 EIE60029.02 才带班号），无法拼 bjdm"
    if not prefix:
        return None, (
            "无法确定学年学期前缀（bjdm 前 10 位）。请先在上面三类里选至少一门课，"
            "或保留现有 config.json 里的任意一条课程记录，再重跑本步"
        )
    bqmc_lx = ask_category()
    if bqmc_lx is None:
        return None, "已取消"
    bqmc, lx = bqmc_lx
    return {
        "name": name,
        "kcdm": kcdm,
        "bjdm": f"{prefix}{kcdm}.{ban}",
        "lx": lx,
        "bqmc": bqmc,
        "enabled": True,
    }, ""


def add_courses_manually(
    courses: list, old_courses: list, prefix: str | None, timeout: float = 12.0
) -> int:
    """循环接收 fdjwgl 大纲详情链接，解析后按用户给的位置插入 courses。

    旧 config 里已存在同一课程代码的条目时直接复用（bjdm/lx/bqmc 早已抓准），
    不再重复提问；新课程只问一次子分类和顺位。
    返回成功添加的门数；全程不写文件，由 main 统一落盘。
    """
    log("")
    log("=" * 60)
    log("  手工补充：课程列表里看不到的课")
    log("=" * 60)
    log("  适用：暂时没有选课资格、上面列表里看不到，但想先占位/到点就抢的课")
    log("  把 fdjwgl「教学大纲」详情页链接粘贴进来即可（可多门，逐行粘贴），例如：")
    log("    https://fdjwgl.fudan.edu.cn/manager/teaching-syllabus/open-info/1053822")
    log("  程序会解析课程名与课程序号，自动按当前学期前缀拼好 bjdm；输完直接回车结束")
    seen = {c.get("kcdm") for c in courses if c.get("kcdm")}
    old_by_code: dict[str, dict] = {}
    for c in old_courses:
        if c.get("kcdm") and c["kcdm"] not in old_by_code:
            old_by_code[c["kcdm"]] = c
    added = 0
    n = 1
    while True:
        log("")
        try:
            raw = input(f"第 {n} 门（fdjwgl 教学大纲链接，直接回车结束）：").strip()
        except EOFError:
            raise  # 交给顶层统一收尾
        if not raw:
            break
        cand, err = parse_manual_input(raw, timeout)
        if not cand:
            log(f"  ✗ {err}")
            continue
        kcdm, ban = cand["kcdm"], cand["ban"]
        if kcdm in seen:
            log(f"  ✗ {kcdm} 已在待抢列表里（或本次刚加入过），跳过")
            continue
        legacy = old_by_code.get(kcdm)
        if legacy:
            log(f"  检测到旧 config 里已有这门课，直接复用原条目（重新启用）：")
            log(f"    {legacy.get('name') or kcdm}  bjdm={legacy.get('bjdm')}"
                f"  lx={legacy.get('lx')} bqmc={legacy.get('bqmc')}")
            entry = dict(legacy)
            entry["enabled"] = True
        else:
            entry, why = _compose_entry(cand, prefix)
            if entry is None:
                log(f"  ✗ {why}")
                continue
        log("")
        log(f"  将加入：{entry['name']} [{entry['kcdm']}]")
        log(f"    bjdm={entry['bjdm']}   lx={entry['lx']} bqmc={entry['bqmc']}（参与抢课）")
        pos = ask_position(len(courses), entry["name"])
        courses.insert(pos - 1, entry)
        seen.add(kcdm)
        added += 1
        n += 1
        log(f"  ✓ 已{'复用' if legacy else '补入'}并排到第 {pos} 位"
            f"（资格未开放时服务器会拒收，脚本会自动一直重试到放号/收工）")
    return added


def main() -> int:
    log("复旦研究生选课 · 预选课助手")
    log(f"项目目录：{BASE_DIR}")
    log("")

    # ---- 会话设置：沿用已有 config.json 的其它配置，或首次运行用默认 ----
    old = {}
    if os.path.exists(CONFIG_PATH):
        try:
            old = json.load(open(CONFIG_PATH, encoding="utf-8"))
            log(f"已检测到现有 config.json，将保留其设置，仅重建课程与时间")
        except Exception:
            log("⚠ 现有 config.json 无法解析，将按默认设置重建")
    cfg = {**DEFAULT_CFG, **{k: v for k, v in old.items() if k in DEFAULT_CFG}}

    # ---- 1. 登录态 ----
    log("正在获取并验证登录态 ...")
    cookie = ensure_cookie(cfg)
    log("✓ 登录态有效")

    # ---- 2. 拉课程 ----
    log("正在从选课系统拉取课程 ...")
    lists_ = fetch_lists(cookie, timeout=float(cfg.get("http_timeout", 12)))
    log("")
    log("提示：类别按 学科专业课 → 学位公共课 → 公共选修课 顺序展示；")
    log("      跨类别挑选时，先展示的类别会先进入待抢列表（config 顺序 = 抢课优先级）")
    log("")

    # ---- 3. 逐类选择 ----
    courses: list[dict] = []
    skipped_no_bjdm = 0
    for group, lx, label, bqmc, rows in lists_:
        picked = pick_group(f"{group} · {label}（自动写入 lx={lx} bqmc={bqmc}）", rows)
        added = 0
        for i in picked:
            row = rows[i - 1]
            if not row.get("BJDM"):
                log(f"  ⚠ {row.get('KCMC', '（未命名）')} 没有班级代码，已跳过（服务器未提供该班次）")
                skipped_no_bjdm += 1
                continue
            courses.append(to_course(lx, bqmc, row))
            added += 1
        if added:
            log(f"  ✓ {label}：已选 {added} 门")
    if skipped_no_bjdm:
        log(f"⚠ 共 {skipped_no_bjdm} 个无班级代码的班次被跳过")

    # ---- 3.5 手工补充：列表里看不到的课（如暂无选课资格）----
    prefix = detect_term_prefix(lists_, old)
    added_manual = add_courses_manually(
        courses,
        old.get("courses") or [],
        prefix,
        timeout=float(cfg.get("http_timeout", 12)),
    )

    log("")
    log("=" * 60)
    if not courses:
        log("你一门都没选，已取消，未写入 config.json")
        return 0
    log(f"共选 {len(courses)} 门（顺序即抢课优先级，含手工补充 {added_manual} 门）：")
    for i, c in enumerate(courses, 1):
        log(f"  {i:2d}. [{c['kcdm']}] {c['name']}（{c['bjdm']}）")
    log("")

    # ---- 5. 开抢时间 ----
    old_start, old_end = old.get("start_time"), old.get("end_time")
    if old_start and old_end:
        try:
            old_end_dt = dt.datetime.strptime(old_end, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            old_end_dt = None
        if old_end_dt is not None and old_end_dt <= dt.datetime.now():
            def_start, def_end = default_window()
            log(
                f"原 config 的开抢窗口已过（{old_start} ~ {old_end}），"
                f"默认顺延到最近一场放号：{def_start} 起跑 / {def_end} 收工"
            )
            log("直接回车即可；也可输入新时间覆盖")
        else:
            def_start, def_end = old_start, old_end
            log("沿用现有 config.json 的开抢窗口，直接回车即可；也可输入新时间覆盖")
    else:
        def_start, def_end = default_window()
        log("默认取最近一场放号（每天 10:00 / 13:00 两场，提前 5 秒起跑、放号后 30 分钟收工）")
        log(f"当天两场已过则自动顺延到明天第一场。当前默认：{def_start} 起跑 / {def_end} 收工，直接回车即可")
    start_time = ask_time("开抢时间 start_time", def_start)
    end_time = ask_time("收工时间 end_time", def_end)
    if dt.datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S") <= dt.datetime.strptime(
        start_time, "%Y-%m-%d %H:%M:%S"
    ):
        log("✗ end_time 必须晚于 start_time")
        return 1

    # ---- 6. 写文件 ----
    if os.path.exists(CONFIG_PATH):
        try:
            shutil.copy(CONFIG_PATH, CONFIG_BAK)
            log(f"原 config.json 已备份为 {os.path.basename(CONFIG_BAK)}")
        except OSError as exc:
            log(f"⚠ 备份失败（{exc}），继续写入")
    new_cfg = {**DEFAULT_CFG, **{k: v for k, v in old.items() if k not in ("courses", "start_time", "end_time")}}
    new_cfg["courses"] = courses
    new_cfg["start_time"] = start_time
    new_cfg["end_time"] = end_time
    with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
        json.dump(new_cfg, fh, ensure_ascii=False, indent=2)
    log(f"✓ 已生成 {CONFIG_PATH}（{len(courses)} 门课）")
    log("")
    log("下一步：双击「scripts/选课助手」，先选 1 自检，到点选 3 开始抢课即可")
    log(f"      或命令行：python3 src/grab.py   （--now 立即开抢）")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except EOFError:
        log("\n输入流已结束（非交互环境），未生成 config.json。")
        log("请在真实终端里运行：双击 scripts/选课助手（菜单选 2 预选课）或 python3 src/preselect.py")
        sys.exit(130)
    except KeyboardInterrupt:
        log("\n已手动中止")
        sys.exit(130)
