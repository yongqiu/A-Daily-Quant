# -*- coding: utf-8 -*-
"""
===================================
TushareFetcher - 备用数据源 1 (Priority 2)
===================================

数据来源：Tushare Pro API（挖地兔）
特点：需要 Token、有请求配额限制
优点：数据质量高、接口稳定

流控策略：
1. 实现"每分钟调用计数器"
2. 超过免费配额（80次/分）时，强制休眠到下一分钟
3. 使用 tenacity 实现指数退避重试
"""

import logging
import time
from datetime import datetime
from typing import Optional, Tuple

import pandas as pd
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

from .base import BaseFetcher, DataFetchError, RateLimitError, STANDARD_COLUMNS
from src.config import get_config

logger = logging.getLogger(__name__)


class TushareFetcher(BaseFetcher):
    """
    Tushare Pro 数据源实现
    
    优先级：2
    数据来源：Tushare Pro API
    
    关键策略：
    - 每分钟调用计数器，防止超出配额
    - 超过 80 次/分钟时强制等待
    - 失败后指数退避重试
    
    配额说明（Tushare 免费用户）：
    - 每分钟最多 80 次请求
    - 每天最多 500 次请求
    """
    
    name = "TushareFetcher"
    priority = 2  # 默认优先级，会在 __init__ 中根据配置动态调整

    def __init__(self, rate_limit_per_minute: int = 80):
        """
        初始化 TushareFetcher

        Args:
            rate_limit_per_minute: 每分钟最大请求数（默认80，Tushare免费配额）
        """
        import threading
        self._lock = threading.RLock()
        self.rate_limit_per_minute = rate_limit_per_minute
        self._call_count = 0  # 当前分钟内的调用次数
        self._minute_start: Optional[float] = None  # 当前计数周期开始时间
        self._api: Optional[object] = None  # Tushare API 实例

        # 尝试初始化 API
        self._init_api()

        # 根据 API 初始化结果动态调整优先级
        self.priority = self._determine_priority()
    
    def _init_api(self) -> None:
        """
        初始化 Tushare API
        
        如果 Token 未配置，此数据源将不可用
        """
        config = get_config()
        
        if not config.tushare_token:
            logger.warning("Tushare Token 未配置，此数据源不可用")
            return
        
        try:
            import tushare as ts
            
            # 设置 Token
            ts.set_token(config.tushare_token)
            
            # 获取 API 实例
            self._api = ts.pro_api()
            
            logger.info("Tushare API 初始化成功")
            
        except Exception as e:
            logger.error(f"Tushare API 初始化失败: {e}")
            self._api = None

    def _determine_priority(self) -> int:
        """
        根据 Token 配置和 API 初始化状态确定优先级

        策略：
        - Token 配置且 API 初始化成功：优先级 0（最高）
        - 其他情况：优先级 2（默认）

        Returns:
            优先级数字（0=最高，数字越大优先级越低）
        """
        config = get_config()

        if config.tushare_token and self._api is not None:
            # Token 配置且 API 初始化成功，提升为最高优先级
            logger.info("✅ 检测到 TUSHARE_TOKEN 且 API 初始化成功，Tushare 数据源优先级提升为最高 (Priority 0)")
            return -1

        # Token 未配置或 API 初始化失败，保持默认优先级
        return 2

    def is_available(self) -> bool:
        """
        检查数据源是否可用

        Returns:
            True 表示可用，False 表示不可用
        """
        return self._api is not None

    def _check_rate_limit(self) -> None:
        """
        检查并执行速率限制
        
        流控策略：
        1. 检查是否进入新的一分钟
        2. 如果是，重置计数器
        3. 如果当前分钟调用次数超过限制，强制休眠
        """
        with self._lock:
            current_time = time.time()
            
            # 检查是否需要重置计数器（新的一分钟）
            if self._minute_start is None:
                self._minute_start = current_time
                self._call_count = 0
            elif current_time - self._minute_start >= 60:
                # 已经过了一分钟，重置计数器
                self._minute_start = current_time
                self._call_count = 0
                logger.debug("速率限制计数器已重置")
            
            # 检查是否超过配额
            if self._call_count >= self.rate_limit_per_minute:
                # 计算需要等待的时间（到下一分钟）
                elapsed = current_time - self._minute_start
                sleep_time = max(0, 60 - elapsed) + 1  # +1 秒缓冲
                
                logger.warning(
                    f"Tushare 达到速率限制 ({self._call_count}/{self.rate_limit_per_minute} 次/分钟)，"
                    f"等待 {sleep_time:.1f} 秒..."
                )
                
                time.sleep(sleep_time)
                
                # 重置计数器
                self._minute_start = time.time()
                self._call_count = 0
            
            # 增加调用计数
            self._call_count += 1
            logger.debug(f"Tushare 当前分钟调用次数: {self._call_count}/{self.rate_limit_per_minute}")
    
    def _convert_stock_code(self, stock_code: str) -> str:
        """
        转换股票代码为 Tushare 格式
        
        Tushare 要求的格式：
        - 沪市：600519.SH
        - 深市：000001.SZ
        
        Args:
            stock_code: 原始代码，如 '600519', '000001'
            
        Returns:
            Tushare 格式代码，如 '600519.SH', '000001.SZ'
        """
        code = stock_code.strip()
        
        # 已经包含后缀的情况
        if '.' in code:
            return code.upper()
        
        # 根据代码前缀判断市场
        # 沪市：600xxx, 601xxx, 603xxx, 605xxx, 688xxx (科创板), 689xxx (科创板CDR)
        # 深市：000xxx, 001xxx, 002xxx, 003xxx, 300xxx (创业板)
        # 北交所：4xx, 8xx (Tushare 通常使用 .BJ)
        
        if code.startswith(('600', '601', '603', '605', '688', '689')):
            return f"{code}.SH"
        elif code.startswith(('000', '001', '002', '003', '300', '301')):
            return f"{code}.SZ"
        elif code.startswith(('4', '8')):
            return f"{code}.BJ"
        else:
            # 默认尝试深市
            logger.warning(f"无法确定股票 {code} 的市场，默认使用深市")
            return f"{code}.SZ"
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((ConnectionError, TimeoutError)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def _fetch_raw_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        从 Tushare 获取原始数据
        
        使用 daily() 接口获取日线数据
        
        流程：
        1. 检查 API 是否可用
        2. 执行速率限制检查
        3. 转换股票代码格式
        4. 调用 API 获取数据
        """
        if self._api is None:
            raise DataFetchError("Tushare API 未初始化，请检查 Token 配置")
        
        # 速率限制检查
        self._check_rate_limit()
        
        # 转换代码格式
        ts_code = self._convert_stock_code(stock_code)
        
        # 转换日期格式（Tushare 要求 YYYYMMDD）
        ts_start = start_date.replace('-', '')
        ts_end = end_date.replace('-', '')
        
        logger.debug(f"调用 Tushare daily({ts_code}, {ts_start}, {ts_end})")
        
        try:
            # 调用 daily 接口获取日线数据
            df = self._api.daily(
                ts_code=ts_code,
                start_date=ts_start,
                end_date=ts_end,
            )
            
            return df
            
        except Exception as e:
            error_msg = str(e).lower()
            
            # 检测配额超限
            if any(keyword in error_msg for keyword in ['quota', '配额', 'limit', '权限']):
                logger.warning(f"Tushare 配额可能超限: {e}")
                raise RateLimitError(f"Tushare 配额超限: {e}") from e
            
            raise DataFetchError(f"Tushare 获取数据失败: {e}") from e
    
    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        """
        标准化 Tushare 数据
        
        Tushare daily 返回的列名：
        ts_code, trade_date, open, high, low, close, pre_close, change, pct_chg, vol, amount
        
        需要映射到标准列名：
        date, open, high, low, close, volume, amount, pct_chg
        """
        df = df.copy()
        
        # 列名映射
        column_mapping = {
            'trade_date': 'date',
            'vol': 'volume',
            # open, high, low, close, amount, pct_chg 列名相同
        }
        
        df = df.rename(columns=column_mapping)
        
        # 转换日期格式（YYYYMMDD -> YYYY-MM-DD）
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'], format='%Y%m%d')
        
        # 成交量单位转换（Tushare 的 vol 单位是手，需要转换为股）
        if 'volume' in df.columns:
            df['volume'] = df['volume'] * 100
        
        # 成交额单位转换（Tushare 的 amount 单位是千元，转换为元）
        if 'amount' in df.columns:
            df['amount'] = df['amount'] * 1000
        
        # 添加股票代码列
        df['code'] = stock_code
        
        # 只保留需要的列
        keep_cols = ['code'] + STANDARD_COLUMNS
        existing_cols = [col for col in keep_cols if col in df.columns]
        df = df[existing_cols]
        
        return df


if __name__ == "__main__":
    # 测试代码
    logging.basicConfig(level=logging.DEBUG)
    
    fetcher = TushareFetcher()
    
    try:
        df = fetcher.get_daily_data('600519')  # 茅台
        print(f"获取成功，共 {len(df)} 条数据")
        print(df.tail())
    except Exception as e:
        print(f"获取失败: {e}")
