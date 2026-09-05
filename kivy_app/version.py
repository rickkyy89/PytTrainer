"""Application version information.

Keep ``__version__`` as a plain literal: Buildozer can read it without
importing Kivy.  The last component is the build number.
"""

__version__ = "0.2.0.7"


def version_name() -> str:
    """Return the user-facing semantic version (without the build number)."""
    return ".".join(__version__.split(".")[:3])


def build_number() -> int:
    """Return the integer build number encoded in ``__version__``."""
    return int(__version__.split(".")[3])


def version_label() -> str:
    """Return the compact version label used by the PC and Android UI."""
    return f"pyTrainer {version_name()} · build {build_number()}"


def version_display() -> str:
    """Return the version in the form requested for release information."""
    return f"{version_name()} + build {build_number()}"
