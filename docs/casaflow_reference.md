# CasaFlow Reference

CasaFlow is a private real-estate finance app for managing an owner-share view of a property portfolio. It keeps operational property data, unit and tenant history, loans, deals, and bank-facing exports in one place.

The most important rule: day-to-day financial analysis is on the Dashboard and Loans pages. Property and Unit pages are for maintaining clean source data.

## Workflow Mind Map

The in-app Reference page shows a visual CasaFlow Modes mind map. It groups the app into Portfolio Tracking, Portfolio Analysis, and Portfolio Decisions.

## Data Structure

- Property: one grouped real-estate object. A house with several apartments is one property.
- Unit: an apartment or rentable unit below a property.
- Tenant / Person: a reusable person record.
- Lease: the time period in which a tenant group rents a unit.
- Rent Period: the rent amount valid from a specific date inside a lease.
- Loan: the financing contract for a property.
- Annual Loan Data: yearly closing balances used to calculate debt, interest, principal repayment, and debt service.
- Annual Property Data: yearly values, vacancy/loss, and non-recoverable costs.
- Deal: a possible future property that is not part of the real portfolio yet.
- Financing Scenario: one possible loan/cash setup for a deal.

## Naming Conventions

- Cashflow means the property result after operating costs, vacancy/loss, interest, and, on the Dashboard portfolio totals, the selected tax mode.
- Free Cashflow means liquidity left after the full loan payment and selected tax mode.
- Equity Build means debt reduction through principal repayment.
- Your Cash Invested means the real cash you personally invested. Bank-financed amounts are not included.
- Annual Owner ROI means annual owner return compared with Your Cash Invested.
- Effective Interest Rate is the interest actually paid compared with the relevant debt balance.
- LTV means loan-to-value in the real-estate sense.
- Cold rent excludes utilities and tenant prepayments.
- Operating costs are non-recoverable costs, meaning costs tenants do not pay back.
- Showing your share means amounts are multiplied by the relevant ownership share.
- Showing full property values means amounts are total property values before ownership-share calculation.

## Core Formulas

```text
Cashflow = cold rent - operating costs - vacancy/loss - interest
Portfolio taxable result = portfolio Cashflow before tax - yearly tax-deductible costs
After-tax Cashflow = portfolio Cashflow before tax - estimated tax
Free Cashflow = Cashflow - principal repayment
Equity Build = principal repayment
Total Value Added = Free Cashflow + Equity Build + unrealized value gain
Annual Owner ROI = Cashflow / Your Cash Invested
NOI = cold rent - vacancy/loss - operating costs
LTV = debt / property value
Net Yield = NOI / property value
Gross Yield = cold rent / property value
Debt Service = interest + principal repayment
DSCR = NOI / debt service
```

## Formula Principles

- Principal repayment is not treated as a cost in Cashflow because it becomes equity by reducing debt.
- Free Cashflow is the real cash left after the complete loan payment.
- Equity Build is shown separately so liquidity and wealth building are both visible.
- Unrealized value gain is not part of Cashflow because it is not real cash until a sale or refinancing event.
- Total Value Added is a broader future-facing concept that can include unrealized value gain.
- Dashboard values use the ownership share.
- Bank exports use full-property values and show ownership share separately.

## Before Tax And After Tax Mode

The Dashboard can run with tax calculations enabled or disabled in Settings. If tax is disabled, all tax UI is hidden and Dashboard values are before tax. If tax is enabled, the Dashboard has a Before Tax / After Tax toggle, with After Tax as the default view.

- Before Tax keeps the core formula: Cashflow = cold rent - operating costs - vacancy/loss - interest.
- After Tax subtracts an estimated portfolio tax from portfolio Cashflow using the effective tax rate from Settings.
- Yearly tax-deductible costs are entered once per year in Settings. They are tax-only deductions and do not reduce pre-tax Cashflow unless already entered elsewhere as operating costs.
- If the taxable result is negative and tax-loss benefits are enabled, CasaFlow treats the negative tax estimate as an estimated benefit.
- Tax is calculated once for the selected portfolio scope, not separately per property. Property rows and property charts remain before portfolio tax.
- V1 does not model depreciation schedules, allowances, tax brackets, or formal tax accounting.
- NOI, Gross Yield, Net Yield, LTV, DSCR, Debt, Debt Service, Equity, Equity Build, and Property Value stay tax-independent.

## Dashboard Metrics

- Cashflow: main profitability indicator for the selected year. Portfolio totals follow the Dashboard tax toggle.
- Free Cashflow: liquidity after principal repayment. Portfolio totals follow the Dashboard tax toggle.
- Equity Build: debt reduction through principal repayment.
- Annual Owner ROI: selected portfolio Cashflow divided by Your Cash Invested.
- Cumulative Owner ROI: cumulative selected portfolio Cashflow divided by Your Cash Invested.
- Portfolio Value: property valuations multiplied by ownership share.
- Total Debt: loan balances multiplied by ownership share.
- LTV: Total Debt divided by Portfolio Value.

## Loan Metrics

- Current Debt: current or approximated loan balance multiplied by ownership share.
- Effective Interest Rate: interest paid divided by opening debt.
- Interest Cost: annual interest paid multiplied by ownership share.
- Principal Paid: annual debt reduction multiplied by ownership share.
- Debt Service: interest plus principal repayment.
- Amortization Rate: principal paid divided by opening debt.

## Deal Metrics

Deals use full-property inputs but show decision KPIs using the ownership share.

- Cashflow = expected cold rent share - operating cost share - interest cost share.
- Free Cashflow = Cashflow - estimated principal repayment.
- Equity Build = estimated principal repayment.
- Annual Owner ROI = Cashflow / Your Cash Invested.
- Your Cash Invested belongs to each financing scenario, not the deal itself.
- Financing scenarios should be compared by return, liquidity, added debt, and cash invested requirement.

## Exports

The Bank Financing Overview is meant for loan applications and bank communication.

- Real-estate values are full-property amounts.
- Loan amounts are full-property amounts.
- Ownership share is shown separately.
- Annual cold rent is based on current expected cold rent.
- Current loan amount uses the best available annual loan data.

## Current Non-Goals

- CasaFlow does not track actual tenant payment collection.
- CasaFlow uses a simple Dashboard tax estimate, not formal tax accounting.
- CasaFlow does not include unrealized value gain in Cashflow.
- CasaFlow does not replace formal accounting or tax advice.
- Deals are planning records and do not affect the real portfolio until manually converted in a future version.
