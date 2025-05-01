import os
import json
import time
import logging
import datetime
import requests
import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Union, Tuple
from dataclasses import dataclass, field
from google import genai
from web3 import Web3
import ta  
import pickle

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("crypto_mcp.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("CryptoMCP")

print("Starting Enhanced CryptoMCP System...")

# Updated Configuration
@dataclass
class Config:
    gemini_api_key: str
    webhook_urls: Dict[str, str]  # Mapping of ticker -> webhook URL
    cryptocurrencies: List[str]
    cryptopanic_api_key: str  # CryptoPanic API key for news
    web3_providers: Dict[str, str] = field(default_factory=dict)  # Network -> provider URL
    data_fetch_interval: int = 3600  # Default 1 hour
    model_name: str = "gemini-pro"  # Gemini model to use
    webhook_enabled: bool = False  # Default to disabled for testing
    default_webhook_url: Optional[str] = None  # Default URL if ticker not found
    track_whale_wallets: bool = True  # Track large wallet movements
    technical_indicators: List[str] = field(default_factory=lambda: ["rsi", "macd", "bollinger"])
    lookback_days: int = 30  # Days of historical data to analyze
    backtest_enabled: bool = True  # Enable backtesting
    whale_threshold: float = 1000000  # $1M USD for whale transactions
    performance_evaluation_interval: int = 86400  # 24 hours
    check_tp_sl_interval: int = 500  # Check take profit/stop loss every 10 minutes
    position_check_interval: int = 60  # Check positions every minute
    
    @classmethod
    def from_file(cls, filename: str) -> 'Config':
        print(f"Loading config from {filename}...")
        try:
            with open(filename, 'r') as f:
                config_data = json.load(f)
            
            # Handle webhook_urls in different formats
            webhook_urls = {}
            
            # Check if we have the new webhook_urls format
            if 'webhook_urls' in config_data:
                webhook_urls = config_data['webhook_urls']
            # Check if we have the old webhook_url format (use as default)
            elif 'webhook_url' in config_data:
                webhook_urls = {}
                config_data['default_webhook_url'] = config_data['webhook_url']
            
            # Add web3 providers with defaults if not present
            if 'web3_providers' not in config_data:
                config_data['web3_providers'] = {
                    "ethereum": "https://eth-mainnet.g.alchemy.com/v2/demo",
                    "bsc": "https://bsc-dataseed.binance.org/",
                    "polygon": "https://polygon-rpc.com"
                }

            # Create a new dict with the values we need
            cleaned_config = {
                'gemini_api_key': config_data.get('gemini_api_key', ''),
                'webhook_urls': webhook_urls,
                'cryptocurrencies': config_data.get('cryptocurrencies', []),
                'cryptopanic_api_key': config_data.get('cryptopanic_api_key', ''),
                'web3_providers': config_data.get('web3_providers', {}),
                'data_fetch_interval': config_data.get('data_fetch_interval', 3600),
                'model_name': config_data.get('model_name', 'gemini-pro'),
                'webhook_enabled': config_data.get('webhook_enabled', False),
                'default_webhook_url': config_data.get('default_webhook_url', ''),
                'track_whale_wallets': config_data.get('track_whale_wallets', True),
                'technical_indicators': config_data.get('technical_indicators', ["rsi", "macd", "bollinger"]),
                'lookback_days': config_data.get('lookback_days', 30),
                'backtest_enabled': config_data.get('backtest_enabled', True),
                'whale_threshold': config_data.get('whale_threshold', 1000000),
                'performance_evaluation_interval': config_data.get('performance_evaluation_interval', 86400),
                'check_tp_sl_interval': config_data.get('check_tp_sl_interval', 600),
                'position_check_interval': config_data.get('position_check_interval', 60)
            }
            
            # Ensure cryptocurrencies is a list
            if not isinstance(cleaned_config['cryptocurrencies'], list):
                cleaned_config['cryptocurrencies'] = [cleaned_config['cryptocurrencies']]
            
            return cls(**cleaned_config)
        except Exception as e:
            print(f"Error loading config: {e}")
            logger.error(f"Error loading config: {e}")
            raise

# Enhanced data structures
@dataclass
class MarketData:
    ticker: str
    price: float
    open: float
    high: float
    low: float
    volume: float
    timestamp: datetime.datetime
    market_cap: Optional[float] = None
    price_change_24h: Optional[float] = None
    price_change_percentage_24h: Optional[float] = None
    rsi: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_histogram: Optional[float] = None
    bollinger_upper: Optional[float] = None
    bollinger_middle: Optional[float] = None
    bollinger_lower: Optional[float] = None
    sma_20: Optional[float] = None
    sma_50: Optional[float] = None
    sma_200: Optional[float] = None
    ema_12: Optional[float] = None
    ema_26: Optional[float] = None

@dataclass
class NewsItem:
    title: str
    summary: str
    source: str
    url: str
    sentiment: Optional[str] = None
    sentiment_score: Optional[float] = None
    timestamp: Optional[datetime.datetime] = None
    tickers_mentioned: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)

@dataclass
class OnChainData:
    ticker: str
    network: str
    timestamp: datetime.datetime
    large_transactions: List[Dict[str, Any]] = field(default_factory=list)
    active_addresses_24h: Optional[int] = None
    transaction_volume_24h: Optional[float] = None
    avg_transaction_value: Optional[float] = None
    whale_wallet_changes: Dict[str, float] = field(default_factory=dict)
    dex_volume: Optional[float] = None
    exchange_inflows: Optional[float] = None
    exchange_outflows: Optional[float] = None

@dataclass
class TradeSignal:
    ticker: str
    action: str  # buy, sell, exit_buy, exit_sell, hold
    price: float
    time: datetime.datetime
    confidence_score: float = 0.0
    size: Optional[float] = None
    sl: Optional[float] = None   # Stop loss
    tp: Optional[float] = None   # Take profit
    rationale: Optional[str] = None
    expected_holding_period: Optional[str] = None  # short, medium, long
    risk_assessment: Optional[str] = None  # low, medium, high
    source_signals: Dict[str, Any] = field(default_factory=dict)  # market, news, onchain, etc.
    per: Optional[float] = None  # Percentage return (positive only, 0 for losses)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert the trade signal to a dictionary for webhook payload"""
        # Format time in the accepted webhook format
        formatted_time = self.time.strftime("%Y-%m-%d %H:%M:%S")
        
        # Base payload with common fields
        payload = {
            "ticker": self.ticker,
            "action": self.action,
            "price": str(self.price),
            "time": formatted_time
        }
        
        # Add specific fields based on action type
        if self.action == "exit_buy" or self.action == "exit_sell":
            per_value = max(0, self.per if self.per is not None else 0)
            payload.update({
                "size": str(self.size if self.size is not None else ""),
                "per": str(per_value),
                "sl": str(self.sl if self.sl is not None else ""),
                "tp": str(self.tp if self.tp is not None else "")
            })
        elif self.action == "hold" and self.rationale:
            payload["rationale"] = self.rationale
            
        return payload

@dataclass
class Position:
    ticker: str
    action: str  # buy or sell
    entry_price: float
    entry_time: datetime.datetime
    size: float
    sl: float
    tp: float
    exit_price: Optional[float] = None
    exit_time: Optional[datetime.datetime] = None
    status: str = "open"  # open, closed_tp, closed_sl, closed_manual
    
    def is_take_profit_hit(self, current_price: float) -> bool:
        """Check if take profit has been hit"""
        if self.action == "buy":
            return current_price >= self.tp
        else:  # sell
            return current_price <= self.tp
    
    def is_stop_loss_hit(self, current_price: float) -> bool:
        """Check if stop loss has been hit"""
        if self.action == "buy":
            return current_price <= self.sl
        else:  # sell
            return current_price >= self.sl
    
    def calculate_profit_percentage(self) -> float:
        """Calculate profit percentage"""
        if not self.exit_price:
            return 0.0
        
        if self.action == "buy":
            profit_pct = (self.exit_price - self.entry_price) / self.entry_price * 100
        else:  # sell
            profit_pct = (self.entry_price - self.exit_price) / self.entry_price * 100
            
        return profit_pct
    
    def to_exit_signal(self, current_price: float, reason: str) -> TradeSignal:
        """Convert position to exit signal"""
        exit_action = f"exit_{self.action}"
        exit_time = datetime.datetime.now()
        
        # Calculate profit percentage
        if self.action == "buy":
            profit_pct = (current_price - self.entry_price) / self.entry_price * 100
        else:  # sell
            profit_pct = (self.entry_price - current_price) / self.entry_price * 100
        
        # Use max to ensure per is never negative
        per_value = max(0, profit_pct)
        
        return TradeSignal(
            ticker=self.ticker,
            action=exit_action,
            price=current_price,
            time=exit_time,
            size=self.size,
            sl=self.sl,
            tp=self.tp,
            rationale=f"Position closed: {reason}",
            per=per_value
        )

@dataclass
class PerformanceMetrics:
    ticker: str
    start_date: datetime.datetime
    end_date: datetime.datetime
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    profit_loss: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: Optional[float] = None
    win_rate: Optional[float] = None
    avg_profit_per_trade: Optional[float] = None
    avg_loss_per_trade: Optional[float] = None
    risk_reward_ratio: Optional[float] = None
    
    def calculate_metrics(self, completed_trades: List[Dict[str, Any]]):
        """Calculate performance metrics from completed trades"""
        if not completed_trades:
            return
        
        self.total_trades = len(completed_trades)
        profits = [t['profit'] for t in completed_trades if t['profit'] > 0]
        losses = [t['profit'] for t in completed_trades if t['profit'] < 0]
        
        self.winning_trades = len(profits)
        self.losing_trades = len(losses)
        
        self.profit_loss = sum(profits) + sum(losses)
        
        if self.total_trades > 0:
            self.win_rate = self.winning_trades / self.total_trades
        
        if profits:
            self.avg_profit_per_trade = sum(profits) / len(profits)
        
        if losses:
            self.avg_loss_per_trade = sum(losses) / len(losses)
        
        if self.avg_loss_per_trade and self.avg_profit_per_trade and self.avg_loss_per_trade != 0:
            self.risk_reward_ratio = abs(self.avg_profit_per_trade / self.avg_loss_per_trade)
        
        # Calculate drawdown
        equity_curve = []
        running_total = 0
        for trade in completed_trades:
            running_total += trade['profit']
            equity_curve.append(running_total)
        
        if equity_curve:
            peak = 0
            max_dd = 0
            
            for i, equity in enumerate(equity_curve):
                peak = max(peak, equity)
                drawdown = peak - equity
                max_dd = max(max_dd, drawdown)
            
            self.max_drawdown = max_dd

# Enhanced CoinGecko Provider with Technical Indicators
class CoinGeckoProvider:
    """Enhanced provider for CoinGecko with technical analysis indicators"""
    
    def __init__(self):
        self.base_url = "https://api.coingecko.com/api/v3"
        # Simple ticker mapping
        self.ticker_map = {
            "BTC": "bitcoin",
            "SOL": "solana"
        }
        # Rate limiting
        self.last_request_time = 0
        self.min_request_interval = 12  # seconds between requests for free tier
    
    def _make_request(self, endpoint: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Make a request to the CoinGecko API with rate limiting"""
        # Apply rate limiting
        time_since_last_request = time.time() - self.last_request_time
        if time_since_last_request < self.min_request_interval:
            sleep_time = self.min_request_interval - time_since_last_request
            logger.debug(f"Rate limiting: sleeping for {sleep_time:.2f} seconds")
            time.sleep(sleep_time)
        
        if params is None:
            params = {}
        
        # Make the request
        url = f"{self.base_url}/{endpoint}"
        logger.debug(f"Making request to {url} with params {params}")
        
        try:
            response = requests.get(url, params=params, timeout=30)
            self.last_request_time = time.time()
            
            # Check for rate limiting
            if response.status_code == 429:
                wait_time = int(response.headers.get('retry-after', 60))
                logger.warning(f"Rate limit hit. Waiting for {wait_time} seconds before retrying.")
                time.sleep(wait_time)
                return self._make_request(endpoint, params)
            
            # Handle other errors
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"API request error: {e}")
            # Return empty dict instead of raising to avoid crashing
            return {}
    
    def get_coin_id(self, ticker: str) -> str:
        """Get the CoinGecko ID for a cryptocurrency ticker"""
        ticker = ticker.upper()
        
        # Check the predefined mappings first
        if ticker in self.ticker_map:
            return self.ticker_map[ticker]
        
        # Return the ticker in lowercase as fallback (might work for some coins)
        logger.warning(f"No mapping found for {ticker}, using lowercase ticker as ID")
        return ticker.lower()
    
    def get_market_data(self, ticker: str) -> MarketData:
        """Fetch current market data from CoinGecko"""
        try:
            coin_id = self.get_coin_id(ticker)
            
            # Use the simpler markets endpoint
            market_data = self._make_request('coins/markets', {
                'vs_currency': 'usd',
                'ids': coin_id,
                'price_change_percentage': '24h'
            })
            
            if not market_data or len(market_data) == 0:
                logger.error(f"No market data returned for {ticker}")
                raise ValueError(f"No market data returned for {ticker}")
            
            data = market_data[0]
            logger.debug(f"Received data for {ticker}: {data}")
            
            # Extract data from the response
            current_price = data.get('current_price', 0)
            price_change_24h = data.get('price_change_24h', 0)
            
            # Create base market data
            market_data = MarketData(
                ticker=ticker,
                price=current_price,
                open=current_price - price_change_24h if price_change_24h else current_price,
                high=data.get('high_24h', current_price),
                low=data.get('low_24h', current_price),
                volume=data.get('total_volume', 0),
                timestamp=datetime.datetime.now(),
                market_cap=data.get('market_cap', 0),
                price_change_24h=price_change_24h,
                price_change_percentage_24h=data.get('price_change_percentage_24h', 0)
            )
            
            # Add technical indicators from historical data
            self._add_technical_indicators(market_data, ticker)
            
            return market_data
            
        except Exception as e:
            logger.error(f"Error fetching market data for {ticker}: {e}")
            # Return placeholder data as fallback
            return MarketData(
                ticker=ticker,
                price=0,
                open=0,
                high=0,
                low=0,
                volume=0,
                timestamp=datetime.datetime.now()
            )
    
    def _add_technical_indicators(self, market_data: MarketData, ticker: str):
        """Calculate and add technical indicators to market data"""
        try:
            # Get 30 days of historical data for calculating indicators
            historical = self.get_historical_data(ticker, days=30)
            
            if not historical:
                logger.warning(f"Could not calculate technical indicators for {ticker}: no historical data")
                return
            
            # Convert to DataFrame for technical analysis
            df = pd.DataFrame([{
                'timestamp': h.timestamp,
                'close': h.price,
                'open': h.open,
                'high': h.high,
                'low': h.low,
                'volume': h.volume
            } for h in historical])
            
            # Sort by timestamp
            df = df.sort_values('timestamp')
            
            # Calculate RSI
            rsi = ta.momentum.RSIIndicator(df['close'], window=14)
            market_data.rsi = rsi.rsi().iloc[-1]
            
            # Calculate MACD
            macd = ta.trend.MACD(df['close'])
            market_data.macd = macd.macd().iloc[-1]
            market_data.macd_signal = macd.macd_signal().iloc[-1]
            market_data.macd_histogram = macd.macd_diff().iloc[-1]
            
            # Calculate Bollinger Bands
            bollinger = ta.volatility.BollingerBands(df['close'])
            market_data.bollinger_upper = bollinger.bollinger_hband().iloc[-1]
            market_data.bollinger_middle = bollinger.bollinger_mavg().iloc[-1]
            market_data.bollinger_lower = bollinger.bollinger_lband().iloc[-1]
            
            # Calculate Moving Averages
            market_data.sma_20 = ta.trend.sma_indicator(df['close'], window=20).iloc[-1]
            market_data.sma_50 = ta.trend.sma_indicator(df['close'], window=50).iloc[-1]
            market_data.sma_200 = ta.trend.sma_indicator(df['close'], window=200).iloc[-1]
            market_data.ema_12 = ta.trend.ema_indicator(df['close'], window=12).iloc[-1]
            market_data.ema_26 = ta.trend.ema_indicator(df['close'], window=26).iloc[-1]
            
            logger.debug(f"Added technical indicators for {ticker}")
            
        except Exception as e:
            logger.error(f"Error calculating technical indicators for {ticker}: {e}")
    
    def get_historical_data(self, ticker: str, days: int = 30) -> List[MarketData]:
        """Fetch historical data from CoinGecko with technical indicators"""
        try:
            coin_id = self.get_coin_id(ticker)
            
            params = {
                'vs_currency': 'usd',
                'days': days,
                'interval': 'daily'
            }
            
            data = self._make_request(f'coins/{coin_id}/market_chart', params)
            
            prices = data.get('prices', [])
            volumes = data.get('total_volumes', [])
            
            # Combine the data
            result = []
            for i, (price_data, volume_data) in enumerate(zip(prices, volumes)):
                timestamp = datetime.datetime.fromtimestamp(price_data[0] / 1000)
                price = price_data[1]
                
                result.append(MarketData(
                    ticker=ticker,
                    price=price,
                    open=price,  # Simplification
                    high=price,  # Simplification
                    low=price,   # Simplification
                    volume=volume_data[1],
                    timestamp=timestamp
                ))
            
            return result
        except Exception as e:
            logger.error(f"Error fetching historical data for {ticker}: {e}")
            return []

# Enhanced CryptoPanic Provider with Keyword Extraction
class CryptoPanicProvider:
    """Enhanced provider for crypto news from CryptoPanic with sentiment analysis"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://cryptopanic.com/api/v1/posts/"
        # Keywords to track
        self.important_keywords = [
            "regulation", "sec", "lawsuit", "hack", "security", "breach", 
            "partnership", "adoption", "launch", "update", "upgrade", 
            "hardfork", "fork", "listing", "delisting", "bankruptcy",
            "whale", "pump", "dump", "scam", "fraud", "investigation"
        ]
    
    def get_news(self, ticker: str, limit: int = 10) -> List[NewsItem]:
        """Fetch crypto news from CryptoPanic API with enhanced analysis"""
        try:
            params = {
                'auth_token': self.api_key,
                'currencies': ticker,
                'public': 'true',
                'limit': limit
            }
            
            logger.debug(f"Fetching news for {ticker}")
            response = requests.get(self.base_url, params=params)
            
            if response.status_code != 200:
                logger.error(f"CryptoPanic API error: {response.status_code}")
                return []
            
            data = response.json()
            
            news_items = []
            for item in data.get('results', []):
                # Simple sentiment from votes (positive, negative or neutral)
                votes = item.get('votes', {})
                positive = votes.get('positive', 0)
                negative = votes.get('negative', 0)
                
                sentiment = "neutral"
                sentiment_score = 0.0
                
                if positive > negative:
                    sentiment = "positive"
                    sentiment_score = min(0.5 + (positive / (positive + negative + 1)) * 0.5, 1.0)
                elif negative > positive:
                    sentiment = "negative"
                    sentiment_score = max(-0.5 - (negative / (positive + negative + 1)) * 0.5, -1.0)
                
                # Parse timestamp if available
                timestamp = None
                if item.get('published_at'):
                    try:
                        timestamp = datetime.datetime.fromisoformat(item['published_at'].replace('Z', '+00:00'))
                    except:
                        timestamp = datetime.datetime.now()
                
                # Extract title and text
                title = item.get('title', '')
                
                # Extract mentioned tickers
                tickers_mentioned = []
                currencies = item.get('currencies', [])
                for currency in currencies:
                    currency_code = currency.get('code', '')
                    if currency_code:
                        tickers_mentioned.append(currency_code)
                
                # Extract important keywords
                keywords = []
                text = title.lower()
                for keyword in self.important_keywords:
                    if keyword in text:
                        keywords.append(keyword)
                
                # Create news item
                news_items.append(NewsItem(
                    title=title,
                    summary=title,  # Use title as summary for simplicity
                    source=item.get('source', {}).get('title', 'CryptoPanic'),
                    url=item.get('url', ''),
                    sentiment=sentiment,
                    sentiment_score=sentiment_score,
                    timestamp=timestamp,
                    tickers_mentioned=tickers_mentioned,
                    keywords=keywords
                ))
            
            return news_items
            
        except Exception as e:
            logger.error(f"Error fetching news for {ticker}: {e}")
            return []

# New OnChain Data Provider
class OnChainDataProvider:
    """Provider for on-chain data using Web3"""
    
    def __init__(self, config: Config):
        self.config = config
        self.web3_connections = {}
        self.whale_wallets = {
            "BTC": [
                "1P5ZEDWTKTFGxQjZphgWPQUpe554WKDfHQ",  # Binance
                "3Kzh9qAqVWQhEsfQz7zEQL1EuSx5tyNLNS",  # Bitfinex
                "bc1qgdjqv0av3q56jvd82tkdjpy7gdp9ut8tlqmgrpmv24sq90ecnvqqjwvw97"  # Largest BTC wallet
            ],
            "ETH": [
                "0xDA9dfA130Df4dE4673b89022EE50ff26f6EA73Cf",  # Binance
                "0x28C6c06298d514Db089934071355E5743bf21d60",  # Binance 2
                "0xA929022c9107643515F5c777cE9a910F0D1e490C"  # Major wallet
            ],
            "SOL": [
                "3LKy8xNEWAzNtX9YcPj3pTxce5Wxh6Lq8mzuMRz7zxVM",  # Major wallet
                "8rUvvjhJHMJrfMwGC4QX9aDL1T8maYvJ5Dq4qxcXBjK6",  # Major wallet
                "7vYe1Dzuod7BgwVCFVFMGHWtpMvXCi5wAtUwR3422qZ4"  # Exchange wallet
            ]
        }
        
        # Initialize Web3 connections
        for network, provider_url in self.config.web3_providers.items():
            try:
                self.web3_connections[network] = Web3(Web3.HTTPProvider(provider_url))
                logger.info(f"Connected to {network} blockchain")
            except Exception as e:
                logger.error(f"Failed to connect to {network} blockchain: {e}")
    
    def _get_network_for_ticker(self, ticker: str) -> Optional[str]:
        """Map ticker to appropriate blockchain network"""
        ticker = ticker.upper()
        if ticker == "BTC":
            return "bitcoin"
        elif ticker in ["ETH", "LINK", "UNI", "AAVE", "MKR"]:
            return "ethereum"
        elif ticker in ["BNB", "CAKE"]:
            return "bsc"
        elif ticker in ["SOL"]:
            return "solana"
        elif ticker in ["MATIC"]:
            return "polygon"
        else:
            return None
    
    def get_onchain_data(self, ticker: str) -> OnChainData:
        """Get on-chain data for a cryptocurrency"""
        network = self._get_network_for_ticker(ticker)
        
        # Create base OnChainData object
        onchain_data = OnChainData(
            ticker=ticker,
            network=network if network else "unknown",
            timestamp=datetime.datetime.now()
        )
        
        # Placeholder for actual blockchain data
        # In a production system, this would connect to a full blockchain node
        # or use specialized APIs like Alchemy, Infura, or TheGraph
        
        # Simulate some on-chain data for demo purposes
        if ticker in self.whale_wallets:
            # Simulate whale wallet movements
            for wallet in self.whale_wallets[ticker]:
                change = np.random.normal(0, 100000)  # Random change with normal distribution
                if abs(change) > 50000:  # Only track significant changes
                    onchain_data.whale_wallet_changes[wallet] = change
            
            # Simulate large transactions
            num_large_txs = np.random.randint(0, 5)  # 0-5 large transactions
            for _ in range(num_large_txs):
                tx_value = np.random.uniform(500000, 5000000)  # $500K to $5M
                tx_type = np.random.choice(["deposit", "withdrawal", "transfer"])
                onchain_data.large_transactions.append({
                    "value": tx_value,
                    "type": tx_type,
                    "timestamp": datetime.datetime.now() - datetime.timedelta(hours=np.random.randint(0, 24))
                })
        
        # Simulate basic metrics
        onchain_data.active_addresses_24h = np.random.randint(50000, 500000)
        onchain_data.transaction_volume_24h = np.random.uniform(10000000, 1000000000)
        onchain_data.avg_transaction_value = onchain_data.transaction_volume_24h / (onchain_data.active_addresses_24h * 2)  # Rough estimate
        
        # Exchange flows
        onchain_data.exchange_inflows = np.random.uniform(1000000, 100000000)
        onchain_data.exchange_outflows = np.random.uniform(1000000, 100000000)
        
        # DEX volume (for relevant chains)
        if network in ["ethereum", "bsc", "polygon", "solana"]:
            onchain_data.dex_volume = np.random.uniform(5000000, 500000000)
        
        logger.debug(f"Generated on-chain data for {ticker}")
        return onchain_data

# Enhanced Market Analyst with Technical Analysis
class MarketAnalyst:
    """Enhanced Market Analyst with technical indicators"""
    
    def __init__(self, config: Config):
        self.config = config
        self.client = genai.Client(api_key=config.gemini_api_key)
    
    def analyze(self, ticker: str, market_data: MarketData, historical_data: List[MarketData]) -> str:
        """Analyze market data with technical indicators and provide insights"""
        if not market_data or market_data.price <= 0:
            return "Insufficient data for analysis"
        
        # Create an enhanced prompt with technical indicators
        
        prompt = f"""
        You are an expert cryptocurrency market analyst with deep knowledge of technical analysis. Analyze this comprehensive market data for {ticker}:

        Current price: ${market_data.price:.2f}
        24h High: ${market_data.high:.2f}
        24h Low: ${market_data.low:.2f}
        24h Change: {market_data.price_change_percentage_24h:.2f}%
        24h Volume: ${market_data.volume:.2f}
        Market Cap: ${market_data.market_cap:.2f}

        Technical Indicators:
        RSI (14): {f"{market_data.rsi:.2f}" if market_data.rsi is not None and not pd.isna(market_data.rsi) else "N/A"}
        MACD: {f"{market_data.macd:.4f}" if market_data.macd is not None and not pd.isna(market_data.macd) else "N/A"}
        MACD Signal: {f"{market_data.macd_signal:.4f}" if market_data.macd_signal is not None and not pd.isna(market_data.macd_signal) else "N/A"}
        MACD Histogram: {f"{market_data.macd_histogram:.4f}" if market_data.macd_histogram is not None and not pd.isna(market_data.macd_histogram) else "N/A"}

        Bollinger Bands:
          - Upper: ${f"{market_data.bollinger_upper:.2f}" if not pd.isna(market_data.bollinger_upper) else "N/A"}
          - Middle: ${f"{market_data.bollinger_middle:.2f}" if not pd.isna(market_data.bollinger_middle) else "N/A"}
          - Lower: ${f"{market_data.bollinger_lower:.2f}" if not pd.isna(market_data.bollinger_lower) else "N/A"}
        Moving Averages:
          - SMA 20: ${f"{market_data.sma_20:.2f}" if not pd.isna(market_data.sma_20) else "N/A"}
          - SMA 50: ${f"{market_data.sma_50:.2f}" if not pd.isna(market_data.sma_50) else "N/A"}
          - SMA 200: ${f"{market_data.sma_200:.2f}" if not pd.isna(market_data.sma_200) else "N/A"}
          - EMA 12: ${f"{market_data.ema_12:.2f}" if not pd.isna(market_data.ema_12) else "N/A"}
          - EMA 26: ${f"{market_data.ema_26:.2f}" if not pd.isna(market_data.ema_26) else "N/A"}
        
        Historical price data (last {len(historical_data)} days):
        {self._format_historical_data(historical_data)}
        
        Provide a comprehensive market analysis focusing on:
        1. Overall trend direction (bullish, bearish, or neutral)
        2. Support/resistance levels (identify key price levels)
        3. Technical indicator analysis (RSI, MACD, Bollinger Bands, MAs)
        4. Chart patterns or formations (if any)
        5. Volume analysis
        6. Short-term price prediction (1-7 days)
        7. Medium-term outlook (1-4 weeks)
        
        Keep your analysis structured but comprehensive. Focus on data-driven insights, not general market sentiment.
        """
        
        try:
            # Create a chat and send the prompt
            chat = self.client.chats.create(model=self.config.model_name)
            response = chat.send_message(prompt)
            return response.text.strip()
        except Exception as e:
            logger.error(f"Error generating market analysis: {e}")
            return f"Error generating analysis: {str(e)}"
    
    def _format_historical_data(self, data: List[MarketData]) -> str:
        """Format historical data for the prompt"""
        result = []
        
        # Only use the last 7 data points to keep the prompt manageable
        sample_data = data[-7:] if len(data) > 7 else data
        
        for entry in sample_data:
            result.append(f"{entry.timestamp.strftime('%Y-%m-%d')}: Price: ${entry.price:.2f}, Volume: ${entry.volume:.2f}")
        
        return "\n".join(result)

# Enhanced News Analyst with Topic Extraction
class NewsAnalyst:
    """Enhanced News Analyst with topic extraction"""
    
    def __init__(self, config: Config):
        self.config = config
        self.client = genai.Client(api_key=config.gemini_api_key)
    
    def analyze(self, ticker: str, news_items: List[NewsItem]) -> str:
        """Analyze news with topic extraction and provide insights"""
        if not news_items:
            return "No news items available for analysis"
        
        # Extract keywords and sentiment from news items
        keywords = set()
        sentiment_scores = []
        for item in news_items:
            keywords.update(item.keywords)
            if item.sentiment_score is not None:
                sentiment_scores.append(item.sentiment_score)
        
        # Calculate average sentiment
        avg_sentiment = 0
        if sentiment_scores:
            avg_sentiment = sum(sentiment_scores) / len(sentiment_scores)
        
        # Create enhanced prompt for news analysis
        prompt = f"""
        You are an expert cryptocurrency news analyst. Analyze these news items for {ticker} with particular attention to keywords and sentiment:
        
        {self._format_news_items(news_items)}
        
        Important keywords detected: {', '.join(keywords) if keywords else 'None'}
        Average sentiment score: {avg_sentiment:.2f} (-1.0 is very negative, +1.0 is very positive)
        
        Based on these news items:
        1. What is the overall news sentiment (bullish, bearish, or neutral)?
        2. Identify any major events or developments and explain their significance for {ticker}
        3. Analyze recurring themes or topics in the news
        4. Are there any regulatory or legal concerns mentioned?
        5. How might institutional or whale investors react to this news?
        6. How might this news affect market behavior in the short term (1-7 days)?
        7. Are there any contradicting news items that could create market confusion?
        
        Provide a detailed news analysis that synthesizes all this information.
        """
        
        try:
            # Create a chat and send the prompt
            chat = self.client.chats.create(model=self.config.model_name)
            response = chat.send_message(prompt)
            return response.text.strip()
        except Exception as e:
            logger.error(f"Error generating news analysis: {e}")
            return f"Error generating analysis: {str(e)}"
    
    def _format_news_items(self, news_items: List[NewsItem]) -> str:
        """Format news items for the prompt"""
        result = []
        
        for i, item in enumerate(news_items[:8]):  # Include up to 8 news items
            timestamp_str = item.timestamp.strftime('%Y-%m-%d') if item.timestamp else 'N/A'
            keywords_str = ', '.join(item.keywords) if item.keywords else 'None'
            tickers_str = ', '.join(item.tickers_mentioned) if item.tickers_mentioned else 'None'
            
            # Format sentiment score properly
            if item.sentiment_score is not None:
                sentiment_score_str = f"{item.sentiment_score:.2f}"
            else:
                sentiment_score_str = "0.0"
            
            result.append(f"""
            {i+1}. Title: {item.title}
            Source: {item.source}
            Date: {timestamp_str}
            Sentiment: {item.sentiment} (score: {sentiment_score_str})
            Keywords: {keywords_str}
            Tickers mentioned: {tickers_str}
            """)
        
        return "\n".join(result)

# New OnChain Analyst
class OnChainAnalyst:
    """Analyst for on-chain data using Gemini"""
    
    def __init__(self, config: Config):
        self.config = config
        self.client = genai.Client(api_key=config.gemini_api_key)
    
    def _safe_format(self, value, format_spec=",.2f", default=0):
        """Safely format a value that might be None"""
        if value is None:
            return f"${default:{format_spec}}"
        return f"${value:{format_spec}}"
    
    def analyze(self, ticker: str, onchain_data: OnChainData) -> str:
        """Analyze on-chain data and provide insights"""
        if not onchain_data:
            return "Insufficient on-chain data for analysis"
        
        # Format large transactions
        large_txs = []
        for tx in onchain_data.large_transactions:
            value = tx.get('value', 0)
            tx_type = tx.get('type', 'unknown')
            timestamp = tx.get('timestamp', datetime.datetime.now())
            large_txs.append(f"- ${value:.2f} {tx_type} at {timestamp.strftime('%Y-%m-%d %H:%M')}")
        
        large_txs_str = "\n".join(large_txs) if large_txs else "None detected"
        
        # Format whale wallet changes
        whale_changes = []
        for wallet, change in onchain_data.whale_wallet_changes.items():
            if wallet and change is not None:
                direction = "accumulated" if change > 0 else "distributed"
                # Make sure wallet is long enough to slice
                if len(wallet) > 14:
                    wallet_display = f"{wallet[:8]}...{wallet[-6:]}"
                else:
                    wallet_display = wallet
                whale_changes.append(f"- Wallet {wallet_display}: {direction} ${abs(change):.2f}")
        
        whale_changes_str = "\n".join(whale_changes) if whale_changes else "No significant movements"
        
        # Safely format values
        active_addresses = f"{onchain_data.active_addresses_24h:,}" if onchain_data.active_addresses_24h is not None else "N/A"
        tx_volume = self._safe_format(onchain_data.transaction_volume_24h)
        avg_tx_value = self._safe_format(onchain_data.avg_transaction_value)
        exchange_inflows = self._safe_format(onchain_data.exchange_inflows)
        exchange_outflows = self._safe_format(onchain_data.exchange_outflows)
        
        # Calculate net flow safely
        if onchain_data.exchange_outflows is not None and onchain_data.exchange_inflows is not None:
            net_flow = self._safe_format(onchain_data.exchange_outflows - onchain_data.exchange_inflows)
        else:
            net_flow = "$0.00"
        
        dex_volume = self._safe_format(onchain_data.dex_volume)
        
        # Create prompt for on-chain analysis
        prompt = f"""
        You are an expert cryptocurrency on-chain analyst. Analyze this on-chain data for {ticker} on the {onchain_data.network} network:
        
        Transaction Metrics:
        - Active addresses (24h): {active_addresses}
        - Transaction volume (24h): {tx_volume}
        - Average transaction value: {avg_tx_value}
        
        Exchange Flow:
        - Exchange inflows: {exchange_inflows}
        - Exchange outflows: {exchange_outflows}
        - Net flow: {net_flow}
        
        DEX Volume: {dex_volume}
        
        Large Transactions:
        {large_txs_str}
        
        Whale Wallet Activity:
        {whale_changes_str}
        
        Based on this on-chain data:
        1. What does the overall on-chain activity suggest about {ticker}?
        2. Analyze the exchange flows and their implications for price
        3. What conclusions can be drawn from whale wallet activity?
        4. How does the on-chain data compare to general market sentiment?
        5. Are there any warning signs or positive signals in the data?
        6. What might this on-chain data suggest for short and medium-term price action?
        
        Provide a detailed on-chain analysis focusing on actionable insights.
        """
        
        try:
            # Create a chat and send the prompt
            chat = self.client.chats.create(model=self.config.model_name)
            response = chat.send_message(prompt)
            return response.text.strip()
        except Exception as e:
            logger.error(f"Error generating on-chain analysis: {e}")
            return f"Error generating on-chain analysis: {str(e)}"

# Enhanced Position Manager with improved tracking
class PositionManager:
    """Manages open positions and handles take profit/stop loss conditions"""
    
    def __init__(self, config: Config):
        self.config = config
        self.open_positions: Dict[str, List[Position]] = {}
        self.closed_positions: List[Position] = []
        self.last_check_time = time.time()
        self.max_positions_per_ticker = 1  # IMPORTANT: Limit to 1 position per ticker
        
        # Create position data directory
        os.makedirs("data/positions", exist_ok=True)
        
        # Load existing positions
        self._load_positions()
    
    def _load_positions(self):
        """Load positions from disk"""
        try:
            if os.path.exists("data/positions/open_positions.pkl"):
                with open("data/positions/open_positions.pkl", "rb") as f:
                    self.open_positions = pickle.load(f)
                    logger.info(f"Loaded open positions for {len(self.open_positions)} tickers")
            
            if os.path.exists("data/positions/closed_positions.pkl"):
                with open("data/positions/closed_positions.pkl", "rb") as f:
                    self.closed_positions = pickle.load(f)
                    logger.info(f"Loaded {len(self.closed_positions)} closed positions")
        except Exception as e:
            logger.error(f"Error loading positions: {e}")
            self.open_positions = {}
            self.closed_positions = []
    
    def _save_positions(self):
        """Save positions to disk"""
        try:
            with open("data/positions/open_positions.pkl", "wb") as f:
                pickle.dump(self.open_positions, f)
            
            with open("data/positions/closed_positions.pkl", "wb") as f:
                pickle.dump(self.closed_positions, f)
            
            logger.info("Saved positions")
        except Exception as e:
            logger.error(f"Error saving positions: {e}")
    
    def get_position_count(self, ticker: str) -> int:
        """Get number of open positions for a ticker"""
        return len(self.open_positions.get(ticker, []))
    
    def add_position(self, signal: TradeSignal) -> Optional[Position]:
        """Add a new position from a trade signal"""
        # Only add buy or sell signals, not exit or hold
        if signal.action not in ["buy", "sell"]:
            logger.warning(f"Cannot add position for action {signal.action}")
            return None
        
        # Check if we already have the maximum positions for this ticker
        if self.get_position_count(signal.ticker) >= self.max_positions_per_ticker:
            logger.warning(f"Maximum positions ({self.max_positions_per_ticker}) already open for {signal.ticker}, skipping")
            return None
        
        # Create position with 3 pip fixed SL/TP
        position = Position(
            ticker=signal.ticker,
            action=signal.action,
            entry_price=signal.price,
            entry_time=signal.time,
            size=signal.size or 10.0,  # Default to 10% if not specified
            sl=signal.sl or (signal.price - 3 if signal.action == "buy" else signal.price + 3),  # 3 pips SL
            tp=signal.tp or (signal.price + 3 if signal.action == "buy" else signal.price - 3)   # 3 pips TP
        )
        
        # Add to open positions
        if signal.ticker not in self.open_positions:
            self.open_positions[signal.ticker] = []
        
        self.open_positions[signal.ticker].append(position)
        logger.info(f"Added new {signal.action} position for {signal.ticker} at {signal.price} with TP: {position.tp}, SL: {position.sl}")
        
        # Save positions
        self._save_positions()
        
        return position
    
    def close_position(self, position: Position, current_price: float, reason: str) -> Position:
        """Close an open position"""
        # Update position
        position.exit_price = current_price
        position.exit_time = datetime.datetime.now()
        position.status = reason
        
        # Remove from open positions
        if position.ticker in self.open_positions:
            self.open_positions[position.ticker] = [p for p in self.open_positions[position.ticker] if p != position]
            
            # Remove ticker key if no more positions
            if not self.open_positions[position.ticker]:
                del self.open_positions[position.ticker]
        
        # Add to closed positions
        self.closed_positions.append(position)
        
        logger.info(f"Closed {position.action} position for {position.ticker}: {reason}")
        
        # Save positions
        self._save_positions()
        
        return position
    
    def check_positions(self, ticker: str, current_price: float) -> List[TradeSignal]:
        """Check open positions for take profit/stop loss conditions"""
        if ticker not in self.open_positions:
            return []
        
        exit_signals = []
        
        # Check each position for this ticker
        for position in self.open_positions.get(ticker, [])[:]:  # Create a copy to avoid modifying during iteration
            if position.is_take_profit_hit(current_price):
                # Close position at take profit
                self.close_position(position, current_price, "closed_tp")
                exit_signal = position.to_exit_signal(current_price, "Take Profit hit")
                exit_signals.append(exit_signal)
                logger.info(f"Take profit hit for {ticker} at {current_price}")
                
            elif position.is_stop_loss_hit(current_price):
                # Close position at stop loss
                self.close_position(position, current_price, "closed_sl")
                exit_signal = position.to_exit_signal(current_price, "Stop Loss hit")
                exit_signals.append(exit_signal)
                logger.info(f"Stop loss hit for {ticker} at {current_price}")
        
        return exit_signals
    
    def get_positions_for_ticker(self, ticker: str) -> List[Position]:
        """Get all open positions for a ticker"""
        return self.open_positions.get(ticker, [])
    
    def has_open_positions(self, ticker: str) -> bool:
        """Check if there are open positions for a ticker"""
        return ticker in self.open_positions and len(self.open_positions[ticker]) > 0
    
    def should_check_positions(self) -> bool:
        """Check if it's time to check positions"""
        current_time = time.time()
        elapsed = current_time - self.last_check_time
        
        if elapsed >= self.config.position_check_interval:  # Changed to check more frequently
            self.last_check_time = current_time
            return True
        
        return False

# Reflection Agent
class ReflectionAgent:
    """Agent for evaluating past performance and learning"""
    
    def __init__(self, config: Config):
        self.config = config
        self.client = genai.Client(api_key=config.gemini_api_key)
        self.completed_trades = []
        self.signals_history = {}
        self.last_reflection_time = time.time()
        
        # Create directories for storing reflection data
        os.makedirs("data/performance", exist_ok=True)
        
        # Load any existing trade history
        self._load_history()
    
    def _load_history(self):
        """Load trade history from disk"""
        try:
            if os.path.exists("data/performance/completed_trades.pkl"):
                with open("data/performance/completed_trades.pkl", "rb") as f:
                    self.completed_trades = pickle.load(f)
                    logger.info(f"Loaded {len(self.completed_trades)} completed trades")
            
            if os.path.exists("data/performance/signals_history.pkl"):
                with open("data/performance/signals_history.pkl", "rb") as f:
                    self.signals_history = pickle.load(f)
                    logger.info(f"Loaded signals history for {len(self.signals_history)} tickers")
        except Exception as e:
            logger.error(f"Error loading trade history: {e}")
    
    def _save_history(self):
        """Save trade history to disk"""
        try:
            with open("data/performance/completed_trades.pkl", "wb") as f:
                pickle.dump(self.completed_trades, f)
            
            with open("data/performance/signals_history.pkl", "wb") as f:
                pickle.dump(self.signals_history, f)
            
            logger.info("Saved trade history")
        except Exception as e:
            logger.error(f"Error saving trade history: {e}")
    
    def add_signal(self, signal: TradeSignal):
        """Add a new signal to history"""
        if signal.ticker not in self.signals_history:
            self.signals_history[signal.ticker] = []
        
        # Add the signal
        self.signals_history[signal.ticker].append({
            "signal": signal,
            "timestamp": datetime.datetime.now(),
            "evaluated": False,
            "outcome": None
        })
        
        # Save history
        self._save_history()
    
    def add_trade_outcome(self, ticker: str, entry_time: datetime.datetime, 
                          exit_time: datetime.datetime, entry_price: float,
                          exit_price: float, action: str, size: float):
        """Add a completed trade outcome"""
        # Calculate profit/loss
        if action == "buy":
            profit = (exit_price - entry_price) / entry_price * size
        else:  # sell
            profit = (entry_price - exit_price) / entry_price * size
        
        # Create trade record
        trade = {
            "ticker": ticker,
            "entry_time": entry_time,
            "exit_time": exit_time,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "action": action,
            "size": size,
            "profit": profit,
            "profit_percentage": profit * 100 / size
        }
        
        # Add to completed trades
        self.completed_trades.append(trade)
        
        # Update signal history
        if ticker in self.signals_history:
            # Find the matching entry signal
            for signal_data in self.signals_history[ticker]:
                if not signal_data["evaluated"] and signal_data["signal"].action == action:
                    # Calculate time difference to make sure it's the right signal
                    time_diff = abs((signal_data["timestamp"] - entry_time).total_seconds())
                    if time_diff < 3600:  # Within an hour
                        signal_data["evaluated"] = True
                        signal_data["outcome"] = trade
                        break
        
        # Save history
        self._save_history()
        
        return trade
    
    def simulate_outcomes(self, ticker: str, current_price: float):
        """Simulate outcomes for signals that haven't been evaluated yet"""
        if ticker not in self.signals_history:
            return
        
        # Get current time
        now = datetime.datetime.now()
        
        # Check all signals for this ticker
        for signal_data in self.signals_history[ticker]:
            # Skip already evaluated signals
            if signal_data["evaluated"]:
                continue
            
            signal = signal_data["signal"]
            
            # Check if signal is at least 24 hours old
            age = (now - signal_data["timestamp"]).total_seconds() / 3600
            if age >= 24:
                # Simulate outcome
                if signal.action == "buy":
                    # For buy signals, check if price hit take profit or stop loss
                    if current_price >= signal.tp:
                        # Take profit hit
                        self.add_trade_outcome(
                            ticker=ticker,
                            entry_time=signal_data["timestamp"],
                            exit_time=now,
                            entry_price=signal.price,
                            exit_price=signal.tp,
                            action=signal.action,
                            size=signal.size
                        )
                    elif current_price <= signal.sl:
                        # Stop loss hit
                        self.add_trade_outcome(
                            ticker=ticker,
                            entry_time=signal_data["timestamp"],
                            exit_time=now,
                            entry_price=signal.price,
                            exit_price=signal.sl,
                            action=signal.action,
                            size=signal.size
                        )
                elif signal.action == "sell":
                    # For sell signals, check if price hit take profit or stop loss
                    if current_price <= signal.tp:
                        # Take profit hit
                        self.add_trade_outcome(
                            ticker=ticker,
                            entry_time=signal_data["timestamp"],
                            exit_time=now,
                            entry_price=signal.price,
                            exit_price=signal.tp,
                            action=signal.action,
                            size=signal.size
                        )
                    elif current_price >= signal.sl:
                        # Stop loss hit
                        self.add_trade_outcome(
                            ticker=ticker,
                            entry_time=signal_data["timestamp"],
                            exit_time=now,
                            entry_price=signal.price,
                            exit_price=signal.sl,
                            action=signal.action,
                            size=signal.size
                        )
    
    def analyze_performance(self, ticker: str = None) -> str:
        """Analyze trading performance overall or for a specific ticker"""
        # Filter trades if ticker is specified
        trades = self.completed_trades
        if ticker:
            trades = [t for t in trades if t["ticker"] == ticker]
        
        if not trades:
            return "Insufficient trade data for analysis"
        
        # Calculate performance metrics
        start_date = min(t["entry_time"] for t in trades)
        end_date = max(t["exit_time"] for t in trades)
        
        metrics = PerformanceMetrics(
            ticker=ticker if ticker else "ALL",
            start_date=start_date,
            end_date=end_date
        )
        
        metrics.calculate_metrics(trades)
        
        # Create an analysis prompt
        prompt = f"""
        You are a cryptocurrency trading performance analyst. Analyze these trading performance metrics:

        Time Period: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}
        Asset: {"All cryptocurrencies" if not ticker else ticker}

        Performance Metrics:
        - Total Trades: {metrics.total_trades}
        - Winning Trades: {metrics.winning_trades} ({f"{metrics.win_rate*100:.1f}%" if metrics.win_rate else "0%"})
        - Losing Trades: {metrics.losing_trades} ({f"{(1-metrics.win_rate)*100:.1f}%" if metrics.win_rate is not None else "0%"})
        - Total Profit/Loss: {metrics.profit_loss:.2f}%
        - Maximum Drawdown: {metrics.max_drawdown:.2f}%
        - Average Profit per Winning Trade: {metrics.avg_profit_per_trade:.2f}% (if available)
        - Average Loss per Losing Trade: {metrics.avg_loss_per_trade:.2f}% (if available)
        - Risk-Reward Ratio: {metrics.risk_reward_ratio:.2f if metrics.risk_reward_ratio else "N/A"}
        
        Trade Breakdown:
        {self._format_trades(trades[:5])}
        
        Based on this performance data:
        1. Evaluate the overall trading strategy effectiveness
        2. Identify strengths and weaknesses in the trading approach
        3. Analyze patterns in winning vs losing trades
        4. Suggest specific improvements to increase win rate and profit
        5. Identify any risk management issues
        6. Provide actionable recommendations for future trading
        
        Provide a comprehensive performance analysis with actionable insights.
        """
        
        try:
            # Create a chat and send the prompt
            chat = self.client.chats.create(model=self.config.model_name)
            response = chat.send_message(prompt)
            return response.text.strip()
        except Exception as e:
            logger.error(f"Error generating performance analysis: {e}")
            return f"Error generating performance analysis: {str(e)}"
    
    def _format_trades(self, trades: List[Dict[str, Any]]) -> str:
        """Format trades for the prompt"""
        result = []
        
        for i, trade in enumerate(trades):
            result.append(f"""
            {i+1}. {trade['ticker']} {trade['action'].upper()}
               Entry: ${trade['entry_price']:.2f} at {trade['entry_time'].strftime('%Y-%m-%d %H:%M')}
               Exit: ${trade['exit_price']:.2f} at {trade['exit_time'].strftime('%Y-%m-%d %H:%M')}
               Size: {trade['size']:.1f}%
               P/L: {trade['profit_percentage']:.2f}%
            """)
        
        return "\n".join(result)
    
    def should_run_reflection(self) -> bool:
        """Check if it's time to run reflection"""
        current_time = time.time()
        elapsed = current_time - self.last_reflection_time
        
        if elapsed >= self.config.performance_evaluation_interval:
            self.last_reflection_time = current_time
            return True
        
        return False
    
    def run_reflection(self):
        """Run the reflection analysis"""
        if self.should_run_reflection():
            logger.info("Running performance reflection...")
            print("Running performance reflection...")
            
            # Analyze overall performance
            overall_analysis = self.analyze_performance()
            logger.info(f"Performance reflection: {overall_analysis[:100]}...")
            print(f"Performance Analysis: {overall_analysis[:100]}...")

# Enhanced Trading Advisor
class TradingAdvisor:
    """Enhanced Trading Advisor using Gemini"""
    
    def __init__(self, config: Config):
        self.config = config
        self.client = genai.Client(api_key=config.gemini_api_key)
    
    def get_signal(self, ticker: str, price: float, market_analysis: str, 
                   news_analysis: str, onchain_analysis: str, has_open_position: bool) -> Optional[TradeSignal]:
        """Generate an advanced trading signal based on multiple analyses"""
        
        # If there's already an open position, return a hold signal
        if has_open_position:
            logger.info(f"Already have an open position for {ticker}, generating HOLD signal")
            return TradeSignal(
                ticker=ticker,
                action="hold",
                price=price,
                time=datetime.datetime.now(),
                rationale="Already have an open position for this ticker"
            )
        
        # Create a comprehensive prompt for trading decisions
        prompt = f"""
        You are an expert cryptocurrency trading advisor. Based on the following comprehensive information for {ticker},
        decide whether to BUY, SELL, or HOLD.
        
        Current price: ${price:.2f}
        
        MARKET ANALYSIS:
        {market_analysis}
        
        NEWS ANALYSIS:
        {news_analysis}
        
        ON-CHAIN ANALYSIS:
        {onchain_analysis}
        
        Considering all these factors - technical indicators, news sentiment, and on-chain activity - provide your most informed trading decision.
        
        Your response must be in this exact format:
        
        DECISION: [BUY/SELL/HOLD]
        CONFIDENCE: [0.0 to 1.0]
        TIME_HORIZON: [SHORT/MEDIUM/LONG]
        RISK_LEVEL: [LOW/MEDIUM/HIGH]
        REASON: [Detailed explanation with key factors]
        STOP_LOSS: [Price level for stop loss]
        TAKE_PROFIT: [Price level for take profit]
        SIZE: [Position size as percentage, 1-10%]
        MARKET_SIGNAL: [Bullish/Bearish/Neutral]
        NEWS_SIGNAL: [Bullish/Bearish/Neutral]
        ONCHAIN_SIGNAL: [Bullish/Bearish/Neutral]
        
        Make your decision now.
        """
        
        try:
            # Create a chat and send the prompt
            chat = self.client.chats.create(model=self.config.model_name)
            response = chat.send_message(prompt)
            
            # Parse the response
            return self._parse_signal(response.text, ticker, price)
        except Exception as e:
            logger.error(f"Error generating trading signal: {e}")
            return None
    
    def _parse_signal(self, response_text: str, ticker: str, current_price: float) -> Optional[TradeSignal]:
        """Parse the AI response into a trading signal with enhanced attributes"""
        lines = response_text.strip().split('\n')
        data = {}
        
        # Extract data from response
        for line in lines:
            if ':' in line:
                key, value = line.split(':', 1)
                data[key.strip().upper()] = value.strip()
        
        # Get the decision
        decision = data.get('DECISION', 'HOLD').upper()
        
        # Convert decision to action
        action = decision.lower() if decision in ['BUY', 'SELL'] else 'hold'
        
        # Extract other parameters
        try:
            confidence = float(data.get('CONFIDENCE', '0.8'))
        except:
            confidence = 0.8
            
        reason = data.get('REASON', 'No rationale provided')
        time_horizon = data.get('TIME_HORIZON', 'MEDIUM').lower()
        risk_level = data.get('RISK_LEVEL', 'MEDIUM').lower()
        
        # Source signals
        source_signals = {
            'market': data.get('MARKET_SIGNAL', 'Neutral'),
            'news': data.get('NEWS_SIGNAL', 'Neutral'),
            'onchain': data.get('ONCHAIN_SIGNAL', 'Neutral')
        }
        
        # Parse stop loss with fixed 3 pip distance if not specified
        try:
            sl_str = data.get('STOP_LOSS', '0').replace('$', '')
            sl = float(sl_str)
        except:
            # Set SL to fixed 3 pips away
            sl = current_price - 3 if action == 'buy' else current_price + 3
        
        # Parse take profit with fixed 3 pip distance if not specified
        try:
            tp_str = data.get('TAKE_PROFIT', '0').replace('$', '')
            tp = float(tp_str)
        except:
            # Set TP to fixed 3 pips away
            tp = current_price + 3 if action == 'buy' else current_price - 3
        
        # Parse size
        try:
            size_str = data.get('SIZE', '10').replace('%', '')
            size = float(size_str)
            # Cap at 20%
            size = min(size, 20.0)
        except:
            size = 10.0
        
        # Create and return signal
        return TradeSignal(
            ticker=ticker,
            action=action,
            price=current_price,
            time=datetime.datetime.now(),
            confidence_score=confidence,
            size=size,
            sl=sl,
            tp=tp,
            rationale=reason,
            expected_holding_period=time_horizon,
            risk_assessment=risk_level,
            source_signals=source_signals
        )

# Enhanced CryptoMCP Class
class CryptoMCP:
    """Enhanced Multi-agent Crypto Trading System"""
    
    def __init__(self, config_file: str):
        print(f"Initializing Enhanced CryptoMCP with config file: {config_file}")
        # Load configuration
        self.config = Config.from_file(config_file)
        print(f"Loaded configuration for cryptocurrencies: {self.config.cryptocurrencies}")
        
        # Initialize providers
        self.market_provider = CoinGeckoProvider()
        self.news_provider = CryptoPanicProvider(self.config.cryptopanic_api_key)
        self.onchain_provider = OnChainDataProvider(self.config)
        
        # Initialize analysts and agents
        self.market_analyst = MarketAnalyst(self.config)
        self.news_analyst = NewsAnalyst(self.config)
        self.onchain_analyst = OnChainAnalyst(self.config)
        self.trading_advisor = TradingAdvisor(self.config)
        self.position_manager = PositionManager(self.config)
        self.reflection_agent = ReflectionAgent(self.config)
        
        # Create necessary directories
        os.makedirs("data", exist_ok=True)
        os.makedirs("data/market", exist_ok=True)
        os.makedirs("data/news", exist_ok=True)
        os.makedirs("data/signals", exist_ok=True)
        
        print("Initialization complete")
        
        # Debug information - log webhook configuration
        if self.config.webhook_enabled:
            logger.info(f"Webhooks enabled with URLs: {self.config.webhook_urls}")
            logger.info(f"Default webhook URL: {self.config.default_webhook_url}")
        else:
            logger.info("Webhooks are disabled")
    
    def process_ticker(self, ticker: str):
        """Process a single cryptocurrency ticker with enhanced analysis"""
        logger.info(f"Processing {ticker}")
        print(f"Processing {ticker}...")
        
        try:
            # 1. Get market data with technical indicators
            print(f"Fetching market data for {ticker}...")
            market_data = self.market_provider.get_market_data(ticker)
            
            if market_data.price <= 0:
                logger.warning(f"Invalid price data for {ticker}, skipping")
                print(f"Invalid price data for {ticker}, skipping")
                return
            
            print(f"Current price for {ticker}: ${market_data.price:.2f}")
            
            # 2. Check open positions for take profit / stop loss
            # This is now done more frequently (every position_check_interval seconds)
            exit_signals = self.position_manager.check_positions(ticker, market_data.price)
            
            # Send exit signals to webhook
            for signal in exit_signals:
                print(f"Position closed: {signal.action.upper()} {ticker} at ${signal.price:.2f}")
                logger.info(f"Position closed: {signal.action.upper()} {ticker} at ${signal.price:.2f}")
                if self.config.webhook_enabled:
                    self.send_webhook(signal)
            
            # 3. Update reflection agent with current price for simulating outcomes
            self.reflection_agent.simulate_outcomes(ticker, market_data.price)
            
            # 4. Get historical data
            historical_data = self.market_provider.get_historical_data(ticker, days=self.config.lookback_days)
            
            # 5. Get news
            print(f"Fetching news for {ticker}...")
            news_items = self.news_provider.get_news(ticker, limit=10)
            
            # 6. Get on-chain data
            print(f"Fetching on-chain data for {ticker}...")
            onchain_data = self.onchain_provider.get_onchain_data(ticker)
            
            # 7. Analyze market data
            print(f"Analyzing market data for {ticker}...")
            market_analysis = self.market_analyst.analyze(ticker, market_data, historical_data)
            print(f"Market Analysis: {market_analysis[:100]}...")
            
            # 8. Analyze news
            print(f"Analyzing news for {ticker}...")
            news_analysis = self.news_analyst.analyze(ticker, news_items)
            print(f"News Analysis: {news_analysis[:100]}...")
            
            # 9. Analyze on-chain data
            print(f"Analyzing on-chain data for {ticker}...")
            try:
                onchain_analysis = self.onchain_analyst.analyze(ticker, onchain_data)
                print(f"On-chain Analysis: {onchain_analysis[:100]}...")
            except Exception as e:
                logger.error(f"Error analyzing on-chain data for {ticker}: {e}")
                print(f"Error analyzing on-chain data for {ticker}: {e}")
                # Set a default value to continue processing
                onchain_analysis = f"Error analyzing on-chain data for {ticker}: {e}"
            
            # 10. Check if we already have an open position for this ticker
            has_open_position = self.position_manager.has_open_positions(ticker)
            
            # 11. Get trading signal - now passing whether we have an open position
            print(f"Generating trading signal for {ticker}...")
            signal = self.trading_advisor.get_signal(
                ticker=ticker,
                price=market_data.price,
                market_analysis=market_analysis,
                news_analysis=news_analysis,
                onchain_analysis=onchain_analysis,
                has_open_position=has_open_position  # Pass if we already have a position
            )
            
            # 12. Process signal
            if signal:
                if signal.action in ["buy", "sell"] and not has_open_position:
                    print(f"Generated signal: {signal.action.upper()} {ticker} at ${signal.price:.2f}")
                    logger.info(f"Generated signal: {signal.action.upper()} {ticker} at ${signal.price:.2f}")
                    
                    # Add position
                    position = self.position_manager.add_position(signal)
                    if position:
                        logger.info(f"Added {signal.action} position for {ticker} with TP: {position.tp}, SL: {position.sl}")
                    
                    # Add signal to reflection agent
                    self.reflection_agent.add_signal(signal)
                    
                    # Send webhook
                    if self.config.webhook_enabled:
                        self.send_webhook(signal)
                elif has_open_position:
                    print(f"Already have an open position for {ticker}, not generating new signal")
                    logger.info(f"Already have an open position for {ticker}, not generating new signal")
                else:
                    print(f"No trading signal for {ticker} (HOLD recommendation)")
                    logger.info(f"HOLD recommendation for {ticker}")
                    
            else:
                print(f"No trading signal for {ticker}")
                logger.info(f"No trading signal for {ticker}")
        
        except Exception as e:
            logger.error(f"Error processing {ticker}: {e}")
            print(f"Error processing {ticker}: {e}")
    
    def get_webhook_url(self, ticker: str) -> Optional[str]:
        """Get the appropriate webhook URL for a ticker"""
        # First try to get a ticker-specific URL
        if ticker in self.config.webhook_urls:
            return self.config.webhook_urls.get(ticker)
        
        # If not found, use the default URL
        return self.config.default_webhook_url
    
    def send_webhook(self, signal: TradeSignal):
        """Send a webhook with the trade signal using the properly formatted JSON payload"""
        if not self.config.webhook_enabled:
            logger.info("Webhooks are disabled, skipping")
            return
        
        # Get the appropriate webhook URL for this ticker
        webhook_url = self.get_webhook_url(signal.ticker)
        if not webhook_url:
            logger.warning(f"No webhook URL configured for {signal.ticker}, skipping")
            return
        
        # Get signal payload in the correct format
        payload = signal.to_dict()
        
        # Add the prefix message for clarity
        message_prefix = signal.action.upper()
        
        # Prepare the webhook payload
        webhook_payload = {
            "text": f"{message_prefix}\n{json.dumps(payload)}"
        }
        
        logger.info(f"Sending webhook for {signal.ticker} to {webhook_url}: {webhook_payload}")
        print(f"Sending webhook for {signal.ticker} to {webhook_url}: {webhook_payload}")
        
        try:
            # Send webhook with the correctly formatted data
            response = requests.post(
                webhook_url,
                json=webhook_payload,
                timeout=30
            )
            
            # Log response
            if response.status_code == 200:
                logger.info(f"Webhook sent successfully: {response.status_code}")
                print(f"Webhook sent successfully: {response.status_code}")
            else:
                logger.error(f"Failed to send webhook: {response.status_code} - {response.text}")
                print(f"Failed to send webhook: {response.status_code} - {response.text}")
                
                # Try again with direct payload (no text wrapper)
                try:
                    # Add the action as a field directly in the payload
                    direct_payload = payload.copy()
                    direct_payload["signal"] = message_prefix
                    
                    retry_response = requests.post(
                        webhook_url,
                        json=direct_payload,
                        timeout=30
                    )
                    
                    if retry_response.status_code == 200:
                        logger.info(f"Webhook sent successfully with direct payload: {retry_response.status_code}")
                        print(f"Webhook sent successfully with direct payload: {retry_response.status_code}")
                    else:
                        logger.error(f"Failed to send webhook with direct payload: {retry_response.status_code}")
                        print(f"Failed to send webhook with direct payload: {retry_response.status_code}")
                except Exception as e:
                    logger.error(f"Error sending direct webhook payload: {e}")
        
        except Exception as e:
            logger.error(f"Error sending webhook: {e}")
            print(f"Error sending webhook: {e}")
    
    def check_all_positions(self):
        """Check positions for all cryptocurrencies"""
        for ticker in self.config.cryptocurrencies:
            try:
                # Only fetch market data if there are positions to check
                if self.position_manager.has_open_positions(ticker):
                    market_data = self.market_provider.get_market_data(ticker)
                    
                    if market_data.price <= 0:
                        logger.warning(f"Invalid price data for {ticker}, skipping position check")
                        continue
                    
                    # Check positions
                    exit_signals = self.position_manager.check_positions(ticker, market_data.price)
                    
                    # Send exit signals to webhook
                    for signal in exit_signals:
                        print(f"Position closed: {signal.action.upper()} {ticker} at ${signal.price:.2f}")
                        logger.info(f"Position closed: {signal.action.upper()} {ticker} at ${signal.price:.2f}")
                        if self.config.webhook_enabled:
                            self.send_webhook(signal)
            except Exception as e:
                logger.error(f"Error checking positions for {ticker}: {e}")
    
    def run_once(self):
        """Run one cycle of the enhanced system"""
        logger.info("Running Enhanced CryptoMCP cycle")
        print("Running Enhanced CryptoMCP cycle...")
        
        for ticker in self.config.cryptocurrencies:
            self.process_ticker(ticker)
        
        # Run reflection if needed
        self.reflection_agent.run_reflection()
        
        logger.info("Cycle completed")
        print("Cycle completed")
    
    def run(self):
        """Run the system continuously"""
        logger.info("Starting Enhanced CryptoMCP system")
        print("Starting Enhanced CryptoMCP system")
        
        while True:
            try:
                self.run_once()
                
                interval = self.config.data_fetch_interval
                logger.info(f"Sleeping for {interval} seconds")
                print(f"Sleeping for {interval} seconds")
                
                # Sleep in smaller increments so we can check positions frequently
                last_position_check = time.time()
                last_normal_cycle = time.time()
                
                while (time.time() - last_normal_cycle) < interval:
                    # Check if it's time to check positions
                    if (time.time() - last_position_check) >= self.config.position_check_interval:
                        print("Checking positions during sleep cycle...")
                        self.check_all_positions()
                        last_position_check = time.time()
                    
                    # Sleep a short time
                    time.sleep(1)
                
            except KeyboardInterrupt:
                logger.info("Shutting down Enhanced CryptoMCP system")
                print("Shutting down Enhanced CryptoMCP system")
                break
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                print(f"Unexpected error: {e}")
                # Sleep for a shorter time before retrying
                time.sleep(60)

# Updated example configuration
EXAMPLE_CONFIG = {
    "gemini_api_key": "your-gemini-api-key",
    "webhook_urls": {
        "BTC": "http://localhost:5000/webhook/btc",
        "SOL": "http://localhost:5000/webhook/sol"
    },
    "default_webhook_url": "http://localhost:5000/webhook/default",
    "cryptocurrencies": ["BTC/USDT", "SOL/USDT"],
    "cryptopanic_api_key": "your-cryptopanic-api-key",
    "web3_providers": {
        "ethereum": "https://eth-mainnet.g.alchemy.com/v2/demo",
        "bsc": "https://bsc-dataseed.binance.org/",
        "polygon": "https://polygon-rpc.com"
    },
    "data_fetch_interval": 3600,
    "model_name": "gemini-pro",
    "webhook_enabled": True,
    "track_whale_wallets": True,
    "technical_indicators": ["rsi", "macd", "bollinger", "sma", "ema"],
    "lookback_days": 30,
    "backtest_enabled": True,
    "whale_threshold": 1000000,
    "performance_evaluation_interval": 86400,
    "check_tp_sl_interval": 600,  # Check take profit/stop loss every 10 minutes
    "position_check_interval": 60  # Check positions every minute
}

# Main entry point
if __name__ == "__main__":
    # Check if config file exists
    config_file = "C:\\Users\\mas\\Downloads\\updated-confi.json"
    if not os.path.exists(config_file):
        print(f"No {config_file} found. Creating example config...")
        with open(config_file, "w") as f:
            json.dump(EXAMPLE_CONFIG, f, indent=2)
        print(f"Created example {config_file} file. Please update it with your API keys.")
        exit(0)
    
    # Run the system
    try:
        print("Starting Enhanced CryptoMCP system...")
        mcp = CryptoMCP(config_file)
        mcp.run()
    except Exception as e:
        print(f"Fatal error: {e}")
        import traceback
        traceback.print_exc()