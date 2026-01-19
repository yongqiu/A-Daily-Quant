"""
Database layer for A-Share Strategy Monitor
Handles MySQL connection and CRUD operations for portfolio.
"""
import pymysql
import os
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

CONFIG_FILE = "config.json"

def get_db_config():
    """Load database configuration"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                return config.get('database', {})
        except Exception as e:
            print(f"❌ Error loading config for database: {e}")
    return {}

def get_connection():
    """Get MySQL database connection"""
    db_config = get_db_config()
    if not db_config:
        # Fallback default (though this should ideally come from config)
        db_config = {
            'host': 'localhost',
            'user': 'root',
            'password': '',
            'db': 'db_daily_strategy',
            'port': 3306
        }
    
    return pymysql.connect(
        host=db_config.get('host', 'localhost'),
        port=db_config.get('port', 3306),
        user=db_config.get('user', 'root'),
        password=db_config.get('password', ''),
        db=db_config.get('db', 'db_daily_strategy'),
        charset='utf8mb4',
        cursorclass=pymysql.cursors.DictCursor
    )

def init_db():
    """Initialize database tables"""
    create_table_sql = """
    CREATE TABLE IF NOT EXISTS holdings (
        id INT AUTO_INCREMENT PRIMARY KEY,
        symbol VARCHAR(20) NOT NULL UNIQUE,
        name VARCHAR(100) NOT NULL,
        type VARCHAR(20) DEFAULT 'stock',
        cost_price DECIMAL(10, 4) DEFAULT 0.0,
        position_size INT DEFAULT 0,
        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        notes TEXT
    );
    """
    
    create_analysis_table_sql = """
    CREATE TABLE IF NOT EXISTS holding_analysis (
        id INT AUTO_INCREMENT PRIMARY KEY,
        symbol VARCHAR(20) NOT NULL,
        analysis_date DATE NOT NULL,
        price DECIMAL(10, 4),
        ma20 DECIMAL(10, 4),
        z_score DECIMAL(10, 4) DEFAULT 0,
        trend_signal VARCHAR(50),
        composite_score INT,
        ai_analysis TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY unique_daily_analysis (symbol, analysis_date),
        FOREIGN KEY (symbol) REFERENCES holdings(symbol) ON DELETE CASCADE
    );
    """

    create_selection_table_sql = """
    CREATE TABLE IF NOT EXISTS daily_selections (
        id INT AUTO_INCREMENT PRIMARY KEY,
        selection_date DATE NOT NULL,
        symbol VARCHAR(20) NOT NULL,
        name VARCHAR(100),
        close_price DECIMAL(10, 4),
        volume_ratio DECIMAL(10, 2),
        composite_score INT,
        ai_analysis TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY unique_daily_selection (selection_date, symbol)
    );
    """
    
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(create_table_sql)
                cursor.execute(create_analysis_table_sql)
                cursor.execute(create_selection_table_sql)
            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        print(f"❌ Database initialization error: {e}")

def add_holding(symbol: str, name: str, cost_price: float, position_size: int = 0, asset_type: str = 'stock') -> bool:
    """Add a new holding position"""
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO holdings (symbol, name, type, cost_price, position_size, added_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (symbol, name, asset_type, cost_price, position_size, datetime.now())
                )
            conn.commit()
            print(f"✅ Added holding: {name} ({symbol})")
            return True
        except pymysql.IntegrityError:
            print(f"⚠️ Holding already exists: {symbol}")
            return False
        except Exception as e:
            print(f"❌ Error adding holding {symbol}: {e}")
            return False
        finally:
            conn.close()
    except Exception as e:
        print(f"❌ Database connection error: {e}")
        return False

def remove_holding(symbol: str) -> bool:
    """Remove a holding by symbol"""
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM holdings WHERE symbol = %s", (symbol,))
                row_count = cursor.rowcount
            conn.commit()
            if row_count > 0:
                print(f"✅ Removed holding: {symbol}")
                return True
            else:
                print(f"⚠️ Holding not found for removal: {symbol}")
                return False
        except Exception as e:
            print(f"❌ Error removing holding {symbol}: {e}")
            return False
        finally:
            conn.close()
    except Exception as e:
        print(f"❌ Database connection error: {e}")
        return False

def update_holding(symbol: str, cost_price: Optional[float] = None, position_size: Optional[int] = None) -> bool:
    """Update existing holding"""
    try:
        conn = get_connection()
        try:
            updates = []
            params = []
            
            if cost_price is not None:
                updates.append("cost_price = %s")
                params.append(cost_price)
                
            if position_size is not None:
                updates.append("position_size = %s")
                params.append(position_size)
                
            if not updates:
                return False
                
            params.append(symbol)
            sql = f"UPDATE holdings SET {', '.join(updates)} WHERE symbol = %s"
            
            with conn.cursor() as cursor:
                cursor.execute(sql, tuple(params))
                row_count = cursor.rowcount
            conn.commit()
            return row_count > 0
        except Exception as e:
            print(f"❌ Error updating holding {symbol}: {e}")
            return False
        finally:
            conn.close()
    except Exception as e:
        print(f"❌ Database connection error: {e}")
        return False

def get_all_holdings(analysis_date: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get all holdings as a list of dictionaries, optionally with daily analysis score"""
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                if analysis_date:
                    sql = """
                        SELECT h.*, ha.composite_score
                        FROM holdings h
                        LEFT JOIN holding_analysis ha ON h.symbol = ha.symbol AND ha.analysis_date = %s
                        ORDER BY h.added_at DESC
                    """
                    cursor.execute(sql, (analysis_date,))
                else:
                    cursor.execute("SELECT * FROM holdings ORDER BY added_at DESC")
                    
                rows = cursor.fetchall()
            
            result = []
            for row in rows:
                item = {
                    'symbol': row['symbol'],
                    'name': row['name'],
                    'type': row['type'],
                    'asset_type': row['type'], # Compatibility alias
                    'cost_price': float(row['cost_price']), # Decimal to float
                    'position_size': row['position_size'],
                    'added_at': row['added_at']
                }
                if analysis_date:
                    item['composite_score'] = row.get('composite_score')
                
                result.append(item)
            return result
        except Exception as e:
            print(f"❌ Error fetching holdings: {e}")
            return []
        finally:
            conn.close()
    except Exception as e:
        print(f"❌ Database connection error: {e}")
        return []

def get_holding(symbol: str) -> Optional[Dict[str, Any]]:
    """Get single holding details"""
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM holdings WHERE symbol = %s", (symbol,))
                row = cursor.fetchone()
            if row:
                return {
                    'symbol': row['symbol'],
                    'name': row['name'],
                    'type': row['type'],
                    'asset_type': row['type'],
                    'cost_price': float(row['cost_price']),
                    'position_size': row['position_size']
                }
            return None
        except Exception as e:
            print(f"❌ Error fetching holding {symbol}: {e}")
            return None
        finally:
            conn.close()
    except Exception as e:
        print(f"❌ Database connection error: {e}")
        return None

def save_holding_analysis(symbol: str, analysis_date: str, data: Dict[str, Any]) -> bool:
    """
    Save or update daily analysis for a holding.
    data dict should contain: price, ma20, trend_signal, composite_score, ai_analysis
    """
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                sql = """
                INSERT INTO holding_analysis
                (symbol, analysis_date, price, ma20, trend_signal, composite_score, ai_analysis)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                price = VALUES(price),
                ma20 = VALUES(ma20),
                trend_signal = VALUES(trend_signal),
                composite_score = VALUES(composite_score),
                ai_analysis = VALUES(ai_analysis),
                created_at = CURRENT_TIMESTAMP
                """
                cursor.execute(sql, (
                    symbol,
                    analysis_date,
                    data.get('price', 0),
                    data.get('ma20', 0),
                    data.get('trend_signal', ''),
                    data.get('composite_score', 0),
                    data.get('ai_analysis', '')
                ))
            conn.commit()
            print(f"✅ Saved analysis for {symbol} on {analysis_date}")
            return True
        except Exception as e:
            print(f"❌ Error saving analysis for {symbol}: {e}")
            return False
        finally:
            conn.close()
    except Exception as e:
        print(f"❌ Database connection error: {e}")
        return False

def save_daily_selection(selection_date: str, selection_data: Dict[str, Any]) -> bool:
    """
    Save a daily selection result.
    selection_data should contain: symbol, name, close_price, volume_ratio, composite_score, ai_analysis
    """
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                sql = """
                INSERT INTO daily_selections
                (selection_date, symbol, name, close_price, volume_ratio, composite_score, ai_analysis)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                close_price = VALUES(close_price),
                volume_ratio = VALUES(volume_ratio),
                composite_score = VALUES(composite_score),
                ai_analysis = VALUES(ai_analysis),
                created_at = CURRENT_TIMESTAMP
                """
                cursor.execute(sql, (
                    selection_date,
                    selection_data['symbol'],
                    selection_data.get('name', ''),
                    selection_data.get('close_price', 0),
                    selection_data.get('volume_ratio', 0),
                    selection_data.get('composite_score', 0),
                    selection_data.get('ai_analysis', '')
                ))
            conn.commit()
            return True
        except Exception as e:
            print(f"❌ Error saving selection for {selection_data.get('symbol')}: {e}")
            return False
        finally:
            conn.close()
    except Exception as e:
        print(f"❌ Database connection error: {e}")
        return False

def get_daily_analysis_by_date(analysis_date: str) -> List[Dict[str, Any]]:
    """
    Get all holding analyses for a specific date.
    Returns a list of analysis records joined with holding info.
    """
    # Simple validation as per logs showing "status" or "logs" being passed
    if not analysis_date or analysis_date in ['status', 'logs', 'latest']:
        return []
        
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                sql = """
                SELECT ha.*, h.name
                FROM holding_analysis ha
                JOIN holdings h ON ha.symbol = h.symbol
                WHERE ha.analysis_date = %s
                ORDER BY ha.composite_score ASC
                """
                cursor.execute(sql, (analysis_date,))
                rows = cursor.fetchall()
                
                result = []
                for row in rows:
                    result.append({
                        'symbol': row['symbol'],
                        'name': row.get('name', row['symbol']),
                        'analysis_date': row['analysis_date'].strftime('%Y-%m-%d'),
                        'price': float(row['price']) if row['price'] else 0,
                        'ma20': float(row['ma20']) if row['ma20'] else 0,
                        'trend_signal': row['trend_signal'],
                        'composite_score': row['composite_score'],
                        'ai_analysis': row['ai_analysis']
                    })
                return result
        finally:
            conn.close()
    except Exception as e:
        print(f"❌ Error fetching daily analysis for {analysis_date}: {e}")
        return []

def get_holding_analysis(symbol: str, analysis_date: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Get holding analysis from DB.
    If date is None, gets the latest analysis.
    """
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                if analysis_date:
                    sql = "SELECT * FROM holding_analysis WHERE symbol = %s AND analysis_date = %s"
                    params = (symbol, analysis_date)
                else:
                    sql = "SELECT * FROM holding_analysis WHERE symbol = %s ORDER BY analysis_date DESC LIMIT 1"
                    params = (symbol,)
                
                cursor.execute(sql, params)
                row = cursor.fetchone()
                
                if row:
                    # Convert date/decimal to native types if needed (pymysql dictcursor usually helps)
                     return {
                        'symbol': row['symbol'],
                        'analysis_date': row['analysis_date'].strftime('%Y-%m-%d'),
                        'price': float(row['price']) if row['price'] else 0,
                        'ma20': float(row['ma20']) if row['ma20'] else 0,
                        'trend_signal': row['trend_signal'],
                        'composite_score': row['composite_score'],
                        'ai_analysis': row['ai_analysis']
                    }
                return None
        finally:
            conn.close()
    except Exception as e:
        print(f"❌ Error fetching analysis for {symbol}: {e}")
        return None

def get_daily_selections(selection_date: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Get daily selections from DB.
    If date is None, gets the latest date available in DB.
    """
    # Simple validation
    if selection_date in ['status', 'logs', 'latest']:
         return []

    try:
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                if not selection_date:
                    # Find latest date first
                    cursor.execute("SELECT MAX(selection_date) as max_date FROM daily_selections")
                    res = cursor.fetchone()
                    if res and res['max_date']:
                        selection_date = res['max_date']
                    else:
                        return []
                
                sql = "SELECT * FROM daily_selections WHERE selection_date = %s"
                cursor.execute(sql, (selection_date,))
                rows = cursor.fetchall()
                
                result = []
                for row in rows:
                    result.append({
                        'symbol': row['symbol'],
                        'name': row['name'],
                        'close_price': float(row['close_price']) if row['close_price'] else 0,
                        'volume_ratio': float(row['volume_ratio']) if row['volume_ratio'] else 0,
                        'composite_score': row['composite_score'],
                        'ai_analysis': row['ai_analysis'],
                         'selection_date': row['selection_date'].strftime('%Y-%m-%d')
                    })
                return result
        finally:
            conn.close()
    except Exception as e:
        print(f"❌ Error fetching selections: {e}")
        return []

def get_all_strategies() -> List[Dict[str, Any]]:
    """Get all strategies"""
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM strategies ORDER BY category, id")
                return cursor.fetchall()
        finally:
            conn.close()
    except Exception as e:
        print(f"❌ Error getting all strategies: {e}")
        return []

def get_strategy_by_slug(slug: str) -> Optional[Dict[str, Any]]:
    """Get full strategy details including params by slug"""
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                # 1. Get Strategy
                cursor.execute("SELECT * FROM strategies WHERE slug = %s", (slug,))
                strategy = cursor.fetchone()
                
                if not strategy:
                    return None
                
                # 2. Get Params
                cursor.execute("SELECT param_key, param_value FROM strategy_params WHERE strategy_id = %s", (strategy['id'],))
                params = cursor.fetchall()
                
                # Convert list of dicts to single dict
                param_dict = {p['param_key']: p['param_value'] for p in params}
                strategy['params'] = param_dict
                
                return strategy
        finally:
            conn.close()
    except Exception as e:
        print(f"❌ Error getting strategy {slug}: {e}")
        return None

def get_strategy_by_id(strategy_id: int) -> Optional[Dict[str, Any]]:
    """Get full strategy details by ID"""
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM strategies WHERE id = %s", (strategy_id,))
                strategy = cursor.fetchone()
                
                if not strategy:
                    return None
                    
                cursor.execute("SELECT * FROM strategy_params WHERE strategy_id = %s", (strategy_id,))
                params = cursor.fetchall()
                strategy['params_list'] = params # Full list with metadata
                
                return strategy
        finally:
            conn.close()
    except Exception as e:
        print(f"❌ Error getting strategy {strategy_id}: {e}")
        return None

def update_strategy_template(strategy_id: int, template_content: str) -> bool:
    """Update strategy prompt template"""
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "UPDATE strategies SET template_content = %s WHERE id = %s",
                    (template_content, strategy_id)
                )
            conn.commit()
            return True
        finally:
            conn.close()
    except Exception as e:
        print(f"❌ Error updating strategy template: {e}")
        return False

def update_strategy_param(strategy_id: int, param_key: str, param_value: str) -> bool:
    """Update or insert a strategy parameter"""
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                sql = """
                INSERT INTO strategy_params (strategy_id, param_key, param_value)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE param_value = VALUES(param_value)
                """
                cursor.execute(sql, (strategy_id, param_key, param_value))
            conn.commit()
            return True
        finally:
            conn.close()
    except Exception as e:
        print(f"❌ Error updating param {param_key}: {e}")
        return False

# Auto-initialize on module load
init_db()