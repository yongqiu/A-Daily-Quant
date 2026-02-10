import database
import json

def fetch_strategy_template(slug):
    strategy = database.get_strategy_by_slug(slug)
    if strategy:
        print(f"\n{'='*20} {slug} ({strategy['name']}) {'='*20}")
        print(f"Description: {strategy.get('description')}")
        print(f"\n[Template Content]:\n{strategy.get('template_content')}")
        if strategy.get('params'):
            print(f"\n[Params]: {json.dumps(strategy['params'], ensure_ascii=False, indent=2)}")
    else:
        print(f"\n❌ Strategy {slug} not found.")

def main():
    slugs = [
        # Multi-Agent
        "agent_technician",
        "agent_fundamentalist", 
        "agent_risk_officer",
        "agent_cio",
        
        # Single Prompt Modes (Likely Candidates)
        "deep_monitor",     # Stocks
        "realtime_intraday" # Legacy
    ]
    
    print("Fetching Prompt Templates...")
    for slug in slugs:
        fetch_strategy_template(slug)

if __name__ == "__main__":
    main()
