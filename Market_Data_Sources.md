# Market Data Sources Documentation

## Overview

This document provides a comprehensive reference of all market data sources used by the Agentic Crypto Trading System.

---

## 1. External API Sources

### 1.1 Binance API

| Attribute | Details |
|-----------|---------|
| **Provider Class** | `OHLCVProvider`, `OrderBookProvider` |
| **Authentication** | None required (public API) |
| **Base URL** | `https://api.binance.com/api/v3` |

#### Endpoints

| Endpoint | Purpose | Parameters |
|----------|---------|------------|
| `/klines` | OHLCV Candles | `symbol`, `interval`, `limit` |
| `/ticker/price` | Current Price | `symbol` |
| `/depth` | Order Book | `symbol`, `limit` |

#### Supported Symbols
- BTCUSDT
- SOLUSDT
- ETHUSDT

#### Cache TTL
- OHLCV: 30 seconds
- Order Book: 5 seconds

---

### 1.2 Binance Futures API

| Attribute | Details |
|-----------|---------|
| **Provider Class** | `OnChainProvider` |
| **Authentication** | None required (public API) |
| **Base URL** | `https://fapi.binance.com/fapi/v1` |

#### Endpoints

| Endpoint | Purpose | Parameters |
|----------|---------|------------|
| `/fundingRate` | Funding Rates | `symbol`, `limit` |

#### Supported Symbols
- BTCUSDT
- SOLUSDT

#### Cache TTL
- 10 minutes

---

### 1.3 CoinGecko API

| Attribute | Details |
|-----------|---------|
| **Provider Class** | `OHLCVProvider` |
| **Authentication** | Optional (`coingecko_api_key`) |
| **Auth Header** | `x-cg-pro-api-key` |
| **Base URL** | `https://api.coingecko.com/api/v3` |

#### Endpoints

| Endpoint | Purpose | Parameters |
|----------|---------|------------|
| `/coins/{coin_id}/ohlc` | OHLC Candles | `vs_currency`, `days` |

#### Supported Coin IDs
- bitcoin
- solana
- ethereum

#### Notes
- Used as fallback source when Binance is unavailable
- Returns OHLC data (no volume)
- Period: 30 days

---

### 1.4 CryptoPanic API

| Attribute | Details |
|-----------|---------|
| **Provider Class** | `SentimentProvider` |
| **Authentication** | Required (`cryptopanic_api_key`) |
| **Auth Method** | Query parameter `auth_token` |
| **Base URL** | `https://cryptopanic.com/api/v1` |

#### Endpoints

| Endpoint | Purpose | Parameters |
|----------|---------|------------|
| `/posts/` | News Headlines | `auth_token`, `currencies`, `filter` |

#### Data Provided
- News headlines
- Bullish/bearish sentiment counts
- Top keywords from news

#### Cache TTL
- 5 minutes

---

### 1.5 Alternative.me API (Fear & Greed Index)

| Attribute | Details |
|-----------|---------|
| **Provider Class** | `SentimentProvider` |
| **Authentication** | None required (public API) |
| **Base URL** | `https://api.alternative.me` |

#### Endpoints

| Endpoint | Purpose | Parameters |
|----------|---------|------------|
| `/fng/` | Fear & Greed Index | None |

#### Data Provided
- Daily fear/greed index (0-100 scale)
- Market psychology indicator

#### Cache TTL
- 5 minutes

---

### 1.6 CryptoQuant API

| Attribute | Details |
|-----------|---------|
| **Provider Class** | `OnChainProvider` |
| **Authentication** | Required (`cryptoquant_api_key`) |
| **Auth Header** | `Authorization: Bearer {key}` |
| **Base URL** | `https://api.cryptoquant.com/v1` |

#### Endpoints

| Endpoint | Purpose |
|----------|---------|
| `/btc/exchange-flows/reserve` | Exchange Reserve Data |
| `/btc/exchange-flows/netflow` | Exchange Netflow Data |
| `/btc/miner-flows/mpi` | Miner Position Index |

#### Data Provided
- Exchange inflows/outflows/netflow
- Miner activity metrics

#### Cache TTL
- 10 minutes

---

### 1.7 Glassnode API

| Attribute | Details |
|-----------|---------|
| **Provider Class** | `OnChainProvider` |
| **Authentication** | Required (`glassnode_api_key`) |
| **Auth Method** | Query parameter `api_key` |
| **Base URL** | `https://api.glassnode.com/v1/metrics` |

#### Endpoints

| Endpoint | Purpose |
|----------|---------|
| `/indicators/sopr` | Spent Output Profit Ratio |
| `/indicators/net_unrealized_profit_loss` | NUPL Metric |
| `/market/mvrv` | Market Value to Realized Value |
| `/addresses/active_count` | Active Addresses Count |

#### Data Provided
- Profitability metrics (SOPR, NUPL, MVRV)
- Network activity (active addresses)

#### Cache TTL
- 10 minutes

---

## 2. Provider Classes

All provider classes are located in: `agentic_trader/data/providers.py`

### 2.1 OHLCVProvider (Lines 66-210)

**Purpose:** Fetches OHLCV (Open, High, Low, Close, Volume) candlestick data

**Sources:**
- Primary: Binance API
- Fallback: CoinGecko API

**Configuration:**
- Interval: 1-hour candles
- Lookback: 200 periods (configurable)

---

### 2.2 SentimentProvider (Lines 475-613)

**Purpose:** Aggregates market sentiment from news and indices

**Sources:**
- CryptoPanic (news sentiment)
- Alternative.me (Fear & Greed Index)

**Metrics Provided:**
- News sentiment score (-1.0 to 1.0)
- Fear & Greed index value (0-100)
- Bullish/bearish mention counts
- Top keywords from news
- Overall sentiment score

---

### 2.3 OnChainProvider (Lines 617-754)

**Purpose:** Fetches blockchain and derivatives metrics

**Sources:**
- CryptoQuant (exchange flows, miner data)
- Glassnode (on-chain metrics)
- Binance Futures (funding rates)

**Metrics Provided:**
- Exchange inflows/outflows/netflow
- Network activity (active addresses, transaction counts)
- Whale transactions
- Profitability metrics (SOPR, NUPL, MVRV)
- Mining activity (Miner Position Index)
- Derivatives (funding rates, open interest, long/short ratio)

---

### 2.4 OrderBookProvider (Lines 758-847)

**Purpose:** Fetches order book depth data

**Source:** Binance API

**Metrics Provided:**
- Bid depth (total value on bids)
- Ask depth (total value on asks)
- Imbalance ratio ((bid-ask)/(bid+ask))
- Spread (in price units and percentage)
- Mid price
- Large bid/ask walls (>3x average size)

---

### 2.5 TechnicalAnalyzer (Lines 214-471)

**Purpose:** Calculates technical indicators from OHLCV data

**Trend Indicators:**
- SMA: 20, 50, 200 periods
- EMA: 12, 26 periods
- ADX (Average Directional Index)
- SuperTrend

**Momentum Indicators:**
- RSI (14 period)
- MACD (12, 26, 9)
- Stochastic K/D (14, 3)

**Volatility Indicators:**
- ATR (14 period)
- Bollinger Bands (20, 2 std dev)

**Volume Indicators:**
- OBV (On-Balance Volume)
- VWAP (Volume Weighted Average Price)
- Volume SMA (20 period)

---

### 2.6 RegimeDetector (Lines 851-924)

**Purpose:** Classifies current market conditions

**Detection Regimes:**
- TRENDING_UP
- TRENDING_DOWN
- RANGING
- HIGH_VOLATILITY
- LOW_VOLATILITY
- UNKNOWN

---

### 2.7 DataAggregator (Lines 927-972)

**Purpose:** Combines all providers into unified MarketContext

**Output Contains:**
- OHLCV candles
- Technical indicators
- Order book metrics
- Sentiment data
- On-chain metrics
- Market regime with confidence score
- Current price

---

## 3. Trading Symbols Mapping

| Trading Pair | Binance Symbol | CoinGecko ID |
|--------------|----------------|--------------|
| BTC/USDT | BTCUSDT | bitcoin |
| SOL/USDT | SOLUSDT | solana |
| ETH/USDT | ETHUSDT | ethereum |

---

## 4. API Configuration

Configuration is located in: `agentic_trader/config/settings.py`

### APIConfig Class (Lines 75-89)

| Config Key | Description | Required |
|------------|-------------|----------|
| `claude_api_key` | Anthropic Claude API | Yes |
| `coingecko_api_key` | CoinGecko Pro API | No |
| `cryptopanic_api_key` | CryptoPanic News API | No |
| `cryptoquant_api_key` | CryptoQuant On-Chain Data | No |
| `glassnode_api_key` | Glassnode On-Chain Metrics | No |
| `api_rate_limit` | Rate limit between API calls | No (default: 0.5s) |

---

## 5. Rate Limiting & Caching Summary

| Data Type | Cache TTL | Rate Limit |
|-----------|-----------|------------|
| OHLCV Data | 30 seconds | 0.5 sec between calls |
| Current Price | 30 seconds | 0.5 sec between calls |
| Order Book | 5 seconds | 0.5 sec between calls |
| Sentiment | 5 minutes | 0.5 sec between calls |
| On-Chain | 10 minutes | 0.5 sec between calls |

---

## 6. Key Files Reference

| File | Description | Lines |
|------|-------------|-------|
| `agentic_trader/data/providers.py` | Main data provider module | 973 |
| `agentic_trader/config/settings.py` | Configuration & data structures | 636 |
| `agentic_trader/agents/agents.py` | Agent analysis module | 693 |

---

## 7. Data Flow Diagram

```
                    +-------------------+
                    |  DataAggregator   |
                    +-------------------+
                            |
        +-------------------+-------------------+
        |         |         |         |         |
        v         v         v         v         v
  +---------+ +-------+ +--------+ +--------+ +--------+
  | OHLCV   | | Order | | Senti- | | OnChain| | Regime |
  |Provider | | Book  | | ment   | |Provider| |Detector|
  +---------+ +-------+ +--------+ +--------+ +--------+
        |         |         |         |
        v         v         v         v
  +---------+ +-------+ +--------+ +--------+
  | Binance | |Binance| |Crypto  | |Crypto  |
  |CoinGecko| |       | |Panic   | |Quant   |
  +---------+ +-------+ |Alt.me  | |Glassnode
                        +--------+ |Binance |
                                   +--------+
```

---

*Document generated from codebase analysis*
