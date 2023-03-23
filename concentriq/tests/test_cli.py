#
# Copyright (c) 2020 Bayer AG.
#
# This file is part of `python-concentriq`
#

from __future__ import annotations

import subprocess
import sys


def test_concentriq_command():
    output = subprocess.run(
        [
            sys.executable,
            "-m",
            "concentriq",
            "--help",
        ],
        capture_output=True,
    )
    assert output.returncode == 0
    assert "concentriq" in output.stdout.decode()
