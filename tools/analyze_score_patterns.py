#!/usr/bin/env python3
"""Detailed score analysis - compare actual values between winners/losers."""

import sys
import os
import logging
from datetime import datetime, timezone
from collections import defaultdict
import statistics

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from tradebot_sci.simulation.backtester import Backtester
from tradebot_sci.config.loader import load_settings

logging.basicConfig(stream=sys.stderr, level=logging.WARNING)

os.environ['PROFILE_NAME'] = 'coinbase_futures'
os.environ['CCXT_EXCHANGE'] = 'coinbase'

settings = load_settings()

START_DATE = datetime(2025, 11, 1, 0, 0, tzinfo=timezone.utc)
END_DATE = datetime(2025, 11, 6, 0, 0, tzinfo=timezone.utc)
INITIAL_CAPITAL = 150.0

print("=" * 80)
print("DETAILED SCORE ANALYSIS")
print("=" * 80)

backtester = Backtester(None, settings, None)
result = backtester.run_backtest(start_date=START_DATE, end_date=END_DATE, initial_capital=INITIAL_CAPITAL)

winners = [t for t in result.trades if t.pnl > 0]
losers = [t for t in result.trades if t.pnl < 0]

print(f"\nTotal: {len(result.trades)} | Winners: {len(winners)} | Losers: {len(losers)}")
print(f"Return: {result.total_return_pct:.2f}%")

def extract_score_values(trades, label):
    """Extract score values from trades."""
    scores = []
    htf_strengths = []
    ltf_strengths = []
    has_sweep = 0
    has_htf_align = 0
    score_breakdowns = defaultdict(list)
    
    for t in trades:
        gates = getattr(t, 'entry_gates', None)
        if gates:
            score = gates.get('score', 0)
            scores.append(score)
            
            htf_str = gates.get('htf_strength', 0)
            if htf_str:
                htf_strengths.append(float(htf_str))
            
            ltf_str = gates.get('ltf_strength', 0)
            if ltf_str:
                ltf_strengths.append(float(ltf_str))
            
            if gates.get('sweep'):
                has_sweep += 1
            if gates.get('htf_align'):
                has_htf_align += 1
            
            breakdown = gates.get('score_breakdown', {})
            for key, val in breakdown.items():
                score_breakdowns[key].append(val)
    
    print(f"\n{'='*40}")
    print(f"{label} (n={len(trades)})")
    print(f"{'='*40}")
    
    if scores:
        print(f"  Total Score: avg={statistics.mean(scores):.1f}, min={min(scores):.1f}, max={max(scores):.1f}")
    
    if htf_strengths:
        print(f"  HTF Strength: avg={statistics.mean(htf_strengths):.2f}, min={min(htf_strengths):.2f}, max={max(htf_strengths):.2f}")
    
    if ltf_strengths:
        print(f"  LTF Strength: avg={statistics.mean(ltf_strengths):.2f}, min={min(ltf_strengths):.2f}, max={max(ltf_strengths):.2f}")
    
    print(f"  Has Sweep: {has_sweep}/{len(trades)} ({has_sweep/len(trades)*100:.1f}%)")
    print(f"  Has HTF Align: {has_htf_align}/{len(trades)} ({has_htf_align/len(trades)*100:.1f}%)")
    
    print(f"\n  Score Components:")
    for key, vals in sorted(score_breakdowns.items()):
        non_zero = [v for v in vals if v > 0]
        if non_zero:
            avg = statistics.mean(non_zero)
            pct = len(non_zero) / len(vals) * 100
            print(f"    {key}: avg={avg:.1f}, present={pct:.1f}%")
    
    return {
        'scores': scores,
        'htf_strengths': htf_strengths,
        'has_sweep_pct': has_sweep / len(trades) * 100 if trades else 0,
        'has_htf_align_pct': has_htf_align / len(trades) * 100 if trades else 0,
    }

winner_stats = extract_score_values(winners, "WINNERS")
loser_stats = extract_score_values(losers, "LOSERS")

# Compare and recommend
print("\n" + "=" * 80)
print("DIFFERENTIAL ANALYSIS")
print("=" * 80)

if winner_stats['scores'] and loser_stats['scores']:
    w_avg = statistics.mean(winner_stats['scores'])
    l_avg = statistics.mean(loser_stats['scores'])
    print(f"\nScore Difference: Winners avg={w_avg:.1f} vs Losers avg={l_avg:.1f} (Δ={w_avg-l_avg:.1f})")

if winner_stats['htf_strengths'] and loser_stats['htf_strengths']:
    w_htf = statistics.mean(winner_stats['htf_strengths'])
    l_htf = statistics.mean(loser_stats['htf_strengths'])
    print(f"HTF Strength: Winners avg={w_htf:.2f} vs Losers avg={l_htf:.2f} (Δ={w_htf-l_htf:.2f})")

sweep_diff = winner_stats['has_sweep_pct'] - loser_stats['has_sweep_pct']
htf_align_diff = winner_stats['has_htf_align_pct'] - loser_stats['has_htf_align_pct']

print(f"\nSweep Presence: Winners={winner_stats['has_sweep_pct']:.1f}% vs Losers={loser_stats['has_sweep_pct']:.1f}% (Δ={sweep_diff:.1f}%)")
print(f"HTF Align: Winners={winner_stats['has_htf_align_pct']:.1f}% vs Losers={loser_stats['has_htf_align_pct']:.1f}% (Δ={htf_align_diff:.1f}%)")

print("\n" + "=" * 80)
print("RECOMMENDATIONS")
print("=" * 80)

# Calculate median loser score to find threshold
if loser_stats['scores']:
    loser_median = statistics.median(loser_stats['scores'])
    winner_median = statistics.median(winner_stats['scores']) if winner_stats['scores'] else 0
    print(f"\nLoser median score: {loser_median:.1f}")
    print(f"Winner median score: {winner_median:.1f}")
    
    # Find a threshold that would have blocked more losers than winners
    thresholds = [60, 65, 70, 75, 80]
    for thresh in thresholds:
        losers_blocked = sum(1 for s in loser_stats['scores'] if s < thresh)
        winners_blocked = sum(1 for s in winner_stats['scores'] if s < thresh)
        net_benefit = losers_blocked - winners_blocked
        print(f"  Threshold {thresh}: Would block {losers_blocked} losers, {winners_blocked} winners (Net: +{net_benefit})")

print("\n" + "=" * 80)
