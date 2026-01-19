"""
Portfolio Business Logic Layer
Handles migration from config.json and high-level portfolio operations.
"""
import json
import os
import database
from typing import List, Dict, Any

CONFIG_FILE = "config.json"
MIGRATION_FLAG_FILE = "portfolio.migrated"

def load_config_to_db_if_not_migrated():
    """
    One-time migration: Import portfolio from config.json to SQLite.
    Checks for existence of 'portfolio.migrated' file.
    """
    if os.path.exists(MIGRATION_FLAG_FILE):
        return

    print("📦 Starting migration from config.json to database...")
    
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            config = json.load(f)
            
        portfolio = config.get('portfolio', [])
        migrated_count = 0
        
        for item in portfolio:
            # Basic validation
            if 'symbol' not in item or 'name' not in item:
                continue
                
            success = database.add_holding(
                symbol=item['symbol'],
                name=item['name'],
                cost_price=item.get('cost_price', 0.0),
                position_size=item.get('position_size', 0),
                asset_type=item.get('type', 'stock')
            )
            if success:
                migrated_count += 1
                
        print(f"✅ Migration complete. Imported {migrated_count} items.")
        
        # Mark as migrated
        with open(MIGRATION_FLAG_FILE, 'w') as f:
            f.write("migrated=true")
            
    except Exception as e:
        print(f"❌ Migration failed: {e}")

def get_portfolio() -> List[Dict[str, Any]]:
    """Get all portfolio items from DB"""
    return database.get_all_holdings()

def add_position(symbol: str, name: str, cost_price: float, position_size: int = 0, asset_type: str = 'stock') -> Dict[str, Any]:
    """Add a new position"""
    try:
        success = database.add_holding(symbol, name, cost_price, position_size, asset_type)
        return {
            "success": success, 
            "message": "添加成功" if success else "添加失败或已存在",
            "symbol": symbol
        }
    except Exception as e:
        return {"success": False, "message": str(e)}

def remove_position(symbol: str) -> Dict[str, Any]:
    """Remove a position"""
    try:
        success = database.remove_holding(symbol)
        return {
            "success": success,
            "message": "移除成功" if success else "未找到该持仓"
        }
    except Exception as e:
        return {"success": False, "message": str(e)}

def update_position(symbol: str, cost_price: float = None, position_size: int = None) -> Dict[str, Any]:
    """Update position details"""
    try:
        success = database.update_holding(symbol, cost_price, position_size)
        return {
            "success": success,
            "message": "更新成功" if success else "更新失败"
        }
    except Exception as e:
        return {"success": False, "message": str(e)}

# Initialize migration on load
load_config_to_db_if_not_migrated()