from app.modules.products.products_dto import ProductOut
from app.modules.products.products_model import Product


def to_product_out(product: Product) -> ProductOut:
    return ProductOut(
        id=product.id,
        name=product.name,
        category_id=product.category_id,
        category_name=product.category.name,
        reference=product.reference,
        unit_price=product.unit_price,
        purchase_price=product.purchase_price,
        quantity=product.quantity,
        unit=product.unit,
        pack_size=product.pack_size,
        is_transformable=product.is_transformable,
        unit_secondaire=product.unit_secondaire,
        conversion_ratio=product.conversion_ratio,
        unit_price_secondaire=product.unit_price_secondaire,
        purchase_price_secondaire=product.purchase_price_secondaire,
        quantity_secondaire=product.quantity_secondaire,
        created_at=product.created_at,
    )
