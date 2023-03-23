#
# Copyright (c) 2020 Bayer AG.
#
# This file is part of `python-concentriq`
#

"""concentriq.api

python API interface for interacting with the Proscia Concentriq instance.

See: https://<your-concentriq-url>/api-documentation

Author: Santiago Villalba <santiago.villalba@bayer.com>
        Andreas Poehlmann <andreas.poehlmann@bayer.com>

NOTE:
    And to instantiate it you need:
    >>> api = API.from_secrets_file("~/.secrets/proscia.json")
    For from_secrets to work, make a file:
    $ touch ~/.secrets/proscia.json

    And the contents of that file should look like this:
    {
        "api_url": "https://my-proscia-deployment.company.com/"
        "user": "your-email-that-you-use-for-proscia@company.com",
        "password": "your-complicated-proscia-password",
        "ssl_certificate": "/an/absolute/path/incase-you-need-a-special-ssl-cert.pem"  # or None
    }

"""
from __future__ import annotations

import json
import logging
import math
import os.path
import sys
import textwrap
import traceback
from itertools import count
from pathlib import Path
from typing import Any
from typing import Iterator
from typing import overload
from urllib.parse import urljoin

if sys.version_info >= (3, 8):
    from typing import Literal
else:
    from typing_extensions import Literal

import requests
import requests.utils

from concentriq.annotations import proscia_from_geojson
from concentriq.annotations import proscia_to_geojson
from concentriq.models import Annotation
from concentriq.models import AnnotationFilters
from concentriq.models import Folder
from concentriq.models import FolderFilters
from concentriq.models import Group
from concentriq.models import Image
from concentriq.models import ImageFilters
from concentriq.models import ImageSet
from concentriq.models import ImageStatus
from concentriq.models import Organization
from concentriq.models import Pagination
from concentriq.models import SortBy
from concentriq.upload import ProsciaS3Uploader

__all__ = ["API", "APIError"]

_log = logging.getLogger(__name__)

# === Proscia Concentriq Configuration ========================================

CQ_ENV_PREFIX = "CONCENTRIQ"
CQ_API_URL = "API_URL"
CQ_USER = "USER"
CQ_PASS = "PASSWORD"
CQ_CERTS = "SSL_CERTIFICATE"


# === Proscia Python Interface ================================================


class APIError(Exception):
    """proscia api error"""

    def __init__(self, error: dict):
        self.status = error["status"]
        self.name = error["name"]
        self.code = error["code"]
        super().__init__(error["message"])
        _log.error(f"{self.name} [{self.status}] {self}")

    def __repr__(self):
        return f"{type(self).__name__}({str(self)!r}, code={self.code}, status={self.status}, name={self.name!r})"


class _RequestProxy:
    """handle requests to proscia's json api - low level

    This proxy provides some extra logging and handles pagination
    """

    API_URL: str

    def __init__(
        self, api_url: str, user: str, password: str, ssl_certificate: str | Path | None
    ) -> None:
        """gather username password and ssl certs for interacting with proscia"""
        if not isinstance(api_url, str):
            raise TypeError(
                f"api_url must be of type 'str', got: {type(api_url).__name__!r}"
            )
        if not api_url.startswith("http"):
            raise ValueError(f"api_url must start with http*..., got: {api_url!r}")
        if not isinstance(user, str):
            raise TypeError(f"user must be of type 'str', got: {type(user).__name__!r}")
        if not user.strip():
            raise ValueError("user must be non-empty")
        if not isinstance(password, str):
            raise TypeError(
                f"password must be of type 'str', got: {type(password).__name__!r}"
            )
        if not password.strip():
            raise ValueError("password must be non-empty")
        self._auth_kw: dict[str, Any] = {
            "auth": (user, password),
        }
        if not api_url.endswith("/"):
            api_url = f"{api_url}/"
        self.API_URL = api_url
        if ssl_certificate:
            self._auth_kw["verify"] = os.fspath(ssl_certificate)

    @staticmethod
    def _check_response(out: dict, *, paginate=False, **kw):
        assert not kw, f"unused kwargs {kw!r}"
        if "error" in out:
            raise APIError(out["error"])
        _log.debug(f"META: {json.dumps(out['meta'])}")

        assert set(out).issubset(
            {"error", "data", "meta"}
        ), f"unknown response keys {out!r}"

        if paginate:
            return out["data"], out["meta"]["pagination"]
        else:
            if out["meta"]["pagination"] is not None:
                raise RuntimeError("response is paginated. This might be unintended.")
            return out["data"]

    @staticmethod
    def format_prepped_request(prepped, encoding=None):
        # prepped has .method, .path_url, .headers and .body attribute to view the request
        encoding = encoding or requests.utils.get_encoding_from_headers(prepped.headers)
        if prepped.body is None:
            body = ""
        else:
            body = prepped.body.decode(encoding) if encoding else "<binary data>"
        headers = "\n".join(["{}: {}".format(*hv) for hv in prepped.headers.items()])
        return textwrap.dedent(
            f"""\
            {prepped.method} {prepped.path_url} HTTP/1.1
            {headers}

            {body}"""
        )

    def get_raw(self, endpoint, *, params=None, **kwargs) -> requests.Response:
        url = urljoin(self.API_URL, endpoint, allow_fragments=False)
        out = requests.get(url, params=params, **self._auth_kw, **kwargs)
        return out

    def get(self, endpoint, *, params=None, paginate=False) -> dict:
        url = urljoin(self.API_URL, endpoint, allow_fragments=False)
        out = requests.get(url, params=params, **self._auth_kw)
        _log.debug(
            f"REQUEST\n<RAW>\n{self.format_prepped_request(out.request, encoding='utf8')}\n</RAW>"
        )
        return self._check_response(out.json(), paginate=paginate)

    def get_text(self, endpoint, *, params=None) -> str:
        url = urljoin(self.API_URL, endpoint, allow_fragments=False)
        out = requests.get(url, params=params, **self._auth_kw)
        _log.debug(
            f"REQUEST\n<RAW>\n{self.format_prepped_request(out.request, encoding='utf8')}\n</RAW>"
        )
        return out.content.decode()

    def get_paginated(
        self,
        endpoint,
        *,
        params=None,
        offset: int,
        size: int,
        sort_by: SortBy = SortBy.CREATED,
        descending: bool = False,
    ) -> Iterator[dict]:
        """only get is paginated in the proscia api"""
        if params is None:
            params = {}
        for page in count(offset + 1):
            _pagination = Pagination(
                rows_per_page=int(size),
                page=page,
                sort_by=sort_by,
                descending=descending,
            )
            params["pagination"] = _pagination.json(by_alias=True)
            data, page_info = self.get(endpoint, params=params, paginate=True)
            if page_info["rowsReturned"] <= 0:
                break
            yield data

    def post(
        self, endpoint, data=None, *, params=None, headers=None, files=None
    ) -> dict:
        url = urljoin(self.API_URL, endpoint, allow_fragments=False)
        out = requests.post(
            url, data=data, params=params, headers=headers, files=files, **self._auth_kw
        ).json()
        return self._check_response(out)

    def patch(self, endpoint, data, *, params=None) -> dict:
        url = urljoin(self.API_URL, endpoint, allow_fragments=False)
        out = requests.patch(url, data, params=params, **self._auth_kw).json()
        return self._check_response(out)

    def delete(self, endpoint, *, params=None) -> dict:
        url = urljoin(self.API_URL, endpoint, allow_fragments=False)
        out = requests.delete(url, params=params, **self._auth_kw).json()
        return self._check_response(out)


# === Proscia API =============================================================


class API:
    """proscia API abstraction - higher level"""

    def __init__(
        self,
        api_url: str,
        user: str,
        password: str,
        ssl_certificate: str | Path | None = None,
    ):
        self.c = _RequestProxy(api_url, user, password, ssl_certificate)

    @classmethod
    def from_secrets_file(
        cls, path: str | Path, api_url: str | None = None, env_override: bool = True
    ):
        """create an API instance from a secrets json"""
        try:
            with Path(path).expanduser().open("rt") as reader:
                auth_settings = json.load(reader)
        except FileNotFoundError:
            auth_settings = {}
        if api_url is not None:
            auth_settings["api_url"] = api_url
        if env_override:
            auth_settings.update(cls._get_env_dct())
        if "api_url" not in auth_settings:
            raise ValueError("missing key in config 'api_url'")
        return cls(**auth_settings)

    @classmethod
    def from_env(cls):
        """create an API instance from environment vars"""
        kw = cls._get_env_dct()
        return cls(**kw)

    @staticmethod
    def _get_env_dct():
        dct = {}
        try:
            dct["user"] = os.environ[f"{CQ_ENV_PREFIX}_{CQ_USER}"]
        except KeyError:
            pass
        try:
            dct["password"] = os.environ[f"{CQ_ENV_PREFIX}_{CQ_PASS}"]
        except KeyError:
            pass
        try:
            dct["ssl_certificate"] = os.environ[f"{CQ_ENV_PREFIX}_{CQ_CERTS}"]
        except KeyError:
            pass
        try:
            dct["api_url"] = os.environ[f"{CQ_ENV_PREFIX}_{CQ_API_URL}"]
        except KeyError:
            pass
        return dct

    # --- Group endpoints --- (NOTE: proscia api calls them ImageSetGroups?)

    def group_list(self) -> list[Group]:
        """return groups that you belong to..."""
        return [Group(**x) for x in self.c.get("imageSetGroups")["groups"]]

    def group_get(self, group: Group | int) -> Group:
        """return the requested group"""
        group_id = id_from_model(group, Group)
        data = self.c.get(f"imageSetGroups/{group_id}")

        def _fix_broken_key(dct):
            # fixme: I bet this is broken in the upstream api
            dct["imageSetCount"] = dct.pop("imageCount")
            return dct

        return Group(**_fix_broken_key(data))

    # TODO: ??? do we need to do this programmatically ???
    # def group_create(self, name: str) -> Group: ...
    # def group_update(self, group: Group) -> bool: ...
    # def group_delete(self, group: Union[Group, int]) -> bool: ...

    # --- Organization endpoints ---

    def organization_list(self) -> list[Organization]:
        """return organizations (admin only ...)"""
        return [Organization(**x) for x in self.c.get("organizations")]

    # --- ImageSet endpoints --- (NOTE: proscia web ui calls them Repositories?)

    def imageset_list(self) -> list[ImageSet]:
        """return a list of ImageSets"""
        return [ImageSet(**x) for x in self.c.get("imageSets")["imageSets"]]

    def imageset_get(self, imageset: ImageSet | int) -> ImageSet:
        """return the requested imageset"""
        imageset_id = id_from_model(imageset, ImageSet)
        return ImageSet(**self.c.get(f"imageSets/{imageset_id}"))

    def imageset_create(self, name, group: int | Group) -> ImageSet:
        """create a new ImageSet"""
        group_id = id_from_model(group, Group)
        data = dict(name=str(name), groupId=int(group_id))
        return ImageSet(**self.c.post("imageSets", data))

    def imageset_update(self, imageset: ImageSet) -> bool:
        """update an ImageSet"""
        raise NotImplementedError("todo")

    def imageset_delete(self, imageset: ImageSet | int) -> bool:
        """delete an ImageSet"""
        imageset_id = id_from_model(imageset, ImageSet)
        msg = self.c.delete(f"imageSets/{imageset_id}").get("success", None)
        if msg is not None:
            _log.debug(f"success: {msg!r}")
            return True
        else:
            return False

    def imageset_export_metadata_csv(self, imageset: ImageSet | int) -> str:
        """gather proscia imageset metadata as csv"""
        # todo: expose folder id ???
        imageset_id = id_from_model(imageset, ImageSet)
        return self.c.get_text(f"imageSets/{imageset_id}/export/csv")

    # --- Folder endpoints ---

    def folder_list(
        self,
        *,
        include_metadata: bool = False,
        pagination: Pagination | None = None,
        filters: FolderFilters | None = None,
        # ids_only: bool = False,
    ) -> list[Folder] | list[int]:
        """return a list of requested folders"""
        params = prepare_common_list_parameters(pagination, filters)
        if include_metadata:
            params["includeMetadata"] = "true"
        return [Folder(**x) for x in self.c.get("folders", params=params)["folders"]]

    # --- Image endpoints ---

    @overload
    def image_list(
        self, *, pagination: Pagination | None, filters: ImageFilters | None
    ) -> list[Image]:
        ...

    @overload
    def image_list(
        self,
        *,
        pagination: Pagination | None,
        filters: ImageFilters | None,
        return_pagination_info: Literal[False],
    ) -> list[Image]:
        ...

    @overload
    def image_list(
        self,
        *,
        pagination: Pagination | None,
        filters: ImageFilters | None,
        return_pagination_info: Literal[True],
    ) -> tuple[list[Image], dict]:
        ...

    def image_list(
        self,
        *,
        pagination: Pagination | None = None,
        filters: ImageFilters | None = None,
        # ids_only: bool = False,
        return_pagination_info: bool = False,
    ) -> list[Image] | tuple[list[Image], dict]:
        """return images"""
        params = prepare_common_list_parameters(pagination, filters)
        if pagination is not None:
            data, pg_info = self.c.get("images", params=params, paginate=True)
        else:
            data = self.c.get("images", params=params)
            pg_info = {}

        images = [Image(**x) for x in data["images"]]
        if return_pagination_info:
            return images, pg_info
        else:
            return images

    def image_get(self, image: Image | int) -> Image:
        """return the requested image"""
        image_id = id_from_model(image, Image)
        data = self.c.get(f"images/{image_id}")
        _log.debug(f"IMAGE: {data['id']} {data!r}")
        return Image(**data)

    def image_download(self, image: Image | int, path: Path | None) -> str:
        """download the requested image"""
        image_id = id_from_model(image, Image)
        resp = self.c.get_raw(f"images/{image_id}/download", allow_redirects=False)
        assert resp.status_code == 302, f"expected redirect, got {resp.status_code}"
        return resp.headers["Location"]

    def image_upload(
        self,
        image_pth: Path,
        image_set_id: int,
        *,
        folder_parent_id: int | None,
    ) -> Image:
        """create ??? an image on proscia and get the image model"""
        # --- first do CreateImage
        _img_size = image_pth.stat().st_size
        _post_data = dict(
            name=image_pth.name,
            size=_img_size,
            source="native",
            imageSetId=image_set_id,
            folderParentId=folder_parent_id,
        )
        _data = self.c.post("images", data=_post_data)
        assert set(_data) == {"id"}
        try:
            image = self.image_get(_data["id"])

            # --- sign the s3 url?
            # noinspection PyUnresolvedReferences
            storage_system_entry = image.selected_storage_system_entry
            image_storage_key = storage_system_entry["imageStorageKey"]

            def proscia_sign_s3_request(request_params):
                """sign an s3 request"""
                nonlocal self
                nonlocal image
                resource_type = "image"
                data_out = self.c.get(
                    f"auth/sign/s3-multipart-url/{resource_type}/{image.id}",
                    params=request_params,
                )
                return data_out["signature"]

            uploader = ProsciaS3Uploader.from_signed_thumburl(
                image.thumb_url["signedURL"]
            )

            # --- initiate multipart upload ---
            print("# requesting upload id...")
            upload_id = uploader.create_multipart_upload(
                key=image_storage_key,
                proscia_signing_callback=proscia_sign_s3_request,
            )
            print(f"[upload_id] {upload_id}")

            # --- upload parts ---
            CHUNK_SIZE = 16 * 1024 * 1024  # 16MB
            parts_total = math.ceil(_img_size / CHUNK_SIZE)
            digits = len(str(parts_total))
            print(
                f"# requesting {parts_total} part uploads (chunk_size={CHUNK_SIZE}) ..."
            )
            part_number_etags = []
            for part_number, chunk in iter_chunks(image_pth, size=CHUNK_SIZE):
                etag = uploader.upload_part(
                    part_number=part_number,
                    chunk=chunk,
                    upload_id=upload_id,
                    key=image_storage_key,
                    proscia_signing_callback=proscia_sign_s3_request,
                )
                print(
                    f"[part_upload_etag] ({part_number:0{digits}d}/{parts_total}) {etag!s}"
                )
                part_number_etags.append((part_number, etag))

            # --- finalize upload ---
            print("# finalizing multipart upload....")
            final_etag = uploader.complete_multipart_upload(
                parts=part_number_etags,
                upload_id=upload_id,
                key=image_storage_key,
                proscia_signing_callback=proscia_sign_s3_request,
            )
            print(f"[final_etag] {final_etag}")

        except BaseException as err:
            print(traceback.format_exc())
            print(err)
            self.image_delete(_data["id"])
            raise err
        else:
            image = self.image_get(_data["id"])  # return image
            assert image.status == ImageStatus.UPLOADING, f"??? {image!r}"
            self.c.patch(
                f"images/{image.id}",
                data={
                    "id": _data["id"],  # just to be consistent with the web uploader...
                    "status": int(ImageStatus.OPTIMIZING),
                },
            )
            return self.image_get(_data["id"])

    def image_delete(self, image: Image | int) -> bool:
        """delete an image"""
        image_id = id_from_model(image, Image)
        msg = self.c.delete(f"images/{image_id}").get("success", None)
        if msg is not None:
            _log.debug(f"success: {msg!r}")
            return True
        else:
            return False

    # --- Annotation endpoints ---

    def annotation_list(
        self, filters: AnnotationFilters | None = None
    ) -> list[Annotation]:
        """load the annotations of an image from proscia"""
        params = prepare_common_list_parameters(None, filters)
        out = self.c.get("annotations", params=params)
        # FIXME: ??? can this be paginated ???
        return [Annotation(**x) for x in out["annotations"]]

    def annotation_get(self, annotation: Annotation | int) -> Annotation:
        """get an annotation"""
        annotation_id = id_from_model(annotation, Annotation)
        return Annotation(**self.c.get(f"annotations/{annotation_id}"))

    def annotation_create(self, annotation: Annotation) -> Annotation:
        """create an annotation"""
        data = annotation.json(by_alias=True, exclude_unset=True)
        return Annotation(
            **self.c.post(
                "annotations",
                data=data,
                headers={"content-type": "application/json;charset=UTF-8"},
            )
        )

    def annotation_delete(self, annotation: Annotation | int) -> bool:
        """delete an annotation"""
        annotation_id = id_from_model(annotation, Annotation)
        msg = self.c.delete(f"annotations/{annotation_id}").get("success", None)
        if msg is not None:
            _log.debug(f"success: {msg!r}")
            return True
        else:
            return False

    def annotation_import_geojson(
        self, geojson: Path, image: Image | int, *, skip_errors: bool = False
    ) -> list[Annotation]:
        """load annotations from a geojson"""
        if isinstance(image, int):
            image = self.image_get(image)
        geojson = Path(geojson)
        with geojson.open("r") as f:
            data = json.load(f)

        _annotations = []
        for idx, anno_geojson in enumerate(data):
            # try normal conversion
            try:
                a = proscia_from_geojson(anno_geojson, image)
            except NotImplementedError as err:
                _log.warning(f"skipping annotation #{idx}: {err!r}")
                continue
            try:
                anno_proscia = self.annotation_create(annotation=a)
            except APIError:
                _log.debug(f"failed to import {a!r}")
            else:
                _annotations.append(anno_proscia)
                continue

            # try fix with shapely
            a = proscia_from_geojson(
                anno_geojson, image, shapely_fix_in_viewport_coords=True
            )
            try:
                anno_proscia = self.annotation_create(annotation=a)
            except APIError:
                if skip_errors:
                    _log.warning(f"skipping {a!r}")
                else:
                    _log.error(f"failed to import {a!r}")
                    raise
            else:
                _annotations.append(anno_proscia)
        return _annotations

    def annotation_export_geojson(
        self, image: Image | int, ignore_unsupported: bool = False
    ) -> list[dict]:
        """gather proscia annotations as geojson"""
        if isinstance(image, int):
            image = self.image_get(image)
        ganno = []
        for annotation in self.annotation_list(
            filters=AnnotationFilters(image_id=[image.id])
        ):
            try:
                a = proscia_to_geojson(annotation, image)
            except NotImplementedError:
                if ignore_unsupported:
                    continue
                raise
            else:
                ganno.append(a)
        return ganno

    def annotation_import_xml(self, xml: Path, image: Image | int) -> None:
        """load annotations from xml"""
        image_id = id_from_model(image, Image)
        xml = Path(xml)
        # FIXME: returns 201 even if it can't import some annotations...
        self.c.post(
            f"images/{image_id}/annotations/import",
            files={"files[0]": (xml.name, xml.read_bytes())},
        )

    def annotation_export_xml(self, image: Image | int) -> str:
        """gather proscia annotations as xml"""
        image_id = id_from_model(image, Image)
        return self.c.get_text(f"images/{image_id}/annotations/export/xml")


# === utility functions =======================================================


def id_from_model(obj, cls) -> int:
    """return the model id"""
    if isinstance(obj, int):
        return obj
    elif isinstance(obj, cls):
        return obj.id
    else:
        raise ValueError(f"requires {cls.__name__} or {cls.__name__}.id")


def prepare_common_list_parameters(pagination, filters) -> dict:
    """small helper to prepare common params"""
    params = {}
    if pagination:
        params["pagination"] = pagination.json(by_alias=True, exclude_unset=True)
    if filters:
        params["filters"] = filters.json(by_alias=True, exclude_unset=True)
    return params


def iter_chunks(pth: Path, size: int) -> Iterator[tuple[int, bytes]]:
    """read file in chunks"""
    with pth.open("rb") as f:
        part_idx = 1
        while True:
            chunk = f.read(size)
            if not chunk:
                break
            yield part_idx, chunk
            part_idx += 1
