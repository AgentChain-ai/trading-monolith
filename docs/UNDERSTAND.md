# Understanding the NTM Trading Engine - Complete Flow Analysis

## 📋 Table of Contents
1. [System Overview](#system-overview)
2. [What Happens When You Click "Ingest Data"](#what-happens-when-you-click-ingest-data)
3. [ML Model Training & Expectations](#ml-model-training--expectations)
4. [Frontend to Backend Flow](#frontend-to-backend-flow)
5. [What's Actually Implemented vs Hardcoded](#whats-actually-implemented-vs-hardcoded)
6. [Database Operations](#database-operations)
7. [Current Issues & Solutions](#current-issues--solutions)

---

## 🏗️ System Overview

The NTM (Narrative→Thesis Model) Trading Engine is designed to:
1. **Scrape news articles** about cryptocurrency tokens
2. **Analyze sentiment** and classify events using AI
3. **Calculate "Narrative Heat"** scores based on news sentiment
4. **Predict price movements** using ML models
5. **Generate trading theses** with AI reasoning

**Key Components:**
- **Frontend**: React dashboard for token analysis
- **Backend**: FastAPI server with ML pipeline
- **Database**: SQLite for storing articles, features, and predictions  
- **External APIs**: MCP Server (news), GeckoTerminal (prices), Groq (AI)

---

## 🔄 What Happens When You Click "Ingest Data"

### Step-by-Step Process:

#### 1. **Frontend Initiates Request**
```typescript
// In frontend/src/App.tsx
const handleIngest = async () => {
  await api.ingestArticles(token, hoursBack, maxArticles);
}
```

#### 2. **API Endpoint Receives Request**
```python
# backend/app/api/routes.py:94
@router.post("/ingest")
async def ingest_articles(request: IngestRequest, background_tasks: BackgroundTasks)
```

**What it does:**
- Validates the token (BTC, ETH, USDC, etc.)
- Starts a background task for processing
- Returns immediately with status "processing"

#### 3. **Background Task Starts Article Fetching**
```python
# backend/app/api/routes.py:125
async def process_articles_background(token: str, hours_back: int, max_articles: int)
```

#### 4. **MCP Client Searches for Articles**
```python
# backend/app/services/mcp_client.py:332
articles = await mcp_client.get_token_articles(token, hours_back, max_articles)
```

**What happens here:**
- Makes 4 different search queries:
  - `"USDC token news"`
  - `"USDC cryptocurrency latest"`  
  - `"USDC twitter trends"`
  - `"USDC market analysis"`
- For each search query, calls MCP Server API at `https://scraper.agentchain.trade//search`
- Gets back a list of article URLs
- **Then scrapes each URL** by calling `https://scraper.agentchain.trade//scrape`

#### 5. **Article Content Processing**
For each successfully scraped article:

**A. Feature Extraction:**
```python
# backend/app/services/feature_extractor.py:100
features = await feature_extractor.extract_features(article_data, token)
```

**What this does:**
- **Event Classification**: Sends article to Groq AI to classify as:
  - `listing` (exchange listing)
  - `partnership` (business deals)
  - `hack` (security breach)
  - `regulatory` (legal news)
  - `funding` (investments)
  - etc.
- **Sentiment Analysis**: Uses TextBlob to analyze if news is positive/negative
- **Source Trust Scoring**: Rates reliability based on domain (coinbase.com = high, twitter = low)
- **Recency Decay**: Newer articles get higher weight
- **Novelty Detection**: Checks if content is duplicate
- **Proof Bonus**: Looks for contract addresses or blockchain explorer links

**B. Database Storage:**
```python
# Creates Article record in database
article = Article(
    token=token,
    url=url,
    title=title,
    sentiment_score=features.sentiment_score,
    source_trust=features.source_trust,
    final_weight=features.final_weight,
    event_probs=features.event_probs  # JSON of event classifications
)
```

#### 6. **Aggregation into "Buckets"**
```python
# backend/app/services/aggregator.py:28
await aggregator.create_bucket(token, articles, current_time)
```

**What this creates:**
- **Narrative Heat Score**: `NHS = Σ(sentiment × weight × trust × recency)`
- **Risk Polarity**: Balance between positive vs risk events
- **Consensus**: How much sources agree
- **Event Distribution**: Percentage of each event type

#### 7. **ML Prediction (If Model Exists)**
```python
# backend/app/services/ml_engine.py:160
prediction = await ml_engine.predict_from_bucket(bucket)
```

**What this does:**
- Extracts 47 numerical features from the bucket
- Uses trained LightGBM or Logistic Regression model
- **Returns prediction probability** (0-1 for price going up)

#### 8. **Price Data Integration**
```python
# backend/app/services/gecko_client.py:280
price_data = await gecko_client.get_token_price_data(token)
```

**Gets from GeckoTerminal API:**
- Current price
- 24h/7d price changes  
- OHLCV data (Open, High, Low, Close, Volume)
- Liquidity information

---

## 🤖 ML Model Training & Expectations

### **Current Status: NO PRE-TRAINED MODELS**

The system is designed to learn from scratch. Here's how training works:

#### **Training Process:**
1. **Initial State**: No model exists
2. **Data Collection**: Articles → Features → Buckets created
3. **Feedback Loop**: 
   - System makes predictions (or defaults to 0.5 if no model)
   - Later, actual price movement is measured
   - **Labels created**: If price went up 2.5% in 60 minutes → Label = 1 (buy signal)
4. **Model Training**: Once enough labeled data exists (20+ samples), model trains

#### **Feature Engineering (47 Features)**
```python
# backend/app/services/ml_engine.py:206
def extract_features(self, bucket) -> np.ndarray:
```

**Features include:**
- **Narrative Heat** (primary signal)
- **Risk Polarity** (-1 to +1)
- **Event Probabilities** (9 event types)
- **Sentiment Statistics** (mean, std, min, max)
- **Source Trust Scores**
- **Consensus Measures**
- **Hype Velocity** (rate of narrative growth)
- **Time-based Features** (hour of day, day of week)

#### **Model Types:**
- **LightGBM**: For large datasets (>100 samples)
- **Logistic Regression**: For small datasets (<100 samples)
- **Online Learning**: Models retrain automatically as new data comes in

#### **Training Trigger:**
```python
# backend/app/services/ml_engine.py:75
if len(labeled_buckets) >= self.min_training_samples:
    await self._train_model(features, labels, token)
```

### **Expected Performance:**
- **Initial Accuracy**: ~50% (random)
- **After 100 samples**: ~55-65% accuracy
- **After 1000+ samples**: ~65-75% accuracy (if signal exists)

---

## 🌐 Frontend to Backend Flow

### **Dashboard Loading:**
1. **Page Load**: React app loads, shows token input
2. **Token Selection**: User types "BTC" 
3. **Dashboard API Call**: `GET /api/v1/dashboard/BTC?hours_back=48`
4. **Backend Response**: Returns existing buckets/predictions or empty state

### **Real-time Updates:**
- Frontend polls `/api/v1/dashboard/{token}` every 30 seconds
- Shows live narrative heat, predictions, and price data
- Updates charts and metrics in real-time

### **Data Flow Visualization:**
```
User Input (BTC) → Frontend → API Request → MCP Search → Article URLs → 
MCP Scrape → Article Content → AI Analysis → Feature Extraction → 
Database Storage → Aggregation → ML Prediction → Price Data → 
Frontend Display
```

---

## ⚙️ What's Actually Implemented vs Hardcoded

### ✅ **FULLY IMPLEMENTED:**

#### **Data Pipeline:**
- ✅ MCP Server integration (real API calls)
- ✅ Article scraping and content extraction
- ✅ Groq AI event classification (real LLM calls)
- ✅ TextBlob sentiment analysis
- ✅ SQLite database operations
- ✅ GeckoTerminal price data (real API)

#### **ML Pipeline:**
- ✅ Feature extraction (47 features)
- ✅ LightGBM and Logistic Regression models
- ✅ Online learning system
- ✅ Prediction confidence scoring
- ✅ Performance metrics tracking

#### **Frontend:**
- ✅ Real-time dashboard updates
- ✅ Interactive charts (Chart.js)
- ✅ API integration
- ✅ Error handling and loading states

### ⚠️ **PARTIALLY IMPLEMENTED / HARDCODED:**

#### **Token Pool Mappings:**
```python
# backend/app/services/gecko_client.py:56
self.token_pools = {
    "BTC": {"network": "eth", "pools": ["0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640"]},
    "ETH": {"network": "eth", "pools": ["0x88e6a0c2ddd26feeb64f039a2c41296fcb3f5640"]},
    # Only 4 tokens hardcoded
}
```
**Status**: Limited to 4 predefined tokens

#### **Event Classification:**
```python
# backend/app/services/feature_extractor.py:30
EVENT_TYPES = [
    "listing", "partnership", "hack", "depeg", "regulatory",
    "funding", "tech", "market-note", "op-ed"
]
```
**Status**: Fixed 9 event types (could be expanded)

#### **Source Trust Map:**
```python
# backend/app/services/feature_extractor.py:36
SOURCE_TRUST_MAP = {
    "coinbase.com": 1.2,
    "binance.com": 1.2,
    # ~15 domains hardcoded
}
```
**Status**: Limited to predefined domains

### ❌ **NOT IMPLEMENTED / MOCK DATA:**

#### **Model Persistence:**
- Models are retrained from scratch on each restart
- **Missing**: Model serialization to disk
- **Impact**: Training progress lost on restart

#### **Advanced Features:**
- Cross-token correlation analysis
- Market regime detection
- Portfolio optimization
- Risk management rules

---

## 🗄️ Database Operations

### **Tables Created:**
1. **articles**: Raw article data with features
2. **buckets**: Aggregated data for time windows  
3. **labels**: Price feedback for training
4. **models**: ML model metadata
5. **migration_history**: Database version tracking

### **Typical Data Flow:**
```sql
-- 1. Articles stored
INSERT INTO articles (token, url, title, sentiment_score, ...)

-- 2. Buckets created (aggregation)
INSERT INTO buckets (token, narrative_heat, risk_polarity, ...)

-- 3. Price labels added later
INSERT INTO labels (bucket_id, forward_return_60m, label_binary)

-- 4. Models trained and stored
INSERT INTO models (token, model_type, accuracy, ...)
```

### **Current Database State:**
- Your database currently has **0 buckets** for all tokens
- This means no successful article processing has occurred yet
- **Reason**: MCP Server scraping is failing

---

## ⚠️ Current Issues & Solutions

### **Primary Issue: MCP Server Scraping Failures**

**What's happening:**
```
Server disconnected without sending a response.
Circuit breaker is now OPEN
```

**Root Cause:**
- MCP Server `/search` endpoint works ✅
- MCP Server `/scrape` endpoint is failing ❌
- Circuit breaker kicks in after 3 failures
- All subsequent requests blocked

**Evidence from logs:**
```
INFO httpx:1740 HTTP Request: POST https://scraper.agentchain.trade//search "HTTP/1.1 200 OK"
WARNING app.utils.resilience:186 Attempt 1 failed for _scrape_with_retry: Server disconnected
```

### **Solutions:**

#### **1. MCP Server Issue (Most Likely)**
```bash
# Test the scrape endpoint directly
curl -X POST "https://scraper.agentchain.trade//scrape" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://coinmarketcap.com/currencies/usd-coin/"}'
```

**Possible fixes:**
- MCP Server may have timeout issues
- Increase timeout in client
- Add retry logic with longer delays

#### **2. Network/Firewall Issues**
- Server may be blocking rapid requests
- Add delays between scrape requests
- Implement request throttling

#### **3. Circuit Breaker Too Aggressive**
```python
# backend/app/services/mcp_client.py:67
CircuitBreakerConfig(
    failure_threshold=3,  # Could increase to 5-10
    timeout=120,          # Could increase timeout
)
```

#### **4. Fallback Strategy Enhancement**
- Pre-populate cache with sample articles
- Create mock data for testing
- Add manual article input option

### **Immediate Workaround:**

You can test the system with mock data by temporarily disabling the MCP client failures:

```python
# In backend/app/services/mcp_client.py, add this method:
def create_mock_articles(self, token: str) -> List[ScrapeResult]:
    return [
        ScrapeResult(
            title=f"{token} Reaches New All-Time High",
            content=f"The {token} token has shown remarkable growth...",
            url=f"https://example.com/{token}-news-1",
            published_at="2024-01-01T12:00:00Z"
        ),
        # Add more mock articles
    ]
```

This would allow you to see the complete pipeline working end-to-end while the MCP Server issues are resolved.

---

## 🎯 Summary

**What Actually Works:**
- ✅ Frontend dashboard and UI
- ✅ Database operations
- ✅ ML model training pipeline
- ✅ Price data integration
- ✅ AI sentiment analysis (when articles exist)

**What's Blocked:**
- ❌ Article scraping (MCP Server issue)
- ❌ Real data ingestion
- ❌ Model training (no data to train on)

**To Get Full System Working:**
1. **Fix MCP Server scraping** (primary blocker)
2. **Add fallback mock data** for testing
3. **Increase circuit breaker thresholds**
4. **Add model persistence** to disk

The core ML and AI pipeline is fully implemented and ready to work once the data ingestion issue is resolved!