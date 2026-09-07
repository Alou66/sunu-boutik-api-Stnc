from app.modules.customers.customers_dto import ClientOut
from app.modules.customers.customers_model import Client


def to_client_out(client: Client) -> ClientOut:
    return ClientOut.model_validate(client)
