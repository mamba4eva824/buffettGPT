import {
  GrowthPanel,
  ProfitabilityPanel,
  ValuationPanel,
  CashFlowPanel,
  DebtPanel,
  EarningsQualityPanel,
} from './CategoryPanels';
import ExecutiveDashboard from './ExecutiveDashboard';

export const PANEL_MAP = {
  dashboard: ExecutiveDashboard,
  growth: GrowthPanel,
  profitability: ProfitabilityPanel,
  valuation: ValuationPanel,
  cashflow: CashFlowPanel,
  debt: DebtPanel,
  earnings_quality: EarningsQualityPanel,
};
