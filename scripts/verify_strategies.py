import sys
import os
import json

# Add parent directory to path to import database module
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_all_strategies, get_strategy_by_slug

def verify():
    print("Verifying strategies...")
    strategies = get_all_strategies()
    print(f"Found {len(strategies)} strategies.")
    
    for s in strategies:
        print(f"- [{s['id']}] {s['slug']}: {s['name']} ({s['category']})")
        
    # Check details for one
    slug = "speculator_mode"
    details = get_strategy_by_slug(slug)
    if details:
        print(f"\nDetails for {slug}:")
        print(f"Template Length: {len(details.get('template_content', ''))}")
        print("Template Preview:", details.get('template_content', '')[:50] + "...")
    else:
        print(f"\n❌ Failed to get details for {slug}")

if __name__ == "__main__":
    verify()
