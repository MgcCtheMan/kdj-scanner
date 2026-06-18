"""
A股 KDJ 指标筛选脚本
每天运行一次，找出 J 值 < -5 或 J 值 < 30 的股票
需要: pip install akshare pandas
"""

import akshare as ak
import pandas as pd
import numpy as np
from datetime import datetime, timedelta


def calc_kdj(df: pd.DataFrame, n: int = 9):
    """计算 KDJ 指标，返回最后一行的 K, D, J 值"""
    low_list = df["最低价"].rolling(window=n).min()
    high_list = df["最高价"].rolling(window=n).max()

    rsv = (df["收盘价"] - low_list) / (high_list - low_list) * 100
    rsv = rsv.fillna(50)

    k = rsv.ewm(com=2, adjust=False).mean()  # 1/3 平滑 ≈ ewm(com=2)
    d = k.ewm(com=2, adjust=False).mean()
    j = 3 * k - 2 * d

    return float(k.iloc[-1]), float(d.iloc[-1]), float(j.iloc[-1])


def main():
    print(f"=== A股 KDJ 超卖筛选 ===")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

    # 1. 获取所有 A 股列表
    print("正在获取 A 股列表...")
    stock_list = ak.stock_zh_a_spot_em()
    # 过滤掉新股、ST、科创（可选）
    codes = stock_list[~stock_list["名称"].str.contains("ST|退市|N")]
    print(f"共 {len(codes)} 只股票待筛选\n")

    # 筛选条件
    j_low = []   # J < -5
    j_oversold = []  # J < 30

    total = len(codes)
    for idx, (_, row) in enumerate(codes.iterrows()):
        code = row["代码"]
        name = row["名称"]
        if (idx + 1) % 500 == 0:
            print(f"  进度: {idx + 1}/{total}")

        try:
            # 2. 获取日 K 线（最近 30 天足够算 KDJ(9)）
            df = ak.stock_zh_a_hist(symbol=code, period="daily",
                                     start_date=(datetime.now() - timedelta(days=60)).strftime("%Y%m%d"),
                                     end_date=datetime.now().strftime("%Y%m%d"),
                                     adjust="qfq")  # 前复权
            if len(df) < 12:
                continue

            k, d, j = calc_kdj(df)

            if j < -5:
                j_low.append({"代码": code, "名称": name, "K": round(k, 2), "D": round(d, 2), "J": round(j, 2)})
            elif j < 30:
                j_oversold.append({"代码": code, "名称": name, "K": round(k, 2), "D": round(d, 2), "J": round(j, 2)})

        except Exception:
            continue

    # 3. 输出结果
    print(f"\n{'='*60}")
    print(f"🔴 J值 < -5（极度超卖）: {len(j_low)} 只")
    print(f"{'='*60}")
    if j_low:
        result_df = pd.DataFrame(j_low).sort_values("J")
        for _, r in result_df.iterrows():
            print(f"  {r['代码']}  {r['名称']:<8s}  K={r['K']:.2f}  D={r['D']:.2f}  J={r['J']:.2f}")
    else:
        print("  无")

    print(f"\n{'='*60}")
    print(f"🟡 J值 < 30（超卖区域）: {len(j_oversold)} 只")
    print(f"{'='*60}")
    if j_oversold:
        result_df = pd.DataFrame(j_oversold).sort_values("J")
        for _, r in result_df.iterrows():
            print(f"  {r['代码']}  {r['名称']:<8s}  K={r['K']:.2f}  D={r['D']:.2f}  J={r['J']:.2f}")
    else:
        print("  无")

    # 保存到文件
    today = datetime.now().strftime("%Y%m%d")
    filename = f"kdj_scan_{today}.csv"
    all_results = j_low + j_oversold
    if all_results:
        pd.DataFrame(all_results).sort_values("J").to_csv(filename, index=False, encoding="utf-8-sig")
        print(f"\n结果已保存到 {filename}")


if __name__ == "__main__":
    main()
