import {
  GrowthPanel,
  ProfitabilityPanel,
  ValuationPanel,
  CashFlowPanel,
  DebtPanel,
  EarningsQualityPanel,
  EarningsPerformancePanel,
  MoatPanel,
} from './CategoryPanels';
import ExecutiveDashboard from './ExecutiveDashboard';

export const PANEL_MAP = {
  dashboard: ExecutiveDashboard,
  growth: GrowthPanel,
  profitability: ProfitabilityPanel,
  valuation: ValuationPanel,
  earnings_performance: EarningsPerformancePanel,
  cashflow: CashFlowPanel,
  debt: DebtPanel,
  earnings_quality: EarningsQualityPanel,
  moat: MoatPanel,
};
