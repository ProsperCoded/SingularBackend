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
    if settings.SKIP_PAYMENT_VERIFICATION:
        import uuid

        mock_ref = transaction_ref or f"MOCK_REF_{uuid.uuid4().hex[:8]}"
        print(f"Skipping payment initiation for {email}. Using mock ref: {mock_ref}")
        return {
            "transaction_ref": mock_ref,
            "checkout_url": f"https://mock.checkout/ref={mock_ref}",
            "amount": amount,
        }

    url = f"{settings.SQUAD_BASE_URL}/transaction/initiate"
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
            print(f"Initiating Squad transaction for {email} at {url}")
            response = await client.post(url, headers=headers, json=payload)
            print(f"Squad API Response Status: {response.status_code}")

            resp_json = response.json()
            if response.status_code != 200:
                print(f"Squad API Error Body: {resp_json}")

            response.raise_for_status()

            data = resp_json.get("data")
            if not isinstance(data, dict):
                # Some versions of Squad return the fields at root, though docs say data
                data = resp_json

            checkout_url = data.get("checkout_url") or data.get("auth_url")
            generated_ref = data.get("transaction_ref") or data.get("Transaction_Ref")

            if not isinstance(generated_ref, str) or not generated_ref:
                print(f"Malformed Squad Response (Missing Ref): {resp_json}")
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"Squad did not return a transaction reference. Response: {resp_json}",
                )
            if not isinstance(checkout_url, str) or not checkout_url:
                print(f"Missing Checkout URL: {resp_json}")
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
        print(f"Squad API Connection/HTTP Error: {type(e).__name__} - {e}")
        if hasattr(e, "response") and e.response:
            print(f"Squad Error Response: {e.response.text}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to communicate with the payment gateway: {str(e)}",
        )
    except Exception as e:
        print(
            f"Unexpected Error in initiate_squad_transaction: {type(e).__name__} - {e}"
        )
        import traceback

        traceback.print_exc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal error during payment initiation: {str(e)}",
        )


async def verify_squad_transaction(
    transaction_ref: str, expected_amount: int | None = None
):
    """
    Calls the Squad API to ensure a transaction was actually successful.
    The backend persists the transaction reference after status verification.
    """
    if settings.SKIP_PAYMENT_VERIFICATION:
        print(f"Skipping payment verification for ref: {transaction_ref}")
        return True

    url = f"{settings.SQUAD_BASE_URL}/transaction/verify/{transaction_ref}"

    headers = {
        "Authorization": f"Bearer {settings.SQUAD_SECRET_KEY}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers)
            data = response.json()
            print("response", response, data)
            response.raise_for_status()  # Raises an error for 4xx/5xx responses

            transaction_data = data.get("data", {})
            print(
                "Squad transaction verification result "
                f"ref={transaction_ref} status={transaction_data.get('transaction_status')!r}"
            )

            # Check if Squad actually says it was successful.
            if str(transaction_data.get("transaction_status", "")).lower() != "success":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Transaction was not successful according to Squad.",
                )

            if expected_amount is not None:
                print(
                    "Squad transaction amount check skipped "
                    f"ref={transaction_ref} expected_amount={expected_amount}"
                )

            return True

    except httpx.HTTPError as e:
        print(f"Squad API Error: {type(e).__name__} - {e}")
        print(f"transaction reference: {transaction_ref}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to communicate with the payment gateway.",
        )
