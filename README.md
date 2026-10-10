# JagaPaip — Know Which Pipe First

**Team Insider Info | Dormathon 2026 | Track 1: Predictive Model**

## Overview

JagaPaip is a data-driven water pipeline risk prediction and maintenance decision-support system. It helps water utility managers identify which pipes should be prioritized for inspection or renewal review using historical pipe data.

The goal is to support better maintenance decisions while working within limited operational resources.

## Key Features

- **Overview Dashboard:** View the pipe network, asset information, and maintenance priorities.
- **Risk Worklist:** Rank pipe segments and select maintenance priorities based on available capacity.
- **Pipe Evidence:** Understand the historical evidence behind each recommendation.
- **Proof Mode:** Compare JagaPaip's historical targeting performance against traditional approaches.
- **Evaluation & Data Quality:** Review evaluation results, data limitations, and quality checks.

## Technology Stack

- Python
- Streamlit
- Pandas
- Predictive analytics and historical risk-ranking methods

## How to Run the Website

1. Install Python.
2. Open the repository in VS Code.
3. Open the terminal.
4. Navigate to the `JagaPaip` folder.
5. Create a Python virtual environment using `python -m venv .venv`.
6. Install dependencies using `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`.
7. Launch the application using `.\.venv\Scripts\python.exe -m streamlit run app.py`.
8. Open `http://localhost:8501` in your browser.

## How the System Works

1. **Input:** Load pipe inventory and historical break records.
2. **Predict:** Estimate or rank future pipe-break risk.
3. **Categorize:** Identify risk levels and relevant historical patterns.
4. **Prioritize:** Select high-priority segments within a maintenance capacity.
5. **Explain:** Present supporting evidence and recommended actions.
6. **Evaluate:** Compare historical targeting decisions against recorded outcomes.

## Data and Limitations

The prototype uses historical water infrastructure records from Kitchener, Canada.

Risk percentiles represent relative rankings, not calibrated failure probabilities. Results require local validation before application to Malaysian water networks.

Maintenance recommendations support, rather than replace, professional engineering decisions.

## Repository

https://github.com/104403881/Team-Insider-Info

## Team

Team Insider Info — Dormathon 2026.