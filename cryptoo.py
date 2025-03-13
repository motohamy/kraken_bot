"""
Crypto Trading Bot Core - Real Account Version
"""

import time
import ccxt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Union
import json
import requests
import hmac
import hashlib
import base64
import threading
import websocket
import queue

import logging

# Configure logging with different levels for different modules
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("trading_bot.log"),
        logging.StreamHandler()
    ]
)

# Create logger
logger = logging.getLogger("trading_bot")

# Set more specific logger levels to reduce noise
logging.getLogger("websocket").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("requests").setLevel(logging.WARNING)

# Add a filter to suppress repetitive errors
class DuplicateFilter(logging.Filter):
    def __init__(self, name=''):
        super().__init__(name)
        self.last_log = None
        self.last_count = 0
    
    def filter(self, record):
        # Get the message
        current = record.getMessage()
        
        # If it's the same as the last one
        if current == self.last_log:
            self.last_count += 1
            # Only log every 50th occurrence of the same message
            if self.last_count % 50 == 0:
                record.msg = "%s (repeated %d times)" % (record.msg, self.last_count)
                return True
            return False
        else:
            # It's a new message, so log it and store it
            self.last_log = current
            self.last_count = 0
            return True

# Add filter to logger
logger.addFilter(DuplicateFilter())

class KrakenTradingClient:
    """Custom client for Kraken trading (real accounts only)"""
    
    def __init__(self, api_key, secret):
        """Initialize the client with API credentials"""
        self.api_key = api_key
        self.secret = secret
        self.base_url = "https://futures.kraken.com"
        self.ws_url = "wss://futures.kraken.com/ws/v1"
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'User-Agent': 'KrakenTradingBot/1.0'
        })
    
    def get_instruments(self):
        """Get available trading instruments"""
        try:
            url = f"{self.base_url}/derivatives/api/v3/instruments"
            response = self.session.get(url)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get instruments: {e}")
            return {"instruments": []}
    
    def get_ticker(self, symbol):
        """Get ticker for a symbol"""
        try:
            url = f"{self.base_url}/derivatives/api/v3/tickers"
            response = self.session.get(url)
            response.raise_for_status()
            tickers = response.json()
            
            # Find ticker for the specified symbol
            for ticker in tickers.get('tickers', []):
                if ticker['symbol'] == symbol:
                    return {
                        'symbol': symbol,
                        'last': float(ticker.get('last', 0)),
                        'bid': float(ticker.get('bid', 0)),
                        'ask': float(ticker.get('ask', 0)),
                        'volume': float(ticker.get('vol24h', 0)),
                        'timestamp': int(time.time() * 1000)
                    }
            
            # If symbol not found
            return {
                'symbol': symbol,
                'last': 0,
                'bid': 0,
                'ask': 0,
                'volume': 0,
                'timestamp': int(time.time() * 1000)
            }
        except Exception as e:
            logger.error(f"Failed to get ticker for {symbol}: {e}")
            return {}
    
    def get_ohlc(self, symbol, interval='1', since=None):
        """Get OHLCV data for a symbol"""
        try:
            url = f"{self.base_url}/derivatives/api/v3/history"
            params = {
                'symbol': symbol,
                'interval': interval
            }
            if since:
                params['from'] = since
                
            response = self.session.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            # Format data as OHLCV
            ohlcv = []
            if 'candles' in data:
                for candle in data['candles']:
                    timestamp = int(datetime.strptime(candle['time'], "%Y-%m-%dT%H:%M:%S.%fZ").timestamp() * 1000)
                    ohlcv.append([
                        timestamp,
                        float(candle.get('open', 0)),
                        float(candle.get('high', 0)),
                        float(candle.get('low', 0)),
                        float(candle.get('close', 0)),
                        float(candle.get('volume', 0))
                    ])
            return ohlcv
        except Exception as e:
            logger.error(f"Failed to get OHLCV for {symbol}: {e}")
            return []
    
    def get_accounts(self):
        """Get account information"""
        try:
            url = f"{self.base_url}/derivatives/api/v3/accounts"
            # Create signature
            nonce = str(int(time.time() * 1000))
            endpoint = "/derivatives/api/v3/accounts"
            
            message = nonce + endpoint
            signature = hmac.new(
                base64.b64decode(self.secret),
                message.encode('utf-8'),
                hashlib.sha256
            ).digest()
            
            signed_headers = {
                'APIKey': self.api_key,
                'Nonce': nonce,
                'Authent': base64.b64encode(signature).decode('utf-8')
            }
            
            response = self.session.get(url, headers={**self.session.headers, **signed_headers})
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get accounts: {e}")
            return {"accounts": []}
    
    def create_order(self, symbol, order_type, side, amount, price=None, params=None):
        """Create an order following CCXT style but with Kraken Futures API specifics"""
        try:
            url = f"{self.base_url}/derivatives/api/v3/sendorder"
            
            # Create signature
            nonce = str(int(time.time() * 1000))
            endpoint = "/derivatives/api/v3/sendorder"
            
            # Prepare order data
            order_data = {
                "orderType": order_type.upper(),
                "symbol": symbol,
                "side": side.upper(),
                "size": amount
            }
            
            if price and order_type.lower() == 'limit':
                order_data["limitPrice"] = price
                
            if params:
                order_data.update(params)
                
            # Add client order ID if not present
            if 'cliOrdId' not in order_data:
                order_data['cliOrdId'] = f'bot_{int(time.time())}'
                
            # Handle leverage
            if 'leverage' in params:
                order_data['leverage'] = params['leverage']
            
            message = nonce + endpoint + json.dumps(order_data)
            signature = hmac.new(
                base64.b64decode(self.secret),
                message.encode('utf-8'),
                hashlib.sha256
            ).digest()
            
            signed_headers = {
                'APIKey': self.api_key,
                'Nonce': nonce,
                'Authent': base64.b64encode(signature).decode('utf-8')
            }
            
            response = self.session.post(
                url, 
                headers={**self.session.headers, **signed_headers},
                json=order_data
            )
            response.raise_for_status()
            result = response.json()
            
            # Check if order was sent successfully
            if 'sendStatus' in result and result['sendStatus'].get('status') == 'placed':
                # Format result to match expected structure
                order = {
                    'id': result['sendStatus'].get('orderId', ''),
                    'clientOrderId': order_data['cliOrdId'],
                    'symbol': symbol,
                    'type': order_type,
                    'side': side,
                    'amount': amount,
                    'price': price,
                    'status': 'open',
                    'timestamp': int(time.time() * 1000)
                }
                logger.info(f"Order placed successfully: {order['id']}")
                return order
            else:
                error_msg = result.get('sendStatus', {}).get('status', 'unknown error')
                logger.error(f"Order placement failed: {error_msg}")
                raise Exception(f"Order placement failed: {error_msg}")
            
        except Exception as e:
            logger.error(f"Failed to create order: {e}")
            raise e

    def create_market_order_with_cost(self, symbol, side, cost, params=None):
        """Create a market order with cost (in quote currency) - CCXT style function"""
        try:
            # First get the ticker to calculate the amount
            ticker = self.get_ticker(symbol)
            
            if ticker and 'last' in ticker and ticker['last'] > 0:
                # Calculate amount based on cost and current price
                price = ticker['last']
                
                # Get contract size for futures
                contract_size = self._get_contract_size(symbol)
                if contract_size <= 0:
                    raise ValueError(f"Invalid contract size for {symbol}")
                
                # Calculate number of contracts to meet the cost target
                contracts = cost / (price * contract_size)
                
                # Round to appropriate precision (futures usually use fewer decimals)
                contracts = round(contracts, 2)  # Adjust precision as needed
                
                # Create the market order
                return self.create_order(
                    symbol=symbol,
                    order_type='market',
                    side=side,
                    amount=contracts,
                    price=None,
                    params=params
                )
            else:
                raise ValueError(f"Could not get price for {symbol}")
                
        except Exception as e:
            logger.error(f"Failed to create market order with cost: {e}")
            raise e
    
    def _get_contract_size(self, symbol):
        """Get contract size for a symbol"""
        try:
            instruments = self.get_instruments()
            for inst in instruments.get('instruments', []):
                if inst['symbol'] == symbol:
                    return float(inst.get('contractSize', 1))
            return 0
        except Exception as e:
            logger.error(f"Failed to get contract size: {e}")
            return 0

class CryptoTradingBot:
    """Thread-safe main bot class - Real Account Version"""
    
    def __init__(self, config_file: str):
        """Initialize trading bot with configuration from file"""
        self.config = self._load_config(config_file)
        self.client = self._initialize_client()
        self.ws_client = None
        self.ws_thread = None
        self.positions = {}  # Current open positions
        self.balance = {}  # Account balance
        self.last_buy_time = {}  # Timestamp of last buy for each coin
        self.trailing_stops = {}  # Track trailing stops for each position
        self.profit_stats = {
            'total_profit': 0,
            'wins': 0,
            'losses': 0,
            'trades': []
        }
        self.markets = {}
        self.tickers = {}
        self.running = True
        
        # Thread-safe message queue for logging
        self.message_queue = queue.Queue()
        self.output_handler = None
        
    def set_output_handler(self, handler):
        """Set a handler for UI output"""
        self.output_handler = handler
        
    def log(self, message, level="info", data=None):
        """Thread-safe logging with UI integration"""
        if level == "info":
            logger.info(message)
        elif level == "error":
            logger.error(message)
        elif level == "warning":
            logger.warning(message)
            
        # Queue the message for UI handling
        try:
            self.message_queue.put({
                'timestamp': datetime.now().strftime("%H:%M:%S"),
                'message': message,
                'level': level,
                'data': data
            })
        except Exception as e:
            logger.error(f"Failed to queue message: {e}")
            
    def process_message_queue(self):
        """Process queued messages (call from main thread)"""
        if hasattr(self, 'message_queue'):
            while not self.message_queue.empty():
                try:
                    message = self.message_queue.get_nowait()
                    # Handle the message in the main thread
                    if self.output_handler:
                        self.output_handler(
                            message['message'], 
                            message['level'], 
                            message['data']
                        )
                except queue.Empty:
                    break
                except Exception as e:
                    logger.error(f"Error processing message queue: {e}")
            
    def _load_config(self, config_file: str) -> Dict:
        """Load configuration from JSON file"""
        try:
            with open(config_file, 'r') as f:
                config = json.load(f)
            logger.info(f"Configuration loaded from {config_file}")
            return config
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            raise
    
    def _initialize_client(self):
        """Initialize connection to trading platform"""
        try:
            api_key = self.config['connection']['api_key']
            secret = self.config['connection']['secret']
            
            # Create real account client
            client = KrakenTradingClient(api_key, secret)
            
            # Verify connection by fetching instruments
            instruments = client.get_instruments()
            
            if instruments and 'instruments' in instruments:
                logger.info(f"Connected to Kraken Futures")
                logger.info(f"Found {len(instruments['instruments'])} available instruments")
            else:
                logger.warning("Connected but no instruments found")
                
            return client
            
        except Exception as e:
            logger.error(f"Failed to initialize client: {e}")
            raise
    
    def _initialize_websocket(self):
        """Initialize WebSocket connection for real-time data"""
        try:
            ws_url = self.client.ws_url
            api_key = self.config['connection']['api_key']
            secret = self.config['connection']['secret']
            bot = self  # Store reference to self for callbacks
        
            # Define WebSocket callbacks without direct access to the bot
            def on_message(ws, message):
                try:
                    data = json.loads(message)
                
                    # Check message type
                    if 'event' in data:
                        # Handle system messages
                        event = data.get('event')
                        if event == 'info':
                            logger.info(f"WebSocket info: {data.get('message', '')}")
                        elif event == 'subscribed':
                            logger.info(f"Subscribed to {data.get('feed', '')}")
                        elif event == 'error':
                            logger.error(f"WebSocket error event: {data.get('message', '')}")
                        # Other event types can be handled here
                
                    elif 'feed' in data:
                        feed = data.get('feed')
                      
                        if feed == 'ticker' and 'product_id' in data:
                            # Handle ticker data
                            symbol = data['product_id']
                            bot.tickers[symbol] = data
                            # Check trailing stops on price updates
                            if 'bid' in data:
                                bot._check_trailing_stops(symbol, float(data['bid']))
                    
                        elif feed == 'fills':
                            # Handle fill data
                            logger.info(f"Order filled: {data}")
                            bot._process_fill(data)
                        
                        elif feed == 'heartbeat':
                            # Silently handle heartbeat messages
                            pass
                    
                        else:
                            # Unknown feed type, just log at debug level
                            logger.debug(f"Received message from feed '{feed}'")
                
                    else:
                        # Unknown message format
                        logger.debug(f"Received message with unknown format: {data}")
                    
                except json.JSONDecodeError:
                    logger.error(f"Failed to parse WebSocket message: {message}")
                except Exception as e:
                    logger.error(f"WebSocket message processing error: {str(e)}")
        
            def on_error(ws, error):
                logger.error(f"WebSocket error: {error}")
        
            def on_close(ws, close_status_code, close_msg):
                logger.info(f"WebSocket closed: {close_status_code} - {close_msg}")
                if bot.running:
                    logger.info("Attempting to reconnect WebSocket in 5 seconds...")
                    time.sleep(5)
                    bot._initialize_websocket()
        
            def on_open(ws):
                logger.info("WebSocket connection established")
            
                # Auth message
                nonce = int(time.time() * 1000)
                authent = f"GET/auth/w/websocket:{nonce}"
                signature = hmac.new(
                    base64.b64decode(secret),
                    authent.encode('utf-8'),
                    hashlib.sha256
                ).digest()
            
                auth_msg = {
                    "event": "login",
                    "key": api_key,
                    "sign": base64.b64encode(signature).decode('utf-8'),
                    "timestamp": nonce
                }
                ws.send(json.dumps(auth_msg))
            
                # After authentication, subscribe to required feeds
                product_ids = bot._get_product_ids()
                if product_ids:
                    try:
                        subscribe_msg = {
                            "event": "subscribe",
                            "feed": "ticker",
                            "product_ids": product_ids
                        }
                        ws.send(json.dumps(subscribe_msg))
                        logger.info(f"Subscribed to ticker feed for {len(product_ids)} products")
                    except Exception as e:
                        logger.error(f"Error subscribing to ticker feed: {e}")
            
                # Subscribe to user-specific feeds
                try:
                    user_feeds = {
                        "event": "subscribe",
                        "feed": "fills"
                    }
                    ws.send(json.dumps(user_feeds))
                    logger.info("Subscribed to fills feed")
                except Exception as e:
                    logger.error(f"Error subscribing to fills feed: {e}")
        
            # Initialize WebSocket with ping interval to keep connection alive
            websocket.enableTrace(False)  # Disable trace to reduce output
            ws = websocket.WebSocketApp(
                ws_url,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
                on_open=on_open
            )
        
            # Start WebSocket thread with ping interval
            self.ws_client = ws
            self.ws_thread = threading.Thread(
               target=lambda: ws.run_forever(ping_interval=30, ping_timeout=10)
            )
            self.ws_thread.daemon = True
            self.ws_thread.start()
        
            logger.info("Real-time data connection established")
        
        except Exception as e:
            logger.error(f"Failed to initialize WebSocket: {e}")

    def _get_product_ids(self) -> List[str]:
        """Get list of product IDs for WebSocket subscription"""
        try:
            instruments = self.client.get_instruments()
        
            # Filter for perpetual futures that are trading
            product_ids = []
            for inst in instruments.get('instruments', []):
                if inst.get('tradeable', False) and 'PERP' in inst.get('symbol', ''):
                    product_ids.append(inst.get('symbol', ''))
        
            logger.info(f"Found {len(product_ids)} tradeable perpetual futures")
            return product_ids
        except Exception as e:
            logger.error(f"Failed to get product IDs: {e}")
            return []
            
    def _process_fill(self, fill_data: Dict):
        """Process a fill event from WebSocket"""
        try:
            symbol = fill_data['product_id']
            side = fill_data['side']
            price = float(fill_data['price'])
            size = float(fill_data['size'])
            order_id = fill_data['order_id']
            
            if side.lower() == 'buy':
                # Record new position
                self.positions[order_id] = {
                    'symbol': symbol,
                    'size': size,
                    'price': price,
                    'timestamp': datetime.now(),
                    'order_id': order_id,
                    'highest_price': price  # For trailing stop
                }
                self.log(f"New position opened: {symbol} - {size} @ {price}", "info", {
                    "type": "new_position",
                    "symbol": symbol,
                    "size": size,
                    "price": price
                })
            elif side.lower() == 'sell':
                # Find and update corresponding position
                for pos_id, position in list(self.positions.items()):
                    if position['symbol'] == symbol:
                        # Calculate profit
                        buy_price = position['price']
                        sell_price = price
                        profit_pct = (sell_price - buy_price) / buy_price * 100
                        profit_amount = (sell_price - buy_price) * position['size']
                        
                        # Update stats
                        self.profit_stats['total_profit'] += profit_amount
                        if profit_amount > 0:
                            self.profit_stats['wins'] += 1
                        else:
                            self.profit_stats['losses'] += 1
                            
                        # Record trade
                        trade = {
                            'symbol': symbol,
                            'buy_price': buy_price,
                            'sell_price': sell_price,
                            'size': position['size'],
                            'profit_pct': profit_pct,
                            'profit_amount': profit_amount,
                            'timestamp': datetime.now()
                        }
                        self.profit_stats['trades'].append(trade)
                        
                        # Remove position
                        del self.positions[pos_id]
                        self.log(f"Position closed: {symbol} - Profit: {profit_pct:.2f}%, {profit_amount:.2f}", "info", {
                            "type": "close_position",
                            "symbol": symbol,
                            "profit_pct": profit_pct,
                            "profit_amount": profit_amount
                        })
                        break
                        
        except Exception as e:
            logger.error(f"Error processing fill: {e}")
    
    def sync_balance(self) -> None:
        """Sync balance from trading platform"""
        try:
            # Get account information
            accounts = self.client.get_accounts()
            self.balance = accounts
            # Don't log this every time to reduce output
        except Exception as e:
            logger.error(f"Failed to sync balance: {e}")
            
    def get_quote_currency(self) -> str:
        """Get quote currency from config"""
        return self.config['coins']['quote_currency']
    
    def get_allowed_coins(self) -> List[str]:
        """Get list of allowed futures instruments to trade"""
        try:
            instruments = self.client.get_instruments()
            
            if self.config['coins']['allow_all_coins']:
                coins = [inst['symbol'] for inst in instruments['instruments'] 
                        if inst.get('tradeable', False)]
            else:
                # Filter for selected coins and perpetual futures
                coins = []
                selected = self.config['coins']['selected_coins']
                
                for inst in instruments['instruments']:
                    if inst.get('tradeable', False):
                        symbol = inst['symbol']
                        # Look for perpetual futures for selected coins
                        for coin in selected:
                            if coin in symbol and 'PERP' in symbol:
                                coins.append(symbol)
                                break
            
            return coins
        except Exception as e:
            logger.error(f"Failed to get allowed coins: {e}")
            return []
    
    def calculate_buy_amount(self, symbol: str, current_price: float) -> float:
        """Calculate buy amount based on percentage and account balance"""
        try:
            # For futures, calculate contract quantity
            quote_currency = self.get_quote_currency()
            percentage = self.config['coins']['percentage_buy_amount'] / 100
            
            # Get collateral available
            accounts = self.balance
            if 'accounts' in accounts:
                available_balance = 0
                for account in accounts['accounts']:
                    if account['currency'] == quote_currency:
                        available_balance = float(account.get('available', 0))
                        break
            else:
                # Log error and return 0 if balance can't be determined
                logger.error("Could not retrieve account balance")
                return 0
            
            # Calculate buy amount in quote currency
            buy_amount_quote = available_balance * percentage
            
            # Check minimum order amount
            if buy_amount_quote < self.config['coins']['minimum_amount']:
                if self.config['coins']['force_minimum_buy_amount']:
                    buy_amount_quote = self.config['coins']['minimum_amount']
                else:
                    logger.warning(f"Buy amount {buy_amount_quote} below minimum")
                    return 0
            
            # Check maximum allocated amount if set
            max_allocated = self.config['coins'].get('maximum_amount_allocated')
            if max_allocated and buy_amount_quote > max_allocated:
                buy_amount_quote = max_allocated
                
            # Convert to contract size
            contract_size = self.client._get_contract_size(symbol)
            if contract_size == 0:
                logger.error(f"Failed to get contract size for {symbol}")
                return 0
                
            # Calculate number of contracts
            contracts = buy_amount_quote / (current_price * contract_size)
            
            # Round to appropriate precision
            contracts = round(contracts, 2)  # Adjust precision as needed
            
            logger.info(f"Calculated buy amount for {symbol}: {contracts} contracts (worth approximately {buy_amount_quote:.2f} {quote_currency})")
            return contracts
            
        except Exception as e:
            logger.error(f"Failed to calculate buy amount: {e}")
            return 0
    
    def can_buy_instrument(self, symbol: str, current_price: float) -> bool:
        """Check if a trading instrument can be bought based on settings"""
        now = datetime.now()
        
        # Check cooldown period
        if (self.config['buy_settings']['enable_cooldown'] and 
            symbol in self.last_buy_time):
            cooldown_minutes = self.config['buy_settings']['cooldown_period']
            last_buy = self.last_buy_time[symbol]
            elapsed = (now - last_buy).total_seconds() / 60
            
            if elapsed < cooldown_minutes:
                logger.debug(f"Cooldown period in effect for {symbol} ({elapsed:.1f}/{cooldown_minutes} minutes)")
                return False
        
        # Check if already in position
        if (self.config['buy_settings']['only_buy_if_not_already_in_positions'] and 
            any(p['symbol'] == symbol for p in self.positions.values())):
            logger.debug(f"Already in position for {symbol}, skipping")
            return False
        
        # Check open positions limit
        max_positions = self.config['buy_settings']['max_open_positions']
        if len(self.positions) >= max_positions:
            logger.debug(f"Maximum number of positions reached ({len(self.positions)}/{max_positions})")
            return False
        
        # Check open positions per instrument
        inst_positions = len([p for p in self.positions.values() if p['symbol'] == symbol])
        max_per_inst = self.config['buy_settings']['max_percentage_open_positions_per_coin']
        max_allowed_per_inst = max_positions * max_per_inst / 100
        
        if inst_positions >= max_allowed_per_inst:
            logger.debug(f"Maximum positions for {symbol} reached ({inst_positions}/{max_allowed_per_inst})")
            return False
            
        # Check if only one open buy order per instrument
        if (self.config['buy_settings']['only_1_open_buy_order_per_coin'] and 
            any(p['symbol'] == symbol for p in self.positions.values())):
            logger.debug(f"Already have an open position for {symbol}, not buying more due to settings")
            return False
            
        # Check percentage range
        positions_for_symbol = [p for p in self.positions.values() if p['symbol'] == symbol]
        if positions_for_symbol:
            for position in positions_for_symbol:
                price_diff_pct = abs(position['price'] - current_price) / position['price'] * 100
                if price_diff_pct < self.config['buy_settings']['percent_range']:
                    logger.debug(f"Position for {symbol} exists within {price_diff_pct:.2f}% of current price")
                    return False
        
        return True
    
    def should_buy(self, symbol: str, price_data: pd.DataFrame) -> bool:
        """Determine if bot should buy based on price changes"""
        # Get price change trigger percentage from config
        trigger_pct = self.config['place_order_trigger']['percentage_change']
        
        # Calculate percentage change
        if len(price_data) > 1:
            pct_change = price_data['close'].pct_change().iloc[-1] * 100
            
            # Check if percentage change meets trigger
            if abs(pct_change) >= trigger_pct:
                self.log(f"{symbol} price changed by {pct_change:.2f}%, triggering buy check")
                return True
                
        return False
    
    def execute_buy(self, symbol: str, amount: float, price: float) -> Dict:
        """Execute buy order"""
        try:
            # Generate unique client order ID
            client_order_id = f'bot_{int(time.time())}'
            
            # Order parameters
            params = {
                'cliOrdId': client_order_id,
                'leverage': self.config['buy_settings'].get('leverage', 1)
            }
            
            # Order type (market or limit)
            order_type = self.config['buy_settings']['order_type'].lower()
            
            # Execute order
            self.log(f"Placing {order_type} buy order for {symbol}: {amount} contracts at {price if order_type == 'limit' else 'market price'}")
            
            if order_type == 'market':
                try:
                    order = self.client.create_order(
                        symbol,
                        'market',
                        'buy',
                        amount,
                        None,
                        params
                    )
                except Exception as market_error:
                    logger.error(f"Market order failed, trying CCXT-style order with cost: {market_error}")
                    
                    # Calculate equivalent cost
                    contract_size = self.client._get_contract_size(symbol)
                    cost = amount * price * contract_size
                    
                    # Try using the CCXT-style method
                    order = self.client.create_market_order_with_cost(
                        symbol,
                        'buy',
                        cost,
                        params
                    )
            else:  # limit order
                order = self.client.create_order(
                    symbol,
                    'limit',
                    'buy',
                    amount,
                    price,
                    params
                )
            
            # Record the buy time
            self.last_buy_time[symbol] = datetime.now()
            
            # Add to positions (will be updated by WebSocket on fill)
            position_id = order['id']
            self.positions[position_id] = {
                'symbol': symbol,
                'size': amount,
                'price': price,
                'order_type': order_type,
                'timestamp': datetime.now(),
                'order_id': order['id'],
                'highest_price': price,  # For trailing stop
            }
            
            self.log(f"Buy order placed: {symbol} - {amount} @ {price}", "info", {
                "type": "buy_order",
                "symbol": symbol,
                "amount": amount,
                "price": price
            })
            return order
            
        except Exception as e:
            logger.error(f"Failed to execute buy order: {e}")
            return None
    
    def _check_trailing_stops(self, symbol: str, current_price: float) -> None:
        """Check trailing stops for a symbol when price updates"""
        for position_id, position in list(self.positions.items()):
            if position['symbol'] == symbol:
                # Update highest price if current price is higher
                if current_price > position['highest_price']:
                    self.positions[position_id]['highest_price'] = current_price
                
                # Check trailing stop
                trailing_pct = self.config['sell_settings']['trailing_stop_loss_percentage']
                arm_at_pct = self.config['sell_settings']['arm_trailing_stop_loss_at']
                
                initial_price = position['price']
                highest_price = position['highest_price']
                
                profit_pct = (current_price - initial_price) / initial_price * 100
                
                # If profit percentage reached arm threshold, activate trailing stop
                if profit_pct >= arm_at_pct:
                    # Calculate stop price based on highest price
                    stop_price = highest_price * (1 - trailing_pct / 100)
                    
                    # If current price falls below stop price, sell
                    if current_price <= stop_price:
                        self.log(f"Trailing stop triggered for {symbol} at {current_price:.2f} (stop: {stop_price:.2f})")
                        
                        if self.config['sell_settings']['only_sell_with_profit']:
                            # Check if this would result in profit
                            if current_price > initial_price:
                                self.execute_sell(position_id, current_price)
                            else:
                                self.log(f"Not selling {symbol} - would result in loss")
                        else:
                            self.execute_sell(position_id, current_price)
    
    def update_trailing_stops(self) -> None:
        """Update trailing stops for all positions"""
        for symbol in set(position['symbol'] for position in self.positions.values()):
            try:
                # Get current price
                ticker = self.client.get_ticker(symbol)
                current_price = ticker['last'] if ticker else 0
                
                if current_price > 0:
                    # Update trailing stops for this symbol
                    self._check_trailing_stops(symbol, current_price)
                
            except Exception as e:
                logger.error(f"Error updating trailing stop for {symbol}: {e}")
    
    def execute_sell(self, position_id: str, current_price: float) -> Dict:
        """Execute sell order"""
        try:
            position = self.positions[position_id]
            symbol = position['symbol']
            amount = position['size']
            
            # Generate unique client order ID
            client_order_id = f'bot_sell_{int(time.time())}'
            
            # Order parameters
            params = {
                'cliOrdId': client_order_id,
                'leverage': self.config['buy_settings'].get('leverage', 1)
            }
            
            self.log(f"Executing sell for {symbol}: {amount} contracts at market price")
            
            # Execute market sell order
            try:
                order = self.client.create_order(
                    symbol,
                    'market',
                    'sell',
                    amount,
                    None,
                    params
                )
            except Exception as market_error:
                logger.error(f"Market sell order failed, trying CCXT-style order with cost: {market_error}")
                
                # Calculate equivalent cost
                contract_size = self.client._get_contract_size(symbol)
                cost = amount * current_price * contract_size
                
                # Try using the CCXT-style method
                order = self.client.create_market_order_with_cost(
                    symbol,
                    'sell',
                    cost,
                    params
                )
            
            self.log(f"Sell order placed: {symbol} - {amount} @ {current_price}", "info", {
                "type": "sell_order",
                "symbol": symbol,
                "amount": amount,
                "price": current_price
            })
            return order
            
        except Exception as e:
            logger.error(f"Failed to execute sell order: {e}")
            return None
    
    def fetch_market_data(self, symbol: str, timeframe: str = '1', limit: int = 100) -> pd.DataFrame:
        """Fetch market data"""
        try:
            # Fetch OHLCV data
            since = int((datetime.now() - timedelta(minutes=limit * int(timeframe))).timestamp() * 1000)
            ohlcv = self.client.get_ohlc(symbol, timeframe, since)
            
            # Convert to DataFrame
            if not ohlcv:
                return pd.DataFrame()
                
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            
            return df
            
        except Exception as e:
            logger.error(f"Failed to fetch market data for {symbol}: {e}")
            return pd.DataFrame()
    
    def scan_market(self) -> None:
        """Scan market for trading opportunities"""
        instruments = self.get_allowed_coins()
        
        for symbol in instruments:
            try:
                # Get current price
                ticker = self.client.get_ticker(symbol)
                current_price = ticker['last'] if ticker else 0
                
                if current_price == 0:
                    continue
                
                # Fetch recent price data
                price_data = self.fetch_market_data(symbol)
                
                if price_data.empty:
                    continue
                
                # Check if should buy
                if self.should_buy(symbol, price_data):
                    # Check if can buy based on settings
                    if self.can_buy_instrument(symbol, current_price):
                        # Calculate buy amount
                        amount = self.calculate_buy_amount(symbol, current_price)
                        
                        if amount > 0:
                            # Execute buy
                            self.execute_buy(symbol, amount, current_price)
                            
            except Exception as e:
                logger.error(f"Error processing {symbol}: {e}")
    
    def reset_failed_orders(self) -> None:
        """Reset stop-loss after failed orders if enabled"""
        if not self.config['sell_settings']['reset_stop_loss_after_failed_orders']:
            return
            
        # For demo purposes, we'll just check if positions are older than max_open_time_buy
        try:
            max_open_time = self.config['buy_settings']['max_open_time_buy']
            current_time = datetime.now()
            
            for position_id, position in list(self.positions.items()):
                position_time = position['timestamp']
                elapsed_minutes = (current_time - position_time).total_seconds() / 60
                
                if elapsed_minutes > max_open_time:
                    self.log(f"Resetting failed order: {position_id} (exceeded max open time)")
                    del self.positions[position_id]
                    
        except Exception as e:
            logger.error(f"Error resetting failed orders: {e}")
    
    def get_status_summary(self):
        """Get a summary of current bot status for UI"""
        return {
            "positions": len(self.positions),
            "profit": self.profit_stats['total_profit'],
            "wins": self.profit_stats['wins'],
            "losses": self.profit_stats['losses'],
            "balance": self.balance,
            "active_positions": self.positions
        }
            
    def run(self, single_iteration=False) -> None:
        """Run the trading bot main loop"""
        logger.info("Starting trading bot...")
        
        try:
            # Initialize WebSocket
            self._initialize_websocket()
            
            # Main loop
            while self.running:
                try:
                    # Sync balance (but don't log it every time)
                    self.sync_balance()
                    
                    # Update trailing stops for existing positions
                    self.update_trailing_stops()
                    
                    # Scan market for opportunities
                    self.scan_market()
                    
                    # Reset failed orders if enabled
                    self.reset_failed_orders()
                    
                    # Log current status (only every 10 minutes)
                    if int(time.time()) % 600 < 60:  # Only log every 10 minutes
                        self.log(f"Status: {len(self.positions)} positions, profit: {self.profit_stats['total_profit']:.2f}")
                    
                    # If running in single iteration mode (for UI), break after one loop
                    if single_iteration:
                        break
                        
                    # Sleep before next iteration
                    sleep_time = 60  # 1 minute
                    time.sleep(sleep_time)
                    
                except Exception as e:
                    logger.error(f"Error in main loop: {e}")
                    time.sleep(60)  # Sleep before retry
                    
        except KeyboardInterrupt:
            logger.info("Bot stopping due to keyboard interrupt")
            self.running = False
            
        finally:
            # Close WebSocket when done
            if not single_iteration and self.ws_client:
                self.ws_client.close()
                
            if not single_iteration:
                logger.info("Bot stopped")