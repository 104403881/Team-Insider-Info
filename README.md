# JagaPaip — Know Which Pipe First

**Team Insider Info | Dormathon 2026 | Track 1: Predictive Model**

## 1. Project Overview

JagaPaip is an AI-assisted water pipeline failure risk prediction and maintenance decision-support system.

Water utility companies manage extensive pipeline networks but often face limited resources for inspections, maintenance, and replacement. Traditional approaches, such as prioritizing the oldest pipes, may not effectively identify which segments are most likely to experience future failures.

JagaPaip analyzes historical pipeline records to identify high-risk segments, prioritize maintenance activities, and provide understandable recommendations.

**Our goal: Help water utility managers make better maintenance decisions using historical evidence and predictive analytics.**

## 2. Problem Statement

Water pipeline failures can cause service disruptions, water losses, and additional operational costs.

However, utility companies cannot inspect or replace every pipe simultaneously.

JagaPaip addresses three challenges:

- Identifying pipe segments with higher future failure risk.
- Prioritizing maintenance activities within available resources.
- Explaining why particular pipes require attention.

## 3. Key Features

### 3.1 Overview Dashboard

Provides an overview of the eligible pipeline network, available data, risk information, and maintenance planning.

### 3.2 Risk Worklist

- Ranks pipeline segments according to predicted risk.
- Categorizes segments into risk bands.
- Allows users to adjust network-length maintenance capacity.
- Recalculates which segments fit the available capacity.
- Displays recommended actions and supports worklist export.

### 3.3 Pipe Evidence

Provides transparent evidence for individual pipeline segments, including:

- Pipe age, material, diameter, and length.
- Recorded historical pipe breaks.
- Risk score and planning rank.
- Recorded risk-pattern category.
- Evidence completeness.
- Recommended maintenance action.
- Historical break timeline.

Risk patterns describe recorded evidence, not confirmed physical causes. Risk percentiles do not represent calibrated failure probabilities.

### 3.4 Proof Mode

Evaluates the effectiveness of historical maintenance decisions using the **Hide → Decide → Reveal** workflow.

1. Hide recorded future pipe-break outcomes.
2. Generate maintenance plans using earlier information.
3. Compare JagaPaip's selected segments with a traditional oldest-first approach under the same capacity.
4. Reveal actual recorded breaks and evaluate the decisions.

### 3.5 Evaluation & Data Quality

Displays:

- Historical model performance.
- Capture at a fixed network-length capacity.
- Precision and selected segments without recorded breaks.
- Retrospective time-separated validation.
- Data-quality checks.
- Robustness under missing or inaccurate data.
- Evaluation limitations and evidence sources.

## 4. Predictive Model

JagaPaip evaluates several prediction and ranking methods, including prior-break history, logistic regression, cohort lookup, oldest-first selection, and random selection.

The selected champion method is **prior_breaks**, based on the reported historical evaluation.

Historical features are intended to use information available before the target prediction year.

### Reported Historical Performance

Evaluation: City of Kitchener pipeline data, test years 2023–2025.

| Metric | JagaPaip | Oldest-First |
|---|---|---|
| Mean Capture @ 5% | 32.5% | 6.6% |
| Relative capture improvement | 4.89× | Baseline |

The champion achieved **8.1% precision at the 5% network-length cap**. The evaluation reported 600 selected non-events across the evaluated years.

These figures describe retrospective targeting performance, not actual failures prevented or financial savings.

The champion was selected using the reported evaluation years, so these figures are not from a fully untouched final holdout.

## 5. Predictive Robustness Testing

To evaluate reliability under imperfect data, JagaPaip includes stress tests that simulate missing values, unseen materials, numeric perturbations, and inaccurate historical break counts.

### Latest Measured Results

| Test scenario | Capture @ 5% | Rank correlation |
|---|---|---|
| Baseline | 32.50% | 1.0000 |
| Missing 5% prior-break counts | 32.97% | 0.9712 |
| Missing 10% prior-break counts | 32.35% | 0.9492 |
| Inaccurate 10% prior-break counts | 32.00% | 0.7352 |

The tested scenarios produced similar aggregate capture, although inaccurate break records reduced ranking stability.

These experiments demonstrate sensitivity under simulated conditions and do not guarantee performance on all real-world datasets.

## 6. How JagaPaip Works

**Input → Predict → Categorize → Prioritize → Explain → Evaluate**

1. Load historical pipe inventory and recorded break information.
2. Generate or load historical predictive risk rankings.
3. Categorize risk levels and observed risk patterns.
4. Select pipe segments within the operational length budget.
5. Recommend monitoring, inspection, or engineering renewal review.
6. Validate targeting decisions against recorded historical outcomes.

JagaPaip supports human decision-making and does not automatically replace pipes or authorize maintenance expenditure.

## 7. Technology Stack

- **Python:** Backend and data processing.
- **Streamlit:** Interactive website.
- **Pandas / NumPy:** Data manipulation.
- **Scikit-learn:** Predictive modeling and evaluation.
- **Pytest:** Automated testing.
- **Parquet / JSON:** Data and model-result artifacts.
- **Git / GitHub:** Version control and collaboration.

## 8. Installation and Running the Website

### Requirements

- Python 3.11 or compatible version.
- Git (recommended).
- VS Code or another Python development environment.

### Clone Repository

`git clone https://github.com/104403881/Team-Insider-Info.git`

`cd Team-Insider-Info`

### Install Dependencies

Create and activate a virtual environment:

`python -m venv .venv`

Windows PowerShell:

`.\.venv\Scripts\Activate.ps1`

Install project dependencies:

`python -m pip install -r requirements.txt`

`python -m pip install -r JagaPaip/requirements.txt`

### Run Website

`cd JagaPaip`

`python -m streamlit run app.py`

Open the local address displayed by Streamlit, normally:

**http://localhost:8501**

## 9. Automated Testing

Run machine-learning tests from the repository root:

`python -m pytest -q tests`

Latest verified result: **100 passed**.

Run website tests from the JagaPaip folder:

`cd JagaPaip`

`python -m pytest -q tests`

Latest verified result: **73 passed, 2 skipped**.

These results reflect the October 2026 development checks and should be updated after future changes.

## 10. Hackathon Demonstration

The Dormathon live demonstration follows five steps:

1. **Overview:** Introduce the pipeline data and operational problem.
2. **Risk Worklist:** Demonstrate maintenance-capacity prioritization.
3. **Pipe Evidence:** Select Pipe 41030 and explain its recorded risk pattern and recommended action.
4. **Proof Mode:** Demonstrate historical comparison against oldest-first selection.
5. **Evaluation & Data Quality:** Show historical performance, precision, robustness tests, and limitations.

The recommended live demonstration duration is four minutes.

## 11. Dataset and Limitations

The prototype uses historical City of Kitchener pipeline data as a method demonstrator.

Important limitations include:

- Results have not been independently validated on Malaysian utility networks.
- The prototype does not use real-time leak sensors.
- Risk scores are ranking signals, not calibrated failure probabilities.
- Historical break patterns do not establish physical failure causes.
- Low precision means many selected segments did not experience recorded breaks during the evaluated period.
- Robustness results are based on simulated data problems.
- Local engineering assessment is needed before maintenance or replacement decisions.
- An independent untouched evaluation would provide stronger evidence of generalization.

## 12. Future Improvements

- Validate the method with Malaysian utility partners.
- Integrate local geographic and pipeline asset data.
- Strengthen out-of-sample evaluation.
- Improve risk calibration and confidence communication.
- Explore additional operational signals where reliable data is available.
- Incorporate actual maintenance costs and engineering constraints.
- Support longer-term operational deployment and monitoring.

## 13. Team and Repository

**Team:** Team Insider Info

**Event:** Dormathon 2026

**Track:** Predictive Model Track

**Repository:** https://github.com/104403881/Team-Insider-Info

---

**JagaPaip — Know Which Pipe First.**

*Predict. Prioritize. Explain. Prove.*