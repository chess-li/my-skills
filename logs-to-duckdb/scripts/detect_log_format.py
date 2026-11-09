#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""分析日志目录的行格式，推荐入库 profile；都不匹配时输出未命中样例行，指引写自定义正则。

用法:
    python3 detect_log_format.py --dir <日志目录> [--files N] [--lines N] [--min-rate 0.9] [--profile 名]

输出解读:
- 每个内置 profile 对候选起始行的匹配率；推荐匹配率最高且 >= --min-rate 的 profile；
- 目录内各文件最佳 profile 不一致或最高匹配率不足时，逐文件列出匹配率并给出未命中样例行，
  提示用 logs_to_duckdb.py --regex 自定义命名组正则（约定见 references/formats.md）。
"""
import argparse
import gzip
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from profiles import PROFILES, compile_profile  # noqa: E402

# 起始行启发：以日期时间开头；续行（堆栈帧 / ... N more / Caused by）排除
START_HINT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}")
CONT_RE = re.compile(r"^\s*(at\s|\.\.\. \d+ more|Caused by:)")


def open_log(path):
    if path.endswith(".gz"):
        return gzip.open(path, "rt", encoding="utf-8", errors="replace")
    return open(path, "r", encoding="utf-8", errors="replace")


def collect_candidates(path, limit):
    """抽取疑似日志起始行（按起始行启发 + 排除续行），最多 limit 条。"""
    out = []
    with open_log(path) as f:
        for line in f:
            s = line.rstrip("\n")
            if CONT_RE.match(s):
                continue
            if START_HINT_RE.match(s):
                out.append(s)
                if len(out) >= limit:
                    break
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="日志目录（.log/.log.gz）")
    ap.add_argument("--files", type=int, default=8, help="抽样文件数（默认 8，按文件名排序）")
    ap.add_argument("--lines", type=int, default=1000, help="每文件最多抽样起始行数（默认 1000）")
    ap.add_argument("--min-rate", type=float, default=0.9, help="推荐阈值（默认 0.9）")
    ap.add_argument("--profile", help="只测指定 profile")
    ap.add_argument("--verbose", action="store_true", help="打印未命中样例行（最多 10 条/文件）")
    args = ap.parse_args()

    names = [args.profile] if args.profile else sorted(PROFILES)
    compiled = {}
    for name in names:
        try:
            compiled[name] = compile_profile(name)[0]
        except ValueError as e:
            sys.exit(str(e))

    files = sorted(f for f in os.listdir(args.dir) if f.endswith((".log", ".log.gz")))
    if not files:
        sys.exit(f"目录下没有 .log/.log.gz 文件: {args.dir}")
    sampled = files[: args.files]

    total = {n: 0 for n in names}
    n_candidates = 0
    per_file = []          # (file, 最佳profile, 最佳匹配数, 候选数, {profile: matched})
    unmatched_samples = {} # file -> list[str]

    for fname in sampled:
        path = os.path.join(args.dir, fname)
        cands = collect_candidates(path, args.lines)
        if not cands:
            per_file.append((fname, None, 0, 0, {}))
            continue
        matched = {}
        best_name, best_n = None, -1
        misses = []
        for line in cands:
            hit = None
            for name, rx in compiled.items():
                if rx.match(line):
                    matched[name] = matched.get(name, 0) + 1
                    hit = name
                    break
            if hit is None:
                misses.append(line)
            else:
                if matched[hit] > best_n:
                    best_name, best_n = hit, matched[hit]
        for name in names:
            total[name] += matched.get(name, 0)
        n_candidates += len(cands)
        per_file.append((fname, best_name, best_n, len(cands), matched))
        if misses:
            unmatched_samples[fname] = misses[:10]

    print(f"==> 抽样 {len(sampled)}/{len(files)} 个文件, 候选起始行 {n_candidates} 条")
    if n_candidates == 0:
        print("\n未抽到任何疑似日志起始行——日期前缀可能不是 yyyy-MM-dd[ T] 形态，内置档案均不适用。")
        print("对策: 直接 head 几个文件看行格式，写自定义命名组正则用 --regex 入库（约定见 references/formats.md）。")
        print("（可用 --verbose 参看抽样文件里的原始行，辅助判断哪些行该算起始行。）")
        return

    print("\n各 profile 总体匹配率:")
    ranked = sorted(names, key=lambda n: total[n], reverse=True)
    for name in ranked:
        rate = total[name] / n_candidates if n_candidates else 0.0
        print(f"  {name:16s} {total[name]:>6d}/{n_candidates:<6d} ({rate:.1%})  {PROFILES[name]['desc']}")

    best = ranked[0]
    best_rate = total[best] / n_candidates if n_candidates else 0.0
    print()
    if best_rate >= args.min_rate:
        print(f"推荐 profile: {best}（匹配率 {best_rate:.1%}）")
        print(f"入库命令: python3 scripts/logs_to_duckdb.py --dir {args.dir} --db logs.duckdb --profile {best}")
    else:
        print(f"最高匹配率 {best_rate:.1%}（{best}）低于阈值 {args.min_rate:.0%}，内置档案均不适用。")
        print("对策: 取未命中样例行写自定义命名组正则，用 --regex 入库（命名组约定见 references/formats.md）。")

    mixed = [pf for pf in per_file if pf[4] and (pf[1] != best or pf[2] / pf[3] < args.min_rate)]
    if mixed:
        print("\n匹配不足或与推荐不一致的文件:")
        for fname, bn, bn_n, n, matched in mixed:
            detail = ", ".join(f"{k}:{v}" for k, v in sorted(matched.items(), key=lambda kv: -kv[1]))
            print(f"  {fname}: 最佳={bn or '无'} {bn_n}/{n} ({bn_n / n:.1%}) [{detail}]")

    if unmatched_samples and (args.verbose or best_rate < args.min_rate):
        print("\n未命中样例行（前 10 条/文件）:")
        for fname, misses in unmatched_samples.items():
            print(f"-- {fname}")
            for ln in misses:
                print(f"   {ln[:200]}")


if __name__ == "__main__":
    main()
