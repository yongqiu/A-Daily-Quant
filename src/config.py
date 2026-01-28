# -*- coding: utf-8 -*-
"""
Adapter for Project A (a_daily_strategy) to support Project B's data_provider.
Reads config.json and exposes a Config object compatible with daily_stock_analysis.
"""
import os
import json
from dataclasses import dataclass, field
from typing import Optional, List
from pathlib import Path

# Constants for default values
DEFAULT_TUSHARE_TOKEN = "14ffbaa9fb770941ee1660ceccf195ece7aafde49d5d8fc4c764753e"

@dataclass
class Config:
    # Data Source
    tushare_token: Optional[str] = None
    
    # Realtime Quotes
    enable_realtime_quote: bool = True
    realtime_source_priority: str = "akshare_sina,tencent,efinance,akshare_em"
    realtime_cache_ttl: int = 600
    circuit_breaker_cooldown: int = 300
    enable_chip_distribution: bool = True

    # Rate Limiting & Retry
    akshare_sleep_min: float = 2.0
    akshare_sleep_max: float = 5.0
    max_retries: int = 3
    retry_base_delay: float = 1.0
    retry_max_delay: float = 30.0
    
    # Instance management
    _instance: Optional['Config'] = None

    @classmethod
    def get_instance(cls) -> 'Config':
        if cls._instance is None:
            cls._instance = cls._load_from_json()
        return cls._instance

    @classmethod
    def _load_from_json(cls) -> 'Config':
        """Load configuration from config.json in the project root."""
        config = cls()
        
        try:
            # Plan A: Try to find config.json in current or parent directories
            current_path = Path(__file__).parent.absolute()
            project_root = current_path.parent
            config_path = project_root / 'config.json'
            
            if not config_path.exists():
                # Fallback: try finding it relative to CWD
                config_path = Path('config.json').absolute()
            
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                    # Extract Tushare Token
                    if 'data_source' in data and 'tushare_token' in data['data_source']:
                        config.tushare_token = data['data_source']['tushare_token']
                    
                    # You can map other fields here if they exist in config.json
                    # For now, we use defaults for realtime/retry logic as they aren't in config.json
            else:
                pass # Use defaults
                
        except Exception as e:
            print(f"Warning: Failed to load config.json: {e}. Using defaults.")

        # Ensure tushare token is set (fallback to known default if missing in json)
        if not config.tushare_token:
            config.tushare_token = DEFAULT_TUSHARE_TOKEN

        return config

def get_config() -> Config:
    return Config.get_instance()
