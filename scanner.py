"""
A股 KDJ 超卖筛选 — GitHub Actions 每日自动版
并发获取数据，全市场扫描约 15-30 分钟
"""

import akshare as ak
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import warnings
import os
import sys

warnings.filterwarnings("ignore")


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


def main():
    today = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"=== A股 KDJ 超卖筛选 ===")
    print(f"时间: {today}")
    print(f"并发线程: 8\n")

    # 获取 A 股列表
    print("获取 A 股列表...")
    stock_df = ak.stock_zh_a_spot_em()
    stock_df = stock_df[~stock_df["名称"].str.contains("ST|退市|N|C", na=False)]
    total = len(stock_df)
    print(f"共 {total} 只待筛选\n")

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
        return

    df = pd.DataFrame(results)

    # 分类
    j_low = df[df["J"] < -5].sort_values("J")
    j_oversold = df[(df["J"] >= -5) & (df["J"] < 30)].sort_values("J")

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
    print("\n完成!")


if __name__ == "__main__":
    main()
