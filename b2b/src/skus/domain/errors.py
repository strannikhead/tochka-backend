class ProductNotFoundError(RuntimeError):
    pass


class ProductHardBlockedError(RuntimeError):
    pass


class ProductAccessDeniedError(RuntimeError):
    pass
