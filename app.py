"""
Crypto Trading Bot Streamlit Application - Real Account Version
"""

import streamlit as st
import json
import time
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta
import threading
import os

# Import the bot core
from cryptoo import CryptoTradingBot

# Set page config
st.set_page_config(
    page_title="Crypto Trading Bot",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom styling
st.markdown("""
<style>
    .main {
        background-color: #1e1e2f;
        color: white;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 10px;
    }
    .stTabs [data-baseweb="tab"] {
        background-color: #252547;
        border-radius: 4px 4px 0px 0px;
        padding: 10px 20px;
        color: white;
    }
    .stTabs [aria-selected="true"] {
        background-color: #36368b;
    }
    .stButton>button {
        background-color: #2986cc;
        color: white;
        border: none;
        padding: 10px 24px;
        border-radius: 4px;
    }
    .stToggle>label>div {
        background-color: #36368b;
    }
    .stTextInput>div>div>input {
        background-color: #252547;
        color: white;
    }
    .stSelectbox>div>div>div {
        background-color: #252547;
        color: white;
    }
    .css-deo2e3 {
        background-color: #131324;
    }
    div[data-testid="stVerticalBlock"] div[style*="flex-direction: column;"] div[data-testid="stVerticalBlock"] {
        background-color: #252547;
        padding: 20px;
        border-radius: 5px;
        margin-bottom: 20px;
    }
    
    /* Custom box styling */
    .info-box {
        background-color: #252547;
        border-radius: 5px;
        padding: 20px;
        margin: 10px 0px;
    }
    .settings-box {
        background-color: #293047;
        border-radius: 5px;
        padding: 15px;
        margin-bottom: 10px;
    }
    .status-good {
        color: #4CAF50;
    }
    .status-warning {
        color: #FF9800;
    }
    .status-bad {
        color: #F44336;
    }
    
    /* Dark theme for dataframes */
    .dataframe {
        background-color: #252547 !important;
        color: white !important;
    }
    .dataframe th {
        background-color: #36368b !important;
        color: white !important;
    }
    .dataframe td {
        background-color: #252547 !important;
        color: white !important;
    }
</style>
""", unsafe_allow_html=True)

# Initialize session state
if 'bot' not in st.session_state:
    st.session_state.bot = None
if 'config' not in st.session_state:
    st.session_state.config = None
if 'bot_running' not in st.session_state:
    st.session_state.bot_running = False
if 'logs' not in st.session_state:
    st.session_state.logs = []
if 'positions' not in st.session_state:
    st.session_state.positions = {}
if 'profit_stats' not in st.session_state:
    st.session_state.profit_stats = {"total_profit": 0, "wins": 0, "losses": 0, "trades": []}
if 'balance' not in st.session_state:
    st.session_state.balance = {}
if 'last_update' not in st.session_state:
    st.session_state.last_update = datetime.now()

# Function to handle bot output for UI
def handle_bot_output(message, level="info", data=None):
    """Handle outputs from the bot to display in UI"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    
    # Thread-safe way to update session state
    log_entry = {"timestamp": timestamp, "message": message, "level": level, "data": data}
    
    # Add to logs (this must be called from the main thread)
    if hasattr(st, 'session_state') and hasattr(st.session_state, 'logs'):
        st.session_state.logs.append(log_entry)
    else:
        # If can't access session state, just log to console
        print(f"[{timestamp}] {level.upper()}: {message}")
    
    # Update UI data if provided
    if data and hasattr(st, 'session_state'):
        if data.get("type") == "new_position" or data.get("type") == "buy_order":
            # Update positions
            symbol = data.get("symbol")
            if symbol and hasattr(st.session_state, 'positions'):
                position = {
                    "symbol": symbol,
                    "size": data.get("size", 0),
                    "price": data.get("price", 0),
                    "timestamp": datetime.now()
                }
                st.session_state.positions[symbol] = position
        
        elif data.get("type") == "close_position" and hasattr(st.session_state, 'profit_stats'):
            # Update profit stats
            profit = data.get("profit_amount", 0)
            st.session_state.profit_stats["total_profit"] += profit
            if profit > 0:
                st.session_state.profit_stats["wins"] += 1
            else:
                st.session_state.profit_stats["losses"] += 1
                
            # Remove from positions
            symbol = data.get("symbol")
            if symbol and symbol in st.session_state.positions:
                del st.session_state.positions[symbol]
    
    # Update timestamp
    if hasattr(st, 'session_state') and hasattr(st.session_state, 'last_update'):
        st.session_state.last_update = datetime.now()

# Function to load config
def load_config(config_file):
    """Load configuration from JSON file"""
    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
        return config
    except Exception as e:
        st.error(f"Failed to load configuration: {e}")
        return None

# Function to save config
def save_config(config, config_file):
    """Save configuration to JSON file"""
    try:
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)
        return True
    except Exception as e:
        st.error(f"Failed to save configuration: {e}")
        return False

# Function to start the bot
def start_bot():
    """Start the trading bot"""
    if st.session_state.config:
        try:
            config_file = "current_config.json"
            save_config(st.session_state.config, config_file)
            
            # Initialize bot with config
            bot = CryptoTradingBot(config_file)
            
            # Set output handler
            bot.set_output_handler(handle_bot_output)
            
            # Log successful initialization
            bot.log("Bot initialized successfully")
            
            # Store bot in session state
            st.session_state.bot = bot
            st.session_state.bot_running = True
            
            # Start bot thread
            bot_thread = threading.Thread(target=bot.run)
            bot_thread.daemon = True
            bot_thread.start()
            
            st.success("Bot started successfully!")
        except Exception as e:
            st.error(f"Failed to start bot: {e}")
    else:
        st.error("Please configure the bot first.")

# Function to stop the bot
def stop_bot():
    """Stop the trading bot"""
    if st.session_state.bot:
        try:
            st.session_state.bot.running = False
            st.session_state.bot_running = False
            st.session_state.bot = None
            st.success("Bot stopped successfully!")
        except Exception as e:
            st.error(f"Failed to stop bot: {e}")
    else:
        st.warning("Bot is not running.")

# Function to update bot status
def update_bot_status():
    """Update bot status data"""
    if st.session_state.bot and st.session_state.bot_running:
        try:
            # Process any pending messages
            st.session_state.bot.process_message_queue()
            
            # Run a single iteration to update data
            st.session_state.bot.run(single_iteration=True)
            
            # Get status summary
            status = st.session_state.bot.get_status_summary()
            
            # Update session state
            st.session_state.positions = status.get("active_positions", {})
            st.session_state.profit_stats["total_profit"] = status.get("profit", 0)
            st.session_state.profit_stats["wins"] = status.get("wins", 0)
            st.session_state.profit_stats["losses"] = status.get("losses", 0)
            st.session_state.balance = status.get("balance", {})
            
            # Process any new messages
            st.session_state.bot.process_message_queue()
            
            # Update timestamp
            st.session_state.last_update = datetime.now()
        except Exception as e:
            st.error(f"Failed to update bot status: {e}")

# Sidebar
with st.sidebar:
    st.title("Bot Controls")
    
    # Start/Stop Bot
    col1, col2 = st.columns(2)
    with col1:
        if not st.session_state.bot_running:
            if st.button("Start Bot", use_container_width=True):
                if st.session_state.config:
                    start_bot()
                else:
                    st.error("Please configure the bot first.")
    with col2:
        if st.session_state.bot_running:
            if st.button("Stop Bot", use_container_width=True):
                stop_bot()
    
    # Bot Status
    st.subheader("Bot Status")
    status_color = "status-good" if st.session_state.bot_running else "status-bad"
    st.markdown(f"<div class='info-box'><strong>Status:</strong> <span class='{status_color}'>{('Running' if st.session_state.bot_running else 'Stopped')}</span><br><strong>Last Update:</strong> {st.session_state.last_update.strftime('%H:%M:%S')}</div>", unsafe_allow_html=True)
    
    # Manual update button
    if st.button("Update Status", use_container_width=True):
        update_bot_status()
    
    # Balance display
    if 'balance' in st.session_state and st.session_state.balance:
        st.subheader("Account Balance")
        if 'accounts' in st.session_state.balance:
            balance_html = "<div class='info-box'>"
            for account in st.session_state.balance['accounts']:
                currency = account.get('currency', '')
                available = float(account.get('available', 0))
                balance_html += f"<strong>{currency}:</strong> {available:.2f}<br>"
            balance_html += "</div>"
            st.markdown(balance_html, unsafe_allow_html=True)
    
    # Profit statistics
    st.subheader("Profit Statistics")
    profit = st.session_state.profit_stats["total_profit"]
    profit_color = "status-good" if profit >= 0 else "status-bad"
    wins = st.session_state.profit_stats["wins"]
    losses = st.session_state.profit_stats["losses"]
    win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
    
    st.markdown(f"""<div class='info-box'>
    <strong>Total Profit:</strong> <span class='{profit_color}'>{profit:.2f}</span><br>
    <strong>Win Rate:</strong> {win_rate:.1f}% ({wins}/{wins+losses})
    </div>""", unsafe_allow_html=True)
    
    # Show active positions
    st.subheader("Active Positions")
    if st.session_state.positions:
        for pos_id, position in st.session_state.positions.items():
            symbol = position.get('symbol', '')
            size = position.get('size', 0)
            price = position.get('price', 0)
            timestamp = position.get('timestamp', datetime.now())
            if isinstance(timestamp, str):
                timestamp = datetime.fromisoformat(timestamp)
            
            time_str = timestamp.strftime("%H:%M:%S")
            st.markdown(f"""<div class='info-box'>
            <strong>{symbol}</strong><br>
            Size: {size}<br>
            Entry: {price:.2f}<br>
            Time: {time_str}
            </div>""", unsafe_allow_html=True)
    else:
        st.info("No active positions")

# Main content
st.title("Crypto Trading Bot")

# Tabs for different sections
tabs = st.tabs(["Dashboard", "Bot Configuration", "Trading Settings", "Logs"])

# Dashboard tab
with tabs[0]:
    st.header("Trading Dashboard")
    
    # Key metrics
    metrics_cols = st.columns(4)
    with metrics_cols[0]:
        st.metric("Active Positions", len(st.session_state.positions))
    with metrics_cols[1]:
        profit = st.session_state.profit_stats["total_profit"]
        st.metric("Total Profit", f"{profit:.2f}")
    with metrics_cols[2]:
        wins = st.session_state.profit_stats["wins"]
        losses = st.session_state.profit_stats["losses"]
        st.metric("Win/Loss", f"{wins}/{losses}")
    with metrics_cols[3]:
        win_rate = (wins / (wins + losses) * 100) if (wins + losses) > 0 else 0
        st.metric("Win Rate", f"{win_rate:.1f}%")
    
    # Recent trades and positions
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Active Positions")
        if st.session_state.positions:
            position_data = []
            for pos_id, pos in st.session_state.positions.items():
                if isinstance(pos, dict):  # Make sure it's a valid position dict
                    position_data.append({
                        "Symbol": pos.get('symbol', ''),
                        "Size": pos.get('size', 0),
                        "Entry Price": f"{pos.get('price', 0):.2f}",
                        "Time": pos.get('timestamp', datetime.now()).strftime("%H:%M:%S") 
                            if not isinstance(pos.get('timestamp'), str) 
                            else pos.get('timestamp', '')
                    })
            
            if position_data:
                positions_df = pd.DataFrame(position_data)
                st.dataframe(positions_df, use_container_width=True)
            else:
                st.info("No active positions")
        else:
            st.info("No active positions")
    
    with col2:
        st.subheader("Recent Trades")
        if st.session_state.profit_stats and 'trades' in st.session_state.profit_stats:
            trades = st.session_state.profit_stats.get('trades', [])
            if trades:
                recent_trades = trades[-10:]  # Get last 10 trades
                trade_data = []
                for trade in recent_trades:
                    if isinstance(trade, dict):  # Make sure it's a valid trade dict
                        trade_data.append({
                            "Symbol": trade.get('symbol', ''),
                            "Profit %": f"{trade.get('profit_pct', 0):.2f}%",
                            "Profit": f"{trade.get('profit_amount', 0):.2f}",
                            "Time": trade.get('timestamp', datetime.now()).strftime("%H:%M:%S")
                                if not isinstance(trade.get('timestamp'), str)
                                else trade.get('timestamp', '')
                        })
                
                if trade_data:
                    trades_df = pd.DataFrame(trade_data)
                    st.dataframe(trades_df, use_container_width=True)
                else:
                    st.info("No recent trades")
            else:
                st.info("No recent trades")
        else:
            st.info("No recent trades")
    
    # Placeholder for a chart of profit over time
    st.subheader("Profit Chart")
    
    # Create sample data if no trades exist
    if not st.session_state.profit_stats.get('trades', []):
        chart_data = pd.DataFrame({
            'timestamp': pd.date_range(start=datetime.now()-timedelta(hours=24), periods=10, freq='h'),
            'profit': [0] * 10
        })
    else:
        # Use actual trade data
        trades = st.session_state.profit_stats.get('trades', [])
        timestamps = []
        profits = []
        cumulative_profit = 0
        
        for trade in trades:
            if isinstance(trade, dict):
                timestamp = trade.get('timestamp', datetime.now())
                if isinstance(timestamp, str):
                    try:
                        timestamp = datetime.fromisoformat(timestamp)
                    except:
                        timestamp = datetime.now()
                
                profit = trade.get('profit_amount', 0)
                cumulative_profit += profit
                
                timestamps.append(timestamp)
                profits.append(cumulative_profit)
        
        if timestamps:
            chart_data = pd.DataFrame({
                'timestamp': timestamps,
                'profit': profits
            })
        else:
            chart_data = pd.DataFrame({
                'timestamp': pd.date_range(start=datetime.now()-timedelta(hours=24), periods=10, freq='h'),
                'profit': [0] * 10
            })
    
    # Create a profit chart
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=chart_data['timestamp'],
        y=chart_data['profit'],
        mode='lines+markers',
        name='Profit',
        line=dict(color='#4CAF50', width=2),
        marker=dict(color='#2986cc', size=8)
    ))
    
    fig.update_layout(
        title='Cumulative Profit Over Time',
        xaxis_title='Time',
        yaxis_title='Profit',
        plot_bgcolor='#252547',
        paper_bgcolor='#252547',
        font=dict(color='white'),
        margin=dict(l=10, r=10, t=40, b=10)
    )
    
    st.plotly_chart(fig, use_container_width=True)

# Bot Configuration tab
with tabs[1]:
    st.header("Bot Configuration")
    
    # Load default config if none exists
    if not st.session_state.config:
        default_config = {
            "connection": {
                "exchange": "kraken",
                "api_key": "",
                "secret": "",
                "ws_url": "wss://futures.kraken.com/ws/v1"
            },
            "coins": {
                "quote_currency": "GBP",
                "allow_all_coins": False,
                "selected_coins": ["BTC", "ETH", "DOT", "BCH"],
                "percentage_buy_amount": 10,
                "minimum_amount": 28.42,
                "force_minimum_buy_amount": False,
                "maximum_amount_allocated": 100
            },
            "buy_settings": {
                "order_type": "market",
                "max_open_time_buy": 5,
                "max_open_positions": 10,
                "max_percentage_open_positions_per_coin": 100,
                "enable_cooldown": True,
                "cooldown_when": "after_buys_and_sells",
                "cooldown_period": 30,
                "only_1_open_buy_order_per_coin": True,
                "only_buy_when_positive_pairs": False,
                "positive_pairs_timeframe": "1d",
                "only_buy_if_not_already_in_positions": True,
                "percent_range": 0.4,
                "auto_merge_positions": False,
                "leverage": 3
            },
            "place_order_trigger": {
                "follow_chart": True,
                "percentage_change": 0.5
            },
            "sell_settings": {
                "trailing_stop_loss_percentage": 0.25,
                "arm_trailing_stop_loss_at": 1.25,
                "trailing_stop_loss_timeout": 0,
                "use_trailing_stop_loss_only": True,
                "only_sell_with_profit": True,
                "reset_stop_loss_after_failed_orders": True
            }
        }
        st.session_state.config = default_config
    
    # Connection settings
    st.subheader("Connection Settings")
    
    connection_col1, connection_col2 = st.columns(2)
    
    with connection_col1:
        api_key = st.text_input(
            "API Key",
            value=st.session_state.config["connection"]["api_key"],
            type="password"
        )
        st.session_state.config["connection"]["api_key"] = api_key
    
    with connection_col2:
        api_secret = st.text_input(
            "API Secret",
            value=st.session_state.config["connection"]["secret"],
            type="password"
        )
        st.session_state.config["connection"]["secret"] = api_secret
    
    # Quote currency and coins settings
    st.subheader("Quote Currency & Coins")
    
    # Quote currency
    quote_currency = st.selectbox(
        "Quote Currency",
        ["GBP", "USD", "EUR"],
        index=0 if st.session_state.config["coins"]["quote_currency"] == "GBP" else 
              1 if st.session_state.config["coins"]["quote_currency"] == "USD" else 2
    )
    st.session_state.config["coins"]["quote_currency"] = quote_currency
    
    # Coin selection
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("<div class='settings-box'>", unsafe_allow_html=True)
        allow_all_coins = st.toggle(
            "Allow All Coins",
            value=st.session_state.config["coins"]["allow_all_coins"]
        )
        st.session_state.config["coins"]["allow_all_coins"] = allow_all_coins
        st.markdown("</div>", unsafe_allow_html=True)
    
    # Get selected coins
    all_available_coins = ["BTC", "ETH", "BCH", "DOT", "AAVE", "ALGO", "ADA", "ATOM", "FIL", "EUR"]
    selected_coins = st.session_state.config["coins"]["selected_coins"]
    
    with col2:
        if not allow_all_coins:
            selected_coins = st.multiselect(
                "Select Coins to Trade",
                options=all_available_coins,
                default=selected_coins
            )
            st.session_state.config["coins"]["selected_coins"] = selected_coins
    
    # Buy amount settings
    st.subheader("Buy Amount Settings")
    
    col1, col2 = st.columns(2)
    
    with col1:
        percentage_buy = st.slider(
            "Percentage Buy Amount",
            min_value=1,
            max_value=100,
            value=int(st.session_state.config["coins"]["percentage_buy_amount"]),
            step=1
        )
        st.session_state.config["coins"]["percentage_buy_amount"] = percentage_buy
        
        st.markdown(f"<div class='info-box'>Estimated buy amount: <strong>{46.86 * percentage_buy / 10:.2f} {quote_currency}</strong></div>", unsafe_allow_html=True)
    
    with col2:
        min_amount = st.number_input(
            f"Minimum {quote_currency} Per Order",
            min_value=1.0,
            max_value=1000.0,
            value=float(st.session_state.config["coins"]["minimum_amount"]),
            step=0.01
        )
        st.session_state.config["coins"]["minimum_amount"] = min_amount
        
        force_min = st.checkbox(
            "Force Minimum Buy Amount",
            value=st.session_state.config["coins"]["force_minimum_buy_amount"]
        )
        st.session_state.config["coins"]["force_minimum_buy_amount"] = force_min
    
    max_amount = st.number_input(
        f"Maximum {quote_currency} Amount Allocated",
        min_value=0.0,
        max_value=10000.0,
        value=float(st.session_state.config["coins"]["maximum_amount_allocated"]) if st.session_state.config["coins"]["maximum_amount_allocated"] else 0.0,
        step=1.0
    )
    if max_amount > 0:
        st.session_state.config["coins"]["maximum_amount_allocated"] = max_amount
    else:
        st.session_state.config["coins"]["maximum_amount_allocated"] = None
    
    # Save config button
    if st.button("Save Configuration", use_container_width=True):
        # Save to file
        if save_config(st.session_state.config, "saved_config.json"):
            st.success("Configuration saved successfully!")
        else:
            st.error("Failed to save configuration.")

# Trading Settings tab
with tabs[2]:
    st.header("Trading Settings")
    
    # Buy settings
    st.subheader("Buy Settings")
    
    col1, col2 = st.columns(2)
    
    with col1:
        order_type = st.selectbox(
            "Order Type",
            ["market", "limit"],
            index=0 if st.session_state.config["buy_settings"]["order_type"].lower() == "market" else 1
        )
        st.session_state.config["buy_settings"]["order_type"] = order_type
        
        max_open_time = st.number_input(
            "Max Open Time Buy (minutes)",
            min_value=1,
            max_value=60,
            value=int(st.session_state.config["buy_settings"]["max_open_time_buy"]),
            step=1
        )
        st.session_state.config["buy_settings"]["max_open_time_buy"] = max_open_time
        
        max_positions = st.slider(
            "Max Open Positions",
            min_value=1,
            max_value=500,
            value=int(st.session_state.config["buy_settings"]["max_open_positions"]),
            step=1
        )
        st.session_state.config["buy_settings"]["max_open_positions"] = max_positions
    
    with col2:
        max_percentage = st.slider(
            "Max Percentage Open Positions Per Coin",
            min_value=1,
            max_value=100,
            value=int(st.session_state.config["buy_settings"]["max_percentage_open_positions_per_coin"]),
            step=1
        )
        st.session_state.config["buy_settings"]["max_percentage_open_positions_per_coin"] = max_percentage
        
        st.markdown(f"<div class='info-box'>Result: Max {max_positions * max_percentage // 100} open positions per coin</div>", unsafe_allow_html=True)
        
        leverage = st.number_input(
            "Leverage",
            min_value=1,
            max_value=100,
            value=int(st.session_state.config["buy_settings"]["leverage"]),
            step=1
        )
        st.session_state.config["buy_settings"]["leverage"] = leverage
    
    # Cooldown settings
    st.subheader("Cooldown Settings")
    
    col1, col2 = st.columns(2)
    
    with col1:
        enable_cooldown = st.toggle(
            "Enable Cooldown",
            value=st.session_state.config["buy_settings"]["enable_cooldown"]
        )
        st.session_state.config["buy_settings"]["enable_cooldown"] = enable_cooldown
        
        if enable_cooldown:
            cooldown_when = st.selectbox(
                "Cooldown When",
                ["after_buys", "after_sells", "after_buys_and_sells"],
                index=2 if st.session_state.config["buy_settings"]["cooldown_when"] == "after_buys_and_sells" else
                      1 if st.session_state.config["buy_settings"]["cooldown_when"] == "after_sells" else 0
            )
            st.session_state.config["buy_settings"]["cooldown_when"] = cooldown_when
    
    with col2:
        if enable_cooldown:
            cooldown_period = st.number_input(
                "Cooldown Period (minutes)",
                min_value=1,
                max_value=120,
                value=int(st.session_state.config["buy_settings"]["cooldown_period"]),
                step=1
            )
            st.session_state.config["buy_settings"]["cooldown_period"] = cooldown_period
    
    # Additional buy conditions
    st.subheader("Additional Buy Conditions")
    
    col1, col2 = st.columns(2)
    
    with col1:
        only_one_order = st.toggle(
            "Only 1 Open Buy Order Per Coin",
            value=st.session_state.config["buy_settings"]["only_1_open_buy_order_per_coin"]
        )
        st.session_state.config["buy_settings"]["only_1_open_buy_order_per_coin"] = only_one_order
        
        only_positive_pairs = st.toggle(
            "Only Buy When Positive Pairs",
            value=st.session_state.config["buy_settings"]["only_buy_when_positive_pairs"]
        )
        st.session_state.config["buy_settings"]["only_buy_when_positive_pairs"] = only_positive_pairs
        
        if only_positive_pairs:
            positive_timeframe = st.selectbox(
                "Positive Pairs Timeframe",
                ["1 hour", "4 hours", "1 day", "1 week"],
                index=2 if st.session_state.config["buy_settings"]["positive_pairs_timeframe"] == "1d" else
                      3 if st.session_state.config["buy_settings"]["positive_pairs_timeframe"] == "1w" else
                      1 if st.session_state.config["buy_settings"]["positive_pairs_timeframe"] == "4h" else 0
            )
            timeframe_map = {"1 hour": "1h", "4 hours": "4h", "1 day": "1d", "1 week": "1w"}
            st.session_state.config["buy_settings"]["positive_pairs_timeframe"] = timeframe_map[positive_timeframe]
    
    with col2:
        only_if_not_in_position = st.toggle(
            "Only Buy If Not Already In Position",
            value=st.session_state.config["buy_settings"]["only_buy_if_not_already_in_positions"]
        )
        st.session_state.config["buy_settings"]["only_buy_if_not_already_in_positions"] = only_if_not_in_position
        
        percent_range = st.number_input(
            "Percent Range",
            min_value=0.1,
            max_value=10.0,
            value=float(st.session_state.config["buy_settings"]["percent_range"]),
            step=0.1,
            help="Do not buy the same currency if within this percentage range of existing position"
        )
        st.session_state.config["buy_settings"]["percent_range"] = percent_range
        
        auto_merge = st.toggle(
            "Auto Merge Positions",
            value=st.session_state.config["buy_settings"]["auto_merge_positions"]
        )
        st.session_state.config["buy_settings"]["auto_merge_positions"] = auto_merge
    
    # Trigger settings
    st.subheader("Buy Trigger Settings")
    
    percentage_change = st.number_input(
        "Percentage Change to Trigger Buy",
        min_value=0.1,
        max_value=10.0,
        value=float(st.session_state.config["place_order_trigger"]["percentage_change"]),
        step=0.1
    )
    st.session_state.config["place_order_trigger"]["percentage_change"] = percentage_change
    
    # Sell settings
    st.subheader("Sell Settings")
    
    col1, col2 = st.columns(2)
    
    with col1:
        trailing_stop = st.toggle(
            "Enable Trailing Stop-Loss",
            value=True  # Always enabled
        )
        
        trailing_pct = st.number_input(
            "Trailing Stop-Loss Percentage",
            min_value=0.1,
            max_value=10.0,
            value=float(st.session_state.config["sell_settings"]["trailing_stop_loss_percentage"]),
            step=0.01
        )
        st.session_state.config["sell_settings"]["trailing_stop_loss_percentage"] = trailing_pct
        
        arm_at = st.number_input(
            "Arm Trailing Stop-Loss At",
            min_value=0.1,
            max_value=20.0,
            value=float(st.session_state.config["sell_settings"]["arm_trailing_stop_loss_at"]),
            step=0.01
        )
        st.session_state.config["sell_settings"]["arm_trailing_stop_loss_at"] = arm_at
    
    with col2:
        timeout = st.number_input(
            "Trailing Stop-Loss Timeout (minutes, 0=no timeout)",
            min_value=0,
            max_value=1440,
            value=int(st.session_state.config["sell_settings"]["trailing_stop_loss_timeout"]),
            step=1
        )
        st.session_state.config["sell_settings"]["trailing_stop_loss_timeout"] = timeout
        
        use_trailing_only = st.toggle(
            "Use Trailing Stop-Loss Only",
            value=st.session_state.config["sell_settings"]["use_trailing_stop_loss_only"]
        )
        st.session_state.config["sell_settings"]["use_trailing_stop_loss_only"] = use_trailing_only
        
        only_sell_with_profit = st.toggle(
            "Only Sell With Profit",
            value=st.session_state.config["sell_settings"]["only_sell_with_profit"]
        )
        st.session_state.config["sell_settings"]["only_sell_with_profit"] = only_sell_with_profit
        
        reset_after_failed = st.toggle(
            "Reset Stop-Loss After Failed Orders",
            value=st.session_state.config["sell_settings"]["reset_stop_loss_after_failed_orders"]
        )
        st.session_state.config["sell_settings"]["reset_stop_loss_after_failed_orders"] = reset_after_failed
    
    # Save settings button
    if st.button("Save Trading Settings", use_container_width=True):
        # Save to file
        if save_config(st.session_state.config, "saved_config.json"):
            st.success("Trading settings saved successfully!")
        else:
            st.error("Failed to save trading settings.")

# Logs tab
with tabs[3]:
    st.header("Bot Logs")
    
    # Clear logs button
    if st.button("Clear Logs"):
        st.session_state.logs = []
    
    # Show logs
    log_container = st.container()
    
    with log_container:
        # Reverse logs to show newest first
        for log in reversed(st.session_state.logs[-100:] if len(st.session_state.logs) > 0 else []):  # Limit to last 100 logs
            timestamp = log["timestamp"]
            message = log["message"]
            level = log["level"]
            
            # Style based on log level
            if level == "error":
                st.markdown(f"<span style='color:#F44336'>[{timestamp}] ERROR: {message}</span>", unsafe_allow_html=True)
            elif level == "warning":
                st.markdown(f"<span style='color:#FF9800'>[{timestamp}] WARNING: {message}</span>", unsafe_allow_html=True)
            else:
                st.markdown(f"[{timestamp}] {message}", unsafe_allow_html=True)

# Main function
def main():
    # Process message queue if bot is running
    if st.session_state.bot and st.session_state.bot_running:
        st.session_state.bot.process_message_queue()
    
    # Load config if exists
    if os.path.exists("saved_config.json") and not st.session_state.config:
        st.session_state.config = load_config("saved_config.json")
    
    # Update bot status periodically if running
    if st.session_state.bot_running:
        update_bot_status()

if __name__ == "__main__":
    main()
