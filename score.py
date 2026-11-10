"""Optimization score (0 to 100), made only of things that can be changed.

Each criterion has a weight, a target (full points) and a bad limit (zero points);
between the two the points are proportional. Criteria with no data (for example, someone
who doesn't use Codex or doesn't have RTK) are left out and the other weights are rescaled.
Reaching 100 is possible: every criterion just has to hit its target.
"""
from __future__ import annotations

import time

# id: (weight, target, bad limit, unit)
CRITERIA = {
    "context": (25, 80_000, 300_000, "tokens"),    # average input per call (lower is better)
    "sessions": (15, 20, 80, "pct"),               # % of calls in sessions with more than 250 calls
    "cache": (10, 90, 50, "pct"),                  # % of input read from cache (higher is better)
    "model": (10, 60, 100, "pct"),                 # % of new tokens on frontier models (US$ 4+/M)
    "rtk": (15, 90, 40, "pct"),                    # % of the commands RTK can filter that went through it
    "waits": (10, 3, 20, "pct"),                   # % of tool calls that are waits
    "limits": (15, 0, 50, "pct"),                  # % of Codex 5 h windows that reached 95%
}
LONG_SESSION = 250
FRONTIER_PRICE = 4.0


def _hour_ts(h: str) -> float:
    return time.mktime(time.strptime(h[:13], "%Y-%m-%dT%H"))


def _points(value: float, target: float, bad: float) -> float:
    """1.0 at the target (or better), 0.0 at the bad limit (or worse), proportional in between."""
    if target == bad:
        return 1.0
    frac = (bad - value) / (bad - target)
    return max(0.0, min(1.0, frac))


def compute(snap: dict, start: float, end: float) -> dict:
    import prices as prices_mod

    inside = lambda h: start <= _hour_ts(h) + 3599 and _hour_ts(h) <= end
    usage = [r for r in snap["usage"] if inside(r["hour"])]
    vals: dict[str, float] = {}
    extra: dict[str, dict] = {}

    calls = sum(r.get("msgs") or 0 for r in usage)
    inp = sum((r.get("input") or 0) + (r.get("cache_read") or 0) + (r.get("cache_write") or 0) for r in usage)
    if calls:
        vals["context"] = inp / calls
        vals["cache"] = 100 * sum(r.get("cache_read") or 0 for r in usage) / inp if inp else 0

        new_total = new_frontier = 0.0
        by_model: dict[str, float] = {}
        for r in usage:
            n = (r.get("input") or 0) + (r.get("cache_write") or 0) + (r.get("output") or 0)
            new_total += n
            p = prices_mod.price(r["model"])[0]
            if p and (p.get("input") or 0) >= FRONTIER_PRICE:
                new_frontier += n
                by_model[r["model"]] = by_model.get(r["model"], 0) + n
        if new_total:
            vals["model"] = 100 * new_frontier / new_total
            extra["model"] = {"models": sorted(by_model, key=by_model.get, reverse=True)[:3]}

    sess = [s for s in snap["sessions"] if s["end"] >= start and s["start"] <= end]
    tot_sess = sum(s["msgs"] for s in sess)
    if tot_sess:
        long_ones = [s for s in sess if s["msgs"] > LONG_SESSION]
        vals["sessions"] = 100 * sum(s["msgs"] for s in long_ones) / tot_sess
        extra["sessions"] = {"n": len(long_ones), "limit": LONG_SESSION}

    act = [r for r in snap["rtk"].get("activity", []) if inside(r["hour"])]
    if snap["sources"]["rtk"]["ok"]:
        sup = sum(r.get("sup") or 0 for r in act)
        sup_rtk = sum(r.get("sup_rtk") or 0 for r in act)
        if sup >= 20:
            vals["rtk"] = min(100.0, 100 * sup_rtk / sup)
            extra["rtk"] = {"filterable": int(sup), "via_rtk": int(sup_rtk), "bypassed": int(sup - sup_rtk)}
    tools = sum(r.get("tools") or 0 for r in act)
    if tools >= 50:
        vals["waits"] = 100 * sum(r.get("waits") or 0 for r in act) / tools
        extra["waits"] = {"calls": int(tools)}

    win: dict[int, float] = {}
    for l in snap["limits"]["codex"]:
        if l.get("reset_5h") and l.get("p5h") is not None and start <= l["ts"] <= end:
            k = round(l["reset_5h"] / 300)
            win[k] = max(win.get(k, 0), l["p5h"])
    used = [v for v in win.values() if v > 0]
    if len(used) >= 2:
        vals["limits"] = 100 * sum(1 for v in used if v >= 95) / len(used)
        extra["limits"] = {"windows": len(used), "maxed_out": sum(1 for v in used if v >= 95)}

    total_weight = sum(CRITERIA[k][0] for k in vals) or 1
    comps, score = [], 0.0
    for k, (weight, target, bad, unit) in CRITERIA.items():
        if k not in vals:
            continue
        weight_n = 100 * weight / total_weight
        frac = _points(vals[k], target, bad)
        score += weight_n * frac
        comps.append({
            "id": k, "value": round(vals[k], 1), "target": target, "bad": bad, "unit": unit,
            "weight": round(weight_n, 1), "points": round(weight_n * frac, 1), "extra": extra.get(k, {}),
        })
    comps.sort(key=lambda c: c["points"] - c["weight"])  # what loses the most points first
    return {"score": round(score) if comps else None, "components": comps,
            "start": start, "end": end, "excluded": [k for k in CRITERIA if k not in vals]}
