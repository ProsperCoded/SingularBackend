from __future__ import annotations

import httpx
from fastapi import HTTPException, status

from core.config import settings


async def initiate_squad_transaction(
    *,
    email: str,
    amount: int,
    customer_name: str | None = None,
    transaction_ref: str | None = None,
    callback_url: str | None = None,
    metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    url = f"{settings.SQUAD_BASE_URL}/transaction/Initiate"
    headers = {
        "Authorization": f"Bearer {settings.SQUAD_SECRET_KEY}",
        "Content-Type": "application/json",
    }
    payload: dict[str, object] = {
        "email": email,
        "amount": amount,
        "currency": "NGN",
        "initiate_type": "inline",
    }
    if customer_name:
        payload["customer_name"] = customer_name
    if transaction_ref:
        payload["transaction_ref"] = transaction_ref
    if callback_url:
        payload["callback_url"] = callback_url
    if metadata:
        payload["metadata"] = metadata

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json().get("data", {})
            checkout_url = data.get("checkout_url") or data.get("auth_url")
            generated_ref = data.get("transaction_ref")
            if not isinstance(generated_ref, str) or not generated_ref:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Squad did not return a transaction reference.",
                )
            if not isinstance(checkout_url, str) or not checkout_url:
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Squad did not return a checkout URL.",
                )
            return {
                "transaction_ref": generated_ref,
                "checkout_url": checkout_url,
                "amount": amount,
            }
    except httpx.HTTPError as e:
        print(f"Squad API Error: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to communicate with the payment gateway.",
        )


async def verify_squad_transaction(transaction_ref: str, expected_amount: int):
    """
    Calls the Squad API to ensure a transaction was actually successful 
    and matches the amount we expect them to pay.
    """
    url = f"{settings.SQUAD_BASE_URL}/transaction/verify/{transaction_ref}"
    
    headers = {
        "Authorization": f"Bearer {settings.SQUAD_SECRET_KEY}",
        "Content-Type": "application/json"
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status() # Raises an error for 4xx/5xx responses
            
            data = response.json()
            
            # Check if Squad actually says it was successful
            if str(data.get("data", {}).get("transaction_status", "")).lower() != "success":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Transaction was not successful according to Squad."
                )
            
            # Check the amount. Squad returns the amount in kobo (multiply Naira by 100)
            # If your tag costs 5 Naira, expected_amount should be 500 kobo per tag.
            actual_amount = data.get("data", {}).get("transaction_amount")
            
            if actual_amount != expected_amount:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Payment mismatch. Expected {expected_amount} kobo, but Squad reported {actual_amount} kobo."
                )
            
            return True

    except httpx.HTTPError as e:
        print(f"Squad API Error: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to communicate with the payment gateway."
        )
