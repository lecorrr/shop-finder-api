class ObjectIdConverter:
    """A MongoDB ObjectId in a URL: 24 lowercase hex digits, anything else is a 404."""

    regex = "[0-9a-f]{24}"

    def to_python(self, value: str) -> str:
        return value

    def to_url(self, value: str) -> str:
        return value
