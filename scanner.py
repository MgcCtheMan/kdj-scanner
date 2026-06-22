"""
A股 KDJ 超卖筛选 — 腾讯云服务器每日自动版
curl 版：绕过 Python requests TLS 兼容问题
"""

import warnings
import os
import sys

warnings.filterwarnings("ignore")

# ===== 用 curl 替代 requests（解决服务器 TLS 握手失败问题）=====
import subprocess, json, urllib.parse

def _curl_request(url: str, params: dict = None, timeout: int = 15) -> "FakeResponse":
    """用 subprocess+curl 发 HTTP GET 请求，返回伪 requests.Response"""
    full_url = url
    if params:
        query = urllib.parse.urlencode(params)
        full_url = f"{url}?{query}"

    # 构建 User-Agent 和 headers
    import time as _time
    last_err = "unknown"
    for attempt in range(3):
        cmd = [
            "curl", "-s", "-m", str(timeout),
            "--tlsv1.2",  # 强制 TLS 1.2，避免 TLS 1.3 握手问题
            "--retry", "2", "--retry-delay", "2",
            "-H", "Accept: */*",
            "-H", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "-H", "Accept-Language: zh-CN,zh;q=0.9,en;q=0.8",
            "--compressed",
            full_url
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 10)

        class FakeResponse:
            def __init__(self, text, status_code):
                self.text = text
                self.status_code = status_code
                self._text = text

            def json(self):
                return json.loads(self.text)

        if result.returncode == 0 and result.stdout.strip():
            return FakeResponse(result.stdout, 200)
        last_err = result.stderr[:200] if result.stderr else f"empty output (rc={result.returncode})"
        if attempt < 2:
            _time.sleep(2 * (attempt + 1))  # 2, 4 秒退避

    raise ConnectionError(f"curl failed after 3 retries: {last_err}")

# Monkey-patch requests 模块，让 akshare 走 curl
import requests
_original_get = requests.get
def _patched_get(url, params=None, timeout=None, **kwargs):
    t = timeout if isinstance(timeout, (int, float)) else 15
    return _curl_request(url, params=params, timeout=t)

requests.get = _patched_get

# Monkey-patch Session.get too
_original_session_get = requests.sessions.Session.get
def _patched_session_get(self, url, params=None, timeout=None, **kwargs):
    t = timeout if isinstance(timeout, (int, float)) else 15
    return _curl_request(url, params=params, timeout=t)

requests.sessions.Session.get = _patched_session_get

# ===== 现在导入 akshare（会用上面的 curl 替代）=====

import akshare as ak
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


def calc_kdj(df: pd.DataFrame, n: int = 9):
    """计算 KDJ(9,3,3)"""
    low_min = df["最低价"].rolling(window=n).min()
    high_max = df["最高价"].rolling(window=n).max()
    rsv = (df["收盘价"] - low_min) / (high_max - low_min) * 100
    rsv = rsv.fillna(50)

    k = rsv.ewm(com=2, adjust=False).mean()
    d = k.ewm(com=2, adjust=False).mean()
    j = 3 * k - 2 * d

    return float(k.iloc[-1]), float(d.iloc[-1]), float(j.iloc[-1])


def scan_one(row) -> dict | None:
    """扫描单只股票，返回结果或 None"""
    code = row["代码"]
    name = row["名称"]
    try:
        df = ak.stock_zh_a_hist(
            symbol=code, period="daily",
            start_date=(datetime.now() - timedelta(days=60)).strftime("%Y%m%d"),
            end_date=datetime.now().strftime("%Y%m%d"),
            adjust="qfq",
        )
        if df is None or len(df) < 12:
            return None
        k, d, j = calc_kdj(df)
        return {"代码": code, "名称": name, "K": round(k, 2), "D": round(d, 2), "J": round(j, 2)}
    except Exception:
        return None


def send_email(df: pd.DataFrame, today: str):
    """通过 QQ 邮箱 SMTP 发送结果"""
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_pass = os.environ.get("SMTP_PASS", "")
    to_email = os.environ.get("TO_EMAIL", "")

    if not smtp_user or not smtp_pass or not to_email:
        print("\n⚠ 未配置邮箱，跳过发送")
        return

    if len(df) > 0:
        j_low = df[df["J"] < -5].sort_values("J")
        j_oversold = df[(df["J"] >= -5) & (df["J"] < 30)].sort_values("J")
    else:
        j_low = df.copy()
        j_oversold = df.copy()

    # 构建 HTML 邮件
    html = f"""<html><body>
    <h2>KDJ 超卖扫描 — {today}</h2>
    <h3>🔴 J < -5 极度超卖 ({len(j_low)} 只)</h3>
    {j_low.to_html(index=False) if len(j_low) else '<p>无</p>'}
    <h3>🟡 J < 30 超卖区域 ({len(j_oversold)} 只)</h3>
    {j_oversold.to_html(index=False) if len(j_oversold) else '<p>无</p>'}
    <hr><p><small>自动发送 — KDJ Scanner Bot</small></p>
    </body></html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"KDJ 超卖扫描结果 — {today}"
    msg["From"] = smtp_user
    msg["To"] = to_email
    msg.attach(MIMEText(html, "html", "utf-8"))

    try:
        with smtplib.SMTP_SSL("smtp.qq.com", 465, timeout=15) as server:
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_user, [to_email], msg.as_string())
        print(f"\n✅ 邮件已发送到 {to_email}")
    except Exception as e:
        print(f"\n❌ 邮件发送失败: {e}")


def main():
    try:
        _main()
    except Exception as e:
        import traceback
        print(f"\n❌ 脚本异常: {e}")
        traceback.print_exc()
        sys.exit(1)


def _main():
    today = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"=== A股 KDJ 超卖筛选 ===")
    print(f"时间: {today}")
    print(f"并发线程: 8\n")

    # 获取 A 股列表
    print("获取 A 股列表...", flush=True)
    try:
        stock_df = ak.stock_zh_a_spot_em()
        print(f"  获取到 {len(stock_df)} 只股票", flush=True)
        stock_df = stock_df[~stock_df["名称"].str.contains("ST|退市|N|C", na=False)]
        total = len(stock_df)
        print(f"  过滤后共 {total} 只待筛选\n", flush=True)
    except Exception as e:
        print(f"❌ 获取股票列表失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # 并发扫描
    results = []
    done = 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(scan_one, row): row for _, row in stock_df.iterrows()}
        for fut in as_completed(futures):
            done += 1
            if done % 500 == 0 or done == total:
                print(f"  进度: {done}/{total} ({100*done//total}%)")
            r = fut.result()
            if r:
                results.append(r)

    if not results:
        print("\n未找到符合条件的股票")
        df = pd.DataFrame(columns=["代码", "名称", "K", "D", "J"])
    else:
        df = pd.DataFrame(results)

    # 分类
    if len(df) > 0:
        j_low = df[df["J"] < -5].sort_values("J")
        j_oversold = df[(df["J"] >= -5) & (df["J"] < 30)].sort_values("J")
    else:
        j_low = df.copy()
        j_oversold = df.copy()

    # 输出
    def print_section(title, data: pd.DataFrame):
        print(f"\n{'='*70}")
        print(f"  {title}: {len(data)} 只")
        print(f"{'='*70}")
        if len(data) == 0:
            print("  (无)")
        else:
            for _, r in data.iterrows():
                print(f"  {r['代码']}  {r['名称']:<10s}  K={r['K']:6.2f}  D={r['D']:6.2f}  J={r['J']:6.2f}")

    print_section("🔴 J < -5  极度超卖", j_low)
    print_section("🟡 J < 30  超卖区域", j_oversold)

    # 保存 CSV
    out_file = f"result_{datetime.now().strftime('%Y%m%d')}.csv"
    all_results = pd.concat([j_low, j_oversold])
    all_results.to_csv(out_file, index=False, encoding="utf-8-sig")
    print(f"\n结果已保存: {out_file}")

    # GitHub Actions 摘要
    if "GITHUB_STEP_SUMMARY" in os.environ:
        import os
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(f"## KDJ 超卖扫描 — {today}\n\n")
            f.write(f"### 🔴 J < -5 ({len(j_low)} 只)\n\n")
            if len(j_low):
                f.write(j_low.to_markdown(index=False))
            f.write(f"\n### 🟡 J < 30 ({len(j_oversold)} 只)\n\n")
            if len(j_oversold):
                f.write(j_oversold.to_markdown(index=False))

    # 发送邮件
    send_email(df, today)

    print("\n完成!")


if __name__ == "__main__":
    main()
