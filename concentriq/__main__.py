#
# Copyright (c) 2020 Bayer AG.
#
# This file is part of `python-concentriq`
#

"""concentriq.__main__

support calling `python -m concentriq`
"""
import enum
import logging
import os
import os.path
from operator import itemgetter
from pathlib import Path
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from urllib.parse import unquote_plus
from urllib.parse import urlsplit

import click
import typer
import typer.colors
from rich import print as rich_print
from rich.table import Table
from typer import FileTextWrite

from concentriq import APIError
from concentriq._cli import CQ_SECRETS_PATH
from concentriq._cli import get_api
from concentriq._cli import json_dumps
from concentriq._cli import json_loads
from concentriq._cli import typerize_api_error
from concentriq.models import AnnotationFilters
from concentriq.models import ImageFilters
from concentriq.models import Pagination
from concentriq.models import SortBy

# === concentriq cli interface ================================================

if os.environ.get("CONCENTRIQ_DEBUG", "0").lower() in {"true", "1"}:
    logging.basicConfig(level=logging.DEBUG)

app = typer.Typer(
    name="concentriq",
    epilog="#### Proscia Concentriq via Python ####",
    no_args_is_help=True,
)

# --- groups subcommand -------------------------------------------------------

app_groups = typer.Typer(no_args_is_help=True)
app.add_typer(app_groups, name="group")


@app_groups.command(name="list")
def groups_list(
    json_: bool = typer.Option(False, "--json", help="return as json"),
):
    """list available groups"""
    api = get_api()
    with typerize_api_error():
        groups = api.group_list()
    data = [grp.dict() for grp in groups]
    if json_:
        typer.echo(json_dumps(data))
    else:
        columns = {
            "id": "ID",
            "name": "Name",
            "image_set_count": "#ImageSets",
            "owner_name": "Owner",
        }
        tbl = Table(*columns.values(), title="Groups")
        for row in map(itemgetter(*columns.keys()), data):
            tbl.add_row(*map(str, row))
        rich_print(tbl)


@app_groups.command(name="info")
def groups_info(
    id_: int = typer.Argument(..., metavar="id", help="group id"),
    json_: bool = typer.Option(False, "--json", help="return as json"),
):
    """detailed info about a group"""
    api = get_api()
    with typerize_api_error():
        grp = api.group_get(id_)
    if json_:
        typer.echo(json_dumps(grp.dict()))
    else:
        tbl = Table("Key", "Value", title=f"Group #{id_}")
        for key, value in grp.dict().items():
            if isinstance(value, dict):
                continue
            tbl.add_row(key, str(value))
        rich_print(tbl)


# ---  subcommand -------------------------------------------------------

app_imagesets = typer.Typer(no_args_is_help=True)
app.add_typer(app_imagesets, name="imageset")


@app_imagesets.command(name="list")
def imagesets_list(
    json_: bool = typer.Option(False, "--json", help="return as json"),
    filter_group: Optional[str] = typer.Option(
        None, "--filter-group", help="filter by group name"
    ),
    filter_owner: Optional[str] = typer.Option(
        None, "--filter-owner", help="filter by owner name"
    ),
):
    """list imagesets"""
    api = get_api()
    with typerize_api_error():
        im_sets = api.imageset_list()

    def filter_(x):
        return all(
            [
                filter_group is None
                or filter_group.lower() in (x["group_name"] or "").lower(),
                filter_owner is None
                or filter_owner.lower() in (x["owner_name"] or "").lower(),
            ]
        )

    data = [im_set.dict() for im_set in im_sets]
    data = list(filter(filter_, data))
    if json_:
        typer.echo(json_dumps(data))
    else:
        columns = {
            "id": "ID",
            "name": "Name",
            "image_count": "#Images",
            "owner_name": "Owner",
            "group_name": "Group",
        }
        tbl = Table(*columns.values(), title="Groups")
        for row in map(itemgetter(*columns.keys()), data):
            tbl.add_row(*map(str, row))
        rich_print(tbl)


@app_imagesets.command(name="info")
def imagesets_info(
    id_: int = typer.Argument(..., metavar="id", help="imageset id"),
    json_: bool = typer.Option(False, "--json", help="return as json"),
):
    """imageset info"""
    api = get_api()
    with typerize_api_error():
        im_set = api.imageset_get(id_)
    if json_:
        typer.echo(json_dumps(im_set.dict()))
    else:
        tbl = Table("Key", "Value", title=f"Imageset #{id_}")
        for key, value in im_set.dict().items():
            if isinstance(value, dict):
                continue
            tbl.add_row(key, str(value))
        rich_print(tbl)


@app_imagesets.command()
def create(
    name: str = typer.Argument(..., help="imageset name"),
    group_id: int = typer.Option(..., metavar="group-id", help="group id"),
    json_: bool = typer.Option(False, "--json", help="return as json"),
):
    """imageset create"""
    api = get_api()
    with typerize_api_error():
        im_set = api.imageset_create(name, group=group_id)
    if json_:
        typer.echo(json_dumps(im_set.dict()))
    else:
        tbl = Table("Key", "Value", title=f"Imageset #{im_set.id}")
        for key, value in im_set.dict().items():
            if isinstance(value, dict):
                continue
            tbl.add_row(key, str(value))
        rich_print(tbl)


@app_imagesets.command()
def export_metadata_csv(
    id_: int = typer.Argument(..., metavar="id", help="imageset id"),
    output: FileTextWrite = typer.Option(
        click.open_file("-", mode="w"),
        "--output",
        help="output file, default stdout",
    ),
):
    """export imageset metadata as csv"""
    api = get_api()
    with typerize_api_error():
        data = api.imageset_export_metadata_csv(id_)
    output.write(data)


# TODO:
#  - get_api().imageset_delete()
#  - get_api().imageset_update()

# --- image subcommand --------------------------------------------------------

app_images = typer.Typer(no_args_is_help=True)
app.add_typer(app_images, name="image")


@app_images.command(name="list")
def images_list(
    json_: bool = typer.Option(False, "--json", help="return as json"),
    pagination: bool = typer.Option(True, help="paginate"),
    page_size: int = typer.Option(50, help="page size"),
    page: int = typer.Option(1, help="page index"),
    filter_has_annotations: Optional[bool] = typer.Option(
        None,
        "--filter-has-annotations",
        help="filter images that have or dont have annotations",
    ),
    filter_imageset_id: Optional[List[int]] = typer.Option(
        None,
        "--filter-imageset-id",
        help="filter by imageset id",
    ),
    filter_name: Optional[List[str]] = typer.Option(
        None,
        "--filter-name",
        help="filter by names",
    ),
):
    """list images"""
    api = get_api()

    if pagination:
        pg = Pagination(
            rows_per_page=max(10, page_size),
            page=max(1, page),
            sort_by=SortBy.NAME,
            descending=False,
        )
    else:
        pg = None

    _flt: Dict[str, Any] = {}
    if filter_has_annotations is not None:
        _flt["has_annotations"] = filter_has_annotations
    if filter_imageset_id:
        _flt["image_set_id"] = filter_imageset_id
    if filter_name:
        _flt["name"] = filter_name

    if _flt:
        ifilt = ImageFilters(**_flt)
    else:
        ifilt = None

    with typerize_api_error():
        images, pg_info = api.image_list(
            pagination=pg, filters=ifilt, return_pagination_info=True
        )

    data = [image.dict() for image in images]
    if json_:
        typer.echo(json_dumps(data))
    else:
        columns = {
            "id": "ID",
            "name": "Name",
            "image_set_name": "ImageSet",
            "img_width": "Width",
            "img_height": "Height",
            "mppx": "MPP_x",
            "mppy": "MPP_y",
            "filesize": "Filesize",
            "has_annotations": "Has Annotations",
            "status": "Status",
        }
        tbl = Table(*columns.values(), title="Groups")
        for row in map(itemgetter(*columns.keys()), data):
            tbl.add_row(*map(str, row))
        rich_print(tbl)

    if pg_info:
        typer.secho(f"# {pg_info!r}", fg=typer.colors.CYAN, err=True)


@app_images.command(name="info")
def images_info(
    id_: int = typer.Argument(..., metavar="id", help="image id"),
    json_: bool = typer.Option(False, "--json", help="return as json"),
):
    """info image"""
    api = get_api()
    with typerize_api_error():
        im = api.image_get(id_)
    if json_:
        typer.echo(json_dumps(im.dict()))
    else:
        tbl = Table("Key", "Value", title=f"Image #{id_}")
        for key, value in im.dict().items():
            if isinstance(value, dict):
                continue
            tbl.add_row(key, str(value))
        rich_print(tbl)


@app_images.command(name="download")
def images_download(
    id_: int = typer.Argument(..., metavar="id", help="image id"),
    json_: bool = typer.Option(False, "--json", help="return as json"),
    curl: bool = typer.Option(False, "--curl", help="return as curl-urls.txt"),
):
    """download image"""
    api = get_api()
    with typerize_api_error():
        imurl = api.image_download(id_, None)
    if curl:
        fn = unquote_plus(os.path.basename(urlsplit(imurl).path))
        tmpl = f'url = "{imurl}"\noutput = "{fn}"\n\n'
        typer.echo(tmpl)
    elif json_:
        typer.echo(json_dumps({"id": id_, "url": imurl}))
    else:
        typer.echo(imurl)


@app_images.command()
def upload(
    imageset_id: int = typer.Option(..., metavar="imageset-id", help="imageset id"),
    path: Path = typer.Argument(..., exists=True, readable=True, help="path to image"),
    json_: bool = typer.Option(False, "--json", help="return as json"),
):
    """upload image"""
    api = get_api()
    with typerize_api_error():
        im = api.image_upload(
            path, imageset_id, folder_parent_id=None
        )  # todo: implement folder cmds
    if json_:
        typer.echo(json_dumps(im.dict()))
    else:
        tbl = Table("Key", "Value", title=f"Image #{im.id}")
        for key, value in im.dict().items():
            if isinstance(value, dict):
                continue
            tbl.add_row(key, str(value))
        rich_print(tbl)


# TODO:
#  - get_api().image_delete()

# --- image subcommand --------------------------------------------------------

app_folders = typer.Typer(no_args_is_help=True)
app.add_typer(app_folders, name="folder")


@app_folders.command(name="list")
def folders_list():
    """list folders"""
    # TODO: ...
    typerize_api_error()


# --- annotation subcommand ---------------------------------------------------

app_annotations = typer.Typer(no_args_is_help=True)
app.add_typer(app_annotations, name="annotation")


class AnnotationFormat(enum.Enum):
    GEOJSON = "geojson"
    PROSCIA = "proscia"


@app_annotations.command()
def export(
    id_: int = typer.Argument(..., metavar="id", help="image id"),
    file_format: AnnotationFormat = typer.Option(
        AnnotationFormat.GEOJSON.value,
        "--format",
        help="the annotation file format",
    ),
    output: FileTextWrite = typer.Option(
        click.open_file("-", mode="w"),
        "--output",
        help="output file, default stdout",
    ),
    ignore_unsupported: bool = typer.Option(
        False,
        help="ignore not yet implemented annotation types (geojson)",
    ),
):
    """export annotations"""
    api = get_api()
    if file_format == AnnotationFormat.GEOJSON:
        with typerize_api_error():
            resp = api.annotation_export_geojson(
                id_, ignore_unsupported=ignore_unsupported
            )
        data = json_dumps(resp).decode()
    elif file_format == AnnotationFormat.PROSCIA:
        with typerize_api_error():
            data = api.annotation_export_xml(id_)
    output.write(data)


@app_annotations.command(name="import")
def import_(
    path: Path = typer.Argument(
        ..., exists=True, readable=True, help="path to annotations"
    ),
    image_id: int = typer.Option(..., help="image id"),
    skip_errors: bool = typer.Option(
        False, help="skip errors of individual annotations"
    ),
):
    """import annotations"""
    api = get_api()

    if path.suffix == ".json":
        with typerize_api_error():
            resp = api.annotation_import_geojson(
                path, image_id, skip_errors=skip_errors
            )
    elif path.suffix == ".xml":
        raise NotImplementedError("todo")
    else:
        typer.echo("must provide json or xml file", err=True)
        raise typer.Exit(1)
    typer.secho(f"imported {len(resp)} annotations", fg=typer.colors.GREEN)


@app_annotations.command(name="list")
def annotations_list(
    json_: bool = typer.Option(False, "--json", help="return as json"),
    # pagination: bool = typer.Option(True, help="paginate"),
    # page_size: int = typer.Option(50, help="page size"),
    # page: int = typer.Option(1, help="page index"),
    filter_image_id: Optional[List[int]] = typer.Option(
        None,
        "--filter-image-id",
        help="filter by image id",
    ),
    filter_name: Optional[List[str]] = typer.Option(
        None,
        "--filter-name",
        help="filter by names",
    ),
):
    """list annotations"""
    api = get_api()

    _flt: Dict[str, Any] = {}
    if filter_image_id:
        _flt["image_id"] = filter_image_id
    if filter_name:
        _flt["name"] = filter_name

    if _flt:
        afilt = AnnotationFilters(**_flt)
    else:
        afilt = None

    with typerize_api_error():
        annos = api.annotation_list(filters=afilt)

    data = [anno.dict() for anno in annos]
    if json_:
        typer.echo(json_dumps(data))
    else:
        columns = {
            "id": "ID",
            "text": "Text",
            "image_id": "ImageId",
            "color": "Color",
            "creator_name": "Creator",
            "shape": "Shape",
            "size": "Size",
        }
        tbl = Table(*columns.values(), title="Annotations")
        for row in map(itemgetter(*columns.keys()), data):
            tbl.add_row(*map(str, row))
        rich_print(tbl)


@app_annotations.command()
def delete(
    image_id: Optional[List[int]] = typer.Option(
        None,
        help="image id",
    ),
    annotation_id: int = typer.Argument(-1, help="annotation to be deleted"),
    force: bool = typer.Option(False, help="dont ask user"),
):
    """list annotations"""
    api = get_api()

    if image_id:
        if annotation_id != -1:
            typer.echo("cant provide annotation_id when using --image-id", err=True)
            raise typer.Exit(1)
        afilt = AnnotationFilters(image_id=image_id)
        with typerize_api_error():
            annos = api.annotation_list(filters=afilt)
        annotation_ids = [a.id for a in annos]
    else:
        annotation_ids = [annotation_id]

    typer.secho(
        f"Deleting {len(annotation_ids)} annotations", err=True, fg=typer.colors.RED
    )
    if not force:
        _delete = typer.confirm("Are you sure?")
    else:
        _delete = True
    if not _delete:
        typer.echo("not deleting.")
        raise typer.Abort()
    with typer.progressbar(annotation_ids) as progress:
        for a_id in progress:
            api.annotation_delete(a_id)


# --- config subcommand -------------------------------------------------------

app_config = typer.Typer(no_args_is_help=True)
app.add_typer(app_config, name="config")


@app_config.command()
def version():
    """return the version information"""
    try:
        from concentriq._version import __version__
    except ImportError:
        __version__ = "not-installed"
    typer.echo(__version__)


@app_config.command()
def ping():
    """ping the concentriq server"""
    api = get_api()
    try:
        api.group_list()
    except APIError as err:
        typer.secho(
            f"can't reach concentriq instance: {err}", fg=typer.colors.RED, bold=True
        )
        raise typer.Exit(code=1)
    else:
        typer.secho(f"{api.c.API_URL} -> pong", fg=typer.colors.GREEN)


@app_config.command()
def setup(
    api_url: str = typer.Option(..., prompt=True, help="concentriq api_url"),
    user: str = typer.Option(..., prompt=True, help="concentriq user email"),
    password: str = typer.Option(
        ...,
        prompt=True,
        confirmation_prompt=True,
        hide_input=True,
        help="concentriq api key",
    ),
    ssl_certificate: Optional[Path] = typer.Option(
        None,
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
    ),
    backup: bool = typer.Option(True, help="don't backup json"),
    path: Path = typer.Argument(
        CQ_SECRETS_PATH,
        writable=True,
        dir_okay=False,
    ),
):
    """write the secrets to disk"""
    if path.is_file():
        try:
            old_data = json_loads(path.read_bytes())
        except BaseException:
            old_data = {}
    else:
        old_data = {}

    data = dict(old_data)
    data["api_url"] = api_url
    data["user"] = user
    data["password"] = password
    if ssl_certificate:
        data["ssl_certificate"] = os.fspath(ssl_certificate)

    if data == old_data:
        typer.secho("no changes", fg=typer.colors.GREEN)
    else:
        typer.secho("writing secrets")
        if old_data and backup:
            typer.secho("creating backup", fg=typer.colors.YELLOW)
            path.with_suffix(".json.backup").write_bytes(path.read_bytes())
        path.write_text(f"{json_dumps(data)}\n")


if __name__ == "__main__":
    app()
