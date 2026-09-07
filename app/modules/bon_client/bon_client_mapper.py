from app.modules.bon_client.bon_client_dto import BonClientOut
from app.modules.bon_client.bon_client_model import BonClient


def to_bon_client_out(bon_client: BonClient) -> BonClientOut:
    return BonClientOut.model_validate(bon_client)
