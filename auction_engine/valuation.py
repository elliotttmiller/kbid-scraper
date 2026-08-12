from __future__ import annotations

from .config import EngineConfig
from .models import AnalysisResult, AuctionItem, Comparable, CostBreakdown, MarketSnapshot, ScenarioResult


def _round(value: float) -> float:
    return round(value + 1e-10, 2)


def _sale_costs(sell_price: float, config: EngineConfig) -> tuple[float, float]:
    costs = config.costs
    platform = sell_price * costs.platform_fee_rate + costs.platform_fixed_fee
    return_reserve = sell_price * costs.return_rate * costs.return_loss_rate
    return platform, return_reserve


def _fixed_operating_cost(config: EngineConfig) -> float:
    costs = config.costs
    return (
        costs.pickup_cost
        + costs.outbound_shipping
        + costs.packaging_cost
        + costs.labor_hours * costs.hourly_labor_rate
        + costs.storage_cost
        + costs.refurbishment_reserve
    )


def _acquisition_for_bid(bid: float, premium_rate: float, premium_cap: float | None, tax_rate: float) -> tuple[float, float, float]:
    premium = bid * premium_rate
    if premium_cap is not None and premium_cap > 0:
        premium = min(premium, premium_cap)
    tax = (bid + premium) * tax_rate
    return premium, tax, bid + premium + tax


def analyze(item: AuctionItem, market: MarketSnapshot, evidence: tuple[Comparable, ...], config: EngineConfig) -> AnalysisResult:
    costs = config.costs
    premium_rate = item.buyers_premium_rate if item.buyers_premium_rate is not None else costs.buyers_premium_rate
    tax_rate = item.sales_tax_rate if item.sales_tax_rate is not None else costs.sales_tax_rate
    premium, tax, acquisition = _acquisition_for_bid(
        item.current_bid, premium_rate, item.buyers_premium_cap, tax_rate
    )
    base_platform, base_return = _sale_costs(market.median_price, config)
    operating = _fixed_operating_cost(config)
    total_cost = acquisition + operating + base_platform + base_return

    cost_breakdown = CostBreakdown(
        hammer_price=_round(item.current_bid),
        buyers_premium=_round(premium),
        sales_tax=_round(tax),
        acquisition_total=_round(acquisition),
        pickup=_round(costs.pickup_cost),
        outbound_shipping=_round(costs.outbound_shipping),
        packaging=_round(costs.packaging_cost),
        labor=_round(costs.labor_hours * costs.hourly_labor_rate),
        storage=_round(costs.storage_cost),
        refurbishment=_round(costs.refurbishment_reserve),
        platform_fees=_round(base_platform),
        return_reserve=_round(base_return),
        total_cost=_round(total_cost),
    )

    prices = (market.low_price, market.median_price, market.high_price)
    names = ("downside", "base", "upside")
    scenarios: list[ScenarioResult] = []
    for name, price, probability in zip(names, prices, config.market.scenario_probabilities):
        platform, returns = _sale_costs(price, config)
        profit = price - acquisition - operating - platform - returns
        scenarios.append(ScenarioResult(name, _round(price), probability, _round(profit)))

    expected_profit = sum(s.net_profit * s.probability for s in scenarios)
    expected_sell = sum(s.sell_price * s.probability for s in scenarios)
    expected_roi = expected_profit / acquisition if acquisition > 0 else 0.0
    variable_rate = costs.platform_fee_rate + costs.return_rate * costs.return_loss_rate
    break_even = (acquisition + operating + costs.platform_fixed_fee) / max(0.01, 1 - variable_rate)

    base_net_before_acquisition = market.median_price * (1 - variable_rate) - costs.platform_fixed_fee - operating
    maximum_bid = 0.0
    low, high = 0.0, max(0.0, base_net_before_acquisition)
    for _ in range(64):
        candidate = (low + high) / 2
        _, _, candidate_acquisition = _acquisition_for_bid(candidate, premium_rate, item.buyers_premium_cap, tax_rate)
        candidate_profit = base_net_before_acquisition - candidate_acquisition
        candidate_roi = candidate_profit / candidate_acquisition if candidate_acquisition > 0 else float("inf")
        feasible = candidate_profit >= config.decisions.minimum_profit and candidate_roi >= config.decisions.target_roi
        if feasible:
            maximum_bid = candidate
            low = candidate
        else:
            high = candidate

    downside_loss = abs(min(scenarios[0].net_profit, 0))
    capital = max(acquisition, 1.0)
    risk = (
        (1 - market.confidence) * 42
        + min(1.0, market.price_dispersion) * 22
        + (1 - market.liquidity) * 16
        + min(1.0, downside_loss / capital) * 20
    )
    risk_factors: list[str] = []
    if market.sold_count == 0:
        if market.active_count > 0:
            risk_factors.append(
                f"No verified sold comparables; {market.active_count} active asking-price listings found"
            )
        else:
            risk_factors.append("No comparable market evidence found")
    if market.comp_count < config.decisions.minimum_comps:
        risk_factors.append("Insufficient comparable sample")
    if market.price_dispersion > 0.45:
        risk_factors.append("Wide comparable price dispersion")
    if item.condition.lower() in {"unknown", "damaged", "parts"}:
        risk_factors.append(f"Condition risk: {item.condition}")
        risk += 8
    excluded = any(term in f"{item.category} {item.title}".lower() for term in config.decisions.exclude_category_terms)
    if excluded:
        risk_factors.append("Excluded bulky/furniture category")
        risk = 100

    profit_component = min(1.0, max(0.0, expected_profit / max(config.decisions.minimum_profit * 3, 1)))
    roi_component = min(1.0, max(0.0, expected_roi / max(config.decisions.target_roi * 2, 0.01)))
    opportunity = 100 * (
        profit_component * 0.28
        + roi_component * 0.22
        + market.confidence * 0.22
        + market.liquidity * 0.13
        + (1 - min(1.0, risk / 100)) * 0.15
    )
    risk = max(0.0, min(100.0, risk))
    opportunity = max(0.0, min(100.0, opportunity))

    if excluded:
        recommendation = "PASS"
    elif market.comp_count > 0 and (expected_profit <= 0 or maximum_bid <= item.current_bid):
        recommendation = "PASS"
    elif market.comp_count < config.decisions.minimum_comps or market.confidence < config.decisions.minimum_confidence:
        recommendation = "RESEARCH"
    elif risk > config.decisions.maximum_risk_score:
        recommendation = "WATCH"
    elif opportunity >= config.decisions.strong_buy_score:
        recommendation = "STRONG_BUY"
    elif opportunity >= config.decisions.buy_score:
        recommendation = "BUY"
    elif opportunity >= config.decisions.watch_score:
        recommendation = "WATCH"
    else:
        recommendation = "PASS"

    return AnalysisResult(
        item=item,
        market=market,
        costs=cost_breakdown,
        scenarios=tuple(scenarios),
        expected_sell_price=_round(expected_sell),
        expected_profit=_round(expected_profit),
        expected_roi=round(expected_roi * 100, 2),
        break_even_sell_price=_round(break_even),
        maximum_bid=_round(maximum_bid),
        opportunity_score=round(opportunity, 2),
        risk_score=round(risk, 2),
        recommendation=recommendation,
        risk_factors=tuple(risk_factors),
        evidence=evidence,
    )
