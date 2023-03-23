#
# Copyright (c) 2020 Bayer AG.
#
# This file is part of `python-concentriq`
#

"""concentriq.models

Mapping the data model of the internally deployed Concentriq instance.
See: https://<your-concentriq-url>/api-documentation

Author: Andreas Poehlmann <andreas.poehlmann@bayer.com>

"""
from __future__ import annotations

import enum
import sys
from datetime import datetime
from typing import Any
from typing import Dict
from typing import List
from typing import Optional

from pydantic import BaseModel
from pydantic import Extra
from pydantic import Field
from pydantic import NoneStr

if sys.version_info >= (3, 10):
    from typing import TypeAlias
else:
    from typing_extensions import TypeAlias


MaybeDatetime: TypeAlias = Optional[datetime]
MaybeIntList: TypeAlias = Optional[List[int]]
MaybeStrList: TypeAlias = Optional[List[str]]
NoneBool: TypeAlias = Optional[bool]
IdDict: TypeAlias = Dict[int, Any]
MaybeIdDict: TypeAlias = Optional[IdDict]


def to_camel(string: str) -> str:
    first, *rest = string.split("_")
    return "".join((first, *map(str.title, rest)))


class _BaseModel(BaseModel):
    """proscia basemodel"""

    class Config:
        alias_generator = to_camel
        allow_population_by_field_name = True


class _SharePermissions(_BaseModel):
    can_create_annotations: bool
    can_manage_annotations: bool
    can_manage_image_set_share_permissions: bool
    can_manage_images: bool
    can_manage_metadata_fields: bool
    can_manage_metadata_values: bool
    can_modify_image_set: bool
    can_update_navigation: bool
    can_export_data: bool


class SortBy(str, enum.Enum):
    NAME = "name"
    CREATED = "created"
    LAST_MODIFIED = "lastModified"
    SIZE = "size"


class Pagination(_BaseModel):
    rows_per_page: int
    page: int = Field(..., ge=1)
    sort_by: SortBy
    descending: bool


class _CreatedFilters(_BaseModel):
    start: MaybeDatetime = None
    end: MaybeDatetime = None


class ImageFilters(_BaseModel):
    image_set_id: MaybeIntList = None
    image_id: MaybeIntList = None
    name: MaybeStrList = None
    general_search: MaybeStrList = (
        None  # search phrases to search over various fields and case properties
    )
    fields: MaybeIdDict = None  # Dict[metadataFieldId, contentType]
    folder: Any = None  # fixme
    analysis: Any = None  # fixme
    has_overlays: NoneBool = None
    has_multiple_z_layers: NoneBool = None
    has_annotations: NoneBool = None
    has_analysis_results: NoneBool = None
    created: Optional[_CreatedFilters] = None


class Group(_BaseModel):
    """proscia groups (the api calls them ImageSetGroups)"""

    id: int
    name: str
    image_set_count: Optional[int]  # but encoded as string ???
    owner_name: str
    owner_id: int
    is_favorite: bool
    description: Optional[str]
    created: datetime
    last_modified: datetime
    share_permissions: _SharePermissions


class Organization(_BaseModel):
    id: int
    name: str
    billing_email: str


class ImageSet(_BaseModel):
    """proscia collects images in imagesets"""

    id: int
    thumbnail_url: str = Field(..., alias="thumbnailURL")
    shared_with_public: bool
    is_favorite: bool
    name: str
    created: datetime
    last_modified: datetime
    image_count: int
    total_size: int  # but encoded as string ??? 'totalSize': '0'
    owner_name: str
    owner_id: int
    description: str
    group_id: Optional[int]
    group_name: Optional[str]
    share_permissions: _SharePermissions

    class Config:
        extra = Extra.allow


class FolderFilters(_BaseModel):
    image_set_id: MaybeIntList = None
    folder_id: MaybeIntList = None
    has_metadata: NoneBool = None
    has_attachments: NoneBool = None
    name: MaybeStrList = None
    general_search: MaybeStrList = (
        None  # search phrases to search over various fields and case properties
    )
    fields: MaybeIdDict = None  # Dict[metadataFieldId, contentType]
    image: Optional[ImageFilters] = None


class Folder(_BaseModel):
    """proscia can have folders in imagesets"""

    id: int
    label: str
    image_set_id: int
    folder_parent_id: Optional[int]  # None is root
    image_set_name: str
    has_metadata: bool  # from docs: whether this folder is a case ???
    has_attachments: bool
    rank: int
    owner_id: int
    share_permissions: _SharePermissions


class _AssociatedImages(_BaseModel):
    type: str
    signed_url: str = Field(..., alias="signedURL")


class _ImageData(_BaseModel):
    image_sources: Any
    fluorescence_channels: Optional[Any]
    metadata_url: str


class ImageStatus(int, enum.Enum):
    # the error/uploading/optimizing status of the image.
    # -1 is error. 0 is uploading. 1 is optimizing, and setting to one triggers reoptimization. 2 is success.
    ERROR = -1
    UPLOADING = 0
    OPTIMIZING = 1
    SUCCESS = 2


class Image(_BaseModel):
    """the proscia image model"""

    id: int
    name: str
    image_set_id: int
    image_set_name: str
    folder_parent_id: Optional[int]
    owner_id: int
    rank: int
    has_macro: bool
    has_label: bool
    has_overlays: bool
    has_multiple_z_layers: bool
    has_annotations: bool
    has_analysis_results: bool
    mppx: Optional[float]
    mppy: Optional[float]
    img_width: int
    img_height: int
    file_size: Optional[int] = None
    objective_power: Optional[float]
    slide_name: str
    filesize: str
    status: int
    created: datetime
    storage_key: str
    associated_key: str
    thumb_url: Any = Field(..., alias="thumbURL")
    # associated_images: _AssociatedImages
    image_data: Optional[_ImageData] = None
    share_permissions: _SharePermissions
    selected_storage_system_entry: Any = None


class AnnotationFilters(_BaseModel):
    """filters for annotations"""

    annotation_id: MaybeIntList = None
    image_id: MaybeIntList = None
    text: MaybeStrList = (
        None  # this is basically class, because proscia doesnt have classes...
    )
    fields: MaybeIdDict = None


class Annotation(_BaseModel):
    """the proscia annotation model"""

    id: Optional[int] = None
    text: str
    shape: str
    shape_string: str
    capture_bounds: NoneStr = None
    image_id: int
    color: str
    is_negative: bool
    is_segmenting: bool
    label_order_x: NoneStr = None
    label_order_y: NoneStr = None
    # computed properties
    size: Optional[float] = None
    bounds_string: NoneStr = None
    # populated on creation
    user_id: Optional[int] = None
    creator_name: NoneStr = None
    created: MaybeDatetime = None
    share_permissions: Optional[_SharePermissions] = None

    class Config:
        extra = Extra.allow
