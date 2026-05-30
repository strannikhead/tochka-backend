class CategoryNotFoundError(RuntimeError):
    pass


class ProductNotFoundError(RuntimeError):
    """Product is absent or not owned by the requesting seller.

    Both cases surface as 404 so we never reveal that someone else's product exists.
    """

    pass


class ProductNotOwnedError(RuntimeError):
    pass


class ProductHardBlockedError(RuntimeError):
    pass


class SkuNotFoundError(RuntimeError):
    pass


class SkuNotOwnedError(RuntimeError):
    pass
