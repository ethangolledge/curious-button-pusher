"""The two errors reported before any model is called: a configuration that cannot work, and a
request that cannot be met."""


class ConfigurationError(ValueError):
    pass


class InputError(ValueError):
    """A problem with what the user asked for, reported before any model is called."""
