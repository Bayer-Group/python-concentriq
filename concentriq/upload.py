#
# Copyright (c) 2020 Bayer AG.
#
# This file is part of `python-concentriq`
#

"""concentriq.upload

tools required for uploading images to the Concentriq instance.

Author: Andreas Poehlmann <andreas.poehlmann@bayer.com>

"""
from __future__ import annotations

import base64
import hashlib
import re
import sys
import urllib.parse
import warnings
from datetime import datetime
from typing import Callable
from urllib.parse import urljoin
from xml.etree import ElementTree

import requests


def b64encoded_md5(data: bytes) -> str:
    """return a b64 encoded md5 sum of binary data"""
    # b64 encoded md5
    if sys.version_info >= (3, 9):
        digest = hashlib.md5(data, usedforsecurity=False).digest()
    else:
        digest = hashlib.md5(data).digest()  # nosec
    md5b64 = base64.b64encode(digest)
    return md5b64.decode("utf8")


class ProsciaS3Uploader:
    """boto3-like multipart uploader

    To support uploading to Proscia's Concentriq instance we need to roll
    our own multipart uploader because signed s3 urls need to be created
    via the Concentriq API...

    There's three methods that are relevant and feel like boto3:
    - `create_multipart_upload`
    - `upload_part`
    - `complete_multipart_upload`

    Sadly, boto3 doesn't seem to support this workflow directly which is
    why we have to reimplement the entire flow:
    * https://github.com/boto/boto3/issues/2305#issuecomment-865638153

    """

    def __init__(self, access_key, service="s3", region="eu-central-1"):
        self.access_key = access_key
        self.service = service
        self.region = region
        self.host = f"{self.service}-{self.region}.amazonaws.com"
        self.bucket = "concentriq-image-store"
        # Match the algorithm to the hashing algorithm we use: SHA-256
        self.algorithm = "AWS4-HMAC-SHA256"
        self.timestamp = None

    @classmethod
    def from_signed_thumburl(cls, url) -> ProsciaS3Uploader:
        """build a ProsciaS3Uploader from the concentriq thumbnail url

        Notes
        -----
        We do this to get the aws access_key that the webuploader of the
        deployed Concentriq instance uses. I don't think this is intended
        to be used this way, but it works...

        """
        # this is a weird hack, or at least it seems so...
        q = urllib.parse.urlparse(url)
        headers = urllib.parse.parse_qs(q.query)
        # noinspection PyTypeChecker
        access_key = headers["X-Amz-Credential"][0].split("/")[0]
        return cls(access_key)

    # === private api =================================================

    @staticmethod
    def _create_canonical_request(
        method,
        host,
        timestamp,
        uri="/",
        params=None,
        data=None,
        hash_payload=True,
        extra_headers=None,
    ) -> tuple[str, str, str]:
        """build the canonical request for url signing

        https://docs.aws.amazon.com/general/latest/gr/sigv4-create-canonical-request.html

        Step 1:
          is to define the verb (GET, POST, etc.)--already done.
        Step 2:
          Create canonical URI--the part of the URI from domain to query
          string (use '/' if no path)
        Step 3:
          Create the canonical query string. In this example (a GET request),
          request parameters are in the query string. Query string values must
          be URL-encoded (space=%20). The parameters must be sorted by name.
        Step 4:
          Create the canonical headers and signed headers. Header names
          must be trimmed and lowercase, and sorted in code point order from
          low to high. Note that there is a trailing \n.
        Step 5:
          Create the list of signed headers. This lists the headers
          in the canonical_headers list, delimited with ";" and in alpha order.
          Note: The request can include any headers; canonical_headers and
          signed_headers lists those that you want to be included in the
          hash of the request. "Host" and "x-amz-date" are always required.
        Step 6:
          Create payload hash (hash of the request body content). For GET
          requests, the payload is an empty string ("").
        Step 7:
          Combine elements to create canonical request

        Returns
        -------
        canonical_request: str
        """
        assert method in {"GET", "POST", "PUT"}  # etc...
        if params is None:
            canonical_querystring = ""
        else:
            assert sorted(params) == list(params), "params must be sorted"
            canonical_querystring = urllib.parse.urlencode(params)
        if data is None:
            payload = b""
        else:
            payload = data
        assert isinstance(payload, bytes), "you need to .encode('utf-8') your payload"

        if extra_headers is None:
            extra_headers = {}

        amzdate = timestamp.strftime("%Y%m%dT%H%M%SZ")

        canonical_uri = uri
        headers = {
            "host": host.strip().lower(),
            "x-amz-date": amzdate.strip(),
        }
        headers.update(extra_headers)

        canonical_headers = "".join(
            f"{key.lower()}:{value}\n" for key, value in sorted(headers.items())
        )
        signed_headers = ";".join(sorted(headers))
        if hash_payload:
            payload_hash = hashlib.sha256(payload).hexdigest()
        else:
            payload_hash = "UNSIGNED-PAYLOAD"

        canonical_request = (
            f"{method}\n"
            f"{canonical_uri}\n"
            f"{canonical_querystring}\n"
            f"{canonical_headers}\n"
            f"{signed_headers}\n"
            f"{payload_hash}"
        )
        return canonical_request, payload_hash, signed_headers

    def _get_credential_scope(self, timestamp):
        datestamp = timestamp.strftime("%Y%m%d")
        return f"{datestamp}/{self.region}/{self.service}/aws4_request"

    def _create_signing_string(self, timestamp, canonical_request) -> str:
        """create the string for signing

        Parameters
        ----------
        timestamp: datetime
        canonical_request: str

        Returns
        -------
        singing_string: str
        """
        amzdate = timestamp.strftime("%Y%m%dT%H%M%SZ")
        credential_scope = self._get_credential_scope(timestamp)

        return (
            f"{self.algorithm}\n"
            f"{amzdate}\n"
            f"{credential_scope}\n"
            f"{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"
        )

    def _prepare_auth_params_data(
        self,
        storage_path,
        timestamp: datetime,
        *,
        method="POST",
        params=None,
        data=None,
        hash_payload=True,
        extra_headers=None,
    ) -> tuple[dict, dict, str]:
        """params data for signing endpoint"""
        if params is None:
            warnings.warn("please change")
            params = dict(uploads="")
        if extra_headers is None:
            extra_headers = {}

        uri = urljoin(f"/{self.bucket}/", storage_path)
        (
            canonical_request_str,
            payload_hash,
            signed_headers,
        ) = self._create_canonical_request(
            method=method,
            host=self.host,
            timestamp=timestamp,
            uri=uri,
            params=params,
            data=data,
            hash_payload=hash_payload,
            extra_headers=extra_headers,
        )
        signing_str = self._create_signing_string(
            timestamp=timestamp,
            canonical_request=canonical_request_str,
        )

        params = {
            "payload": urllib.parse.quote_plus(signing_str),
            "nonce": timestamp.strftime("%Y%m%dT%H%M%SZ"),
            "canonicalRequest": canonical_request_str,
        }
        extra_params = {
            "x-amz-content-sha256": payload_hash,
        }
        extra_params.update(extra_headers)
        return params, extra_params, signed_headers

    def _create_target_url(self, storage_key):
        return f"https://{self.host}/{self.bucket}/{storage_key}"

    def _create_authorization_headers(
        self, signed_headers, timestamp, signature, extra_headers
    ):
        amzdate = timestamp.strftime("%Y%m%dT%H%M%SZ")
        credential_scope = self._get_credential_scope(timestamp)
        authorization_header = (
            f"{self.algorithm} "
            f"Credential={self.access_key}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, "
            f"Signature={signature}"
        )
        headers = {
            "x-amz-date": amzdate,
            "Authorization": authorization_header,
            **extra_headers,
        }
        return headers

    @staticmethod
    def _new_timestamp(timestamp=None):
        if timestamp is None:
            return datetime.utcnow()
        else:
            return timestamp

    # === user interface ===

    def create_multipart_upload(
        self, key: str, proscia_signing_callback: Callable[[dict], str]
    ) -> str:
        """initiate an s3 multipart upload"""
        request_params = {"uploads": ""}
        request_data = None

        # decide what you want to do here:
        timestamp = self._new_timestamp()
        params, extra_headers, signed_headers = self._prepare_auth_params_data(
            key,
            timestamp,
            method="POST",
            params=request_params,
            data=request_data,
            hash_payload=True,
        )
        # get signature
        signature = proscia_signing_callback(params)

        # --- initiate multipart upload ---
        url = self._create_target_url(storage_key=key)
        headers = self._create_authorization_headers(
            signed_headers, timestamp, signature, extra_headers
        )

        # POST REQUEST TO INITIATE S3 MULTIPART UPLOAD
        out = requests.post(
            url, data=request_data, params=request_params, headers=headers
        )

        # PARSE UPLOAD_ID
        et = ElementTree.fromstring(out.text)  # nosec
        assert et.tag.endswith("InitiateMultipartUploadResult"), f"got: {et.tag!r}"
        multipart_upload_info = {re.sub(r"{[^}]*}", "", c.tag): c.text for c in et}
        assert set(multipart_upload_info) == {"Bucket", "Key", "UploadId"}, repr(
            multipart_upload_info
        )
        assert multipart_upload_info["Bucket"] == self.bucket
        assert multipart_upload_info["Key"] == key
        assert multipart_upload_info["UploadId"]
        upload_id = multipart_upload_info["UploadId"]
        return upload_id

    def upload_part(
        self,
        part_number: int,
        chunk: bytes,
        upload_id: str,
        key: str,
        proscia_signing_callback: Callable[[dict], str],
    ) -> str:
        """upload a part to s3"""
        request_params: dict[str, int | str] = {
            "partNumber": part_number,
            "uploadId": upload_id,
        }
        request_data = chunk

        # decide what you want to do here:
        timestamp = self._new_timestamp()
        params, extra_headers, signed_headers = self._prepare_auth_params_data(
            key,
            timestamp,
            method="PUT",
            params=request_params,
            data=request_data,
            hash_payload=False,
            extra_headers={"content-md5": b64encoded_md5(chunk)},
        )
        # get signature
        signature = proscia_signing_callback(params)

        # --- prepare part upload ---
        url = self._create_target_url(storage_key=key)
        headers = self._create_authorization_headers(
            signed_headers, timestamp, signature, extra_headers
        )

        out = requests.put(
            url, data=request_data, params=request_params, headers=headers
        )

        etag = out.headers["ETag"]
        assert etag, f"got: {etag} in {out.headers!r}"

        # FIXME: the etag is just the md5 I believe?
        #   so we could verify the upload here and raise if not correct...
        return etag

    def complete_multipart_upload(
        self,
        parts: list[tuple[int, str]],
        upload_id: str,
        key: str,
        proscia_signing_callback: Callable[[dict], str],
    ) -> str:
        """complete the multipart upload"""
        request_params = {"uploadId": upload_id}
        _mpu = ElementTree.Element("CompleteMultipartUpload")
        for part_number, etag in parts:
            part = ElementTree.SubElement(_mpu, "Part")
            ElementTree.SubElement(part, "PartNumber").text = f"{part_number:d}"
            ElementTree.SubElement(part, "ETag").text = etag
        request_data = ElementTree.tostring(
            _mpu, encoding="utf-8", short_empty_elements=False
        )

        # decide what you want to do here:
        timestamp = self._new_timestamp()
        params, extra_headers, signed_headers = self._prepare_auth_params_data(
            key,
            timestamp,
            method="POST",
            params=request_params,
            data=request_data,
            hash_payload=True,
            extra_headers={"content-type": "application/xml; charset=UTF-8"},
        )
        # get signature
        signature = proscia_signing_callback(params)

        # --- prepare part upload ---
        url = self._create_target_url(storage_key=key)
        headers = self._create_authorization_headers(
            signed_headers, timestamp, signature, extra_headers
        )

        out = requests.post(
            url, data=request_data, params=request_params, headers=headers
        )

        # PARSE COMPLETED MULTIPART UPLOAD
        et = ElementTree.fromstring(out.text)  # nosec
        assert et.tag.endswith("CompleteMultipartUploadResult"), f"got: {et.tag!r}"
        multipart_upload_info = {re.sub(r"{[^}]*}", "", c.tag): c.text for c in et}
        assert set(multipart_upload_info) == {
            "Location",
            "Bucket",
            "Key",
            "ETag",
        }, repr(multipart_upload_info)
        assert multipart_upload_info["Bucket"] == self.bucket
        assert multipart_upload_info["Key"] == key
        assert multipart_upload_info["ETag"]
        final_etag = multipart_upload_info["ETag"]

        # FIXME: the final_etag is just the md5 of the concatenated part md5s (as bytes) and f"-{NUMBER_OF_PARTS}"?
        #   so we could verify the entire upload here too and raise if not correct...
        # NOTE: the final_etag is f'"{md5_of_md5s}-{num_parts}"'
        return final_etag
