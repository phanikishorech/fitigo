"""Preserve verified provider observations alongside existing reconciliation."""
from decimal import Decimal
from app.services.source_evidence import enabled, snapshot


def observe(db, checkout, attempt, payment, *, provider_event_id=None):
    if not enabled(db): return
    if attempt.checkout_id != checkout.id or attempt.external_id != payment.id or payment.order_id != checkout.gateway_order_id or payment.currency != checkout.currency:
        from fastapi import HTTPException
        raise HTTPException(409, 'Payment source evidence relationship mismatch.')
    state = payment.collection_state or ('CAPTURED' if payment.status=='SUCCESS' else 'FAILED' if payment.status=='FAILED' else 'INITIATED')
    if payment.status != 'SUCCESS' and state == 'CAPTURED': state = 'INITIATED'
    collection_state = state
    if payment.status == 'SUCCESS' and payment.refunded:
        state = 'FULLY_REFUNDED' if payment.refunded == payment.amount else 'PARTIALLY_REFUNDED'
    common = {'attempt_id':attempt.id, 'provider':checkout.provider, 'provider_order_id':payment.order_id,
        'provider_payment_id':payment.id, 'provider_event_id':provider_event_id,
        'verification_source':'AUTHENTICATED_PROVIDER_FETCH', 'verification_status':'VERIFIED',
        'collection_state':collection_state, 'observed_payment_state':state, 'capture_timestamp_source':payment.timestamp_source,
        'capture_timestamp_status':'AVAILABLE' if payment.captured_at else 'UNAVAILABLE',
        'fee_amount':str(Decimal(payment.fee)/100) if payment.fee is not None else None,
        'fee_tax_amount':str(Decimal(payment.fee_tax)/100) if payment.fee_tax is not None else None,
        'fee_basis':payment.fee_basis, 'refund_evidence_status':payment.refund_evidence_status,
        'amount_matches_checkout':Decimal(payment.amount)/100==checkout.amount}
    capture = snapshot(db, 'PAYMENT_CAPTURED' if payment.status=='SUCCESS' else 'PAYMENT_'+state,
        'PAYMENT_ATTEMPT', attempt.id, checkout=checkout, occurred_at=payment.captured_at if payment.status=='SUCCESS' else None,
        amount=Decimal(payment.amount)/100, currency=payment.currency, payload=common)
    if provider_event_id:
        snapshot(db, 'PROVIDER_EVENT_VERIFIED', 'PAYMENT_ATTEMPT', attempt.id, checkout=checkout,
            discriminator=provider_event_id,
            payload={'provider_event_id':provider_event_id, 'provider':checkout.provider,
                'provider_payment_id':payment.id, 'attempt_id':attempt.id, 'observed_evidence_id':capture.id,
                'verification_source':'SIGNED_WEBHOOK_AND_PROVIDER_FETCH'})
    if payment.status=='SUCCESS' and (payment.captured_at is not None or payment.fee is not None or payment.fee_tax is not None):
        # Later provider detail is additive. Never rewrite initial capture evidence
        # or emit a second capture event when a missing timestamp/fee becomes known.
        detail_key=f'{payment.captured_at}:{payment.fee}:{payment.fee_tax}:{payment.fee_basis}'
        snapshot(db, 'PAYMENT_DETAILS_VERIFIED', 'PAYMENT_ATTEMPT', attempt.id, checkout=checkout,
            occurred_at=payment.captured_at, discriminator=detail_key,
            payload={**common, 'capture_evidence_id':capture.id}, amount=Decimal(payment.amount)/100, currency=payment.currency)
    if state in {'PARTIALLY_REFUNDED','FULLY_REFUNDED'}:
        snapshot(db, 'PAYMENT_REFUND_OBSERVED', 'PAYMENT_ATTEMPT', attempt.id, checkout=checkout,
            payload={**common, 'cumulative_refunded_amount':str(Decimal(payment.refunded)/100)}, discriminator=str(payment.refunded))
    seen_refunds = {}
    for refund in payment.refunds:
        signature = (refund.payment_id, refund.amount, refund.currency, refund.status, refund.occurred_at)
        if refund.id in seen_refunds and seen_refunds[refund.id] != signature:
            from fastapi import HTTPException
            raise HTTPException(409, 'Conflicting provider refund identity')
        seen_refunds[refund.id] = signature
        if refund.payment_id != payment.id or refund.currency != payment.currency or refund.amount > payment.amount:
            from fastapi import HTTPException
            raise HTTPException(409, 'Refund evidence does not match original payment')
        confirmed = refund.status in {'SUCCESS','processed'}
        refund_evidence = snapshot(db, 'REFUND_CONFIRMED' if confirmed else 'REFUND_OBSERVED', 'PROVIDER_REFUND',
            f'{checkout.provider}:{refund.id}', checkout=checkout, occurred_at=refund.occurred_at,
            amount=Decimal(refund.amount)/100, currency=refund.currency,
            discriminator='' if confirmed else refund.status,
            payload={'refund_id':refund.id, 'provider_payment_id':payment.id, 'attempt_id':attempt.id,
                'provider':checkout.provider, 'provider_order_id':payment.order_id, 'provider_status':refund.status,
                'provider_event_id':provider_event_id, 'verification_status':'VERIFIED',
                'verification_source':'AUTHENTICATED_PROVIDER_FETCH', 'timestamp_source':refund.timestamp_source})
        if refund_evidence.payload['provider_payment_id'] != payment.id:
            from fastapi import HTTPException
            raise HTTPException(409, 'Refund is already linked to a different payment')
        if confirmed and refund.occurred_at is not None and refund_evidence.occurred_at is None:
            snapshot(db, 'REFUND_DETAILS_VERIFIED', 'PROVIDER_REFUND', f'{checkout.provider}:{refund.id}',
                checkout=checkout, occurred_at=refund.occurred_at, discriminator=str(refund.occurred_at),
                payload={'refund_evidence_id':refund_evidence.id, 'timestamp_source':refund.timestamp_source,
                    'provider_payment_id':payment.id})