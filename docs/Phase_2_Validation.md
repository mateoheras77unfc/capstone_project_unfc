# Phase 2: Validation - MVP UI & Data Connectivity

## Purpose
To provide a visual and functional "proof of life" for the data engine. This phase ensures that the data stored in the Foundation phase is correctly retrieved and rendered in the frontend.

## Key Objectives
1.  **Mock Pages:** Create two simplified dashboard views:
    *   **Page 1 (Single Asset View):** A simple table showing the historical weekly/monthly prices for one selected asset.
    *   **Page 2 (Comparison View):** A table displaying the most recent Closing prices for a group of selected stocks or cryptocurrencies.
2.  **API Endpoints:** Build the bridge between the UI and Supabase to query stored data.
3.  **Basic Navigation:** A simple sidebar or tab system to switch between the two verification views.

## Technical Requirements
*   **No Calculation Yet:** This phase should focus strictly on **displaying raw data** to confirm the pipeline is working.
*   **Responsive Tables:** Ensure data is readable on standard screen sizes.

## Verification / Tests
*   **Data Integrity Check:** Manually compare a value in the UI Table with the value in the Supabase Dashboard for a specific date.
*   **Empty State Test:** Ensure the UI handles "Asset Not Found" cases gracefully with a user message.
*   **Performance Test:** Verify the table loads in under 2 seconds when pulling 2 years of weekly records.
