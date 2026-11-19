"""Pure commercial arithmetic. No DB writes, provider calls or statutory revenue."""
from decimal import Decimal, localcontext, ROUND_DOWN, ROUND_HALF_EVEN, ROUND_HALF_UP
from app.schemas.marketplace_allocation import AllocationInput, AllocationResult, MarketplacePolicy

PAISE = Decimal('0.01')
ROUNDINGS = {'DOWN': ROUND_DOWN, 'HALF_UP': ROUND_HALF_UP, 'HALF_EVEN': ROUND_HALF_EVEN}
SHARES = {'ATTENDED_BOOKING': 'attended', 'NO_SHOW': 'no_show', 'SINGLE_GYM': 'single_gym'}


def commercial_settings(terms):
    from app.schemas.gym_financial_settings import GymFinancialSettings
    from pydantic import ValidationError
    raw = terms.get('financial_settings')
    if not isinstance(raw, dict): block('POLICY_MISSING', 'Consolidated gym settings missing.')
    # Validation defaults are for onboarding only, never fallback transaction rates.
    if any(name not in raw for name in ('contract_version','individual','single_gym','no_show','multi_gym')):
        block('POLICY_MISSING', 'Incomplete stored gym settings.')
    if any(not isinstance(raw[name],dict) or any(key not in raw[name] for key in ('revenue','gateway_fee'))
            for name in ('individual','single_gym','no_show')):
        block('POLICY_MISSING','Stored percentages and fee shares must be explicit.')
    if not isinstance(raw['multi_gym'],dict) or any(key not in raw['multi_gym'] for key in ('reference_amount','reference_visits','gateway_fee')):
        block('POLICY_MISSING','Stored monthly amount, divisor and fee shares must be explicit.')
    try: return GymFinancialSettings.model_validate(raw)
    except ValidationError: block('POLICY_INVALID', 'Invalid stored gym settings.')


def configured_shares(terms, category):
    from app.schemas.financial_agreement import Sharing
    from pydantic import ValidationError
    try:
        if 'financial_settings' in terms:
            section = getattr(commercial_settings(terms), {'ATTENDED_BOOKING':'individual','NO_SHOW':'no_show','SINGLE_GYM':'single_gym'}[category])
            return section.revenue, section.gateway_fee
        return Sharing.model_validate(terms.get(SHARES[category]) or {}), Sharing(gym_percent=50, fitigo_percent=50)
    except ValidationError: block('POLICY_INVALID', 'Explicit valid revenue and fee percentages required.')


class AllocationBlocked(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


def block(code, message):
    raise AllocationBlocked(code, message)


def exact_amount(value):
    if not isinstance(value, Decimal) or not value.is_finite() or value < 0 or value > Decimal('9999999999.99'):
        block('SOURCE_DATA_INVALID', 'Exact nonnegative Decimal money is required.')
    with localcontext() as ctx:
        ctx.prec = 28
        if value != value.quantize(PAISE): block('SOURCE_DATA_INVALID', 'Money cannot contain fractions of a paise.')
    return value


def equal_units(amount, count, residual):
    """Partition across ALL purchased places, before selecting attended visitors.

    Integer paise guarantees conservation. Never divide by attended visitor count.
    """
    exact_amount(amount)
    if type(count) is not int or not 1 <= count <= 100000:
        block('SOURCE_DATA_INVALID', 'Invalid purchased visitor count.')
    if residual not in {'LOWEST_VISITOR_INDEX', 'FINAL_VISITOR', 'REQUIRE_EXACT'}:
        block('POLICY_MISSING', 'Visitor residual policy is required.')
    with localcontext() as ctx:
        ctx.prec = 28
        units, remainder = divmod(int(amount * 100), count)
        if remainder and residual == 'REQUIRE_EXACT': block('ROUNDING_REVIEW_REQUIRED', 'Amount does not divide exactly.')
        parts = [units] * count
        if residual == 'FINAL_VISITOR': parts[-1] += remainder
        else:
            for index in range(remainder): parts[index] += 1
        return tuple(Decimal(part) / 100 for part in parts)


def distribute_fee(fee, gateway_weights):
    """One checkout fee, stable source order, exact largest-remainder paise.

    Called only under approved PROPORTIONAL_GATEWAY_FUNDED_VALUE policy. Wallet
    funding has zero weight. Persistence/budget enforcement belongs to adapters.
    """
    exact_amount(fee)
    if not gateway_weights or len(gateway_weights) > 100000:
        block('SOURCE_DATA_INVALID', 'Fee distribution requires bounded source lines.')
    weights = [exact_amount(value) for value in gateway_weights]
    with localcontext() as ctx:
        ctx.prec = 28
        total = sum(weights, Decimal(0))
        if not total:
            if fee: block('RECONCILIATION_REQUIRED', 'A positive fee has no gateway-funded line.')
            return tuple(Decimal('0.00') for _ in weights)
        # Integer products/divmod avoid unstable Decimal remainder ordering.
        fee_paise = int(fee * 100)
        weight_units = [int(value * 100) for value in weights]
        denominator = sum(weight_units)
        quotients = [divmod(fee_paise * value, denominator) for value in weight_units]
        parts = [whole for whole, _ in quotients]
        remaining = fee_paise - sum(parts)
        order = sorted(range(len(parts)), key=lambda i: (-quotients[i][1], i))
        for index in order[:remaining]: parts[index] += 1
        return tuple(Decimal(part) / 100 for part in parts)


def monthly_visit_amounts(rates):
    """Exact rational accrual, HALF_UP once at the gym/month total.

    Input order is stable (admission time, check-in ID). Largest fractional paise
    receive the remainder, then lowest input index. No per-visit rate rounding.
    """
    from fractions import Fraction
    exact = []
    for amount, visits in rates:
        exact_amount(amount)
        if type(visits) is not int or visits <= 0: block('POLICY_INVALID', 'Positive reference visit divisor required.')
        exact.append(Fraction(amount) * 100 / visits)
    total = sum(exact, Fraction(0))
    rounded = (2 * total.numerator + total.denominator) // (2 * total.denominator)
    parts = [value.numerator // value.denominator for value in exact]
    order = sorted(range(len(parts)), key=lambda i: (-(exact[i]-parts[i]), i))
    for index in order[:rounded-sum(parts)]: parts[index] += 1
    with localcontext() as ctx:
        ctx.prec=28
        return Decimal(rounded)/100, tuple(Decimal(value)/100 for value in parts)


def policy_from_terms(terms):
    if 'financial_settings' in terms:
        commercial_settings(terms)
        # Operational arithmetic protocol approved for Increment 2, not a second
        # persisted policy contract or statutory-recognition approval.
        from types import SimpleNamespace
        data = dict(allocation_basis='SOURCE_PRICE_AFTER_DISCOUNTS_EXCLUDING_TAX',
            price_representation='GROSS_BEFORE_DISCOUNT', tax_treatment='EXCLUDE_EVIDENCED_TAX',
            rounding='HALF_UP', visitor_residual='LOWEST_VISITOR_INDEX', fee_residual='FITIGO',
            fee_before_payout='REQUIRED', single_gym_entitlement='UPFRONT_ON_VERIFIED_PURCHASE',
            fee_distribution='PROPORTIONAL_GATEWAY_FUNDED_VALUE', cancellation_reversal='FULL_ORIGINAL_ALLOCATION',
            protocol='GYM_SETTINGS_V1', fee_partition_order='LINE_THEN_CONFIGURED_PARTIES')
        return SimpleNamespace(**data, model_dump=lambda **kwargs: dict(data))
    raw = terms.get('marketplace_contract')
    if raw is None: block('POLICY_MISSING', 'Agreement has no approved marketplace allocation contract.')
    from pydantic import ValidationError
    try: policy = MarketplacePolicy.model_validate(raw)
    except ValidationError: block('POLICY_INVALID', 'Marketplace contract is invalid or incomplete.')
    if policy.approval.status != 'APPROVED': block('POLICY_AWAITING_APPROVAL', 'Marketplace contract approval is required.')
    return policy


def split_actual_fee(fee, residual, gym_percent=Decimal('50')):
    exact_amount(fee)
    if residual not in {'FITIGO','GYM_OWNER'}: block('POLICY_MISSING', 'Fee residual policy is required.')
    with localcontext() as ctx:
        ctx.prec=28
        if not isinstance(gym_percent, Decimal) or not gym_percent.is_finite() or not 0 <= gym_percent <= 100:
            block('POLICY_INVALID', 'Invalid fee percentage.')
        gym=(fee*gym_percent/100).quantize(PAISE,rounding=ROUND_DOWN)
        if residual=='GYM_OWNER':gym=fee-(fee*(100-gym_percent)/100).quantize(PAISE,rounding=ROUND_DOWN)
        return gym,fee-gym


def calculate(terms, values: AllocationInput, *, transaction_fee_partition=None):
    """Use only the terms of the already-pinned agreement, never today's template."""
    if not isinstance(values, AllocationInput): raise TypeError('Validated AllocationInput required.')
    policy = policy_from_terms(terms)
    revenue, fee_sharing = configured_shares(terms, values.category)
    gym_percent = revenue.gym_percent
    if values.discount_amount is None or values.tax_amount is None:
        block('SOURCE_DATA_MISSING', 'Discount and tax evidence must be explicit; missing is not zero.')
    with localcontext() as ctx:
        ctx.prec = 28
        price = values.price_amount
        if policy.price_representation == 'GROSS_BEFORE_DISCOUNT': price -= values.discount_amount
        eligible = price - values.tax_amount
        if eligible < 0: block('SOURCE_DATA_INVALID', 'Discount or tax exceeds the transaction price.')
        if values.wallet_amount + values.gateway_amount != price:
            block('FUNDING_MISMATCH', 'Wallet and gateway funding do not equal the after-discount customer amount.')
        gym = (eligible * gym_percent / 100).quantize(PAISE, rounding=ROUNDINGS[policy.rounding])
        fitigo = eligible - gym  # exact commercial residual, never two independent roundings
        fee = None
        fee_status = 'PENDING_EVIDENCE'
        if values.actual_gateway_fee is not None:
            if values.gateway_amount == 0 and values.actual_gateway_fee != 0:
                block('RECONCILIATION_REQUIRED', 'Wallet-only units cannot bear a gateway fee.')
            if not values.fee_evidence_reference: block('SOURCE_DATA_MISSING', 'An actual fee requires its source evidence reference.')
            if values.fee_basis == 'INCLUDING_TAX': fee = values.actual_gateway_fee
            elif values.fee_basis == 'EXCLUDING_TAX' and values.fee_tax is not None:
                fee = values.actual_gateway_fee + values.fee_tax
            # Unknown tax on an excluding-tax fee leaves net pending, not zero.
            if fee is not None:
                exact_amount(fee)
                if values.fee_basis == 'INCLUDING_TAX' and values.fee_tax is not None and values.fee_tax > fee:
                    block('SOURCE_DATA_INVALID', 'Included fee tax exceeds total fee.')
                fee_status = 'VERIFIED'
        elif values.gateway_amount == 0:
            if values.fee_tax is not None or values.fee_evidence_reference:
                block('SOURCE_DATA_MISSING', 'Incomplete explicit fee evidence cannot be treated as zero.')
            fee = Decimal('0.00'); fee_status = 'WALLET_ONLY_NO_GATEWAY_FEE'
        gym_fee = fitigo_fee = gym_net = fitigo_net = None
        readiness = 'FEE_PENDING' if policy.fee_before_payout == 'REQUIRED' else 'PROVISIONAL_GROSS'
        if fee is not None:
            gym_fee,fitigo_fee=split_actual_fee(fee,policy.fee_residual,fee_sharing.gym_percent)
            if transaction_fee_partition is not None:
                gym_fee,fitigo_fee=transaction_fee_partition
                exact_amount(gym_fee);exact_amount(fitigo_fee)
                if gym_fee+fitigo_fee!=fee:
                    block('RECONCILIATION_REQUIRED','Transaction fee partition does not conserve actual fee.')
            gym_net, fitigo_net = gym - gym_fee, fitigo - fitigo_fee
            readiness = 'NEGATIVE_NET_REVIEW' if min(gym_net, fitigo_net) < 0 else 'NET_VALIDATED'
        return AllocationResult(category=values.category, eligible_amount=eligible,
            customer_funded_amount=price, wallet_amount=values.wallet_amount, gateway_amount=values.gateway_amount,
            gym_gross_share=gym, fitigo_gross_commission=fitigo, gateway_fee=fee,
            gym_gateway_fee_share=gym_fee, fitigo_gateway_fee_share=fitigo_fee,
            gym_owner_net_entitlement=gym_net, fitigo_net_commission=fitigo_net,
            fee_status=fee_status, payout_readiness=readiness,
            entitlement_timing='UPFRONT' if values.category=='SINGLE_GYM' else 'CONFIGURED_SETTLEMENT_CYCLE')