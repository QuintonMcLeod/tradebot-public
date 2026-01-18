
import logging

def verify_nano_suitability():
    print("\n=== COINBASE NANO FUTURES VIABILITY ===")
    
    # 1. Market Data (Approximate)
    eth_price = 3350.00
    nano_eth_size = 0.1 # 1 contract = 0.1 ETH
    contract_notional = eth_price * nano_eth_size
    
    # 2. Capital & Margin
    user_capital = 68.0
    
    # Coinbase Retail Margin Requirements (Typical Estimate)
    # Initial Margin often ~20-25% for Crypto Futures (5x-4x leverage)
    estimated_initial_margin_pct = 0.25 
    required_margin_1_contract = contract_notional * estimated_initial_margin_pct
    
    # Fees (Retail Nano)
    fee_per_contract = 0.15 # $0.15 per side (approx)
    
    print(f"Instrument: Nano Ether (ET)")
    print(f"Price: ${eth_price:,.2f}")
    print(f"Contract Size: {nano_eth_size} ETH")
    print(f"Contract Notional: ${contract_notional:,.2f}")
    print(f"Est. Margin Req (25%): ${required_margin_1_contract:,.2f}")
    print(f"User Capital: ${user_capital:,.2f}")
    
    if user_capital < required_margin_1_contract:
        print("\n[CRITICAL] INSUFFICIENT CAPITAL")
        print(f"You need ~${required_margin_1_contract:.2f} to open ONE Nano ETH contract.")
        print(f"Shortfall: ${required_margin_1_contract - user_capital:.2f}")
        return
        
    print("\n[SUCCESS] Capital Sufficient! (Barely)")
    
    # 3. Growth Simulation (Integer Contracts Only)
    print("-" * 40)
    print("Simulating Growth with Integer Contracts (1/10 ETH units)...")
    
    current_cap = user_capital
    days = 30
    trades_per_day = 10
    win_rate = 0.50
    reward_ratio = 2.0
    stop_loss_move_pct = 0.01 # 1% move ($33.50 per contract value change)
    
    # Outcome values per contract
    # Stop Hit (-1% move): -$3.35 per contract
    # Target Hit (+2% move): +$6.70 per contract
    
    loss_per_contract = contract_notional * stop_loss_move_pct
    win_per_contract = loss_per_contract * reward_ratio
    round_trip_fee = fee_per_contract * 2
    
    print(f"Win Per Contract: ${win_per_contract:.2f}")
    print(f"Loss Per Contract: ${loss_per_contract:.2f}")
    print(f"Fee Per Contract: ${round_trip_fee:.2f}")
    
    for day in range(1, days + 1):
        if current_cap < required_margin_1_contract:
            print(f"Day {day}: BROKEN (Capital ${current_cap:.2f} < Min Margin ${required_margin_1_contract:.2f})")
            break
            
        start_cap = current_cap
        
        for t in range(trades_per_day):
            # Calculate Max Contracts
            # Leave 10% buffer for drawdown/fees
            safe_cap = current_cap * 0.90
            max_contracts = int(safe_cap // required_margin_1_contract)
            
            if max_contracts < 1:
                # Try with full cap if desperate? No, margin call risk.
                max_contracts = 0 # Cant trade
            
            if max_contracts == 0:
                break
                
            # Outcome
            is_win = (t % 2 == 0)
            
            pnl = 0
            fees = round_trip_fee * max_contracts
            
            if is_win:
                pnl = (win_per_contract * max_contracts) - fees
            else:
                pnl = -(loss_per_contract * max_contracts) - fees
                
            current_cap += pnl
            
        if max_contracts > 0:
            print(f"Day {day}: ${current_cap:,.2f} (Traded {max_contracts} contracts)")
        else:
             print(f"Day {day}: ${current_cap:,.2f} (Unable to trade)")
             break

if __name__ == "__main__":
    verify_nano_suitability()
