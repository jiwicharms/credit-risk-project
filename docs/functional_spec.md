# Functional Specification

**Author**: Jihwan Park
**Course/Project**: MSDS434 - Credit Risk Predictor
**Platform**: Amazon Web Services (AWS)
**Version**: 1.0

---

## 1. Purpose

### 1.1 Prompt

Given constant changing economic conditions, such as unemployment, Federal Reserve changes rates,
changes in consumer spending, and economic expansion/recession, credit card companies must
consider when, to whom, and how much credit to lend out to individuals based on these changes.

Credit issuers that can predict future changes can adjust proactively, rather than reactively,
to changes in the market, which can reduce potential losses as well as increase potential profits
in both the short-term and long-term.

### 1.2 Question
**Immediate**
With current macroeconomic conditions, what is the predicted month-to-month percentage
change in U.S. consumer credit outstanding in the next month?

**Predictive**
Which conditions are the greatest predictors and does it differ during expansions and recessions?

## 2. Project Scope

- Data ingestion of U.S. macroeconomic time series from FRED
- Storage of raw data in Amazon S3 and structured data in Amazon RedShift
- Training of models using RedShift ML
- 

## 3. Data


### 3.1 Source

Federal Reserve Economic Data (FRED), from Federal Reserve Bank of St. Louis.
Public API, requires free registration.

### 3.2 Series

## 4. Model

### 4.1 Amazon RedShiftML
*TBD

## 5. PaaS vs IaaS

PaaS (Platform as a Service) is a great choice for this use-case, because are no
unique or custom system dependencies and no performance needs that a ready-to-use
development and deployment platform such as AWS cannot provide. An IaaS would require
additional patching, runtime installation, web server configuration, and other additional
steps which, this use-case, will marginally benefit from, even more so when considering
the costs of using AWS.

Below are the applicable AWS services, are ready to deploy

**Amazon S3 and Redshift Serverless** for holding data
**Redshift ML** for model training and investigation
**AWS Elastic Beanstalk** for handling user infrastructure and deployment
