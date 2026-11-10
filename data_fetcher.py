"""
Data Fetcher v3.0 - Нервная Система ИИ-Хедж-Фонда
Исправленная версия (без await для ccxt)
"""

import ccxt
import pandas as pd
import numpy as np
import asyncio
import aiohttp
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, List

# ================= НАСТРОЙКИ =================
EXCHANGE_ID = 'binance'
TOP_N = 30
TIMEFRAMES = ['1m', '5m', '15m', '1h']
CANDLE_LIMITS = {'1m': 500, '5m': 500, '15m': 500, '1h': 500}

MAX_CORRELATION = 0.6

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


class DataFetcher:
    """Нервная система бота"""
    
    def __init__(self):
        # Binance Spot для свечей (синхронный)
        self.exchange = ccxt.binance({
            'enableRateLimit': True,
            'options': {'defaultType': 'spot'}
        })
        
        # HTTP сессия для прямых запросов к API фьючерсов
        self.session = None
        
        # Кэш данных
        self.market_data: Dict[str, Dict] = {}
        self.last_update: Dict[str, datetime] = {}
        self.coins: List[str] = []
        
        # Данные BTC и ETH для корреляции
        self.btc_returns = None
        self.eth_returns = None
        
        logger.info("🧠 Data Fetcher v3.0 инициализирован")
    
    async def start(self):
        """Запуск HTTP сессии"""
        self.session = aiohttp.ClientSession()
        logger.info("🌐 HTTP сессия запущена")
    
    async def stop(self):
        """Остановка"""
        if self.session:
            await self.session.close()
            logger.info("🌐 HTTP сессия закрыта")
    
    # ================= СПИСОК МОНЕТ =================
    
    def get_top_coins_sync(self) -> List[str]:
        """Получает топ монет (синхронно)"""
        try:
            self.exchange.load_markets()
            tickers = self.exchange.fetch_tickers()
            
            stablecoins = [
                'USDC', 'TUSD', 'FDUSD', 'DAI', 'BUSD', 'USDD', 'PYUSD', 'GHO',
                'CRVUSD', 'USDP', 'DOLA', 'FRAX', 'LUSD', 'SUSD', 'EURC', 'EUROC',
                'USD1', 'RLUSD', 'RUSD', 'EURT', 'USDN', 'UST', 'USDK', 'USDJ',
                'EUR', 'TRY', 'GBP', 'BRL', 'AUD', 'UP', 'DOWN', 'BEAR', 'BULL'
            ]
            
            usdt_pairs = {}
            for symbol, ticker in tickers.items():
                if not symbol.endswith('/USDT'):
                    continue
                coin = symbol.replace('/USDT', '')
                if coin in stablecoins or any(x in coin for x in stablecoins):
                    continue
                price = ticker.get('last') or 0
                if 0.90 <= price <= 1.10 or price == 0:
                    continue
                usdt_pairs[symbol] = ticker
            
            sorted_pairs = sorted(
                usdt_pairs.items(),
                key=lambda x: x[1].get('quoteVolume') or 0,
                reverse=True
            )
            
            top_symbols = [pair[0] for pair in sorted_pairs[:TOP_N]]
            
            # Загружаем BTC и ETH для корреляции
            self._load_btc_eth_data_sync()
            
            # Фильтруем по корреляции
            uncorrelated_coins = []
            for symbol in top_symbols:
                coin = symbol.replace('/USDT', '')
                
                if coin in ['BTC', 'ETH']:
                    uncorrelated_coins.append(coin)
                    continue
                
                correlation = self._calculate_correlation_sync(symbol)
                
                if correlation <= MAX_CORRELATION:
                    uncorrelated_coins.append(coin)
                else:
                    logger.debug(f"❌ {coin} отфильтрован (корреляция {correlation:.2f})")
            
            if len(uncorrelated_coins) < 10:
                logger.warning(f"⚠️ Мало некоррелированных монет ({len(uncorrelated_coins)}). Беру топ-20.")
                return [s.replace('/USDT', '') for s in top_symbols[:20]]
            
            self.coins = uncorrelated_coins
            logger.info(f"✅ Загружено {len(uncorrelated_coins)} монет: {', '.join(uncorrelated_coins[:10])}...")
            
            return uncorrelated_coins
            
        except Exception as e:
            logger.error(f"Ошибка получения списка монет: {e}")
            return []
    
    def _load_btc_eth_data_sync(self):
        """Загружает данные BTC и ETH (синхронно)"""
        try:
            btc_ohlcv = self.exchange.fetch_ohlcv('BTC/USDT', '1h', limit=72)
            eth_ohlcv = self.exchange.fetch_ohlcv('ETH/USDT', '1h', limit=72)
            
            if btc_ohlcv and len(btc_ohlcv) >= 10:
                btc_df = pd.DataFrame(btc_ohlcv, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
                self.btc_returns = btc_df['close'].pct_change().dropna().values
            
            if eth_ohlcv and len(eth_ohlcv) >= 10:
                eth_df = pd.DataFrame(eth_ohlcv, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
                self.eth_returns = eth_df['close'].pct_change().dropna().values
                
        except Exception as e:
            logger.error(f"Ошибка загрузки BTC/ETH: {e}")
    
    def _calculate_correlation_sync(self, symbol: str) -> float:
        """Считает корреляцию с BTC и ETH (синхронно)"""
        try:
            ohlcv = self.exchange.fetch_ohlcv(symbol, '1h', limit=72)
            if not ohlcv or len(ohlcv) < 10:
                return 1.0
            
            df = pd.DataFrame(ohlcv, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
            returns = df['close'].pct_change().dropna().values
            
            if len(returns) < 10:
                return 1.0
            
            corr_btc = 0.0
            if self.btc_returns is not None:
                min_len = min(len(returns), len(self.btc_returns))
                corr_btc = abs(np.corrcoef(returns[-min_len:], self.btc_returns[-min_len:])[0, 1])
                if np.isnan(corr_btc):
                    corr_btc = 0.0
            
            corr_eth = 0.0
            if self.eth_returns is not None:
                min_len = min(len(returns), len(self.eth_returns))
                corr_eth = abs(np.corrcoef(returns[-min_len:], self.eth_returns[-min_len:])[0, 1])
                if np.isnan(corr_eth):
                    corr_eth = 0.0
            
            return max(corr_btc, corr_eth)
            
        except Exception as e:
            logger.debug(f"Ошибка расчёта корреляции для {symbol}: {e}")
            return 1.0
    
    # ================= СВЕЧИ =================
    
    def fetch_ohlcv_sync(self, symbol: str, timeframe: str) -> Optional[pd.DataFrame]:
        """Получает свечи OHLCV (синхронно)"""
        try:
            limit = CANDLE_LIMITS.get(timeframe, 500)
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            
            if not ohlcv:
                return None
            
            df = pd.DataFrame(ohlcv, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
            df['time'] = pd.to_datetime(df['time'], unit='ms')
            df = df.set_index('time')
            
            return df
            
        except Exception as e:
            logger.debug(f"Ошибка загрузки свечей {symbol} {timeframe}: {e}")
            return None
    
    # ================= OPEN INTEREST =================
    
    async def fetch_open_interest(self, symbol: str) -> Optional[Dict]:
        """Получает Open Interest (асинхронно через HTTP)"""
        try:
            url = f"https://fapi.binance.com/fapi/v1/openInterest"
            params = {'symbol': symbol}
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    oi = float(data['openInterest'])
                    
                    prev_oi = self.market_data.get(symbol, {}).get('open_interest', oi)
                    oi_change = ((oi - prev_oi) / prev_oi * 100) if prev_oi > 0 else 0
                    
                    return {
                        'open_interest': oi,
                        'oi_change_percent': oi_change
                    }
            
            return None
            
        except Exception as e:
            logger.debug(f"Ошибка получения OI для {symbol}: {e}")
            return None
    
    # ================= FUNDING RATE =================
    
    async def fetch_funding_rate(self, symbol: str) -> Optional[float]:
        """Получает Funding Rate"""
        try:
            url = f"https://fapi.binance.com/fapi/v1/fundingRate"
            params = {'symbol': symbol, 'limit': 1}
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if data:
                        return float(data[0]['fundingRate'])
            
            return None
            
        except Exception as e:
            logger.debug(f"Ошибка получения Funding Rate для {symbol}: {e}")
            return None
    
    # ================= LONG/SHORT RATIO =================
    
    async def fetch_long_short_ratio(self, symbol: str) -> Optional[Dict]:
        """Получает Long/Short Ratio"""
        try:
            url_global = f"https://fapi.binance.com/futures/data/globalLongShortAccountRatio"
            params_global = {'symbol': symbol, 'period': '5m', 'limit': 1}
            
            url_top = f"https://fapi.binance.com/futures/data/topLongShortAccountRatio"
            params_top = {'symbol': symbol, 'period': '5m', 'limit': 1}
            
            global_ratio = None
            top_ratio = None
            
            async with self.session.get(url_global, params=params_global) as response:
                if response.status == 200:
                    data = await response.json()
                    if data:
                        global_ratio = float(data[0]['longShortRatio'])
            
            async with self.session.get(url_top, params=params_top) as response:
                if response.status == 200:
                    data = await response.json()
                    if data:
                        top_ratio = float(data[0]['longShortRatio'])
            
            if global_ratio or top_ratio:
                return {
                    'global': global_ratio,
                    'top_traders': top_ratio
                }
            
            return None
            
        except Exception as e:
            logger.debug(f"Ошибка получения L/S Ratio для {symbol}: {e}")
            return None
    
    # ================= ИНДИКАТОРЫ =================
    
    def calculate_indicators(self, df: pd.DataFrame) -> Dict:
        """Рассчитывает все технические индикаторы"""
        try:
            if df is None or len(df) < 250:
                return {}
            
            close = df['close']
            high = df['high']
            low = df['low']
            volume = df['volume']
            
            indicators = {}
            
            indicators['ema_9'] = self._calculate_ema(close, 9)
            indicators['ema_200'] = self._calculate_ema(close, 200)
            indicators['ema_250'] = self._calculate_ema(close, 250)
            indicators['vwap'] = self._calculate_vwap(high, low, close, volume)
            indicators['atr_14'] = self._calculate_atr(high, low, close, 14)
            indicators['rsi'] = self._calculate_rsi(close, 14)
            
            stoch_k, stoch_d = self._calculate_stochastic(high, low, close, 14, 3, 3)
            indicators['stoch_k'] = stoch_k
            indicators['stoch_d'] = stoch_d
            
            vi_plus, vi_minus = self._calculate_vortex(high, low, close, 14)
            indicators['vortex_vi_plus'] = vi_plus
            indicators['vortex_vi_minus'] = vi_minus
            
            indicators['roc'] = self._calculate_roc(close, 12)
            
            return indicators
            
        except Exception as e:
            logger.debug(f"Ошибка расчёта индикаторов: {e}")
            return {}
    
    def _calculate_ema(self, series: pd.Series, period: int) -> float:
        if len(series) < period:
            return series.iloc[-1] if len(series) > 0 else 0.0
        ema = series.ewm(span=period, adjust=False).mean()
        return ema.iloc[-1]
    
    def _calculate_vwap(self, high: pd.Series, low: pd.Series, 
                        close: pd.Series, volume: pd.Series) -> float:
        typical_price = (high + low + close) / 3
        vwap = (typical_price * volume).cumsum() / volume.cumsum()
        return vwap.iloc[-1]
    
    def _calculate_atr(self, high: pd.Series, low: pd.Series, 
                       close: pd.Series, period: int) -> float:
        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()
        return atr.iloc[-1]
    
    def _calculate_rsi(self, close: pd.Series, period: int) -> float:
        delta = close.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        avg_gain = gain.rolling(window=period).mean()
        avg_loss = loss.rolling(window=period).mean()
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return rsi.iloc[-1]
    
    def _calculate_stochastic(self, high: pd.Series, low: pd.Series, 
                              close: pd.Series, k_period: int, 
                              k_smooth: int, d_smooth: int):
        lowest_low = low.rolling(window=k_period).min()
        highest_high = high.rolling(window=k_period).max()
        k = 100 * (close - lowest_low) / (highest_high - lowest_low)
        k_smoothed = k.rolling(window=k_smooth).mean()
        d = k_smoothed.rolling(window=d_smooth).mean()
        return k_smoothed.iloc[-1], d.iloc[-1]
    
    def _calculate_vortex(self, high: pd.Series, low: pd.Series, 
                          close: pd.Series, period: int):
        tr = self._calculate_tr(high, low, close)
        vm_plus = (high - low.shift()).abs()
        vm_minus = (low - high.shift()).abs()
        vi_plus = vm_plus.rolling(window=period).sum() / tr.rolling(window=period).sum()
        vi_minus = vm_minus.rolling(window=period).sum() / tr.rolling(window=period).sum()
        return vi_plus.iloc[-1], vi_minus.iloc[-1]
    
    def _calculate_roc(self, close: pd.Series, period: int) -> float:
        roc = ((close - close.shift(period)) / close.shift(period)) * 100
        return roc.iloc[-1]
    
    def _calculate_tr(self, high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        return pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # ================= ОБНОВЛЕНИЕ ДАННЫХ =================
    
    async def update_coin_data(self, coin: str):
        """Обновляет все данные по монете"""
        try:
            symbol = f"{coin}/USDT"
            futures_symbol = f"{coin}USDT"
            
            if coin not in self.market_data:
                self.market_data[coin] = {
                    'ohlcv': {},
                    'open_interest': 0,
                    'oi_change_percent': 0,
                    'funding_rate': 0,
                    'long_short_ratio': {'global': 1.0, 'top_traders': 1.0},
                    'indicators': {},
                    'last_update': None
                }
            
            # Обновляем свечи (синхронно)
            for tf in TIMEFRAMES:
                df = self.fetch_ohlcv_sync(symbol, tf)
                if df is not None:
                    self.market_data[coin]['ohlcv'][tf] = df
                    
                    if tf == '5m':
                        indicators = self.calculate_indicators(df)
                        self.market_data[coin]['indicators'] = indicators
            
            # Обновляем OI (асинхронно)
            oi_data = await self.fetch_open_interest(futures_symbol)
            if oi_data:
                self.market_data[coin]['open_interest'] = oi_data['open_interest']
                self.market_data[coin]['oi_change_percent'] = oi_data['oi_change_percent']
            
            # Обновляем Funding
            funding = await self.fetch_funding_rate(futures_symbol)
            if funding is not None:
                self.market_data[coin]['funding_rate'] = funding
            
            # Обновляем L/S Ratio
            ls_ratio = await self.fetch_long_short_ratio(futures_symbol)
            if ls_ratio:
                self.market_data[coin]['long_short_ratio'] = ls_ratio
            
            self.market_data[coin]['last_update'] = datetime.now()
            
        except Exception as e:
            logger.error(f"Ошибка обновления данных для {coin}: {e}")
    
    async def update_all_coins(self):
        """Обновляет данные по всем монетам"""
        if not self.coins:
            self.coins = self.get_top_coins_sync()
        
        logger.info(f"🔄 Обновление данных для {len(self.coins)} монет...")
        
        for coin in self.coins:
            await self.update_coin_data(coin)
            await asyncio.sleep(0.1)
        
        logger.info("✅ Обновление завершено")
    
    # ================= ПОЛУЧЕНИЕ ДАННЫХ =================
    
    def get_data(self, coin: str, timeframe: str = '5m') -> Optional[Dict]:
        """Получает все данные по монете"""
        if coin not in self.market_data:
            return None
        
        data = self.market_data[coin].copy()
        
        if timeframe in data['ohlcv']:
            data['df'] = data['ohlcv'][timeframe]
        
        return data
    
    def get_all_coins_data(self) -> Dict[str, Dict]:
        """Получает данные по всем монетам"""
        return self.market_data.copy()


# ================= ТЕСТ =================

async def test_data_fetcher():
    """Тестовый запуск"""
    fetcher = DataFetcher()
    await fetcher.start()
    
    try:
        coins = fetcher.get_top_coins_sync()
        print(f"\n📊 Список монет ({len(coins)}):")
        print(coins[:10])
        
        await fetcher.update_all_coins()
        
        if coins:
            coin = coins[0]
            data = fetcher.get_data(coin, '5m')
            if data:
                print(f"\n📈 Данные для {coin}:")
                print(f"  OI: {data['open_interest']:,.2f}")
                print(f"  OI Change: {data['oi_change_percent']:.2f}%")
                print(f"  Funding Rate: {data['funding_rate']:.6f}")
                print(f"  L/S Ratio (Global): {data['long_short_ratio']['global']:.3f}")
                print(f"  L/S Ratio (Top): {data['long_short_ratio']['top_traders']:.3f}")
                print(f"  EMA 9: {data['indicators'].get('ema_9', 0):.6f}")
                print(f"  EMA 200: {data['indicators'].get('ema_200', 0):.6f}")
                print(f"  VWAP: {data['indicators'].get('vwap', 0):.6f}")
                print(f"  ATR 14: {data['indicators'].get('atr_14', 0):.6f}")
                print(f"  RSI: {data['indicators'].get('rsi', 0):.2f}")
                print(f"  Stoch K: {data['indicators'].get('stoch_k', 0):.2f}")
                print(f"  Vortex VI+: {data['indicators'].get('vortex_vi_plus', 0):.3f}")
                print(f"  Vortex VI-: {data['indicators'].get('vortex_vi_minus', 0):.3f}")
                print(f"  ROC: {data['indicators'].get('roc', 0):.2f}%")
        
    finally:
        await fetcher.stop()


if __name__ == '__main__':
    asyncio.run(test_data_fetcher())