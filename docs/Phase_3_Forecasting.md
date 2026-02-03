# Phase 3: Forecasting Lab (Model Agnostic)

## Purpose
To implement the analytical engine that predicts future asset performance. This phase is designed to be **model-agnostic**, allowing different teams to experiment with various mathematical approaches while maintaining a consistent data structure.

## Key Objectives
1.  **Agnostic Interface Design:** Define a standard input (historical price series) and output (forecast object) so that models can be swapped (e.g., SARIMA, Prophet, LSTM, or Simple Moving Averages).
2.  **Forecasting Pipeline:**
    *   Retrieve weekly/monthly data from Foundation layer.
    *   Apply the selected mathematical transformation.
    *   Generate a forecast for the next 4 units (weeks or months).
3.  **Confidence Visualization:** Standardize how "Risk" or "Probability" is returned alongside the prediction.

## Technical Requirements
*   **Input Format:** `[Date, Adjusted Close]` at Weekly/Monthly intervals.
*   **Output Format:** A JSON object containing `[Date, Projected Value, Lower Bound, Upper Bound]`.

## Verification / Tests
*   **Interface Test:** Replace one model with a "Dummy Flat Model" and verify the UI still renders the forecast graph correctly.
*   **Timestep Alignment:** Confirm that a "Monthly" forecast actually produces a date 30 days in the future, not 1 day.
*   **Directional Accuracy:** Check if the model can successfully "predict" the last 4 weeks of known data (Backtesting).
