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
"""
from __future__ import annotations

import datetime as dt
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

# 首次运行（无 config.json）时的默认设置，与 grab.py 内置默认对齐
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


def pick_category(
    remaining: list[int], lists_: list[tuple[str, int, str, int, list[dict]]]
) -> int | None:
    """循环式挑选的一步：展示「还没挑过」的类别，让用户选一个去挑课。

    返回选中的 lists_ 下标；返回 None 表示用户结束挑选（输入 0 或回车）。
    main 里用它逐轮驱动：每轮挑一个类别、挑完回到本菜单再选下一个，
    直到结束才进入下一步（开抢时间设置）。
    """
    log("")
    log("=" * 60)
    log("  选择要挑的课程类别（每轮挑一个，挑完回到这里）")
    log("=" * 60)
    for idx in remaining:
        _group, _lx, label, _bqmc, rows = lists_[idx]
        log(f"  [{idx + 1}] {label}（{len(rows)} 门）")
    log("")
    log("  输入一个类别编号去挑课；挑完会回到本菜单，可继续挑下一个。")
    log("  输入 0 或直接回车 = 结束挑选（进入开抢时间设置）")
    while True:
        raw = input("  挑哪个类别（回车/0=结束）：").strip()
        if not raw or raw == "0":
            return None
        if not raw.isdigit():
            log(f"  ✗ 无法识别「{raw}」，请输入类别编号")
            continue
        i = int(raw)
        if not (1 <= i <= len(lists_)):
            log(f"  ✗ 编号 {i} 超出范围（1~{len(lists_)}）")
            continue
        idx = i - 1
        if idx not in remaining:
            log(f"  ✗ 类别「{lists_[idx][2]}」已经挑过了")
            continue
        return idx


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

    # ---- 3. 已有课程展示 + 覆盖确认 ----
    old_courses = [dict(c) for c in (old.get("courses") or [])]
    courses: list[dict] = []
    skipped_no_bjdm = 0
    skip_pick = False
    if old_courses:
        log("")
        log("检测到上一轮预选的课程：")
        for i, c in enumerate(old_courses, 1):
            mark = "✓" if c.get("enabled", True) else "✗ 已停用"
            log(f"  {i:2d}. [{c.get('kcdm')}] {c.get('name')}（{c.get('bjdm')}）"
                f" lx={c.get('lx')} bqmc={c.get('bqmc')} {mark}")
        log("")
        ans = input("是否覆盖更新这些课程？[Y/n]（n=保留现有，跳过重新挑选）：").strip()
        if ans.lower() in ("n", "no"):
            courses = old_courses
            skip_pick = True
            log("✓ 保留上一轮预选的课程，跳过类别挑选。")
        else:
            log("将清空上一轮课程，重新挑选。")

    # ---- 3.1 逐类选择（循环式：每轮挑一个类别，挑完回到菜单，0/回车结束）----
    if not skip_pick:
        remaining = list(range(len(lists_)))
        while remaining:
            idx = pick_category(remaining, lists_)
            if idx is None:
                break
            remaining.remove(idx)
            group, lx, label, bqmc, rows = lists_[idx]
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

    log("")
    log("=" * 60)
    if not courses:
        log("你一门都没选，已取消，未写入 config.json")
        return 0
    log(f"共选 {len(courses)} 门（顺序即抢课优先级）：")
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
            def_start, def_end = grab.default_window()
            log(
                f"原 config 的开抢窗口已过（{old_start} ~ {old_end}），"
                f"默认顺延到最近一场放号：{def_start} 起跑 / {def_end} 收工"
            )
            log("直接回车即可；也可输入新时间覆盖")
        else:
            def_start, def_end = old_start, old_end
            log("沿用现有 config.json 的开抢窗口，直接回车即可；也可输入新时间覆盖")
    else:
        def_start, def_end = grab.default_window()
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
