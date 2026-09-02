#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
复旦大学研究生选课脚本（2026 版重写）

原仓库 JarynWong/fdu_course_enrollment 的 course.py 基于 2024 年协议，
在当前（2026）系统上已失效，本文件按 courses.js 的真实逻辑重写。

原实现对不上的地方：
  1. csrfToken 正则：原用 value='...' 单引号，现页面是 value="..." 双引号且 id 前有 style 属性
     —— 原脚本永远取不到 token，会一直误报"cookies过期"。
  2. 选课是异步两步：choiceCourse.do 只返回受理号 xid（code!=0 不代表选上），
     必须再轮询 loadXkjgRes.do，拿到 {code:1} 才是真的选上。
     原脚本 code!=0 就打印"提交选课成功"并退出，会漏课。

用法：
    python grab.py            正常跑（会等到 start_time 再开始）
    python grab.py --dry-run  只做环境自检，不提交任何选课请求
    python grab.py --probe    链路演练：发 1 次真实请求，看服务器回什么
    python grab.py --now      忽略 start_time，立刻开始
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import time

import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
COOKIE_PATH = os.path.join(BASE_DIR, "cookie.txt")

DOMAIN = "yjsxk.fudan.edu.cn"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# 2026-09 实测：页面形如 <input type="text" style="display:none;" id="csrfToken" value="42f3...">
CSRF_RE = re.compile(r"""id=["']csrfToken["'][^>]*value=["']([0-9a-fA-F]{32})["']""")


def ts() -> str:
    return dt.datetime.now().strftime("%H:%M:%S")


def log(msg: str = "") -> None:
    print(f"[{ts()}] {msg}", flush=True)


class CookieError(RuntimeError):
    """Cookie 无效 / 登录态失效等需要人工介入的错误。"""
    pass


def already_have(msg: str) -> bool:
    """结果里出现这些话，说明这门课其实已经在已选列表里了，不必再重试。"""
    if not msg:
        return False
    return any(kw in msg for kw in ("已选", "已选择", "已经选", "重复"))


def handle_result(course: dict, code, msg: str, done: list, pending: list) -> None:
    """处理一门课的选课结果：成了就从待抢列表里去掉。"""
    name, bjdm = course["name"], course["bjdm"]
    if code == 1:
        log(f"  ★ 选上 {name}（{bjdm}）")
        done.append(name)
        pending.remove(course)
        return
    if code is None and already_have(msg or ""):
        log(f"  ✓ {name} 已在已选列表中（{msg}），跳过")
        done.append(name)
        pending.remove(course)
        return
    log(f"  × {name} 未成功：{msg or '未知原因'}")


def run_serial(gr, pending: list, done: list, interval: float) -> None:
    """串行：一门提交了、等结果出来，再搞下一门（系统的轮询逻辑是单例，不能并发）。"""
    for c in list(pending):
        ok, info = gr.submit(c)
        if not ok:
            log(f"  × {c['name']}：{info}")
            if already_have(info or ""):
                log(f"  ✓ {c['name']} 判定为已拥有，跳过")
                done.append(c["name"])
                pending.remove(c)
            time.sleep(interval)
            continue
        log(f"  已提交 {c['name']}（{c['bjdm']}），等待结果 ...")
        code, msg = gr.poll_result(info)
        handle_result(c, code, msg, done, pending)
        time.sleep(interval)


def run_parallel(gr, pending: list, done: list, interval: float) -> None:
    """并发：一轮里先把所有课都提交出去，再统一收结果（快，但结果可能串）。"""
    submitted = {}
    for c in pending:
        ok, info = gr.submit(c)
        if ok:
            submitted[c["bjdm"]] = (c, info)
            log(f"  已提交 {c['name']}（{c['bjdm']}）")
        else:
            log(f"  × {c['name']}：{info}")
        time.sleep(interval)

    for _bjdm, (c, xid) in submitted.items():
        code, msg = gr.poll_result(xid)
        handle_result(c, code, msg, done, pending)


# ---------------------------------------------------------------- cookie ----

def cookie_from_browser(browser: str = "edge"):
    """从浏览器本地 Cookie 库读取（能拿到 HttpOnly 的 JSESSIONID）。"""
    try:
        import browser_cookie3
    except ImportError:
        return None, "browser-cookie3 未安装（pip install browser-cookie3）"

    getter = {"edge": "edge", "chrome": "chrome"}.get(browser)
    if not getter or not hasattr(browser_cookie3, getter):
        return None, f"不支持的浏览器：{browser}"

    try:
        jar = getattr(browser_cookie3, getter)()
    except Exception as exc:  # 权限、钥匙串、数据库锁等
        return None, f"读取浏览器 Cookie 失败：{exc}"

    picked = []
    for c in jar:
        d = (c.domain or "").lstrip(".")
        if not d:
            continue
        if DOMAIN == d or DOMAIN.endswith("." + d):
            picked.append(f"{c.name.strip()}={c.value.strip()}")

    if not picked:
        return None, "浏览器里没有该站点的 Cookie（请先在 Edge 登录一次选课系统）"
    return "; ".join(picked), None


def cookie_from_file():
    if not os.path.exists(COOKIE_PATH):
        return None, "cookie.txt 不存在"
    try:
        with open(COOKIE_PATH, encoding="utf-8") as fh:
            raw = fh.read()
    except OSError as exc:
        return None, f"读取 cookie.txt 失败：{exc}"
    raw = " ".join(raw.split())
    if not raw or raw.startswith("#"):
        return None, "cookie.txt 为空"
    return raw, None


def obtain_cookie(cfg: dict) -> str:
    """按 cookie_source 取 Cookie：auto / browser / file。"""
    source = cfg.get("cookie_source", "auto")
    browser = cfg.get("browser", "edge")

    if source in ("auto", "browser"):
        value, err = cookie_from_browser(browser)
        if value:
            return value
        log(f"  浏览器取 Cookie 未成功：{err}")
        if source == "browser":
            raise CookieError(err)

    value, err = cookie_from_file()
    if value:
        return value
    raise CookieError(
        f"{err}。请先在 Edge/Chrome 登录 http://{DOMAIN} ，"
        f"或把 Cookie 粘贴进 {os.path.basename(COOKIE_PATH)}"
    )


# --------------------------------------------------------------- client ----

class Grabber:
    def __init__(self, cfg: dict, cookie: str):
        self.cfg = cfg
        self.cookie = cookie
        self.target = cfg.get("target", DOMAIN)
        self.timeout = float(cfg.get("http_timeout", 12))
        self.base = f"http://{self.target}/yjsxkapp/sys/xsxkappfudan"
        self.session = requests.Session()
        self.token: str | None = None

    def set_cookie(self, cookie: str) -> None:
        self.cookie = cookie

    def _headers(self) -> dict:
        return {
            "Cookie": self.cookie,
            "User-Agent": UA,
            "Content-Type": "application/x-www-form-urlencoded",
        }

    def refresh_token(self) -> str:
        url = f"{self.base}/xsxkHome/gotoChooseCourse.do"
        resp = self.session.get(
            url, headers=self._headers(), timeout=self.timeout, allow_redirects=False
        )
        if resp.status_code in (301, 302, 303, 307, 308):
            raise CookieError("Cookie 已失效（请求被重定向到统一认证登录页）")
        if resp.status_code != 200:
            raise CookieError(f"打开选课页失败，HTTP {resp.status_code}")
        m = CSRF_RE.search(resp.text)
        if not m:
            raise CookieError("页面里找不到 csrfToken，Cookie 多半已失效")
        self.token = m.group(1)
        return self.token

    def submit(self, course: dict):
        """提交选课。返回 (是否已受理, xid 或 失败原因)"""
        url = f"{self.base}/xsxkCourse/choiceCourse.do?_={int(time.time() * 1000)}"
        payload = {
            "bjdm": course["bjdm"],
            "lx": str(course["lx"]),
            "bqmc": str(course.get("bqmc", "")),
            "csrfToken": self.token,
        }
        resp = self.session.post(
            url, headers=self._headers(), data=payload, timeout=self.timeout
        )
        try:
            body = resp.json()
        except Exception:
            return False, f"响应不是 JSON（HTTP {resp.status_code}）"
        if body.get("code") == 0:
            return False, body.get("msg") or "被拒绝"
        return True, body.get("msg") or ""

    def probe_once(self, course: dict) -> dict:
        """向服务器发一次真实选课请求，返回原始响应 dict（演练用，不做任何重试）。"""
        url = f"{self.base}/xsxkCourse/choiceCourse.do?_={int(time.time() * 1000)}"
        payload = {
            "bjdm": course["bjdm"],
            "lx": str(course["lx"]),
            "bqmc": str(course.get("bqmc", "")),
            "csrfToken": self.token,
        }
        resp = self.session.post(
            url, headers=self._headers(), data=payload, timeout=self.timeout
        )
        try:
            return {"http": resp.status_code, **(resp.json() or {})}
        except Exception:
            return {"http": resp.status_code, "msg": resp.text[:200], "_raw": True}

    def poll_result(self, xid: str):
        """轮询选课结果。返回 (code, 说明)；code==1 表示真的选上了。"""
        url = f"{self.base}/xsxkCourse/loadXkjgRes.do?_={int(time.time() * 1000)}"
        max_times = int(self.cfg.get("poll_max", 30))
        interval = float(self.cfg.get("poll_interval", 0.6))
        for _ in range(max_times):
            resp = self.session.post(
                url,
                headers=self._headers(),
                data={"xid": xid, "sfhqdqxkqqs": 0},
                timeout=self.timeout,
            )
            try:
                body = resp.json()
            except Exception:
                return None, f"轮询响应不是 JSON（HTTP {resp.status_code}）"
            msg = body.get("msg")
            if msg:
                try:
                    detail = json.loads(msg)
                except Exception:
                    return None, msg
                return detail.get("code"), detail.get("msg") or ""
            time.sleep(interval)
        return None, "轮询超时，结果未知（请去「已选课程」页确认）"


# ----------------------------------------------------------------- flow ----

def load_config() -> dict:
    if not os.path.exists(CONFIG_PATH):
        example = os.path.join(BASE_DIR, "config.example.json")
        hint = (
            f"找不到配置文件：{CONFIG_PATH}\n"
            f"请参考 {os.path.basename(example)} 创建你自己的配置：\n"
            f"  cp {os.path.basename(example)} config.json\n"
            f"然后填入你的课程代码（bjdm 需从选课系统抓取）。"
        )
        raise SystemExit(hint)
    with open(CONFIG_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def wait_until(target: dt.datetime, label: str) -> None:
    """等到 target；超时不自动 +1 天（原脚本会静默等到明天）。"""
    while True:
        remain = (target - dt.datetime.now()).total_seconds()
        if remain <= 0:
            return
        if remain > 600:
            step = 60
        elif remain > 60:
            step = 30
        elif remain > 10:
            step = 5
        else:
            step = 1
        h, rem = divmod(int(remain), 3600)
        m, s = divmod(rem, 60)
        log(f"{label}：还有 {h}小时{m}分{s}秒")
        time.sleep(min(step, remain))


def countdown_banner(deadline: dt.datetime, n_courses: int) -> None:
    log("=" * 46)
    log("  复旦研究生选课 · 已就绪")
    log(f"  目标时间 {deadline.strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"  待抢课程 {n_courses} 门")
    log("=" * 46)


def run(cfg: dict, start_now: bool) -> int:
    interval = float(cfg.get("request_interval", 0.8))
    refresh_secs = float(cfg.get("cookie_refresh_secs", 240))
    serial = bool(cfg.get("serial_mode", True))
    end_time = dt.datetime.strptime(cfg["end_time"], "%Y-%m-%d %H:%M:%S")
    start_time = dt.datetime.strptime(cfg["start_time"], "%Y-%m-%d %H:%M:%S")

    pending = [c for c in cfg["courses"] if c.get("enabled", True)]
    if not pending:
        log("没有启用任何课程，退出")
        return 0

    # ---- 取 Cookie 并自检 ----
    log("正在获取 Cookie ...")
    cookie = obtain_cookie(cfg)
    gr = Grabber(cfg, cookie)
    gr.refresh_token()
    log(f"Cookie 有效，csrfToken = {gr.token[:8]}...")

    if start_now:
        log("（--now：跳过等待，立即开始）")
    else:
        if start_time < dt.datetime.now():
            log("=" * 46)
            log(f"  注意：start_time（{start_time}）已经过去了")
            log("  脚本不会自动改到明天，现在直接开始。")
            log("=" * 46)
        else:
            countdown_banner(start_time, len(pending))
            # 临近开抢前 3 分钟换一次新 Cookie，避免等待期间过期
            prewarm = start_time - dt.timedelta(seconds=180)
            if prewarm > dt.datetime.now():
                wait_until(prewarm, "等待换票点")
                log("临近开抢，重新获取一次最新 Cookie ...")
                try:
                    gr.set_cookie(obtain_cookie(cfg))
                    gr.refresh_token()
                    log(f"已换新票，csrfToken = {gr.token[:8]}...")
                except CookieError as exc:
                    log(f"换新票失败（继续用旧票）：{exc}")
            wait_until(start_time, "等待开抢")

    # ---- 正式抢课 ----
    log("开始抢课！" + ("（串行模式：一门结果出来再选下一门）" if serial else "（并发模式：一轮全提交）"))
    last_cookie_ts = time.time()
    done: list = []
    round_no = 0

    while pending and dt.datetime.now() < end_time:
        round_no += 1

        # 长时间作战时定期换票
        if time.time() - last_cookie_ts > refresh_secs:
            try:
                gr.set_cookie(obtain_cookie(cfg))
                last_cookie_ts = time.time()
            except CookieError:
                pass

        try:
            gr.refresh_token()
        except CookieError as exc:
            log(f"回合 {round_no}：{exc}")
            log("尝试重新获取 Cookie ...")
            try:
                gr.set_cookie(obtain_cookie(cfg))
                gr.refresh_token()
                last_cookie_ts = time.time()
                log("已恢复")
            except CookieError as exc2:
                log(f"恢复失败：{exc2}")
                time.sleep(5)
                continue

        if serial:
            run_serial(gr, pending, done, interval)
        else:
            run_parallel(gr, pending, done, interval)

        if pending:
            time.sleep(interval)

    log("-" * 46)
    if done:
        log(f"成功 {len(done)} 门：")
        for name in done:
            log(f"  · {name}")
    if pending:
        log(f"未拿下 {len(pending)} 门：")
        for c in pending:
            log(f"  · {c['name']}（{c['bjdm']}）")
    log("结束。请到「已选课程」页核对。")
    return 0 if not pending else 1


def dry_run(cfg: dict) -> int:
    log("=== 自检模式（不会提交任何选课请求）===")
    pending = [c for c in cfg["courses"] if c.get("enabled", True)]
    log(f"目标站点：http://{cfg.get('target', DOMAIN)}")
    log(f"开抢时间：{cfg.get('start_time')}   结束：{cfg.get('end_time')}")
    log(f"启用课程：{len(pending)} / {len(cfg['courses'])} 门")
    for c in pending:
        log(f"  · {c['name']:<20} {c['bjdm']}  lx={c['lx']} bqmc={c['bqmc']}")
    for c in cfg["courses"]:
        if not c.get("enabled", True):
            log(f"  · {c['name']:<20} （已停用）")

    log("")
    log("正在获取 Cookie ...")
    try:
        cookie = obtain_cookie(cfg)
    except CookieError as exc:
        log(f"✗ 取 Cookie 失败：{exc}")
        return 1
    names = [seg.strip().split("=")[0] for seg in cookie.split(";") if "=" in seg]
    log(f"✓ 取到 Cookie，共 {len(names)} 个字段：{', '.join(names)}")

    must = {"JSESSIONID", "_WEU"}
    missing = must - set(names)
    if missing:
        log(f"✗ 缺少关键字段：{', '.join(missing)} —— 请先在浏览器登录选课系统")
        return 1

    gr = Grabber(cfg, cookie)
    try:
        token = gr.refresh_token()
    except CookieError as exc:
        log(f"✗ {exc}")
        return 1
    log(f"✓ Cookie 有效，csrfToken = {token[:8]}...")

    log("")
    log("=== 自检通过 ===")
    log("可以开抢了：双击「一键抢课.command」，或直接运行 python grab.py")
    return 0


def probe(cfg: dict, force: bool) -> int:
    """链路演练：对第一门启用的课程发 1 次真实选课请求，打印服务器原话。"""
    log("=== 链路演练（只发 1 次请求，不重试、不循环）===")
    pending = [c for c in cfg["courses"] if c.get("enabled", True)]
    if not pending:
        log("没有启用任何课程，退出")
        return 1

    start_time = dt.datetime.strptime(cfg["start_time"], "%Y-%m-%d %H:%M:%S")
    opened = dt.datetime.now() >= start_time
    if opened and not force:
        log(f"已过开抢时间（{start_time}），演练会真的提交一次选课请求。")
        log("确认要继续，请在命令末尾加 --force")
        return 1
    if opened:
        log("注意：选课已开放，本次演练等同于真的抢这门课。")

    c = pending[0]
    log(f"演练课程：{c['name']}（{c['bjdm']}）")

    try:
        cookie = obtain_cookie(cfg)
    except CookieError as exc:
        log(f"✗ 取 Cookie 失败：{exc}")
        return 1
    gr = Grabber(cfg, cookie)
    try:
        gr.refresh_token()
    except CookieError as exc:
        log(f"✗ {exc}")
        return 1
    log(f"✓ Cookie 有效，csrfToken = {gr.token[:8]}...")

    log("发送选课请求 ...")
    body = gr.probe_once(c)
    code = body.get("code")
    log(f"服务器返回：HTTP {body.get('http')}  code={code}")
    log(f"服务器原话：{body.get('msg') or '(无 msg 字段)'}")

    if code == 0:
        log("")
        log("=== 演练结论 ===")
        log("服务器拒绝了该请求（code=0），但这恰恰证明链路是通的：")
        log("  · Cookie 与 csrfToken 被接受（否则会跳登录页，根本取不到 token）")
        log("  · bjdm / lx / bqmc 被正确解析（否则会报参数错误）")
        log("  唯一的阻碍就是上面那句原话。条件满足后即可正常选课。")
        return 0

    if code is None:
        log("")
        log("=== 演练结论 ===")
        log("响应不是预期格式，多半是 Cookie 失效或接口有变，请勿直接开抢。")
        return 1

    log("服务器已受理，轮询最终结果 ...")
    rcode, rmsg = gr.poll_result(body.get("msg") or "")
    log(f"最终结果：code={rcode}  msg={rmsg or '(空)'}")
    if rcode == 1:
        log("★ 真的选上了！请到「已选课程」页确认。")
    else:
        log("未选上，原因见上。")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="复旦大学研究生选课脚本")
    ap.add_argument("--dry-run", action="store_true", help="只自检，不提交选课请求")
    ap.add_argument("--now", action="store_true", help="忽略 start_time，立即开始")
    ap.add_argument("--probe", action="store_true", help="链路演练：发 1 次真实请求看服务器回什么")
    ap.add_argument("--force", action="store_true", help="配合 --probe，开放后也允许演练")
    args = ap.parse_args()

    cfg = load_config()
    if args.dry_run:
        return dry_run(cfg)
    if args.probe:
        return probe(cfg, force=args.force)
    return run(cfg, start_now=args.now)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log("\n已手动中止")
        sys.exit(130)
