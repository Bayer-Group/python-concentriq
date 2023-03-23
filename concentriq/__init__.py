#
# Copyright (c) 2020 Bayer AG.
#
# This file is part of `python-concentriq`
#

try:
    from ._version import version as __version__
except ImportError:  # pragma: no cover
    __version__ = "not-installed"

__author__ = """\
Santiago Villalba <santiago.villalba@bayer.com>
Andreas Poehlmann <andreas.poehlmann@bayer.com>
"""

from concentriq.api import API
from concentriq.api import APIError

__all__ = [
    "API",
    "APIError",
]
