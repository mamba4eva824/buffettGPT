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
import DecisionTriggersPanel from './DecisionTriggersPanel';

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
  triggers: DecisionTriggersPanel,
};
