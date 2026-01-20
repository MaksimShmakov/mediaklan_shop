from pydantic import BaseModel


class RedeemRequest(BaseModel):
    variant_id: int
