"""Dummy MLFlow tracking module."""


class MLFlowDummy:
    """Dummy object that can be called with everything."""

    def __getattr__(self: "MLFlowDummy", name: str) -> "MLFlowDummy":
        """Return a new instance of MLFlowDummy for any attribute access.

        Args:
        ----
            name: The name of the attribute being accessed.

        Returns:
        -------
            A new instance of MLFlowDummy.

        """
        return MLFlowDummy()

    def __call__(self: "MLFlowDummy", *args: tuple, **kwargs: dict) -> None:
        """Do nothing when the object is called as a function.

        Args:
        ----
            *args: Positional arguments (ignored).
            **kwargs: Keyword arguments (ignored).

        """
