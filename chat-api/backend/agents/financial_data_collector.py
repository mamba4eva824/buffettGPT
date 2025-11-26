#!/usr/bin/env python3
"""
Financial Data Collector Agent
Collects and processes financial statements from SEC EDGAR and other sources
"""

import asyncio
import json
import logging
import os
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
import time

import boto3
import pandas as pd
import requests
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field
from loguru import logger

# Configure logging
logging.basicConfig(level=logging.INFO)
logger.add("financial_data_collector.log", rotation="100 MB")


class FinancialStatement(BaseModel):
    """Model for financial statement data"""
    company_ticker: str
    company_name: str
    cik: str
    fiscal_year: int
    fiscal_period: str  # Q1, Q2, Q3, Q4, FY
    statement_type: str  # income, balance_sheet, cash_flow
    filing_type: str  # 10-K, 10-Q
    filing_date: str
    data: Dict[str, Any]
    source: str  # SEC, manual, perplexity, etc.
    raw_text: Optional[str] = None
    confidence_score: float = 1.0
    verification_status: str = "unverified"
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class SECDataCollector:
    """Collects financial data from SEC EDGAR"""

    BASE_URL = "https://data.sec.gov"
    ARCHIVES_URL = "https://www.sec.gov/Archives/edgar"

    # Standard financial statement line items to extract
    INCOME_STATEMENT_ITEMS = [
        "revenue", "total_revenue", "net_sales",
        "cost_of_revenue", "cost_of_goods_sold",
        "gross_profit", "operating_expenses",
        "research_development", "selling_general_administrative",
        "operating_income", "ebit", "interest_expense",
        "pretax_income", "income_tax_expense",
        "net_income", "eps_basic", "eps_diluted",
        "shares_outstanding_basic", "shares_outstanding_diluted"
    ]

    BALANCE_SHEET_ITEMS = [
        "cash_and_cash_equivalents", "short_term_investments",
        "accounts_receivable", "inventory", "current_assets",
        "property_plant_equipment", "goodwill", "intangible_assets",
        "total_assets", "accounts_payable", "short_term_debt",
        "current_liabilities", "long_term_debt", "total_debt",
        "total_liabilities", "retained_earnings",
        "total_stockholders_equity", "total_equity"
    ]

    CASH_FLOW_ITEMS = [
        "operating_cash_flow", "capital_expenditures",
        "free_cash_flow", "investing_cash_flow",
        "financing_cash_flow", "dividends_paid",
        "stock_repurchases", "net_change_in_cash"
    ]

    def __init__(self, rate_limit_delay: float = 0.1):
        """
        Initialize SEC Data Collector

        Args:
            rate_limit_delay: Delay between API calls to respect SEC rate limits
        """
        self.rate_limit_delay = rate_limit_delay
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Buffett Chat API Financial Data Collector/1.0'
        })

        # Company CIK mapping
        self.company_ciks = {
            'AMZN': '0001018724',  # Amazon
            'AXP': '0000004962',   # American Express
            'COST': '0000909832',  # Costco
            'AAPL': '0000320193',  # Apple
            'BAC': '0000070858',   # Bank of America
            'CVX': '0000093410',   # Chevron
            'KO': '0000021344',    # Coca-Cola
            'DIS': '0001001039',   # The Walt Disney Company
        }

    def get_company_filings(self, ticker: str, filing_type: str = "10-K",
                           start_year: int = 2010) -> List[Dict]:
        """
        Get list of company filings from SEC

        Args:
            ticker: Company ticker symbol
            filing_type: Type of filing (10-K, 10-Q, etc.)
            start_year: Start year for filings

        Returns:
            List of filing metadata
        """
        cik = self.company_ciks.get(ticker)
        if not cik:
            logger.error(f"CIK not found for ticker {ticker}")
            return []

        # Get company submissions
        url = f"{self.BASE_URL}/submissions/CIK{cik}.json"

        try:
            response = self.session.get(url)
            response.raise_for_status()
            time.sleep(self.rate_limit_delay)

            data = response.json()
            filings = []

            recent_filings = data.get('filings', {}).get('recent', {})
            forms = recent_filings.get('form', [])
            filing_dates = recent_filings.get('filingDate', [])
            accession_numbers = recent_filings.get('accessionNumber', [])
            primary_documents = recent_filings.get('primaryDocument', [])

            for i in range(len(forms)):
                if forms[i] == filing_type:
                    filing_year = int(filing_dates[i][:4])
                    if filing_year >= start_year:
                        filings.append({
                            'ticker': ticker,
                            'form': forms[i],
                            'filing_date': filing_dates[i],
                            'year': filing_year,
                            'accession_number': accession_numbers[i].replace('-', ''),
                            'primary_document': primary_documents[i],
                            'cik': cik
                        })

            logger.info(f"Found {len(filings)} {filing_type} filings for {ticker} since {start_year}")
            return sorted(filings, key=lambda x: x['year'])

        except Exception as e:
            logger.error(f"Error fetching filings for {ticker}: {e}")
            return []

    def extract_xbrl_data(self, filing: Dict) -> Dict[str, Any]:
        """
        Extract financial data from XBRL filing

        Args:
            filing: Filing metadata

        Returns:
            Extracted financial data
        """
        # Construct XBRL data URL
        cik = filing['cik']
        accession = filing['accession_number']

        # Try to get XBRL JSON data
        xbrl_url = f"{self.BASE_URL}/api/xbrl/companyfacts/CIK{cik}.json"

        try:
            response = self.session.get(xbrl_url)
            response.raise_for_status()
            time.sleep(self.rate_limit_delay)

            xbrl_data = response.json()
            facts = xbrl_data.get('facts', {})

            # Extract relevant facts for the filing year
            extracted_data = {
                'income_statement': {},
                'balance_sheet': {},
                'cash_flow': {}
            }

            # Process US-GAAP facts
            us_gaap = facts.get('us-gaap', {})

            for fact_name, fact_data in us_gaap.items():
                units = fact_data.get('units', {})

                # Look for USD values
                if 'USD' in units:
                    for entry in units['USD']:
                        if entry.get('fy') == filing['year'] and entry.get('form') == filing['form']:
                            # Map to our standard names
                            mapped_name = self._map_xbrl_to_standard(fact_name)
                            if mapped_name:
                                statement_type = self._get_statement_type(mapped_name)
                                if statement_type:
                                    extracted_data[statement_type][mapped_name] = entry.get('val')

            return extracted_data

        except Exception as e:
            logger.warning(f"Could not extract XBRL data for {filing['ticker']} {filing['year']}: {e}")
            return {}

    def _map_xbrl_to_standard(self, xbrl_name: str) -> Optional[str]:
        """Map XBRL concept names to standard names"""

        mapping = {
            'Revenues': 'revenue',
            'SalesRevenueNet': 'net_sales',
            'CostOfRevenue': 'cost_of_revenue',
            'CostOfGoodsAndServicesSold': 'cost_of_goods_sold',
            'GrossProfit': 'gross_profit',
            'OperatingExpenses': 'operating_expenses',
            'ResearchAndDevelopmentExpense': 'research_development',
            'SellingGeneralAndAdministrativeExpense': 'selling_general_administrative',
            'OperatingIncomeLoss': 'operating_income',
            'InterestExpense': 'interest_expense',
            'IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest': 'pretax_income',
            'IncomeTaxExpenseBenefit': 'income_tax_expense',
            'NetIncomeLoss': 'net_income',
            'EarningsPerShareBasic': 'eps_basic',
            'EarningsPerShareDiluted': 'eps_diluted',
            'WeightedAverageNumberOfSharesOutstandingBasic': 'shares_outstanding_basic',
            'WeightedAverageNumberOfDilutedSharesOutstanding': 'shares_outstanding_diluted',
            'CashAndCashEquivalentsAtCarryingValue': 'cash_and_cash_equivalents',
            'AccountsReceivableNetCurrent': 'accounts_receivable',
            'InventoryNet': 'inventory',
            'AssetsCurrent': 'current_assets',
            'PropertyPlantAndEquipmentNet': 'property_plant_equipment',
            'Goodwill': 'goodwill',
            'Assets': 'total_assets',
            'AccountsPayableCurrent': 'accounts_payable',
            'LiabilitiesCurrent': 'current_liabilities',
            'LongTermDebt': 'long_term_debt',
            'Liabilities': 'total_liabilities',
            'RetainedEarningsAccumulatedDeficit': 'retained_earnings',
            'StockholdersEquity': 'total_stockholders_equity',
            'NetCashProvidedByUsedInOperatingActivities': 'operating_cash_flow',
            'PaymentsToAcquirePropertyPlantAndEquipment': 'capital_expenditures',
            'NetCashProvidedByUsedInInvestingActivities': 'investing_cash_flow',
            'NetCashProvidedByUsedInFinancingActivities': 'financing_cash_flow',
            'PaymentsOfDividends': 'dividends_paid',
            'PaymentsForRepurchaseOfCommonStock': 'stock_repurchases'
        }

        return mapping.get(xbrl_name)

    def _get_statement_type(self, field_name: str) -> Optional[str]:
        """Determine which financial statement a field belongs to"""

        if field_name in self.INCOME_STATEMENT_ITEMS:
            return 'income_statement'
        elif field_name in self.BALANCE_SHEET_ITEMS:
            return 'balance_sheet'
        elif field_name in self.CASH_FLOW_ITEMS:
            return 'cash_flow'
        return None

    async def collect_company_data(self, ticker: str, start_year: int = 2010,
                                  end_year: int = 2024) -> List[FinancialStatement]:
        """
        Collect all financial data for a company

        Args:
            ticker: Company ticker symbol
            start_year: Start year for collection
            end_year: End year for collection

        Returns:
            List of FinancialStatement objects
        """
        statements = []

        # Get 10-K filings
        filings = self.get_company_filings(ticker, "10-K", start_year)

        for filing in filings:
            if filing['year'] > end_year:
                continue

            logger.info(f"Processing {ticker} {filing['form']} for {filing['year']}")

            # Extract XBRL data
            financial_data = self.extract_xbrl_data(filing)

            # Create FinancialStatement objects for each statement type
            for statement_type, data in financial_data.items():
                if data:  # Only create if we have data
                    statement = FinancialStatement(
                        company_ticker=ticker,
                        company_name=ticker,  # Will be updated with full name
                        cik=filing['cik'],
                        fiscal_year=filing['year'],
                        fiscal_period="FY",
                        statement_type=statement_type.replace('_', ' ').title(),
                        filing_type=filing['form'],
                        filing_date=filing['filing_date'],
                        data=data,
                        source="SEC_EDGAR",
                        confidence_score=0.95,  # High confidence for direct SEC data
                        verification_status="sec_sourced"
                    )
                    statements.append(statement)

        logger.info(f"Collected {len(statements)} financial statements for {ticker}")
        return statements


class FinancialDataCollectorAgent:
    """Main agent for orchestrating financial data collection"""

    def __init__(self, dynamodb_client=None):
        """
        Initialize the Financial Data Collector Agent

        Args:
            dynamodb_client: Optional DynamoDB client for AWS storage
        """
        self.sec_collector = SECDataCollector()
        self.dynamodb_client = dynamodb_client or boto3.client('dynamodb', region_name='us-east-1')
        self.local_storage_path = "financial_data_cache"

        # Create local storage directory
        os.makedirs(self.local_storage_path, exist_ok=True)

    def save_to_dynamodb(self, statement: FinancialStatement, table_name: str) -> bool:
        """
        Save financial statement to DynamoDB

        Args:
            statement: FinancialStatement object
            table_name: DynamoDB table name

        Returns:
            Success status
        """
        try:
            item = {
                'company_ticker': {'S': statement.company_ticker},
                'statement_key': {'S': f"{statement.fiscal_year}_{statement.filing_type}_{statement.statement_type}"},
                'filing_year': {'N': str(statement.fiscal_year)},
                'fiscal_period': {'S': statement.fiscal_period},
                'statement_type': {'S': statement.statement_type},
                'filing_type': {'S': statement.filing_type},
                'filing_date': {'S': statement.filing_date},
                'data': {'S': json.dumps(statement.data)},
                'source': {'S': statement.source},
                'confidence_score': {'N': str(statement.confidence_score)},
                'verification_status': {'S': statement.verification_status},
                'created_at': {'S': statement.created_at}
            }

            self.dynamodb_client.put_item(
                TableName=table_name,
                Item=item
            )

            logger.info(f"Saved {statement.company_ticker} {statement.fiscal_year} {statement.statement_type} to DynamoDB")
            return True

        except Exception as e:
            logger.error(f"Error saving to DynamoDB: {e}")
            return False

    def save_to_local(self, statement: FinancialStatement) -> bool:
        """
        Save financial statement to local file system

        Args:
            statement: FinancialStatement object

        Returns:
            Success status
        """
        try:
            # Create company directory
            company_dir = os.path.join(self.local_storage_path, statement.company_ticker)
            os.makedirs(company_dir, exist_ok=True)

            # Create filename
            filename = f"{statement.fiscal_year}_{statement.filing_type}_{statement.statement_type.replace(' ', '_')}.json"
            filepath = os.path.join(company_dir, filename)

            # Save as JSON
            with open(filepath, 'w') as f:
                json.dump(statement.dict(), f, indent=2)

            logger.info(f"Saved {statement.company_ticker} {statement.fiscal_year} {statement.statement_type} to {filepath}")
            return True

        except Exception as e:
            logger.error(f"Error saving to local storage: {e}")
            return False

    def load_from_local(self, ticker: str, year: int, statement_type: str) -> Optional[FinancialStatement]:
        """
        Load financial statement from local storage

        Args:
            ticker: Company ticker
            year: Fiscal year
            statement_type: Type of statement

        Returns:
            FinancialStatement object or None
        """
        try:
            company_dir = os.path.join(self.local_storage_path, ticker)
            filename = f"{year}_10-K_{statement_type.replace(' ', '_')}.json"
            filepath = os.path.join(company_dir, filename)

            if os.path.exists(filepath):
                with open(filepath, 'r') as f:
                    data = json.load(f)
                return FinancialStatement(**data)

        except Exception as e:
            logger.error(f"Error loading from local storage: {e}")

        return None

    async def collect_all_companies(self, tickers: List[str], start_year: int = 2010,
                                   end_year: int = 2024, save_to_aws: bool = False) -> Dict[str, List[FinancialStatement]]:
        """
        Collect financial data for multiple companies

        Args:
            tickers: List of company tickers
            start_year: Start year for collection
            end_year: End year for collection
            save_to_aws: Whether to save to AWS DynamoDB

        Returns:
            Dictionary mapping tickers to their financial statements
        """
        all_statements = {}

        for ticker in tickers:
            logger.info(f"Starting collection for {ticker}")

            # Collect data
            statements = await self.sec_collector.collect_company_data(ticker, start_year, end_year)
            all_statements[ticker] = statements

            # Save data
            for statement in statements:
                # Always save locally
                self.save_to_local(statement)

                # Optionally save to AWS
                if save_to_aws:
                    table_name = "buffett-chat-ml-dev-financial-statements-raw"
                    self.save_to_dynamodb(statement, table_name)

            logger.info(f"Completed collection for {ticker}: {len(statements)} statements")

        return all_statements

    def get_data_gaps(self, ticker: str, start_year: int = 2010,
                     end_year: int = 2024) -> List[Dict[str, Any]]:
        """
        Identify missing or incomplete data for a company

        Args:
            ticker: Company ticker
            start_year: Start year
            end_year: End year

        Returns:
            List of data gaps
        """
        gaps = []
        expected_statements = ['Income Statement', 'Balance Sheet', 'Cash Flow']

        for year in range(start_year, end_year + 1):
            for statement_type in expected_statements:
                # Check if data exists locally
                statement = self.load_from_local(ticker, year, statement_type)

                if not statement:
                    gaps.append({
                        'ticker': ticker,
                        'year': year,
                        'statement_type': statement_type,
                        'status': 'missing'
                    })
                elif statement and len(statement.data) < 5:  # Arbitrary threshold
                    gaps.append({
                        'ticker': ticker,
                        'year': year,
                        'statement_type': statement_type,
                        'status': 'incomplete',
                        'fields_count': len(statement.data)
                    })

        return gaps


# CLI Interface
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Financial Data Collector Agent")
    parser.add_argument("--tickers", nargs="+", default=["AMZN", "AXP", "COST"],
                       help="Company tickers to collect")
    parser.add_argument("--start-year", type=int, default=2010,
                       help="Start year for data collection")
    parser.add_argument("--end-year", type=int, default=2024,
                       help="End year for data collection")
    parser.add_argument("--save-to-aws", action="store_true",
                       help="Save data to AWS DynamoDB")
    parser.add_argument("--check-gaps", action="store_true",
                       help="Check for data gaps")

    args = parser.parse_args()

    # Initialize agent
    agent = FinancialDataCollectorAgent()

    if args.check_gaps:
        # Check for data gaps
        for ticker in args.tickers:
            gaps = agent.get_data_gaps(ticker, args.start_year, args.end_year)
            if gaps:
                print(f"\nData gaps for {ticker}:")
                for gap in gaps:
                    print(f"  - Year {gap['year']}, {gap['statement_type']}: {gap['status']}")
            else:
                print(f"\n{ticker}: No data gaps found")
    else:
        # Collect data
        async def main():
            statements = await agent.collect_all_companies(
                args.tickers,
                args.start_year,
                args.end_year,
                args.save_to_aws
            )

            # Print summary
            for ticker, stmts in statements.items():
                print(f"\n{ticker}: Collected {len(stmts)} statements")
                years = set(s.fiscal_year for s in stmts)
                print(f"  Years covered: {sorted(years)}")

        asyncio.run(main())