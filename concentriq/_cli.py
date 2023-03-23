#
# Copyright (c) 2020 Bayer AG.
#
# This file is part of `python-concentriq`
#

from __future__ import annotations

import os.path
from contextlib import contextmanager
from typing import NoReturn

import orjson
import typer

from concentriq import API
from concentriq import APIError

# constants: todo use platformdirs
CQ_SECRETS_PATH = os.path.expanduser("~/.secrets/proscia.json")


def get_api() -> API:
    """return an instantiated api"""
    try:
        return API.from_secrets_file(CQ_SECRETS_PATH)
    except ValueError as err:
        if "api_url" in str(err):
            typer.secho(
                "please run `concentriq config setup` to add api_url to your config",
                fg="red",
                err=True,
            )
            raise typer.Exit(1)
        raise


def json_dumps(data):
    """serialize more datatypes"""
    return orjson.dumps(data, option=orjson.OPT_INDENT_2).decode()


def json_loads(string):
    """deserialize json"""
    return orjson.loads(string)


def typer_not_implemented() -> NoReturn:
    """typer styled n/a"""
    typer.secho("not implemented", fg=typer.colors.RED)
    raise typer.Exit(code=1)


@contextmanager
def typerize_api_error():
    try:
        yield
    except APIError as err:
        typer.secho(f"APIError: {err}", fg=typer.colors.RED)
        raise typer.Exit(code=1)
