"""
Database layer for A-Share Strategy Monitor
Handles MySQL connection and CRUD operations for portfolio.
"""

try:
    import pymysql
except ImportError:
    pass
import sqlite3
import re
import os
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

try:
    import yaml
except ImportError:
    yaml = None

AGENTS_YAML_FILE = "agents.yaml"
_agents_yaml_cache: Dict[str, Any] = {}
_agents_yaml_mtime: Optional[float] = None
_agents_yaml_warning_emitted = False


def _load_agents_from_yaml() -> Dict[str, Any]:
    global _agents_yaml_cache, _agents_yaml_mtime, _agents_yaml_warning_emitted

    if not os.path.exists(AGENTS_YAML_FILE):
        _agents_yaml_cache = {}
        _agents_yaml_mtime = None
        return {}

    if yaml is None:
        if not _agents_yaml_warning_emitted:
            print("⚠️ PyYAML not installed, skipping agents.yaml parsing")
            _agents_yaml_warning_emitted = True
        return {}

    try:
        current_mtime = os.path.getmtime(AGENTS_YAML_FILE)
        if _agents_yaml_mtime == current_mtime:
            return _agents_yaml_cache

        with open(AGENTS_YAML_FILE, "r", encoding="utf-8") as f:
            _agents_yaml_cache = yaml.safe_load(f) or {}
            _agents_yaml_mtime = current_mtime
            return _agents_yaml_cache
    except Exception as e:
        print(f"❌ Error loading {AGENTS_YAML_FILE}: {e}")
        return {}


def _fmt_dt(val, fmt):
    if not val:
        return ""
    if hasattr(val, "strftime"):
        return val.strftime(fmt)
    s = str(val)
    if fmt == "%Y-%m-%d":
        return s[:10]
    if fmt == "%H:%M:%S":
        return s[11:19] if len(s) > 11 else s
    if fmt == "%Y-%m-%d %H:%M:%S":
        return s[:19]
    return s


CONFIG_FILE = "config.json"

# Determine DB Type from environment
DB_TYPE = os.getenv("DB_TYPE", "sqlite").lower()
DB_FILE = os.getenv("DB_FILE", "a_daily_quant.db")


def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d


class DBConnectionWrapper:
    def __init__(self, conn):
        self.conn = conn

    def cursor(self):
        return CursorWrapper(self.conn.cursor())

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    def close(self):
        self.conn.close()


class CursorWrapper:
    def __init__(self, cursor):
        self.cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cursor.close()

    def execute(self, sql, params=None):
        sql = translate_sql(sql)
        if params is not None:
            self.cursor.execute(sql, params)
        else:
            self.cursor.execute(sql)

    def fetchone(self):
        return self.cursor.fetchone()

    def fetchall(self):
        return self.cursor.fetchall()

    @property
    def rowcount(self):
        return self.cursor.rowcount

    @property
    def lastrowid(self):
        return self.cursor.lastrowid

    def close(self):
        self.cursor.close()


def translate_sql(sql):
    if DB_TYPE != "sqlite":
        return sql
    # Replace %s with ?
    sql = sql.replace("%s", "?")

    # Auto increment specific fix for SQLite
    sql = sql.replace(
        "INT AUTO_INCREMENT PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT"
    )
    sql = sql.replace("AUTO_INCREMENT", "AUTOINCREMENT")

    # Remove MySQL specific syntax that fails in SQLite
    sql = sql.replace("ON UPDATE CURRENT_TIMESTAMP", "")

    # Fix UNIQUE KEY constraint syntax
    # Replaces 'UNIQUE KEY index_name (cols)' with 'UNIQUE (cols)'
    sql = re.sub(r"UNIQUE KEY \w+\s*\((.*?)\)", r"UNIQUE (\1)", sql)

    # Handle ON DUPLICATE KEY UPDATE
    if "ON DUPLICATE KEY UPDATE" in sql:
        if "holding_analysis" in sql:
            sql = sql.replace(
                "ON DUPLICATE KEY UPDATE",
                "ON CONFLICT(symbol, analysis_date, mode) DO UPDATE SET",
            )
        elif "daily_selections" in sql:
            sql = sql.replace(
                "ON DUPLICATE KEY UPDATE",
                "ON CONFLICT(selection_date, symbol) DO UPDATE SET",
            )
        elif "daily_metrics" in sql:
            sql = sql.replace(
                "ON DUPLICATE KEY UPDATE", "ON CONFLICT(symbol, date) DO UPDATE SET"
            )
        elif "strategy_params" in sql:
            sql = sql.replace(
                "ON DUPLICATE KEY UPDATE",
                "ON CONFLICT(strategy_id, param_key) DO UPDATE SET",
            )

        # Replace VALUES(col) with excluded.col
        sql = re.sub(r"VALUES\(([a-zA-Z0-9_]+)\)", r"excluded.\1", sql)

    return sql


def get_db_config():
    """Load database configuration"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
                return config.get("database", {})
        except Exception as e:
            print(f"❌ Error loading config for database: {e}")
    return {}


def get_connection():
    """Get database connection"""
    if DB_TYPE == "sqlite":
        conn = sqlite3.connect(DB_FILE, timeout=20.0)
        conn.row_factory = dict_factory
        return DBConnectionWrapper(conn)

    db_config = get_db_config()
    if not db_config:
        # Fallback default (though this should ideally come from config)
        db_config = {
            "host": "localhost",
            "user": "root",
            "password": "",
            "db": "db_daily_strategy",
            "port": 3306,
        }

    return pymysql.connect(
        host=db_config.get("host", "localhost"),
        port=db_config.get("port", 3306),
        user=db_config.get("user", "root"),
        password=db_config.get("password", ""),
        db=db_config.get("db", "db_daily_strategy"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
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
        mode VARCHAR(20) DEFAULT 'multi_agent',
        price DECIMAL(10, 4),
        ma20 DECIMAL(10, 4),
        z_score DECIMAL(10, 4) DEFAULT 0,
        trend_signal VARCHAR(50),
        composite_score INT,
        snapshot_version INT DEFAULT 1,
        analysis_snapshot JSON NULL,
        final_action VARCHAR(20) NULL,
        risk_level VARCHAR(20) NULL,
        consensus_level VARCHAR(20) NULL,
        agent_outputs JSON NULL,
        ai_analysis TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        UNIQUE KEY unique_daily_analysis (symbol, analysis_date, mode),
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

    create_metrics_table_sql = """
    CREATE TABLE IF NOT EXISTS daily_metrics (
        id INT AUTO_INCREMENT PRIMARY KEY,
        symbol VARCHAR(20) NOT NULL,
        date DATE NOT NULL,
        
        /* Price Data */
        price DECIMAL(10, 4),
        change_pct DECIMAL(10, 2),
        
        /* Moving Averages */
        ma5 DECIMAL(10, 4),
        ma20 DECIMAL(10, 4),
        ma60 DECIMAL(10, 4),
        
        /* Technical Indicators */
        rsi DECIMAL(10, 2),
        kdj_k DECIMAL(10, 2),
        kdj_d DECIMAL(10, 2),
        macd_dif DECIMAL(10, 4),
        macd_dea DECIMAL(10, 4),
        macd_macd DECIMAL(10, 4),
        volume_ratio DECIMAL(10, 2),
        
        /* Scoring & Meta */
        composite_score INT,
        entry_score INT,
        holding_score INT,
        holding_state VARCHAR(32),
        holding_state_label VARCHAR(32),
        rating VARCHAR(20),
        pattern_flags TEXT,
        
        /* Extended Analysis Fields (JSON) */
        score_breakdown JSON,
        score_details JSON,
        entry_score_breakdown JSON,
        entry_score_details JSON,
        holding_score_breakdown JSON,
        holding_score_details JSON,
        operation_suggestion TEXT,
        
        /* Additional Metrics */
        stop_loss_suggest DECIMAL(10, 2),
        atr_pct DECIMAL(10, 2),
        price_vs_high120 DECIMAL(10, 4),
        
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        
        UNIQUE KEY unique_daily_metric (symbol, date)
    );
    """

    create_intraday_logs_sql = """
    CREATE TABLE IF NOT EXISTS intraday_logs (
        id INT AUTO_INCREMENT PRIMARY KEY,
        symbol VARCHAR(20) NOT NULL,
        analysis_time DATETIME DEFAULT CURRENT_TIMESTAMP,
        price DECIMAL(10, 4),
        change_pct DECIMAL(10, 2),
        ai_content TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """

    try:
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(create_table_sql)
                cursor.execute(create_analysis_table_sql)
                cursor.execute(create_selection_table_sql)
                cursor.execute(create_metrics_table_sql)
                cursor.execute(create_intraday_logs_sql)

                # Strategies Tables
                cursor.execute("""
                CREATE TABLE IF NOT EXISTS strategies (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    slug VARCHAR(50) NOT NULL UNIQUE,
                    name VARCHAR(100) NOT NULL,
                    description VARCHAR(255),
                    category VARCHAR(50) DEFAULT 'general',
                    template_content TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                );
                """)

                cursor.execute("""
                CREATE TABLE IF NOT EXISTS strategy_params (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    strategy_id INT NOT NULL,
                    param_key VARCHAR(50) NOT NULL,
                    param_value VARCHAR(255),
                    description VARCHAR(255),
                    FOREIGN KEY (strategy_id) REFERENCES strategies(id) ON DELETE CASCADE,
                    UNIQUE KEY unique_param (strategy_id, param_key)
                );
                """)
            conn.commit()

            # --- Schema Migration for Existing DBs ---
            check_schema_updates()

        finally:
            conn.close()
    except Exception as e:
        print(f"❌ Database initialization error: {e}")


def check_schema_updates():
    """Perform schema migrations if needed"""
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                if DB_TYPE == "sqlite":
                    try:
                        cursor.execute("PRAGMA table_info(holding_analysis)")
                        columns = [row["name"] for row in cursor.fetchall()]
                        if "mode" not in columns:
                            if "analysis_type" in columns:
                                print(
                                    "⚙️ Migrating DB: Renaming analysis_type to mode (SQLite)..."
                                )
                                try:
                                    cursor.execute(
                                        "ALTER TABLE holding_analysis RENAME COLUMN analysis_type TO mode"
                                    )
                                except:
                                    pass
                            else:
                                print("⚙️ Migrating DB: Adding mode column (SQLite)...")
                                cursor.execute(
                                    "ALTER TABLE holding_analysis ADD COLUMN mode VARCHAR(20) DEFAULT 'multi_agent'"
                                )

                        cursor.execute("PRAGMA table_info(holdings)")
                        columns = [row["name"] for row in cursor.fetchall()]
                        if "is_starred" not in columns:
                            print(
                                "⚙️ Migrating DB: Adding is_starred column to holdings (SQLite)..."
                            )
                            cursor.execute(
                                "ALTER TABLE holdings ADD COLUMN is_starred TINYINT(1) NOT NULL DEFAULT 0"
                            )

                        cursor.execute("PRAGMA table_info(daily_metrics)")
                        daily_metric_columns = [row["name"] for row in cursor.fetchall()]
                        sqlite_dual_metric_columns = [
                            ("entry_score", "INTEGER"),
                            ("holding_score", "INTEGER"),
                            ("holding_state", "VARCHAR(32)"),
                            ("holding_state_label", "VARCHAR(32)"),
                            ("entry_score_breakdown", "TEXT"),
                            ("entry_score_details", "TEXT"),
                            ("holding_score_breakdown", "TEXT"),
                            ("holding_score_details", "TEXT"),
                        ]
                        for column_name, column_type in sqlite_dual_metric_columns:
                            if column_name not in daily_metric_columns:
                                print(
                                    f"⚙️ Migrating DB: Adding {column_name} column to daily_metrics (SQLite)..."
                                )
                                cursor.execute(
                                    f"ALTER TABLE daily_metrics ADD COLUMN {column_name} {column_type}"
                                )

                        sqlite_analysis_columns = [
                            ("snapshot_version", "INTEGER DEFAULT 1"),
                            ("analysis_snapshot", "TEXT"),
                            ("final_action", "VARCHAR(20)"),
                            ("risk_level", "VARCHAR(20)"),
                            ("consensus_level", "VARCHAR(20)"),
                            ("agent_outputs", "TEXT"),
                        ]
                        cursor.execute("PRAGMA table_info(holding_analysis)")
                        analysis_columns = [row["name"] for row in cursor.fetchall()]
                        for column_name, column_type in sqlite_analysis_columns:
                            if column_name not in analysis_columns:
                                print(
                                    f"⚙️ Migrating DB: Adding {column_name} column to holding_analysis (SQLite)..."
                                )
                                cursor.execute(
                                    f"ALTER TABLE holding_analysis ADD COLUMN {column_name} {column_type}"
                                )
                    except Exception as sqle:
                        print(f"⚠️ SQLite Schema migration check skipped: {sqle}")
                else:
                    # Original MySQL check_schema_updates
                    cursor.execute("SHOW COLUMNS FROM holding_analysis LIKE 'mode'")
                    if not cursor.fetchone():
                        cursor.execute(
                            "SHOW COLUMNS FROM holding_analysis LIKE 'analysis_type'"
                        )
                        if cursor.fetchone():
                            print("⚙️ Migrating DB: Renaming analysis_type to mode...")
                            cursor.execute(
                                "ALTER TABLE holding_analysis CHANGE COLUMN analysis_type mode VARCHAR(20) DEFAULT 'multi_agent'"
                            )
                        else:
                            print("⚙️ Migrating DB: Adding mode column...")
                            cursor.execute(
                                "ALTER TABLE holding_analysis ADD COLUMN mode VARCHAR(20) DEFAULT 'multi_agent' AFTER analysis_date"
                            )

                    cursor.execute(
                        "SHOW INDEX FROM holding_analysis WHERE Key_name = 'unique_daily_analysis'"
                    )
                    indices = cursor.fetchall()
                    if indices:
                        columns = [row["Column_name"] for row in indices]
                        if "mode" not in columns:
                            print(
                                "⚙️ Migrating DB: Updating unique index for multi-mode support..."
                            )
                            cursor.execute(
                                "ALTER TABLE holding_analysis DROP INDEX unique_daily_analysis"
                            )
                            cursor.execute(
                                "ALTER TABLE holding_analysis ADD UNIQUE KEY unique_daily_analysis (symbol, analysis_date, mode)"
                            )

                    cursor.execute("SHOW COLUMNS FROM holdings LIKE 'is_starred'")
                    if not cursor.fetchone():
                        print("⚙️ Migrating DB: Adding is_starred column to holdings...")
                        cursor.execute(
                            "ALTER TABLE holdings ADD COLUMN is_starred TINYINT(1) NOT NULL DEFAULT 0 AFTER notes"
                        )

                    dual_metric_columns = [
                        ("entry_score", "INT NULL AFTER composite_score"),
                        ("holding_score", "INT NULL AFTER entry_score"),
                        ("holding_state", "VARCHAR(32) NULL AFTER holding_score"),
                        (
                            "holding_state_label",
                            "VARCHAR(32) NULL AFTER holding_state",
                        ),
                        (
                            "entry_score_breakdown",
                            "JSON NULL AFTER score_details",
                        ),
                        (
                            "entry_score_details",
                            "JSON NULL AFTER entry_score_breakdown",
                        ),
                        (
                            "holding_score_breakdown",
                            "JSON NULL AFTER entry_score_details",
                        ),
                        (
                            "holding_score_details",
                            "JSON NULL AFTER holding_score_breakdown",
                        ),
                    ]
                    for column_name, column_def in dual_metric_columns:
                        cursor.execute(
                            f"SHOW COLUMNS FROM daily_metrics LIKE '{column_name}'"
                        )
                        if not cursor.fetchone():
                            print(
                                f"⚙️ Migrating DB: Adding {column_name} column to daily_metrics..."
                            )
                            cursor.execute(
                                f"ALTER TABLE daily_metrics ADD COLUMN {column_name} {column_def}"
                            )

                    holding_analysis_columns = [
                        ("snapshot_version", "INT NULL DEFAULT 1 AFTER composite_score"),
                        ("analysis_snapshot", "JSON NULL AFTER snapshot_version"),
                        ("final_action", "VARCHAR(20) NULL AFTER analysis_snapshot"),
                        ("risk_level", "VARCHAR(20) NULL AFTER final_action"),
                        ("consensus_level", "VARCHAR(20) NULL AFTER risk_level"),
                        ("agent_outputs", "JSON NULL AFTER consensus_level"),
                    ]
                    for column_name, column_def in holding_analysis_columns:
                        cursor.execute(
                            f"SHOW COLUMNS FROM holding_analysis LIKE '{column_name}'"
                        )
                        if not cursor.fetchone():
                            print(
                                f"⚙️ Migrating DB: Adding {column_name} column to holding_analysis..."
                            )
                            cursor.execute(
                                f"ALTER TABLE holding_analysis ADD COLUMN {column_name} {column_def}"
                            )

            conn.commit()
        finally:
            conn.close()
    except Exception as e:
        print(f"⚠️ Schema migration check failed: {e}")


def add_holding(
    symbol: str,
    name: str,
    cost_price: float,
    position_size: int = 0,
    asset_type: str = "stock",
) -> bool:
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
                    (
                        symbol,
                        name,
                        asset_type,
                        cost_price,
                        position_size,
                        datetime.now(),
                    ),
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


def update_holding(
    symbol: str, cost_price: Optional[float] = None, position_size: Optional[int] = None
) -> bool:
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
                # 首先检查记录是否存在
                cursor.execute("SELECT id FROM holdings WHERE symbol = %s", (symbol,))
                if not cursor.fetchone():
                    return False

                cursor.execute(sql, tuple(params))
                # row_count 可能为 0 (如果没有值发生变化)，但这依然算更新成功

            conn.commit()
            return True
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
                    # Default join with multi_agent analysis for scoring
                    sql = """
                        SELECT h.*, ha.composite_score
                        FROM holdings h
                        LEFT JOIN holding_analysis ha
                        ON h.symbol = ha.symbol
                        AND ha.analysis_date = %s
                        AND ha.mode = 'multi_agent'
                        ORDER BY h.added_at DESC
                    """
                    cursor.execute(sql, (analysis_date,))
                else:
                    cursor.execute("SELECT * FROM holdings ORDER BY added_at DESC")

                rows = cursor.fetchall()

            result = []
            for row in rows:
                item = {
                    "symbol": row["symbol"],
                    "name": row["name"],
                    "type": row["type"],
                    "asset_type": row["type"],  # 兼容性别名
                    "cost_price": float(row["cost_price"]),  # Decimal 转 float
                    "position_size": row["position_size"],
                    "added_at": row["added_at"],
                    "is_starred": bool(row.get("is_starred", 0)),  # 收藏状态
                }
                if analysis_date:
                    item["composite_score"] = row.get("composite_score")

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
                    "symbol": row["symbol"],
                    "name": row["name"],
                    "type": row["type"],
                    "asset_type": row["type"],
                    "cost_price": float(row["cost_price"]),
                    "position_size": row["position_size"],
                    "is_starred": bool(row.get("is_starred", 0)),  # 收藏状态
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


def toggle_star_holding(symbol: str) -> Optional[bool]:
    """切换持仓收藏状态，返回切换后的新状态（True=已收藏，False=未收藏，None=失败）"""
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                # 先查询当前状态
                cursor.execute(
                    "SELECT is_starred FROM holdings WHERE symbol = %s", (symbol,)
                )
                row = cursor.fetchone()
                if not row:
                    print(f"⚠️ 未找到持仓: {symbol}")
                    return None
                new_state = 0 if row["is_starred"] else 1
                cursor.execute(
                    "UPDATE holdings SET is_starred = %s WHERE symbol = %s",
                    (new_state, symbol),
                )
            conn.commit()
            state_str = "⭐ 已收藏" if new_state else "☆ 已取消收藏"
            print(f"{state_str}: {symbol}")
            return bool(new_state)
        except Exception as e:
            print(f"❌ Error toggling star for {symbol}: {e}")
            return None
        finally:
            conn.close()
    except Exception as e:
        print(f"❌ Database connection error: {e}")
        return None


def save_holding_analysis(
    symbol: str, analysis_date: str, data: Dict[str, Any], mode: str = "multi_agent"
) -> bool:
    """
    Save or update daily analysis for a holding.
    data dict should contain: price, ma20, trend_signal, composite_score, ai_analysis
    """
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                import json

                def dump_json(obj):
                    if obj is None:
                        return None
                    try:
                        return json.dumps(obj, ensure_ascii=False)
                    except Exception:
                        return None

                sql = """
                INSERT INTO holding_analysis
                (symbol, analysis_date, mode, price, ma20, trend_signal, composite_score,
                 snapshot_version, analysis_snapshot, final_action, risk_level, consensus_level, agent_outputs, ai_analysis)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                price = VALUES(price),
                ma20 = VALUES(ma20),
                trend_signal = VALUES(trend_signal),
                composite_score = VALUES(composite_score),
                snapshot_version = VALUES(snapshot_version),
                analysis_snapshot = VALUES(analysis_snapshot),
                final_action = VALUES(final_action),
                risk_level = VALUES(risk_level),
                consensus_level = VALUES(consensus_level),
                agent_outputs = VALUES(agent_outputs),
                ai_analysis = VALUES(ai_analysis),
                created_at = CURRENT_TIMESTAMP
                """
                cursor.execute(
                    sql,
                    (
                        symbol,
                        analysis_date,
                        mode,
                        data.get("price", 0),
                        data.get("ma20", 0),
                        data.get("trend_signal", ""),
                        data.get("composite_score", 0),
                        data.get("snapshot_version", 1),
                        dump_json(data.get("analysis_snapshot")),
                        data.get("final_action"),
                        data.get("risk_level"),
                        data.get("consensus_level"),
                        dump_json(data.get("agent_outputs")),
                        data.get("ai_analysis", ""),
                    ),
                )
            conn.commit()
            print(f"✅ Saved {mode} analysis for {symbol} on {analysis_date}")
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
                cursor.execute(
                    sql,
                    (
                        selection_date,
                        selection_data["symbol"],
                        selection_data.get("name", ""),
                        selection_data.get("close_price", 0),
                        selection_data.get("volume_ratio", 0),
                        selection_data.get("composite_score", 0),
                        selection_data.get("ai_analysis", ""),
                    ),
                )
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


def save_daily_metrics(date: str, metrics: Dict[str, Any]) -> bool:
    """
    Save objective hard indicators to daily_metrics table.
    """
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                sql = """
                INSERT INTO daily_metrics
                (symbol, date, price, change_pct,
                 ma5, ma20, ma60,
                 rsi, kdj_k, kdj_d,
                 macd_dif, macd_dea, macd_macd,
                 volume_ratio, composite_score, entry_score, holding_score, holding_state, holding_state_label, rating, pattern_flags,
                 score_breakdown, score_details, entry_score_breakdown, entry_score_details, holding_score_breakdown, holding_score_details, operation_suggestion,
                 stop_loss_suggest, atr_pct, price_vs_high120)
                VALUES (%s, %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                price=VALUES(price), change_pct=VALUES(change_pct),
                ma5=VALUES(ma5), ma20=VALUES(ma20), ma60=VALUES(ma60),
                rsi=VALUES(rsi), kdj_k=VALUES(kdj_k), kdj_d=VALUES(kdj_d),
                macd_dif=VALUES(macd_dif), macd_dea=VALUES(macd_dea), macd_macd=VALUES(macd_macd),
                volume_ratio=VALUES(volume_ratio), composite_score=VALUES(composite_score),
                entry_score=VALUES(entry_score), holding_score=VALUES(holding_score),
                holding_state=VALUES(holding_state), holding_state_label=VALUES(holding_state_label),
                rating=VALUES(rating), pattern_flags=VALUES(pattern_flags),
                score_breakdown=VALUES(score_breakdown), score_details=VALUES(score_details),
                entry_score_breakdown=VALUES(entry_score_breakdown),
                entry_score_details=VALUES(entry_score_details),
                holding_score_breakdown=VALUES(holding_score_breakdown),
                holding_score_details=VALUES(holding_score_details),
                operation_suggestion=VALUES(operation_suggestion),
                stop_loss_suggest=VALUES(stop_loss_suggest), atr_pct=VALUES(atr_pct),
                price_vs_high120=VALUES(price_vs_high120)
                """

                # Helper to dump JSON safely
                import json
                import math

                def dump_json(obj):
                    if not obj:
                        return None
                    try:
                        return json.dumps(obj, ensure_ascii=False)
                    except:
                        return None

                # Helper to safely convert to float, handling NaN values
                def safe_float(value, default=None):
                    """将值安全转换为 float，NaN 转换为 None（MySQL NULL）"""
                    if value is None:
                        return default
                    # 检查是否为 NaN（支持 numpy.nan 和 math.nan）
                    try:
                        if math.isnan(value):
                            return default
                    except (TypeError, ValueError):
                        pass
                    try:
                        return float(value)
                    except (ValueError, TypeError):
                        return default

                cursor.execute(
                    sql,
                    (
                        metrics["symbol"],
                        date,
                        safe_float(metrics.get("price", 0)),
                        safe_float(metrics.get("change_pct", 0)),
                        safe_float(metrics.get("ma5")),
                        safe_float(metrics.get("ma20")),
                        safe_float(metrics.get("ma60")),
                        safe_float(metrics.get("rsi")),
                        safe_float(metrics.get("kdj_k")),
                        safe_float(metrics.get("kdj_d")),
                        safe_float(metrics.get("macd_dif")),
                        safe_float(metrics.get("macd_dea")),
                        safe_float(metrics.get("macd_macd")),
                        safe_float(metrics.get("volume_ratio")),
                        safe_float(metrics.get("composite_score")),
                        safe_float(metrics.get("entry_score")),
                        safe_float(metrics.get("holding_score")),
                        metrics.get("holding_state"),
                        metrics.get("holding_state_label"),
                        metrics.get("rating", ""),
                        metrics.get("pattern_flags", ""),
                        dump_json(metrics.get("score_breakdown")),
                        dump_json(metrics.get("score_details")),
                        dump_json(metrics.get("entry_score_breakdown")),
                        dump_json(metrics.get("entry_score_details")),
                        dump_json(metrics.get("holding_score_breakdown")),
                        dump_json(metrics.get("holding_score_details")),
                        metrics.get("operation_suggestion", ""),
                        safe_float(metrics.get("stop_loss_suggest")),
                        safe_float(metrics.get("atr_pct")),
                        safe_float(metrics.get("price_vs_high120")),
                    ),
                )
            conn.commit()
            print(f"✅ Saved daily metrics for {metrics['symbol']} on {date}")
            return True
        except Exception as e:
            print(f"❌ Error saving daily metrics: {e}")
            return False
        finally:
            conn.close()
    except Exception as e:
        print(f"❌ Database connection error: {e}")
        return False


def get_all_daily_metrics(date: str) -> Dict[str, Dict[str, Any]]:
    """
    Get metrics for ALL symbols on a specific date.
    Returns a dict keyed by symbol: { '600000': {...metrics...} }
    """
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM daily_metrics WHERE date = %s", (date,))
                rows = cursor.fetchall()

                result = {}
                for row in rows:
                    # Parse JSON fields simply for completeness, though we mainly need composite_score
                    result[row["symbol"]] = row

                return result
        finally:
            conn.close()
    except Exception as e:
        print(f"❌ Error fetching all daily metrics: {e}")
        return {}


def get_daily_metrics_batch(symbols: List[str], date: str) -> Dict[str, Dict[str, Any]]:
    """
    Get metrics for specific symbols on a specific date (Efficient Batch Query).
    Can utilize (symbol, date) index much better than get_all.
    """
    if not symbols:
        return {}

    try:
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                # Dynamically construct IN clause
                format_strings = ",".join(["%s"] * len(symbols))
                query = f"SELECT * FROM daily_metrics WHERE date = %s AND symbol IN ({format_strings})"

                # Params: date first, then all symbols
                params = [date] + symbols

                cursor.execute(query, tuple(params))
                rows = cursor.fetchall()

                result = {}
                for row in rows:
                    result[row["symbol"]] = row

                return result
        finally:
            conn.close()
    except Exception as e:
        print(f"❌ Error fetching batch metrics: {e}")
        return {}


def get_daily_metrics(symbol: str, date: str) -> Optional[Dict[str, Any]]:
    """Get metrics for specific symbol and date"""
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM daily_metrics WHERE symbol = %s AND date = %s",
                    (symbol, date),
                )
                row = cursor.fetchone()
                if row:
                    # Parse JSON fields if they exist as strings (depends on driver/mysql version)
                    # Pymysql with json might return dict or str
                    for field in [
                        "score_breakdown",
                        "score_details",
                        "entry_score_breakdown",
                        "entry_score_details",
                        "holding_score_breakdown",
                        "holding_score_details",
                    ]:
                        if isinstance(row.get(field), str):
                            try:
                                row[field] = json.loads(row[field])
                            except:
                                row[field] = []

                    # Ensure pattern_flags is a list for consistency in API if it was saved as comma-str
                    if row.get("pattern_flags") and isinstance(
                        row["pattern_flags"], str
                    ):
                        # It is saved as comma string, keep it but maybe API wants list in future
                        pass

                return row
        finally:
            conn.close()
    except Exception as e:
        print(f"❌ Error fetching daily metrics: {e}")
        return None


def get_daily_analysis_by_date(analysis_date: str) -> List[Dict[str, Any]]:
    """
    Get all holding analyses for a specific date.
    Returns a list of analysis records joined with holding info.
    """
    # Simple validation as per logs showing "status" or "logs" being passed
    if not analysis_date or analysis_date in ["status", "logs", "latest"]:
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
                    result.append(
                        {
                            "symbol": row["symbol"],
                            "name": row.get("name", row["symbol"]),
                            "analysis_date": _fmt_dt(row["analysis_date"], "%Y-%m-%d"),
                            "price": float(row["price"]) if row["price"] else 0,
                            "ma20": float(row["ma20"]) if row["ma20"] else 0,
                            "trend_signal": row["trend_signal"],
                            "composite_score": row["composite_score"],
                            "ai_analysis": row["ai_analysis"],
                        }
                    )
                return result
        finally:
            conn.close()
    except Exception as e:
        print(f"❌ Error fetching daily analysis for {analysis_date}: {e}")
        return []


def get_holding_analysis(
    symbol: str, analysis_date: Optional[str] = None, mode: str = "multi_agent"
) -> Optional[Dict[str, Any]]:
    """
    Get holding analysis from DB.
    If date is None, gets the latest analysis of specific type.
    """
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                if analysis_date:
                    sql = "SELECT * FROM holding_analysis WHERE symbol = %s AND analysis_date = %s AND mode = %s"
                    params = (symbol, analysis_date, mode)
                else:
                    sql = "SELECT * FROM holding_analysis WHERE symbol = %s AND mode = %s ORDER BY analysis_date DESC LIMIT 1"
                    params = (symbol, mode)

                cursor.execute(sql, params)
                row = cursor.fetchone()

                if row:
                    if isinstance(row.get("analysis_snapshot"), str):
                        try:
                            row["analysis_snapshot"] = json.loads(row["analysis_snapshot"])
                        except Exception:
                            row["analysis_snapshot"] = None
                    if isinstance(row.get("agent_outputs"), str):
                        try:
                            row["agent_outputs"] = json.loads(row["agent_outputs"])
                        except Exception:
                            row["agent_outputs"] = []
                    # Convert date/decimal to native types if needed (pymysql dictcursor usually helps)
                    return {
                        "symbol": row["symbol"],
                        "analysis_date": _fmt_dt(row["analysis_date"], "%Y-%m-%d"),
                        "mode": row.get("mode", "multi_agent"),
                        "price": float(row["price"]) if row["price"] else 0,
                        "ma20": float(row["ma20"]) if row["ma20"] else 0,
                        "trend_signal": row["trend_signal"],
                        "composite_score": row["composite_score"],
                        "snapshot_version": row.get("snapshot_version", 1),
                        "analysis_snapshot": row.get("analysis_snapshot"),
                        "final_action": row.get("final_action"),
                        "risk_level": row.get("risk_level"),
                        "consensus_level": row.get("consensus_level"),
                        "agent_outputs": row.get("agent_outputs") or [],
                        "ai_analysis": row["ai_analysis"],
                    }
                return None
        finally:
            conn.close()
    except Exception as e:
        print(f"❌ Error fetching analysis for {symbol}: {e}")
        return None


def get_analysis_dates_for_stock(symbol: str, mode: str = "multi_agent") -> List[str]:
    """Get list of available analysis dates for a stock"""
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                sql = "SELECT DISTINCT analysis_date FROM holding_analysis WHERE symbol = %s AND mode = %s ORDER BY analysis_date DESC"
                cursor.execute(sql, (symbol, mode))
                rows = cursor.fetchall()
                return [_fmt_dt(row["analysis_date"], "%Y-%m-%d") for row in rows]
        finally:
            conn.close()
    except Exception as e:
        print(f"❌ Error fetching analysis dates for {symbol}: {e}")
        return []


def get_daily_selection(
    symbol: str, selection_date: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Get a specific daily selection from DB.
    """
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                if not selection_date:
                    # Find latest date for this symbol
                    cursor.execute(
                        "SELECT MAX(selection_date) as max_date FROM daily_selections WHERE symbol = %s",
                        (symbol,),
                    )
                    res = cursor.fetchone()
                    if res and res["max_date"]:
                        selection_date = res["max_date"]
                    else:
                        return None

                sql = "SELECT * FROM daily_selections WHERE symbol = %s AND selection_date = %s"
                cursor.execute(sql, (symbol, selection_date))
                row = cursor.fetchone()

                if row:
                    return {
                        "symbol": row["symbol"],
                        "name": row["name"],
                        "close_price": float(row["close_price"])
                        if row["close_price"]
                        else 0,
                        "volume_ratio": float(row["volume_ratio"])
                        if row["volume_ratio"]
                        else 0,
                        "composite_score": row["composite_score"],
                        "ai_analysis": row["ai_analysis"],
                        "selection_date": _fmt_dt(row["selection_date"], "%Y-%m-%d"),
                        "created_at": _fmt_dt(row["created_at"], "%H:%M:%S")
                        if row.get("created_at")
                        else "",
                    }
                return None
        finally:
            conn.close()
    except Exception as e:
        print(f"❌ Error fetching daily selection for {symbol}: {e}")
        return None


def get_daily_selections(selection_date: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Get daily selections from DB.
    If date is None, gets the latest date available in DB.
    """
    # Simple validation
    if selection_date in ["status", "logs", "latest"]:
        return []

    try:
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                if not selection_date:
                    # Find latest date first
                    cursor.execute(
                        "SELECT MAX(selection_date) as max_date FROM daily_selections"
                    )
                    res = cursor.fetchone()
                    if res and res["max_date"]:
                        selection_date = res["max_date"]
                    else:
                        return []

                sql = "SELECT * FROM daily_selections WHERE selection_date = %s ORDER BY created_at DESC"
                cursor.execute(sql, (selection_date,))
                rows = cursor.fetchall()

                result = []
                for row in rows:
                    result.append(
                        {
                            "symbol": row["symbol"],
                            "name": row["name"],
                            "close_price": float(row["close_price"])
                            if row["close_price"]
                            else 0,
                            "volume_ratio": float(row["volume_ratio"])
                            if row["volume_ratio"]
                            else 0,
                            "composite_score": row["composite_score"],
                            "ai_analysis": row["ai_analysis"],
                            "selection_date": _fmt_dt(
                                row["selection_date"], "%Y-%m-%d"
                            ),
                            "created_at": _fmt_dt(row["created_at"], "%H:%M:%S")
                            if row.get("created_at")
                            else "",
                        }
                    )
                return result
        finally:
            conn.close()
    except Exception as e:
        print(f"❌ Error fetching selections: {e}")
        return []


def save_intraday_log(symbol: str, price: float, change_pct: float, analysis: str):
    """
    Save real-time intraday analysis log.
    """
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                sql = """
                INSERT INTO intraday_logs (symbol, price, change_pct, ai_content, analysis_time)
                VALUES (%s, %s, %s, %s, NOW())
                """
                cursor.execute(sql, (symbol, price, change_pct, analysis))
            conn.commit()
            print(f"✅ Saved intraday log for {symbol}")
            return True
        except Exception as e:
            conn.rollback()
            print(f"❌ Error saving intraday log for {symbol}: {e}")
            return False
        finally:
            conn.close()
    except Exception as e:
        print(f"❌ Database connection error: {e}")
        return False


def get_intraday_log(
    symbol: str, analysis_time: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    获取盘中分析日志。
    如果 analysis_time 为 None，则获取该股票的最新一条记录。
    """
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                if analysis_time:
                    # 查询指定时间的记录
                    sql = "SELECT * FROM intraday_logs WHERE symbol = %s AND analysis_time = %s"
                    params = (symbol, analysis_time)
                else:
                    # 查询最新记录
                    sql = "SELECT * FROM intraday_logs WHERE symbol = %s ORDER BY analysis_time DESC LIMIT 1"
                    params = (symbol,)

                cursor.execute(sql, params)
                row = cursor.fetchone()

                if row:
                    return {
                        "id": row["id"],
                        "symbol": row["symbol"],
                        "analysis_time": _fmt_dt(
                            row["analysis_time"], "%Y-%m-%d %H:%M:%S"
                        )
                        if row.get("analysis_time")
                        else "",
                        "price": float(row["price"]) if row["price"] else 0,
                        "change_pct": float(row["change_pct"])
                        if row["change_pct"]
                        else 0,
                        "ai_content": row["ai_content"],
                        "created_at": _fmt_dt(row["created_at"], "%Y-%m-%d %H:%M:%S")
                        if row.get("created_at")
                        else "",
                    }
                return None
        finally:
            conn.close()
    except Exception as e:
        print(f"❌ Error fetching intraday log for {symbol}: {e}")
        return None


def get_all_strategies() -> List[Dict[str, Any]]:
    """Get all strategies"""
    db_strategies = []
    try:
        conn = get_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM strategies ORDER BY category, id")
                db_strategies = cursor.fetchall()
        finally:
            conn.close()
    except Exception as e:
        print(f"❌ Error getting all strategies: {e}")

    yaml_agents = _load_agents_from_yaml()
    yaml_slugs = set(yaml_agents.keys())

    final_strategies = []
    for s in db_strategies:
        if s["slug"] not in yaml_slugs:
            final_strategies.append(s)

    for slug, data in yaml_agents.items():
        s = {
            "id": data.get("id", 0),
            "slug": slug,
            "name": data.get("name", ""),
            "description": data.get("description", ""),
            "category": data.get("category", "general"),
            "template_content": data.get("template_content", ""),
        }
        final_strategies.append(s)

    final_strategies.sort(key=lambda x: (x.get("category", ""), x.get("id", 0)))
    return final_strategies


def get_strategy_by_slug(slug: str) -> Optional[Dict[str, Any]]:
    """Get full strategy details including params by slug (YAML prioritized)"""
    yaml_agents = _load_agents_from_yaml()
    if slug in yaml_agents:
        data = yaml_agents[slug]
        return {
            "id": data.get("id", 0),
            "slug": slug,
            "name": data.get("name", ""),
            "description": data.get("description", ""),
            "category": data.get("category", "general"),
            "template_content": data.get("template_content", ""),
            "params": {
                "role": data.get("role", ""),
                "system_prompt": data.get("system_prompt", ""),
            },
        }

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
                cursor.execute(
                    "SELECT param_key, param_value FROM strategy_params WHERE strategy_id = %s",
                    (strategy["id"],),
                )
                params = cursor.fetchall()

                # Convert list of dicts to single dict
                param_dict = {p["param_key"]: p["param_value"] for p in params}
                strategy["params"] = param_dict

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

                cursor.execute(
                    "SELECT * FROM strategy_params WHERE strategy_id = %s",
                    (strategy_id,),
                )
                params = cursor.fetchall()
                strategy["params_list"] = params  # Full list with metadata

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
                    (template_content, strategy_id),
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
