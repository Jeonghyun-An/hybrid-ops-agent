from pydantic import BaseModel


class Health(BaseModel):
    status: str = "ok"


class Order(BaseModel):
    order_id: int
    sku: str
    quantity: int


class Stock(BaseModel):
    sku: str
    available: int


class OrderDetail(BaseModel):
    order: Order
    stock: Stock
