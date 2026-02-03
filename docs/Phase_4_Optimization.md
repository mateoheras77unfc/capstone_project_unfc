# Phase 4: Portfolio Optimizer (Model Agnostic)

## Purpose
To calculate the optimal distribution of capital across multiple assets. Like Phase 3, this is **model-agnostic**, focusing on the inputs (basket of assets) and outcomes (allocation percentages).

## Key Objectives
1.  **Multi-Asset Alignment:** Develop the logic to align multiple assets with different trading schedules (e.g., syncing Weekend Crypto data with Weekday Stock data) at Weekly/Monthly frequencies.
2.  **Optimization Engine:** A plug-and-play module that calculates weights. Possible models include:
    *   Mean-Variance Optimization (Max Sharpe Ratio).
    *   Equal Weighting.
    *   Minimum Volatility.
3.  **Visual Output Integration:** Prepare data for the Allocation Pie Chart and Risk-Reward curve.

## Technical Requirements
*   **Input:** A list of asset symbols + timeframe.
*   **Output:** A dictionary of `{symbol: weight}` where the sum of `weight` is 1.0 (100%).

## Verification / Tests
*   **Allocation Sum Check:** Verify that every optimization result sums exactly to 1.0.
*   **Correlation Matrix Test:** Confirm the system correctly identifies high-correlation assets (e.g., SPY vs VOO) versus diverging assets.
*   **Zero-Weight Test:** Ensure the model can handle assets with insufficient data by assigning them a 0% weight without breaking the script.
