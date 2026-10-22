# Inventory AI Agent for Odoo 20

## Overview
**Inventory AI Agent** is a powerful, AI-driven replenishment assistant for Odoo 18. Built for purchase and inventory teams, it intelligently forecasts low stock situations, evaluates vendor performance, and automates Request for Quotation (RFQ) creation before a stockout even occurs. 

By utilizing OpenAI to analyze your stock levels, historical sales, and past vendor reliability, it provides practical, data-backed restocking recommendations without the need for manual calculations.

---

## Key Features
* **AI-Powered Low Stock Analysis**: Automatically identifies products needing replenishment based on configured minimum stock thresholds and historical data.
* **Smart Vendor Recommendations**: Suggests the best vendor for reordering by evaluating lead time, delay days, pricing, and overall vendor reliability.
* **Comprehensive Data Processing**: Gathers product stock, sales history, and purchase history into a consolidated workbook for precise AI context.
* **Automated RFQ Generation**: Automatically or manually draft Requests for Quotation directly from AI-recommended product lines.
* **Configurable Forecasting Periods**: Choose to base sales and purchase forecasts on all-time data or specific recent periods (e.g., last 30 days).
* **Interactive Dashboard**: An intuitive UI to configure AI instructions, view analysis results, trigger AI processing, and manage the generated inventory workbooks.
* **Detailed Run Logs**: Keep track of every AI analysis run, including token usage, success/failure status, recommended product lines, decision rationale, and automatically created RFQs.
* **Scheduled Operations**: Supports manual triggers or automated execution via scheduled cron jobs.

---

## Real-World Use Cases

### 1. Proactive Stock Replenishment
* **Scenario**: A retail business has thousands of consumable and storable products. Keeping track of what to order and when is overwhelming.
* **Solution**: The Inventory AI Agent periodically checks sales velocity and current stock. If an item is predicted to go below the minimum threshold based on recent demand, the AI recommends a restocking quantity.

### 2. Intelligent Vendor Selection
* **Scenario**: A manufacturing company buys components from multiple suppliers. Some are cheap but often delayed, while others are reliable but expensive.
* **Solution**: The module evaluates vendor history (average price, lead time, delay days, and calculated reliability percentage). The AI then picks the optimal vendor based on urgency and historical performance, noting its reasoning in the logs.

### 3. Automated Purchasing Workflow
* **Scenario**: A busy procurement manager spends hours drafting RFQs every week based on minimum stock rules.
* **Solution**: By enabling the "Auto Create RFQ" setting, the Inventory AI Agent seamlessly translates its recommendations into Draft RFQs in Odoo. The manager only needs to review and confirm the orders, saving hours of manual data entry.

---

## How It Works (The Workflow)

1. **Data Preparation**: 
   When triggered (manually or via cron), the module generates an Excel workbook containing three sheets:
   * **Stock Data**: Current, incoming, outgoing, and available stock for active products.
   * **Sales Data**: Aggregated sales quantities, number of orders, and date ranges (filtered by your chosen forecast period).
   * **Purchase Data**: Aggregated purchase histories, calculating average price, lead times, and vendor reliability percentages.

2. **AI Analysis**: 
   The workbook is securely sent to the configured OpenAI model. Guided by a predefined (but customizable) prompt, the AI evaluates forecasted demand against available stock.

3. **Recommendation & Execution**: 
   The AI returns a structured CSV output with decisions (`CREATE_RFQ`), recommended quantities, and the best vendor choice along with a reason. 

4. **Action**: 
   The results are stored in the database. If Auto Create RFQ is enabled, Odoo instantly drafts the Purchase Orders. All rationale is saved in the **Inventory AI Logs** for transparency.

---

## Configuration & Setup

### 1. Prerequisites
* Ensure you have the `vraja_ai` base module installed and configured with a valid OpenAI API Key.
* Ensure your products are properly configured with vendors and historical data for the best AI results.

### 2. Dashboard Settings
Navigate to the **Inventory AI Dashboard** to configure the alert parameters:
* **Minimum Stock Threshold**: The baseline stock level the AI should consider critical.
* **Sales Forecast Period**: Choose between "All Time Data" or "Preferred Data" (e.g., last 30 days) to calculate average daily sales.
* **Purchase Forecast Period**: Choose how far back to look for vendor performance data.
* **Auto Create RFQ**: Toggle this on if you want the system to automatically generate Draft Purchase Orders based on AI recommendations.

### 3. Customizing the AI Prompt
In the dashboard, you can view and edit the **Instructions** and **Default Prompt** sent to the AI, allowing you to fine-tune the decision-making process to your specific business logic.

---

## Monitoring & Logs
To review what the AI recommended and why:
1. Go to **Inventory AI Logs**.
2. Open a specific log entry to view the **Products Recommended**, **Total Recommended Qty**, and **RFQs Created**.
3. Check the line items to see the AI's step-by-step reasoning for each product, including the forecasted demand, suggested vendor, and token usage for the run.

---
*Created by Vraja Technologies.*
