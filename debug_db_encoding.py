
import database
import json

def check_strategies():
    strategies = database.get_all_strategies()
    print(f"Found {len(strategies)} strategies.")
    for s in strategies:
        print(f"--- Strategy: {s.get('name')} ({s.get('slug')}) ---")
        content = s.get('template_content', '')
        print(f"Content length: {len(content)}")
        print("First 100 chars representation:")
        print(repr(content[:100]))
        print("First 100 chars printed:")
        print(content[:100])
        
if __name__ == "__main__":
    check_strategies()
