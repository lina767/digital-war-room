"""
Stripe-hosted Checkout for "Support the Mission" one-time payments.
Redirects customer to Stripe's payment page, then back to success/cancel URLs.
Requires: STRIPE_SECRET_KEY, and either STRIPE_PRICE_ID or STRIPE_PRODUCT_ID.
Optional: FRONTEND_URL for success_url/cancel_url.
See: https://docs.stripe.com/checkout/quickstart
"""
import os
from typing import Optional

from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel
import stripe

router = APIRouter()

stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "").strip()


class CreateCheckoutSessionBody(BaseModel):
    return_url_origin: Optional[str] = None


def _get_return_url_origin(origin: Optional[str] = None) -> str:
    if origin and origin.strip():
        return origin.strip().rstrip("/")
    return os.getenv("FRONTEND_URL", "http://localhost:5173").strip().rstrip("/")


def _get_price_id() -> str:
    """Resolve price ID from STRIPE_PRICE_ID or from STRIPE_PRODUCT_ID (product's default/first price)."""
    price_id = os.getenv("STRIPE_PRICE_ID", "").strip()
    if price_id:
        return price_id
    product_id = os.getenv("STRIPE_PRODUCT_ID", "").strip()
    if not product_id:
        raise ValueError("Set STRIPE_PRICE_ID or STRIPE_PRODUCT_ID")
    product = stripe.Product.retrieve(product_id)
    # default_price can be a string (id) or a Price object when expanded
    default = getattr(product, "default_price", None)
    if default is not None:
        return default if isinstance(default, str) else getattr(default, "id", None) or str(default)
    # Fallback: first price for this product
    prices = stripe.Price.list(product=product_id, limit=1)
    if prices.data:
        return prices.data[0].id
    raise ValueError(f"Product {product_id} has no price. Add a price in the Stripe Dashboard.")


@router.post("/create-checkout-session")
async def create_checkout_session(body: CreateCheckoutSessionBody | None = Body(None)):
    """
    Create a Stripe Checkout Session (hosted page). Returns { url } to redirect the customer.
    """
    if not stripe.api_key:
        raise HTTPException(status_code=503, detail="Stripe is not configured (STRIPE_SECRET_KEY)")
    try:
        price_id = _get_price_id()
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e))

    origin = _get_return_url_origin(body.return_url_origin if body else None)
    success_url = f"{origin}/support/return?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{origin}/support"

    try:
        session = stripe.checkout.Session.create(
            submit_type="donate",
            mode="payment",
            success_url=success_url,
            cancel_url=cancel_url,
            line_items=[
                {
                    "price": price_id,
                    "quantity": 1,
                }
            ],
        )
        return {"url": session.url}
    except stripe.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/session-status")
async def session_status(session_id: str):
    """Return Checkout Session status and customer email for the return page."""
    if not stripe.api_key:
        raise HTTPException(status_code=503, detail="Stripe is not configured")
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id required")
    try:
        session = stripe.checkout.Session.retrieve(session_id)
        return {
            "status": session.status,
            "customer_email": (session.customer_details.email if session.customer_details else None) or "",
        }
    except stripe.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))
