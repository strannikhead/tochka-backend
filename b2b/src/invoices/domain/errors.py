class EmptyInvoiceError(RuntimeError):
    """Invoice was submitted with no items."""


class InvoiceSkuNotFoundError(RuntimeError):
    """An item references a SKU that does not exist."""


class InvoiceSkuNotOwnedError(RuntimeError):
    """An item references a SKU owned by another seller (IDOR / 403)."""


class InvoiceSkuNotModeratedError(RuntimeError):
    """An item references a SKU whose product is not MODERATED."""
