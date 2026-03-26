"""
ICAv2 Service - Self-contained ICAv2 file access service.

Target:
    Provide a minimal, self-contained service class to resolve ICAv2 URIs
    (icav2://<project-uuid>/<path>) and download file contents, without
    depending on the full wrapica package.

Origin:
    The core logic is extracted and adapted from the wrapica library:
    https://github.com/umccr/wrapica
    Source file: wrapica/project_data/functions/project_data_functions.py

    The following wrapica functions are the basis for this service:
    - convert_uri_to_project_data_obj()       (line 1300)
    - get_project_data_obj_from_project_id_and_path()  (line 600)
    - get_project_data_file_id_from_project_id_and_path()  (line 74)
    - get_project_data_folder_id_from_project_id_and_path()  (line 393)
    - get_project_data_obj_by_id()            (line 546)
    - create_download_url()                   (line 1131)
    - read_icav2_file_contents()              (line 2314)

    Configuration logic is adapted from:
    - wrapica/utils/configuration.py :: get_icav2_configuration() (line 209)
    - wrapica/utils/configuration.py :: set_icav2_configuration() (line 200)
    - wrapica/utils/globals.py :: DEFAULT_ICAV2_BASE_URL          (line 12)

Key changes from wrapica:
    1. Class-based design: wrapica uses standalone functions with a module-level
       global Configuration singleton. This service uses instance-level state,
       making it thread-safe and easier to test.
    2. Token from Secret Manager: wrapica reads ICAV2_ACCESS_TOKEN from env var
       or a session file. This service retrieves the token from AWS Secrets
       Manager via the ICAV2_ACCESS_TOKEN_SECRET_ID env var and libsm.
    3. ApiClient context manager fix: wrapica creates ProjectDataApi inside a
       `with ApiClient(...) as api_client:` block but makes the actual API call
       outside it (after __exit__). This service keeps API calls inside the
       `with` block to ensure the client is active during the call.
    4. Error re-raising fix: wrapica does `raise ApiException` (re-raises the
       class, discarding the original exception and traceback). This service
       uses bare `raise` to preserve full error context.
    5. HTTP response validation: wrapica does not check the HTTP status of the
       presigned-URL download. This service adds `raise_for_status()`.
    6. Scope reduction: removed support for S3 URIs, project-name resolution,
       and create-if-not-found logic, since our use case only needs
       icav2://<project-uuid>/... read-only access.
    7. Simplified read_icav2_file_contents: removed the output_path/TextIOWrapper
       parameters since we only need string return for samplesheet content.

Dependencies:
    - libica (ICA SDK)
    - requests
    - libsm (internal secret manager client)
"""

import os
import logging
from pathlib import Path
from typing import List
from urllib.parse import urlparse
from uuid import UUID

import requests
from libumccr.aws import libsm
from libica.openapi.v3 import ApiClient, Configuration, ApiException
from libica.openapi.v3.api.project_data_api import ProjectDataApi
from libica.openapi.v3.models import ProjectData, Download

logger = logging.getLogger(__name__)

DEFAULT_ICAV2_BASE_URL = "https://ica.illumina.com/ica/rest"


class ICAService:
    """
    Self-contained service for resolving ICAv2 URIs and reading file contents.

    Retrieves the ICAv2 access token from AWS Secrets Manager (via libsm)
    using the ICAV2_ACCESS_TOKEN_SECRET_ID environment variable.

    Adapted from wrapica/utils/configuration.py :: set_icav2_configuration() (line 200)
    and get_icav2_configuration() (line 209).

    Changes from wrapica:
    - wrapica uses a module-level global `ICAV2_CONFIGURATION` singleton set via
      `set_icav2_configuration()`. This class stores the Configuration as an instance
      attribute (`self._configuration`), avoiding global mutable state.
    - wrapica reads the token from ICAV2_ACCESS_TOKEN env var or falls back to
      ~/.icav2/.session.*.yaml. This class reads from Secrets Manager via libsm.
    - wrapica reads the base URL from ICAV2_BASE_URL env var or falls back to
      ~/.icav2/config.yaml. This class reads from ICAV2_BASE_URL env var or
      falls back to the default URL constant.
    """

    def __init__(self):
        assert os.environ.get("ICAV2_ACCESS_TOKEN_SECRET_ID", None), "ICAV2_ACCESS_TOKEN_SECRET_ID is not set"
        try:
            ICAV2_ACCESS_TOKEN = libsm.get_secret(
                os.environ.get("ICAV2_ACCESS_TOKEN_SECRET_ID")
            )
        except Exception as e:
            logger.error(f"Error retrieving ICAv2 token from Secret Manager: {e}")
            raise

        if not ICAV2_ACCESS_TOKEN:
            raise ValueError("ICAV2_ACCESS_TOKEN retrieved from Secret Manager is empty")

        self._configuration = Configuration(
            host=os.environ.get("ICAV2_BASE_URL", DEFAULT_ICAV2_BASE_URL),
            access_token=ICAV2_ACCESS_TOKEN,
        )

    def convert_uri_to_project_data_obj(self, data_uri: str) -> ProjectData:
        """
        Given an icav2:// URI, resolve it to a libica ProjectData object.

        Adapted from:
            wrapica/project_data/functions/project_data_functions.py
            :: convert_uri_to_project_data_obj() (line 1300)

        Changes from wrapica:
        - Removed S3 URI support (wrapica lines 1347-1349). Our use case only
          handles icav2:// URIs.
        - Removed project-name resolution (wrapica line 1345). The original
          calls get_project_id_from_project_name() when the netloc is not a
          UUID. This service requires the netloc to be a project UUID directly,
          since we don't need project-name lookup and it avoids an extra API
          call plus the circular-import workaround in wrapica (line 1330).
        - Removed the `create_data_if_not_found` parameter (wrapica line 1302).
          This service is read-only.
        - Replaced cast() calls for DataType/UriType literals with plain string
          comparisons, since we don't use wrapica's type aliases.

        Internally delegates to:
        - _get_data_id_from_path()  (replaces get_project_data_obj_from_project_id_and_path)
        - _get_project_data_obj_by_id()

        :param data_uri: ICAv2 URI, e.g. "icav2://<project-uuid>/path/to/file.csv"
        :return: libica ProjectData object with .project_id, .data.id, .data.details.path, etc.
        :raises ValueError: If the URI scheme is not "icav2" or netloc is not a valid UUID.
        :raises FileNotFoundError: If the file/folder is not found in the project.
        :raises ApiException: If the ICA API call fails.
        """
        uri_obj = urlparse(data_uri)

        if uri_obj.scheme != "icav2":
            raise ValueError(
                f"Unsupported URI scheme '{uri_obj.scheme}'. Only 'icav2' is supported."
            )

        try:
            UUID(uri_obj.netloc, version=4)
        except ValueError:
            raise ValueError(
                f"URI netloc '{uri_obj.netloc}' is not a valid project UUID. "
                "Only icav2://<project-uuid>/... URIs are supported."
            )

        project_id = uri_obj.netloc
        data_path = Path(uri_obj.path)
        data_type = "FOLDER" if uri_obj.path.endswith("/") else "FILE"

        data_id = self._get_data_id_from_path(project_id, data_path, data_type)
        return self._get_project_data_obj_by_id(project_id, data_id)

    def _get_data_id_from_path(
        self,
        project_id: str,
        data_path: Path,
        data_type: str,
    ) -> str:
        """
        Resolve a project file or folder path to its ICA data ID.

        Adapted from (combined):
            wrapica/project_data/functions/project_data_functions.py
            :: get_project_data_file_id_from_project_id_and_path()   (line 74)
            :: get_project_data_folder_id_from_project_id_and_path() (line 393)

        In wrapica these are two separate functions dispatched by
        get_project_data_id_from_project_id_and_path() (line 484). This service
        merges them into one method with a data_type parameter.

        Changes from wrapica:
        - Merged FILE and FOLDER resolution into a single method, since the API
          call and matching logic differ only in the `type` param and the path
          comparison (folders append "/" to the match path).
        - Removed `create_file_if_not_found` / `create_folder_if_not_found`
          parameters (wrapica lines 77, 396) and their fallback create logic
          (wrapica lines 153-157, 471-476). This service is read-only.
        - Fixed ApiClient context manager: wrapica creates api_instance inside
          `with ApiClient(...):` but calls the API outside it (lines 124-147).
          This service keeps the API call inside the `with` block.
        - Fixed error re-raising: wrapica does `raise ApiException` (the class),
          losing the original exception (lines 150-151, 458-460). This service
          uses bare `raise` to preserve the full traceback.

        :param project_id: The ICA project UUID.
        :param data_path: Absolute path to the file/folder within the project.
        :param data_type: "FILE" or "FOLDER".
        :return: The ICA data ID (e.g. "fil.xxxxx" or "fol.xxxxx").
        :raises FileNotFoundError: If no matching file/folder is found.
        :raises ApiException: If the ICA API call fails.
        """
        parent_folder_path = str(data_path.parent.absolute()) + "/"
        if parent_folder_path == "//":
            parent_folder_path = "/"

        with ApiClient(self._configuration) as api_client:
            api_instance = ProjectDataApi(api_client)
            try:
                data_items: List[ProjectData] = api_instance.get_project_data_list(
                    project_id=project_id,
                    parent_folder_path=parent_folder_path,
                    filename=[data_path.name],
                    filename_match_mode="EXACT",
                    file_path_match_mode="FULL_CASE_INSENSITIVE",
                    type=data_type,
                ).items
            except ApiException as e:
                logger.error(f"Error listing project data: {e}")
                raise

        if data_type == "FOLDER":
            match_path = str(data_path) + "/"
        else:
            match_path = str(data_path)

        matched = next(
            (d for d in data_items if d.data.details.path == match_path),
            None,
        )

        if matched is None:
            raise FileNotFoundError(
                f"Could not find {data_type.lower()} at path '{data_path}' in project '{project_id}'"
            )

        return matched.data.id

    def _get_project_data_obj_by_id(
        self,
        project_id: str,
        data_id: str,
    ) -> ProjectData:
        """
        Retrieve the full ProjectData object by project ID and data ID.

        Adapted from:
            wrapica/project_data/functions/project_data_functions.py
            :: get_project_data_obj_by_id() (line 546)

        Changes from wrapica:
        - Fixed ApiClient context manager: wrapica creates api_instance inside
          `with ApiClient(...):` but calls api_instance.get_project_data()
          outside it (lines 582-592). This service keeps the call inside.
        - Fixed error re-raising: wrapica does `raise ApiException` (line 595).
          This service uses bare `raise`.

        :param project_id: The ICA project UUID.
        :param data_id: The ICA data ID (e.g. "fil.xxxxx").
        :return: The full libica ProjectData object.
        :raises ApiException: If the ICA API call fails.
        """
        with ApiClient(self._configuration) as api_client:
            api_instance = ProjectDataApi(api_client)
            try:
                return api_instance.get_project_data(
                    project_id=project_id,
                    data_id=data_id,
                )
            except ApiException as e:
                logger.error(f"Error getting project data: {e}")
                raise

    def _create_download_url(self, project_id: str, file_id: str) -> str:
        """
        Create a presigned download URL for a file in ICAv2.

        Adapted from:
            wrapica/project_data/functions/project_data_functions.py
            :: create_download_url() (line 1131)

        Changes from wrapica:
        - Fixed ApiClient context manager: wrapica creates api_instance inside
          `with ApiClient(...):` but calls create_download_url_for_data()
          outside it (lines 1170-1180). This service keeps the call inside.
        - Fixed error re-raising: wrapica does `raise ApiException` (line 1183).
          This service uses bare `raise`.

        :param project_id: The ICA project UUID.
        :param file_id: The ICA file data ID (e.g. "fil.xxxxx").
        :return: Presigned download URL string.
        :raises ApiException: If the ICA API call fails.
        """
        with ApiClient(self._configuration) as api_client:
            api_instance = ProjectDataApi(api_client)
            try:
                api_response: Download = api_instance.create_download_url_for_data(
                    project_id=project_id,
                    data_id=file_id,
                )
            except ApiException as e:
                logger.error(f"Error creating download URL: {e}")
                raise

        return api_response.url

    def read_icav2_file_contents(self, project_id: str, data_id: str) -> str:
        """
        Download a file from ICAv2 and return its contents as a string.

        Adapted from:
            wrapica/project_data/functions/project_data_functions.py
            :: read_icav2_file_contents() (line 2314)

        Changes from wrapica:
        - Removed the `output_path` parameter (wrapica line 2317). The original
          supports writing to a Path, a TextIOWrapper, or returning a string.
          This service only returns a string, since our use case is reading
          samplesheet content into memory.
        - Added `r.raise_for_status()` after the HTTP GET. The original wrapica
          does not validate the HTTP response status (line 2358), meaning a 403
          or 404 from the presigned URL would silently return garbage content.

        :param project_id: The ICA project UUID.
        :param data_id: The ICA file data ID (e.g. "fil.xxxxx").
        :return: The file contents decoded as a UTF-8 string.
        :raises requests.HTTPError: If the presigned URL download fails.
        :raises ApiException: If the download URL creation fails.
        """
        presigned_url = self._create_download_url(project_id, data_id)
        r = requests.get(presigned_url)
        r.raise_for_status()
        return r.content.decode()

    def get_file_contents_from_uri(self, data_uri: str) -> str:
        """
        Convenience method: resolve an icav2:// URI and return file contents.

        New method (not present in wrapica). Combines convert_uri_to_project_data_obj()
        and read_icav2_file_contents() into a single call for the common use case
        of "give me the file content for this URI".

        :param data_uri: ICAv2 URI, e.g.
            "icav2://9ec02c1f-53ba-47a5-854d-e6b53101adb7/path/to/SampleSheet.csv"
        :return: The file contents decoded as a UTF-8 string.
        :raises ValueError: If the URI is invalid.
        :raises FileNotFoundError: If the file is not found in the project.
        :raises ApiException: If any ICA API call fails.
        :raises requests.HTTPError: If the presigned URL download fails.

        Example::

            svc = ICAService()
            content = svc.get_file_contents_from_uri(
                "icav2://9ec02c1f-53ba-47a5-854d-e6b53101adb7/path/to/SampleSheet.csv"
            )
        """
        project_data_obj = self.convert_uri_to_project_data_obj(data_uri)
        return self.read_icav2_file_contents(
            project_id=project_data_obj.project_id,
            data_id=project_data_obj.data.id,
        )
