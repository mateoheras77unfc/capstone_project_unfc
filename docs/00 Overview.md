### **Project Vision: The Educational Investment Analytics Platform**

**Purpose:** To build a web-based educational tool that helps novice investors understand financial risk and forecasting. The platform allows users to apply advanced mathematical models (Time Series Forecasting) and investment theories (Portfolio Optimization) to real-world data (Stocks and Cryptocurrencies) without needing a background in coding or calculus.

**Expected Outcome:** A user-friendly dashboard where students can visually compare how different assets perform, see scientific price predictions, and learn how to construct a mathematically "efficient" portfolio.

---

### **General Workflow & System Logic**

#### **1. The Data Engine (Smart Retrieval)**
## Must: Supabase is our database

* **Concept:** The system acts as a bridge between the live market and the user. It prioritizes speed and efficiency.
* **Workflow:**
* When the system needs price data for a stock or crypto (e.g., Bitcoin or Apple), it first looks in its own internal **Database**.
* **If the data is there and fresh:** It loads it instantly (fast performance).
* **If the data is missing or old:** It reaches out to the external **Market API**, fetches the history, saves it to the Database for next time, and then displays it.
* *Result:* The more people use the app, the faster it gets, as the internal database builds up a library of market history.



#### **2. Feature A: The Forecasting Lab (Single Asset)**

* **User Action:** The user selects one specific asset (e.g., "Tesla") and a timeframe.
* **System Action:**
* Retrieves historical price data.
* Applies a **SARIMA model** (a statistical method for analyzing trends and seasonality).
* Calculates future price probabilities for the next 7–30 days.


* **Visual Output:** The user sees a line chart showing the past price (black line) and the predicted future price (colored line) surrounded by a "confidence shadow" (showing the range of possible outcomes).

#### **3. Feature B: The Portfolio Optimizer (Multi-Asset)**

* **User Action:** The user picks a basket of mixed assets (e.g., "Bitcoin, Gold, Google, and Amazon").
* **System Action:**
* Aligns the historical data for all selected items (matching dates).
* Analyzes how these assets move together (Correlation) vs. how they move apart (Diversification).
* Runs a mathematical optimization to find the "perfect balance" (Maximal Sharpe Ratio)—the specific percentage mix that gives the best return for the lowest risk.


* **Visual Output:**
* **The Efficient Frontier:** A curve chart showing the risk-reward tradeoff.
* **The Allocation Pie Chart:** A simple visual telling the user: "To optimize this portfolio, buy 40% Bitcoin, 10% Gold, and 50% Google."



#### **4. The User Interface**

* **Design Philosophy:** "Click and Learn." The interface uses sliders, dropdowns, and interactive graphs rather than complex forms.
* **Structure:**
* **Sidebar:** For navigation and inputs (selecting stocks).
* **Main Window:** For data storytelling (charts, metrics, and explanations).
