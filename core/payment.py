import httpx
from fastapi import HTTPException, status
from core.config import settings

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
            if data.get("data", {}).get("transaction_status") != "success":
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