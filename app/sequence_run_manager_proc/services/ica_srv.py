import os
import logging
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse
from uuid import UUID
from libumccr.aws import libsm
import requests

from libica.openapi.v3 import ApiClient, Configuration, ApiException
from libica.openapi.v3.api.project_data_api import ProjectDataApi
from libica.openapi.v3.models import ProjectData, Download

logger = logging.getLogger(__name__)

DEFAULT_ICAV2_BASE_URL = "https://ica.illumina.com/ica/rest"


class ICAService:
    def __init__(self):
        assert os.environ.get("ICAV2_ACCESS_TOKEN_SECRET_ID", None), "ICAV2_ACCESS_TOKEN_SECRET_ID is not set"
        try:
            ICAV2_ACCESS_TOKEN = libsm.get_secret(os.environ.get("ICAV2_ACCESS_TOKEN_SECRET_ID"))
        except Exception as e:
            logger.error(f"Error retrieving ICAv2 token from the Secret Manager: {e}")
            raise e

        if not ICAV2_ACCESS_TOKEN:
            raise ValueError("ICAV2_ACCESS_TOKEN is not set")

        self._configuration = Configuration(
            host=os.environ.get("ICAV2_BASE_URL", DEFAULT_ICAV2_BASE_URL),
            access_token=ICAV2_ACCESS_TOKEN,
        )

    def _get_project_data_api(self) -> ProjectDataApi:
        with ApiClient(self._configuration) as api_client:
            return ProjectDataApi(api_client)

    def convert_uri_to_project_data_obj(self, data_uri: str) -> ProjectData:
        """
        Given an icav2:// URI, resolve it to a ProjectData object.
        The netloc must be a project UUID (not a project name).
        """
        uri_obj = urlparse(data_uri)

        if uri_obj.scheme != "icav2":
            raise ValueError(f"Unsupported URI scheme: {uri_obj.scheme}")

        # Validate that netloc is a UUID (project_id)
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

    def _get_data_id_from_path(self, project_id: str, data_path: Path, data_type: str) -> str:
        """Resolve a project file/folder path to its data ID."""
        api_instance = self._get_project_data_api()

        parent_folder_path = str(data_path.parent.absolute()) + "/"
        if parent_folder_path == "//":
            parent_folder_path = "/"

        try:
            data_items = api_instance.get_project_data_list(
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
            matched = next(
                (d for d in data_items if d.data.details.path == match_path),
                None,
            )
        else:
            match_path = str(data_path)
            matched = next(
                (d for d in data_items if d.data.details.path == match_path),
                None,
            )

        if matched is None:
            raise FileNotFoundError(f"Could not find {data_type.lower()} at path '{data_path}' in project '{project_id}'")

        return matched.data.id

    def _get_project_data_obj_by_id(self, project_id: str, data_id: str) -> ProjectData:
        """Retrieve the full ProjectData object by ID."""
        api_instance = self._get_project_data_api()
        try:
            return api_instance.get_project_data(
                project_id=project_id,
                data_id=data_id,
            )
        except ApiException as e:
            logger.error(f"Error getting project data: {e}")
            raise

    def _create_download_url(self, project_id: str, file_id: str) -> str:
        """Create a presigned download URL for a file."""
        api_instance = self._get_project_data_api()
        try:
            response: Download = api_instance.create_download_url_for_data(
                project_id=project_id,
                data_id=file_id,
            )
        except ApiException as e:
            logger.error(f"Error creating download URL: {e}")
            raise

        return response.url

    def read_icav2_file_contents(self, project_id: str, data_id: str) -> str:
        """Download a file from ICAv2 and return its contents as a string."""
        presigned_url = self._create_download_url(project_id, data_id)
        r = requests.get(presigned_url)
        r.raise_for_status()
        return r.content.decode()

    def get_file_contents_from_uri(self, data_uri: str) -> str:
        """
        Convenience method: given an icav2:// URI, resolve and return file contents.

        Usage:
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
