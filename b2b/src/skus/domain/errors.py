class ProductNotFoundError(RuntimeError):
    pass


class ProductHardBlockedError(RuntimeError):
    pass


class ProductAccessDeniedError(RuntimeError):
    pass


class SkuNotFoundError(RuntimeError):
    pass


class SkuHasActiveReservesError(RuntimeError):
    pass
