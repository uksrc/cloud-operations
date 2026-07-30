import json
import time
from typing import Optional, Tuple, Type


def _gcsdk_exception_types() -> Tuple[
    Type[Exception],
    Type[Exception],
    Type[Exception],
    Type[Exception],
    Type[Exception],
    Type[Exception],
]:
    """Load SDK exception classes without reassigning imported class names in try/except (mypy)."""
    try:
        from graphiant_sdk.exceptions import (
            ApiException,
            BadRequestException,
            ForbiddenException,
            NotFoundException,
            ServiceException,
            UnauthorizedException,
        )

        return (
            ApiException,
            BadRequestException,
            UnauthorizedException,
            ForbiddenException,
            NotFoundException,
            ServiceException,
        )
    except ImportError:
        return (
            type("ApiException", (Exception,), {}),
            type("BadRequestException", (Exception,), {}),
            type("UnauthorizedException", (Exception,), {}),
            type("ForbiddenException", (Exception,), {}),
            type("NotFoundException", (Exception,), {}),
            type("ServiceException", (Exception,), {}),
        )


try:
    import graphiant_sdk

    HAS_GRAPHIANT_SDK = True
except ImportError:
    HAS_GRAPHIANT_SDK = False

(
    ApiException,
    BadRequestException,
    UnauthorizedException,
    ForbiddenException,
    NotFoundException,
    ServiceException,
) = _gcsdk_exception_types()


def _pydantic_validation_error_type() -> Type[Exception]:
    try:
        from pydantic import ValidationError

        return ValidationError
    except ImportError:
        return type("PydanticValidationError", (Exception,), {})


PydanticValidationError = _pydantic_validation_error_type()

# Required dependencies - checked when class is instantiated
# Don't raise at module level to allow import test to pass

from .logger import setup_logger  # noqa: E402
from .poller import poller  # noqa: E402
from .exceptions import APIError, ValidationError  # noqa: E402
from .device_config_common import format_config_payload_for_log  # noqa: E402

LOG = setup_logger()

# Required dependencies - checked when methods are called
# Don't raise at module level to allow import test to pass


def _normalize_raw_access_token(value):
    """Return the token string without a ``Bearer `` prefix, or None if unset/empty."""
    if value is None:
        return None
    t = str(value).strip()
    if not t:
        return None
    if t.lower().startswith("bearer "):
        t = t[7:].strip()
    return t or None


class GraphiantPortalClient:
    def __init__(self, base_url=None, username=None, password=None, access_token=None, check_mode=False):
        if not HAS_GRAPHIANT_SDK:
            raise ImportError("graphiant-sdk is required for this module. Install it with: pip install graphiant-sdk")
        self.config = graphiant_sdk.Configuration(host=base_url, username=username, password=password)
        self.api_client = graphiant_sdk.ApiClient(self.config)
        self.api = graphiant_sdk.DefaultApi(self.api_client)
        self.bearer_token = None
        self.enterprise_info = None
        self.check_mode = check_mode
        self._access_token = access_token

    def _has_password_credentials(self):
        u = self.config.username
        p = self.config.password
        return bool(u is not None and str(u).strip()) and p is not None and str(p) != ""

    @staticmethod
    def _enterprise_session_ok(info):
        return bool(info and info.get("enterprise_id") is not None)

    def set_bearer_token(self):
        """
        Prefer a pre-provisioned access token (SSO / ``graphiant login``), then fall back
        to username/password login when the token is missing, invalid, or expired.
        """
        preprovisioned_token_rejected = False
        raw = _normalize_raw_access_token(self._access_token)
        if raw:
            self.bearer_token = f"Bearer {raw}"
            self.enterprise_info = self.get_enterprise_info()
            if self._enterprise_session_ok(self.enterprise_info):
                LOG.debug("GraphiantPortalClient session established with pre-provisioned access token")
                LOG.info(
                    "Graphiant portal session established using access token "
                    "(e.g. graphiant login / GRAPHIANT_ACCESS_TOKEN)"
                )
                LOG.info("GraphiantPortalClient Enterprise info: %s", self.enterprise_info)
                return
            preprovisioned_token_rejected = True
            LOG.warning(
                "Access token did not establish a valid portal session; "
                "falling back to username/password if provided"
            )
            self.bearer_token = None
            self.enterprise_info = None
            if not self._has_password_credentials():
                raise APIError(
                    "Access token was invalid or expired, and username/password were not "
                    "provided for fallback login."
                )

        if not self._has_password_credentials():
            raise APIError(
                "Authentication requires GRAPHIANT_ACCESS_TOKEN (e.g. run graphiant login and "
                "source ~/.graphiant/env.sh), module option access_token, or username and password."
            )
        try:
            self._login_with_password()
        except APIError as err:
            if preprovisioned_token_rejected:
                raise APIError(
                    "Access token (GRAPHIANT_ACCESS_TOKEN / access_token) was not accepted by the "
                    "API, then username/password login also failed. "
                    f"Login error: {err}"
                ) from err
            raise

    def _login_with_password(self):
        v1_auth_login_post_request = graphiant_sdk.V1AuthLoginPostRequest(
            username=self.config.username, password=self.config.password
        )
        v1_auth_login_post_response = None
        try:
            v1_auth_login_post_response = self.api.v1_auth_login_post(
                v1_auth_login_post_request=v1_auth_login_post_request
            )
        except BadRequestException as e:
            api_url = f"{self.api.api_client.configuration.host}/v1/auth/login"
            self._log_api_error(
                method_name="v1_auth_login_post",
                api_url=api_url,
                # request_body=v1_auth_login_post_request.to_dict(),
                exception=e,
            )
            raise APIError(
                f"v1_auth_login_post: Got BadRequestException. " f"Please verify payload is correct. {e.body}"
            )

        except (UnauthorizedException, ServiceException) as e:
            api_url = f"{self.api.api_client.configuration.host}/v1/auth/login"
            self._log_api_error(method_name="v1_auth_login_post", api_url=api_url, exception=e)
            raise APIError(
                f"v1_auth_login_post: Got {type(e).__name__}. " f"Please verify credentials are correct. {e.body}"
            )

        if not v1_auth_login_post_response.token:
            raise APIError("bearer_token is not retrieved")
        # Security: Do not log the actual bearer token to prevent credential exposure
        LOG.debug("GraphiantPortalClient Bearer token retrieved successfully")
        LOG.info("Graphiant Portal Bearer token retrieved successfully !!! ")
        self.bearer_token = f"Bearer {v1_auth_login_post_response.token}"
        # Get and log enterprise information
        self.enterprise_info = self.get_enterprise_info()
        LOG.info("GraphiantPortalClient Enterprise info: %s", self.enterprise_info)

    def get_enterprise_info(self):
        """
        Get enterprise information for the authenticated user.

        Returns:
            dict: Enterprise information including name and ID, or None if failed
        """
        try:
            # First get the current user's enterprise ID
            current_enterprise_id = None
            try:
                user_response = self.api.v1_auth_user_get(authorization=self.bearer_token)
                if user_response and hasattr(user_response, "enterprise_id"):
                    current_enterprise_id = user_response.enterprise_id
            except Exception as e:
                # Check if it's a Pydantic validation error (enum mismatch)
                error_str = str(e)
                is_validation_error = (
                    isinstance(e, PydanticValidationError)
                    or "validation error" in error_str.lower()
                    or "must be one of enum values" in error_str
                )
                if is_validation_error:
                    # Try to get raw response data to bypass validation
                    try:
                        # Use without_preload_content to get raw response data
                        raw_response = self.api.v1_auth_user_get_without_preload_content(
                            authorization=self.bearer_token
                        )
                        # Parse JSON manually to extract enterprise_id
                        response_data = json.loads(raw_response.data.decode("utf-8"))
                        current_enterprise_id = response_data.get("enterpriseId")
                        if current_enterprise_id:
                            LOG.info(
                                "get_enterprise_info: Successfully extracted enterprise_id from raw response: %s",
                                current_enterprise_id,
                            )
                        else:
                            LOG.warning("get_enterprise_info: Could not extract enterprise_id from raw response")
                            return None
                    except Exception as raw_error:
                        LOG.error("get_enterprise_info: Failed to get raw response: %s", raw_error)
                        return None
                else:
                    # Re-raise if it's not a validation error we can handle
                    raise

            if not current_enterprise_id:
                LOG.warning("get_enterprise_info: Could not get enterprise ID from user info")
                return None

            # Now get all enterprises to find the one matching the current user's enterprise ID
            enterprises_response = self.api.v1_enterprises_get(authorization=self.bearer_token)
            if (
                enterprises_response
                and hasattr(enterprises_response, "enterprises")
                and enterprises_response.enterprises
            ):
                for enterprise in enterprises_response.enterprises:
                    if getattr(enterprise, "enterprise_id", None) == current_enterprise_id:
                        enterprise_name = getattr(enterprise, "company_name", None)
                        LOG.info("Connected to enterprise: '%s' (ID: %s)", enterprise_name, current_enterprise_id)
                        return {"enterprise_id": current_enterprise_id, "company_name": enterprise_name}

            # If we couldn't find the enterprise details, return just the ID
            return {"enterprise_id": current_enterprise_id, "company_name": None}

        except ApiException as e:
            api_url = f"{self.api.api_client.configuration.host}/v1/auth/user"
            self._log_api_error(method_name="get_enterprise_info", api_url=api_url, exception=e)
            return None
        except Exception as e:
            LOG.error("get_enterprise_info: Unexpected error: %s", e)
            return None

    def _log_api_error(
        self,
        method_name: str,
        api_url: str,
        path_params: Optional[dict] = None,
        query_params: Optional[dict] = None,
        request_body: Optional[dict] = None,
        exception: Optional[Exception] = None,
    ) -> None:
        """
        Helper method to log API errors with comprehensive parameter information.

        Args:
            method_name (str): Name of the API method
            api_url (str): Full API URL
            path_params (dict): Path parameters
            query_params (dict): Query parameters
            request_body (dict): Request body for POST/PUT requests
            exception (Exception): The exception that occurred
        """
        LOG.error("%s: API Error - URL: %s", method_name, api_url)

        if path_params:
            LOG.error("%s: Path Parameters - %s", method_name, path_params)

        if query_params:
            query_string = "&".join([f"{k}={v}" for k, v in query_params.items()])
            LOG.error("%s: Query Parameters - %s", method_name, query_string)
        else:
            LOG.error("%s: Query Parameters - None", method_name)

        if request_body:
            LOG.error("%s: Request Body - %s", method_name, request_body)

        if exception:
            LOG.error("%s: Got Exception: %s", method_name, exception)

    def get_all_enterprises(self):
        """
        Get all enterprises on GCS.

        Returns:
            list: A list of enterprise information if successful, otherwise an empty list.
        """
        enterprises = self.api.v1_enterprises_get(authorization=self.bearer_token)
        LOG.debug("get_all_enterprises : %s", enterprises)
        return enterprises

    def get_edges_summary(self, device_id=None):
        """
        Get all edges summary from GCS.

        Args:
            device_id (int, optional): The device ID to filter edges.
            If not provided, returns all edges.

        Returns:
            list or dict: A list of all edges info if no device_id is provided,
            or a single edge's information if a device_id is provided.
        """
        response = self.api.v1_edges_summary_get(authorization=self.bearer_token)
        if device_id:
            for edge_info in response.edges_summary:
                if edge_info.device_id == device_id:
                    return edge_info
        return response.edges_summary

    def get_device_id(self, device_name):
        """
        Retrieve the device ID based on exact device name match.

        Args:
            device_name (str): Exact device name to search for

        Returns:
            int or None: The device ID if exact match found, None otherwise
        """
        output = self.get_edges_summary()
        for device_info in output:
            if device_info.hostname == device_name:
                LOG.debug("get_device_id: Found exact match for '%s' -> %s", device_name, device_info.device_id)
                return device_info.device_id

        LOG.debug("get_device_id: No exact match found for '%s'", device_name)
        return None

    def get_enterprise_id(self):
        """
        Retrieve the enterprise ID from the first available device in the edges summary.

        Returns:
            str or None: The enterprise ID, or None if no devices are found.
        """
        output = self.get_edges_summary()
        if not output:
            return None
        device_info = output[0]
        LOG.debug("get_enterprise_id : %s", device_info.enterprise_id)
        return device_info.enterprise_id

    def get_edges_summary_filter(self, role="gateway", region="us-central-1 (Chicago)", status="active"):
        """
        Get edges summary filtered by role, region, and status.
        """
        response = self.api.v1_edges_summary_get(authorization=self.bearer_token)
        edges_summary = []
        LOG.info(
            "get_edges_summary_filter: Getting edges summary for role: %s, region: %s, status: %s", role, region, status
        )
        for edge_info in response.edges_summary:
            if edge_info.role == role and edge_info.status == status:
                if hasattr(edge_info, "override_region") and edge_info.override_region == region:
                    edges_summary.append(edge_info)
                elif edge_info.region == region:
                    edges_summary.append(edge_info)
                else:
                    continue
        if len(edges_summary) > 0:
            LOG.info(
                "get_edges_summary_filter: Found %s edges summary for role: %s, region: %s, status: %s",
                len(edges_summary),
                role,
                region,
                status,
            )
            return edges_summary
        else:
            LOG.warning(
                "get_edges_summary_filter: No edges summary found for role: %s, region: %s, status: %s",
                role,
                region,
                status,
            )
            return None

    @poller(timeout=120, wait=10)
    def verify_device_portal_status(self, device_id: int):
        """
        Verifies device portal sync Ready status (InSync) and
         also verifies device connections to tunnel terminators status.
        """
        edge_summary = self.get_edges_summary(device_id=device_id)
        if edge_summary.portal_status == "Ready":
            if edge_summary.tt_conn_count and edge_summary.tt_conn_count == 2:
                return
            else:
                LOG.info(
                    "verify_device_portal_status: %s tunnel terminitor conn count: %s "
                    "Expected: tt_conn_count=2. Retrying..",
                    device_id,
                    edge_summary.tt_conn_count,
                )
                raise APIError(
                    f"verify_device_portal_status: "
                    f"{device_id} tunnel terminitor conn count: "
                    f"{edge_summary.tt_conn_count} Expected: tt_conn_count=2. Retry"
                )

        else:
            LOG.info(
                "verify_device_portal_status: %s Portal Status: %s Expected: Ready. Retrying..",
                device_id,
                edge_summary.portal_status,
            )
            raise APIError(
                f"verify_device_portal_status: {device_id} Portal Status: "
                f"{edge_summary.portal_status} Expected: Ready. Retrying.."
            )

    def put_device_config(self, device_id: int, core=None, edge=None):
        """
        Put Devices Config on GCS for Core or Edge

        Args:
            device_id (int): The device ID to push the config.
            core (dict, V1DevicesDeviceIdConfigPutRequestCore, optional): Core configuration data.
            edge (dict, V1DevicesDeviceIdConfigPutRequestEdge, optional): Edge configuration data.

        Returns:
            response (V1DevicesDeviceIdConfigPutResponse):
            The response from the API call to push the device config.

        Raises:
            AssertionError: If the device portal status is not 'Ready' after retries
            ApiException/AssertionError: If there is an API exception during the
            config push after retries
        """
        device_config_put_request = graphiant_sdk.V1DevicesDeviceIdConfigPutRequest(core=core, edge=edge)
        if getattr(self, "check_mode", False):
            LOG.info(
                "[check_mode] put_device_config would push config for device_id=%s: %s",
                device_id,
                format_config_payload_for_log(device_config_put_request.to_dict()),
            )
            return None
        try:
            # Verify device portal status and connection status.
            self.verify_device_portal_status(device_id=device_id)
            LOG.info(
                "put_device_config : config to be pushed for %s: \n%s",
                device_id,
                format_config_payload_for_log(device_config_put_request.to_dict()),
            )
            response = self.api.v1_devices_device_id_config_put(
                authorization=self.bearer_token,
                device_id=device_id,
                v1_devices_device_id_config_put_request=device_config_put_request,
            )
            # Verify device portal status and connection status.
            self.verify_device_portal_status(device_id=device_id)
            return response
        except ForbiddenException as e:
            LOG.error("put_device_config: Got ForbiddenException while config push %s", e)
            raise APIError(
                f"put_device_config : Retrying, Got ForbiddenException "
                f"while config push to {device_id}. "
                f"User {self.config.username} does not have permissions "
                f"to perform the requested operation "
                f"(v1_devices_device_id_config_put)."
            )
        except ApiException as e:
            LOG.warning("put_device_config : Exception while config push %s", e)
            raise APIError(
                f"put_device_config : Retrying, Exception while config push to {device_id}. " f"Exception: {e}"
            )

    def put_device_config_raw(self, device_id: int, payload: dict):
        """
        Put Devices Config on GCS using raw payload dictionary.

        This method accepts a raw payload dictionary that conforms to the
        /v1/devices/{device_id}/config API schema. It is designed for use cases
        where users want to provide the complete configuration payload directly.

        Args:
            device_id (int): The device ID to push the config.
            payload (dict): Raw configuration payload containing edge/core config.
                           Must conform to V1DevicesDeviceIdConfigPutRequest schema.

        Returns:
            response (V1DevicesDeviceIdConfigPutResponse):
            The response from the API call to push the device config.

        Raises:
            AssertionError: If the device portal status is not 'Ready' after retries
            ApiException/AssertionError: If there is an API exception during the
            config push after retries
        """
        # Extract edge and core from payload
        edge = payload.get("edge")
        core = payload.get("core")

        device_config_put_request = graphiant_sdk.V1DevicesDeviceIdConfigPutRequest(core=core, edge=edge)

        # Add optional fields if present in payload
        if "description" in payload:
            device_config_put_request.description = payload["description"]
        if "configurationMetadata" in payload:
            device_config_put_request.configuration_metadata = payload["configurationMetadata"]

        if getattr(self, "check_mode", False):
            LOG.info(
                "[check_mode] put_device_config_raw would push config for device_id=%s: %s",
                device_id,
                format_config_payload_for_log(device_config_put_request.to_dict()),
            )
            return None
        try:
            # Verify device portal status and connection status.
            self.verify_device_portal_status(device_id=device_id)
            LOG.info(
                "put_device_config_raw : config to be pushed for %s: \n%s",
                device_id,
                format_config_payload_for_log(device_config_put_request.to_dict()),
            )
            response = self.api.v1_devices_device_id_config_put(
                authorization=self.bearer_token,
                device_id=device_id,
                v1_devices_device_id_config_put_request=device_config_put_request,
            )
            # Verify device portal status and connection status.
            self.verify_device_portal_status(device_id=device_id)
            return response
        except ForbiddenException as e:
            LOG.error("put_device_config_raw: Got ForbiddenException while config push %s", e)
            raise AssertionError(
                f"put_device_config_raw : Retrying, Got ForbiddenException "
                f"while config push to {device_id}. "
                f"User {self.config.username} does not have permissions "
                f"to perform the requested operation "
                f"(v1_devices_device_id_config_put)."
            )
        except ApiException as e:
            LOG.warning("put_device_config_raw : Exception while config push %s", e)
            raise AssertionError(
                f"put_device_config_raw : Retrying, Exception while config push to {device_id}. " f"Exception: {e}"
            )

    def show_validated_payload(self, device_id: int, payload: dict):
        """
        Show validated device configuration payload using SDK models (dry-run mode).

        This method validates the payload structure by constructing the SDK request
        object and verifies the payload structure using SDK models without pushing the configuration.
        This returns the validated payload.

        Args:
            device_id (int): The device ID to validate the config for.
            payload (dict): Raw configuration payload containing edge/core config.
                           Must conform to V1DevicesDeviceIdConfigPutRequest schema.

        Returns:
            dict: Validation result containing the constructed request payload.

        Raises:
            Exception: If payload structure validation fails
        """
        # Extract edge and core from payload
        edge = payload.get("edge")
        core = payload.get("core")

        try:
            device_config_put_request = graphiant_sdk.V1DevicesDeviceIdConfigPutRequest(core=core, edge=edge)

            # Add optional fields if present in payload
            if "description" in payload:
                device_config_put_request.description = payload["description"]
            if "configurationMetadata" in payload:
                device_config_put_request.configuration_metadata = payload["configurationMetadata"]

            # Convert to dict to validate structure
            validated_payload_dict = device_config_put_request.to_dict()
        except Exception as sdk_e:
            raise ValidationError(
                f"show_validated_payload: Payload failed SDK schema validation for device_id={device_id}: {sdk_e}"
            ) from sdk_e

        LOG.info(
            "show_validated_payload : validated config for %s: \n%s",
            device_id,
            format_config_payload_for_log(validated_payload_dict),
        )

        LOG.info("show_validated_payload: Successfully showed validated payload for %s", device_id)
        return validated_payload_dict

    def post_devices_bringup(self, device_ids):
        """
        Post Devices Bringup On GCS

        Args:
            device_ids (list): List of device IDs to bring up.

        Returns:
            response: The response from the API call to bring up the devices.
        """
        data = {"deviceIds": device_ids}
        LOG.debug("post_devices_bringup : %s", data)
        response = self.api.v1_devices_bringup_post(
            authorization=self.bearer_token, v1_devices_bringup_post_request=data
        )
        return response

    def put_devices_bringup(self, device_ids, status):
        """
        Update the bringup status of the devices specified by their device IDs.

        Args:
            device_ids (list): A list of device IDs whose status needs to be updated.
            status (str): The desired status to be set for the devices:
                        - 'allowed', 'active', 'activate' → 'Allowed'
                        - 'denied', 'deactivate' → 'Denied'
                        - 'removed', 'decommission' → 'Removed'
                        - 'pending', 'staging', 'stage' → 'Pending'
                        - 'maintenance' → 'Maintenance'

        Returns:
            bool: True if the status update was successful, False if ApiException occurs.
        """
        data = {"deviceIds": device_ids, "status": ""}
        data["status"] = status
        if status.lower() in ["allowed", "active", "activate"]:
            data["status"] = "Allowed"
        if status.lower() in ["denied", "deactivate"]:
            data["status"] = "Denied"
        if status.lower() in ["removed", "decommission"]:
            data["status"] = "Removed"
        if status.lower() in ["pending", "staging", "stage"]:
            data["status"] = "Pending"
        if status.lower() == "maintenance":
            data["status"] = "Maintenance"
        try:
            LOG.debug("put_devices_bringup : %s", data)
            self.api.v1_devices_bringup_put(authorization=self.bearer_token, v1_devices_bringup_put_request=data)
            time.sleep(15)
            return True
        except ApiException:
            return False

    def patch_global_config(self, **kwargs):
        """
        Patch the global configuration on the system.

        Args:
            **kwargs: The global configuration parameters to be patched.

        Returns:
            The response from the API

        Raises:
            ApiException: If the API call fails.

        """
        patch_global_config_request = graphiant_sdk.V1GlobalConfigPatchRequest(
            global_prefix_sets=kwargs.get("global_prefix_sets"),
            ipfix_exporters=kwargs.get("ipfix_exporters"),
            ntps=kwargs.get("ntps"),
            prefix_sets=kwargs.get("prefix_sets"),
            routing_policies=kwargs.get("routing_policies"),
            snmps=kwargs.get("snmps"),
            syslog_servers=kwargs.get("syslog_servers"),
            traffic_policies=kwargs.get("traffic_policies"),
            vpn_profiles=kwargs.get("vpn_profiles"),
        )
        if getattr(self, "check_mode", False):
            LOG.info(
                "[check_mode] patch_global_config would push: %s",
                json.dumps(patch_global_config_request.to_dict(), indent=2),
            )
            return None
        try:
            LOG.info(
                "patch_global_config : config to be pushed : \n%s",
                json.dumps(patch_global_config_request.to_dict(), indent=2),
            )
            response = self.api.v1_global_config_patch(
                authorization=self.bearer_token, v1_global_config_patch_request=patch_global_config_request
            )
            return response
        except ForbiddenException as e:
            api_url = f"{self.api.api_client.configuration.host}/v1/global/config"
            self._log_api_error(method_name="v1_global_config_patch", api_url=api_url, exception=e)
            error_msg = (
                f"patch_global_config: Got ForbiddenException (403). "
                f"This may indicate insufficient permissions or authentication issues. "
                f"Please verify that your account has the required permissions to modify global configuration. "
                f"Error details: {e.body if hasattr(e, 'body') else str(e)}"
            )
            LOG.error(error_msg)
            raise APIError(error_msg)
        except (NotFoundException, ServiceException) as e:
            LOG.error(
                "patch_global_config: Got Exception while v1_global_config_patch request. "
                "Global object(s) might not exist."
            )
            raise APIError(
                f"patch_global_config : Got Exception {e} while "
                f"v1_global_config_patch request. "
                f"Global object(s) in the request might not exist."
            )
        except ApiException as e:
            LOG.warning("patch_global_config : Exception While Global config patch %s", e)
            raise APIError("patch_global_config : Retrying, Exception while Global config patch")

    def post_global_summary(self, **kwargs):
        """
        Posts global summary configuration to the system.
        Args:
            **kwargs: The global summary configuration parameters to be posted.

        Returns:
            The response from the API

        Raises:
            ApiException: If the API call fails.
        """
        body = graphiant_sdk.V1GlobalSummaryPostRequest(**kwargs)
        try:
            LOG.info("post_global_summary: %s", body.to_dict())
            response = self.api.v1_global_summary_post(
                authorization=self.bearer_token, v1_global_summary_post_request=body
            )
            return response
        except ApiException as e:
            LOG.warning("post_global_summary : Exception While Global config patch %s", e)
            raise APIError("post_global_summary : Retrying, Exception while Global config patch")

    def _get_global_summaries(self, **summary_kwargs):
        """
        Call post_global_summary with the given kwargs and return the list of summary
        dicts. Each summary may include name, id, numAttachedDevices, numPolicies, etc.
        Used to list existing global config objects and check if they are in use.

        Returns:
            list: List of summary dicts (e.g. [{"name": "...", "numAttachedDevices": 1}]),
                  or empty list on failure. Handles both {"summaries": [...]} and legacy
                  response shapes.
        """
        try:
            result = self.post_global_summary(**summary_kwargs)
            data = result.to_dict() if hasattr(result, "to_dict") else result
            if not isinstance(data, dict):
                return []
            raw_list = None
            for key in ("summaries", "Summaries"):
                if key in data and isinstance(data[key], list):
                    raw_list = data[key]
                    break
            if raw_list is None:
                for key, value in data.items():
                    if isinstance(value, list) and value:
                        raw_list = value
                        break
            if not raw_list:
                return []
            # Normalize to list of dicts when possible (SDK may return model objects)
            out = []
            for item in raw_list:
                if isinstance(item, dict):
                    out.append(item)
                elif hasattr(item, "to_dict"):
                    out.append(item.to_dict())
                else:
                    out.append(item)  # keep as-is; is_global_object_in_use handles objects
            return out
        except Exception as e:
            LOG.warning("_get_global_summaries(%s): %s", summary_kwargs, e)
            return []

    def _summary_int(self, summary, *keys):
        """Get first present key from summary (dict or object); keys can be snake_case or camelCase."""
        for k in keys:
            v = summary.get(k) if isinstance(summary, dict) else getattr(summary, k, None)
            if v is not None:
                return int(v)
        return 0

    def is_global_object_in_use(self, summary, check_num_policies: bool = False) -> bool:
        """
        Return True if the global object is in use and cannot be deleted.

        Uses ManaV2GlobalObjectSummary fields: num_attached_devices, num_attached_sites,
        and optionally num_policies (for prefix sets). Accepts dict or SDK model object,
        and both snake_case and camelCase keys.

        Args:
            summary: One summary from get_global_*_summaries() (dict or model).
            check_num_policies: If True, also treat num_policies > 0 as in use (prefix sets).
        """
        num_devices = self._summary_int(
            summary,
            "num_attached_devices",
            "numAttachedDevices",
        )
        if num_devices > 0:
            return True
        num_sites = self._summary_int(
            summary,
            "num_attached_sites",
            "numAttachedSites",
        )
        if num_sites > 0:
            return True
        if check_num_policies:
            num_policies = self._summary_int(
                summary,
                "num_policies",
                "numPolicies",
            )
            if num_policies > 0:
                return True
        return False

    def _get_existing_global_names_from_summary(self, **summary_kwargs):
        """
        Call post_global_summary with the given kwargs and return a set of object names
        from the response. Used to list existing global config objects by type.

        Returns:
            set: Names from the summary response, or empty set on failure.
        """
        summaries = self._get_global_summaries(**summary_kwargs)
        return {s.get("name") for s in summaries if s.get("name")}

    def get_global_routing_policy_summaries(self):
        """Return list of routing policy (BGP filter) summary dicts from the portal."""
        return self._get_global_summaries(routing_policy_type=True)

    def get_global_prefix_set_summaries(self):
        """Return list of prefix set summary dicts from the portal."""
        return self._get_global_summaries(prefix_set_type=True)

    def get_global_snmp_summaries(self):
        """Return list of SNMP object summary dicts from the portal."""
        return self._get_global_summaries(snmp_type=True)

    def get_global_syslog_server_summaries(self):
        """Return list of syslog server summary dicts from the portal."""
        return self._get_global_summaries(syslog_server_type=True)

    def get_global_ipfix_exporter_summaries(self):
        """Return list of IPFIX exporter summary dicts from the portal."""
        return self._get_global_summaries(ipfix_exported_type=True)

    def get_global_ntp_summaries(self):
        """Return list of NTP object summary dicts from the portal."""
        return self._get_global_summaries(ntp_type=True)

    def get_existing_global_routing_policy_names(self):
        """
        Return the set of names of global routing policies (BGP filters) that exist on the portal.

        Returns:
            set: Names of existing routing policies, or empty set if the API call fails.
        """
        return self._get_existing_global_names_from_summary(routing_policy_type=True)

    def get_existing_global_prefix_set_names(self):
        """
        Return the set of names of global prefix sets that exist on the portal.

        Returns:
            set: Names of existing global prefix sets, or empty set if the API call fails.
        """
        return self._get_existing_global_names_from_summary(prefix_set_type=True)

    def get_existing_global_snmp_names(self):
        """
        Return the set of names of global SNMP objects that exist on the portal.

        Returns:
            set: Names of existing SNMP objects, or empty set if the API call fails.
        """
        return self._get_existing_global_names_from_summary(snmp_type=True)

    def get_existing_global_syslog_server_names(self):
        """
        Return the set of names of global syslog servers that exist on the portal.

        Returns:
            set: Names of existing syslog servers, or empty set if the API call fails.
        """
        return self._get_existing_global_names_from_summary(syslog_server_type=True)

    def get_existing_global_ipfix_exporter_names(self):
        """
        Return the set of names of global IPFIX exporters that exist on the portal.

        Returns:
            set: Names of existing IPFIX exporters, or empty set if the API call fails.
        """
        return self._get_existing_global_names_from_summary(ipfix_exported_type=True)

    def get_existing_global_ntp_names(self):
        """
        Return the set of names of global NTP objects that exist on the portal.

        Returns:
            set: Names of existing NTP objects, or empty set if the API call fails.
        """
        return self._get_existing_global_names_from_summary(ntp_type=True)

    def get_global_routing_policy_id(self, policy_name):
        """
        Retrieve the global routing policy ID based on the policy name.

        Args:
            policy_name (str): The name of the routing policy.

        Returns:
            str or None: The ID of the routing policy if found, otherwise None.
        """
        for summary in self.get_global_routing_policy_summaries():
            if summary.get("name") == policy_name:
                return summary.get("id")
        return None

    # Site API methods
    def create_site(self, site_data: dict):
        """
        Create a new site.

        Args:
            site_data (dict): The site data containing name, location, etc.

        Returns:
            dict: The created site information

        Raises:
            ApiException: If the API call fails.
        """
        if getattr(self, "check_mode", False):
            LOG.info("[check_mode] create_site would create: %s", json.dumps(site_data, indent=2))
            return type("MockSite", (), {"id": 0})()
        try:
            LOG.info("create_site: Creating site with data: %s", json.dumps(site_data, indent=2))
            response = self.api.v1_sites_post(authorization=self.bearer_token, v1_sites_post_request=site_data)
            LOG.info("create_site: Successfully created site with ID: %s", response.site.id)
            return response.site
        except ApiException as e:
            api_url = f"{self.api.api_client.configuration.host}/v1/sites"
            self._log_api_error(method_name="create_site", api_url=api_url, request_body=site_data, exception=e)
            raise e

    def delete_site(self, site_id: int):
        """
        Delete a site.

        Args:
            site_id (int): The ID of the site to delete

        Returns:
            bool: True if deletion was successful, False otherwise
        """
        if getattr(self, "check_mode", False):
            LOG.info("[check_mode] delete_site would delete site with ID: %s", site_id)
            return True
        try:
            LOG.info("delete_site: Deleting site with ID: %s", site_id)
            self.api.v1_sites_site_id_delete(authorization=self.bearer_token, site_id=site_id)
            LOG.info("delete_site: Successfully deleted site with ID: %s", site_id)
            return True
        except ApiException as e:
            api_url = f"{self.api.api_client.configuration.host}/v1/sites/{site_id}"
            self._log_api_error(
                method_name="delete_site", api_url=api_url, path_params={"site_id": site_id}, exception=e
            )
            return False

    def get_sites_details(self):
        """
        Get detailed information about all sites using v1/sites/details API.

        Returns:
            list: List of site details
        """
        try:
            response = self.api.v1_sites_details_get(authorization=self.bearer_token)
            LOG.debug("get_sites_details: Retrieved %s sites using v1/sites/details", len(response.sites))
            return response.sites
        except ApiException as e:
            api_url = f"{self.api.api_client.configuration.host}/v1/sites/details"
            self._log_api_error(method_name="get_sites_details", api_url=api_url, exception=e)
            return []

    def site_exists(self, site_name: str) -> bool:
        """
        Check if a site exists using v1/sites/details API.

        Args:
            site_name (str): The name of the site to check.

        Returns:
            bool: True if site exists, False otherwise.
        """
        try:
            site_id = self.get_site_id(site_name)
            return site_id is not None
        except Exception as e:
            LOG.error("site_exists: Got Exception while checking if site '%s' exists: %s", site_name, e)
            return False

    def post_site_config(self, site_id: int, site_config: dict):
        """
        Update site configuration for global system object attachments.

        Args:
            site_id (int): The site ID to update the configuration for.
            site_config (dict): The site configuration payload containing global object operations.

        Returns:
            The response from the API

        Raises:
            ApiException: If the API call fails.
        """
        if getattr(self, "check_mode", False):
            LOG.info(
                "[check_mode] post_site_config would push for site_id=%s: %s",
                site_id,
                json.dumps(site_config, indent=2),
            )
            return None
        try:
            LOG.info(
                "post_site_config : config to be pushed for site %s: \n%s", site_id, json.dumps(site_config, indent=2)
            )
            response = self.api.v1_sites_site_id_post(
                authorization=self.bearer_token, site_id=site_id, v1_sites_site_id_post_request=site_config
            )
            return response
        except ApiException as e:
            LOG.error("post_site_config: Got Exception while updating site %s config: %s", site_id, e)
            raise e

    def get_site_id(self, site_name: str):
        """
        Get site ID by site name using v1/sites/details API.

        Args:
            site_name (str): The name of the site.

        Returns:
            int or None: The site ID if found, None otherwise.
        """
        try:
            # Get detailed site information using v1/sites/details
            response = self.api.v1_sites_details_get(authorization=self.bearer_token)
            sites = response.sites
            LOG.info("get_site_id: Looking for site '%s' in %s sites using v1/sites/details", site_name, len(sites))

            for site in sites:
                if site.name == site_name:
                    LOG.info("get_site_id: Found site '%s' with ID %s", site_name, site.id)
                    return site.id

            # Log available sites for debugging
            available_sites = [site.name for site in sites]
            LOG.warning("get_site_id: Site '%s' not found. Available sites: %s", site_name, available_sites)
            return None
        except ApiException as e:
            api_url = f"{self.api.api_client.configuration.host}/v1/sites"
            self._log_api_error(
                method_name="get_site_id", api_url=api_url, query_params={"name": site_name}, exception=e
            )
            return None

    # Global LAN Segments API methods
    def post_global_lan_segments(self, name: str, description: str = ""):
        """
        Create a global LAN segment.

        Args:
            name (str): Name of the LAN segment
            description (str): Description of the LAN segment

        Returns:
            dict: Response containing the created LAN segment ID
        """
        post_lan_segments_request = graphiant_sdk.V1GlobalLanSegmentsPostRequest(name=name, description=description)
        if getattr(self, "check_mode", False):
            LOG.info("[check_mode] post_global_lan_segments would create: name=%s description=%s", name, description)
            return type("MockResponse", (), {"id": 0})()
        try:
            LOG.info("post_global_lan_segments: Creating LAN segment '%s' with description '%s'", name, description)
            response = self.api.v1_global_lan_segments_post(
                authorization=self.bearer_token, v1_global_lan_segments_post_request=post_lan_segments_request
            )
            LOG.info("post_global_lan_segments: Successfully created LAN segment '%s' with ID: %s", name, response.id)
            return response
        except ApiException as e:
            api_url = f"{self.api.api_client.configuration.host}/v1/global/lan-segments"
            self._log_api_error(
                method_name="post_global_lan_segments",
                api_url=api_url,
                request_body={"name": name, "description": description},
                exception=e,
            )
            raise

    def delete_global_lan_segments(self, lan_segment_id: int):
        """
        Delete a global LAN segment.

        Args:
            lan_segment_id (int): ID of the LAN segment to delete

        Returns:
            bool: True if deletion was successful, False otherwise
        """
        if getattr(self, "check_mode", False):
            LOG.info("[check_mode] delete_global_lan_segments would delete LAN segment with ID: %s", lan_segment_id)
            return True
        try:
            LOG.info("delete_global_lan_segments: Deleting LAN segment with ID: %s", lan_segment_id)
            # Use the correct method name from the SDK
            self.api.v1_global_lan_segments_id_delete(authorization=self.bearer_token, id=lan_segment_id)
            # DELETE operations typically return 204 (No Content) or empty response
            # We consider any successful call (no exception) as success
            LOG.info("delete_global_lan_segments: Successfully deleted LAN segment with ID: %s", lan_segment_id)
            return True
        except Exception as e:
            LOG.error("delete_global_lan_segments: Got Exception while deleting LAN segment %s: %s", lan_segment_id, e)
            return False

    def get_global_lan_segments(self):
        """
        Get all global LAN segments.

        Returns:
            list: List of global LAN segments
        """
        try:
            response = self.api.v1_global_lan_segments_get(authorization=self.bearer_token)
            LOG.debug("get_global_lan_segments: %s", response)
            # Ensure we always return a list, even if entries is None
            if hasattr(response, "entries") and response.entries is not None:
                return response.entries
            else:
                LOG.info("get_global_lan_segments: No LAN segments found or entries is None")
                return []
        except ApiException as e:
            api_url = f"{self.api.api_client.configuration.host}/v1/global/lan-segments"
            self._log_api_error(method_name="get_global_lan_segments", api_url=api_url, exception=e)
            return []

    def get_lan_segment_id(self, lan_segment_name):
        """
        Retrieve the lan segment ID based on the lan segment name.

        Args:
            lan_segment_name (str): The name of the lan segment (e.g., 'lan-7-test')

        Returns:
            int or None: The ID of the lan segment if found, None otherwise.
        """
        output = self.get_global_lan_segments()
        for lan_segment_obj in output:
            if lan_segment_obj.name == lan_segment_name:
                return lan_segment_obj.id
        return None

    def get_lan_segments_dict(self):
        """
        Retrieve all lan segments as a dictionary mapping names to IDs.

        Returns:
            dict: A dictionary mapping lan segment names to their IDs.
        """
        output = self.get_global_lan_segments()
        lan_segments = {}
        for lan_segment_obj in output:
            lan_segments[lan_segment_obj.name] = lan_segment_obj.id
        return lan_segments

    # Site Lists API methods

    def create_global_site_list(self, site_list_config: dict):
        """
        Create a global site list.
        """
        if getattr(self, "check_mode", False):
            LOG.info("[check_mode] create_global_site_list would create: %s", json.dumps(site_list_config, indent=2))
            return None
        try:
            LOG.info("create_global_site_list: Creating site list '%s'", site_list_config.get("name"))
            response = self.api.v1_global_site_lists_post(
                authorization=self.bearer_token, v1_global_site_lists_post_request=site_list_config
            )
            LOG.info("create_global_site_list: Successfully created site list with ID: %s", response.id)
            return response
        except ApiException as e:
            LOG.error("create_global_site_list: Got Exception while creating site list: %s", e)
            raise e

    def delete_global_site_list(self, site_list_id: int):
        """
        Delete a global site list.
        """
        if getattr(self, "check_mode", False):
            LOG.info("[check_mode] delete_global_site_list would delete site list with ID: %s", site_list_id)
            return True
        try:
            LOG.info("delete_global_site_list: Deleting site list with ID: %s", site_list_id)
            self.api.v1_global_site_lists_id_delete(authorization=self.bearer_token, id=site_list_id)
            LOG.info("delete_global_site_list: Successfully deleted site list with ID: %s", site_list_id)
            return True
        except Exception as e:
            # Handle validation errors for DELETE operations (often return empty responses)
            if "validation error" in str(e) and "V1GlobalSiteListsIdDeleteResponse" in str(e):
                LOG.info(
                    "delete_global_site_list: Delete operation completed (validation error can be ignored): %s",
                    site_list_id,
                )
                return True
            LOG.error("delete_global_site_list: Got Exception while deleting site list %s: %s", site_list_id, e)
            return False

    def get_global_site_lists(self):
        """
        Get all global site lists.
        """
        try:
            LOG.info("get_global_site_lists: Retrieving all global site lists")
            response = self.api.v1_global_site_lists_get(authorization=self.bearer_token)
            if response and hasattr(response, "entries") and response.entries:
                LOG.info("get_global_site_lists: Successfully retrieved %s site lists", len(response.entries))
                return response.entries
            else:
                LOG.info("get_global_site_lists: No site lists found")
                return []
        except ApiException as e:
            LOG.error("get_global_site_lists: Got Exception while retrieving site lists: %s", e)
            return []

    def get_global_site_list(self, site_list_id: int):
        """
        Get a specific global site list by ID.
        """
        try:
            LOG.info("get_global_site_list: Retrieving site list with ID: %s", site_list_id)
            response = self.api.v1_global_site_lists_id_get(authorization=self.bearer_token, id=site_list_id)
            LOG.info("get_global_site_list: Successfully retrieved site list")
            return response
        except ApiException as e:
            LOG.error("get_global_site_list: Got Exception while retrieving site list %s: %s", site_list_id, e)
            raise e

    def get_site_list_id(self, site_list_name: str):
        """
        Get site list ID by site list name using v1/global/site-lists API.

        Args:
            site_list_name (str): The name of the site list.

        Returns:
            int or None: The site list ID if found, None otherwise.
        """
        try:
            # Get all site lists using v1/global/site-lists API
            response = self.api.v1_global_site_lists_get(authorization=self.bearer_token)
            site_lists = response.entries
            if site_lists is None:
                LOG.info("get_site_list_id: No site lists found")
                return None
            LOG.info(
                "get_site_list_id: Looking for site_list '%s' in %s site_lists using v1/global/site-lists",
                site_list_name,
                len(site_lists),
            )

            # Log available site_lists for debugging
            available_site_lists = [site_list.name for site_list in site_lists]
            LOG.info("get_site_list_id: Available site_lists: %s", available_site_lists)

            for site_list in site_lists:
                if site_list.name == site_list_name:
                    LOG.info("get_site_list_id: Found site_list '%s' with ID %s", site_list_name, site_list.id)
                    return site_list.id
            LOG.warning(
                "get_site_list_id: Site_list '%s' not found. Available site_lists: %s",
                site_list_name,
                available_site_lists,
            )
            return None
        except ApiException as e:
            api_url = f"{self.api.api_client.configuration.host}/v1/global/site-lists"
            self._log_api_error(
                method_name="get_site_list_id", api_url=api_url, query_params={"name": site_list_name}, exception=e
            )
            return None

    # Data Exchange API Methods

    def create_data_exchange_services(self, service_config: dict):
        """
        Create a new Data Exchange service.

        Args:
            service_config (dict): Service configuration containing:
                - serviceName: Service name
                - type: Service type (e.g., "peering_service")
                - policy: Service policy configuration

        Returns:
            dict: Created service response
        """
        if getattr(self, "check_mode", False):
            LOG.info(
                "[check_mode] create_data_exchange_services would create: %s", json.dumps(service_config, indent=2)
            )
            return type("MockResponse", (), {"id": 0})()
        try:
            LOG.info("create_data_exchange_services: Creating service '%s'", service_config.get("serviceName"))
            response = self.api.v1_extranets_b2b_peering_producer_post(
                authorization=self.bearer_token, v1_extranets_b2b_peering_producer_post_request=service_config
            )
            LOG.info("create_data_exchange_services: Successfully created service with ID: %s", response.id)
            return response
        except ApiException as e:
            # Log the actual API endpoint URL and request body for debugging
            api_url = f"{self.api.api_client.configuration.host}/v1/extranets-b2b-peering/producer"
            self._log_api_error(
                method_name="create_data_exchange_services", api_url=api_url, request_body=service_config, exception=e
            )
            raise e

    def get_data_exchange_services_summary(self):
        """
        Get summary of all Data Exchange services.

        Returns:
            dict: Services summary response
        """
        try:
            LOG.info("get_data_exchange_services_summary: Retrieving services summary")
            response = self.api.v1_extranets_b2b_general_services_summary_get(authorization=self.bearer_token)
            services_count = len(response.info) if response.info else 0
            LOG.info("get_data_exchange_services_summary: Successfully retrieved %s services", services_count)
            return response
        except ApiException as e:
            # Log the actual API endpoint URL for debugging
            api_url = f"{self.api.api_client.configuration.host}/v1/extranets-b2b-general/services-summary"
            self._log_api_error(method_name="get_data_exchange_services_summary", api_url=api_url, exception=e)
            raise e

    def get_data_exchange_service_by_name(self, service_name: str):
        """
        Get a specific Data Exchange service by name.

        Args:
            service_name (str): Name of the service to retrieve

        Returns:
            dict: Service details or None if not found
        """
        try:
            LOG.info("get_data_exchange_service_by_name: Looking for service '%s'", service_name)
            services_summary = self.get_data_exchange_services_summary()

            # Handle case where services list is None
            if not services_summary.info:
                LOG.info("get_data_exchange_service_by_name: No services found")
                return None

            for service in services_summary.info:
                if service.name == service_name:
                    LOG.info(
                        "get_data_exchange_service_by_name: Found service '%s' with ID: %s", service_name, service.id
                    )
                    return service

            LOG.info("get_data_exchange_service_by_name: Service '%s' not found", service_name)
            return None
        except Exception as e:
            LOG.error("get_data_exchange_service_by_name: Error finding service '%s': %s", service_name, e)
            return None

    def get_data_exchange_service_id_by_name(self, service_name: str):
        """
        Get a Data Exchange service ID by name.

        Args:
            service_name (str): Name of the service to retrieve

        Returns:
            int: Service ID or None if not found
        """
        try:
            LOG.info("get_data_exchange_service_id_by_name: Looking for service ID for '%s'", service_name)
            service = self.get_data_exchange_service_by_name(service_name)

            if service:
                LOG.info("get_data_exchange_service_id_by_name: Found service ID %s for '%s'", service.id, service_name)
                return service.id
            else:
                LOG.info("get_data_exchange_service_id_by_name: Service '%s' not found", service_name)
                return None
        except Exception as e:
            LOG.error("get_data_exchange_service_id_by_name: Error finding service ID for '%s': %s", service_name, e)
            return None

    def create_data_exchange_customers(self, customer_config: dict):
        """
        Create a new Data Exchange customer.

        Args:
            customer_config (dict): Customer configuration containing:
                - name: Customer name
                - type: Customer type (e.g., "non_graphiant_peer")
                - invite: Customer invite configuration

        Returns:
            dict: Created customer response
        """
        if getattr(self, "check_mode", False):
            LOG.info(
                "[check_mode] create_data_exchange_customers would create: %s", json.dumps(customer_config, indent=2)
            )
            return type("MockResponse", (), {"id": 0})()
        try:
            LOG.info("create_data_exchange_customers: Creating customer '%s'", customer_config.get("name"))
            response = self.api.v1_extranets_b2b_peering_customer_post(
                authorization=self.bearer_token, v1_extranets_b2b_peering_customer_post_request=customer_config
            )
            LOG.info("create_data_exchange_customers: Successfully created customer with ID: %s", response.id)
            return response
        except ApiException as e:
            # Log the actual API endpoint URL and request body for debugging
            api_url = f"{self.api.api_client.configuration.host}/v1/extranets-b2b-peering/customer"
            self._log_api_error(
                method_name="create_data_exchange_customers", api_url=api_url, request_body=customer_config, exception=e
            )
            raise e

    def get_data_exchange_customers_summary(self):
        """
        Get summary of all Data Exchange customers.

        Returns:
            dict: Customers summary response
        """
        try:
            LOG.info("get_data_exchange_customers_summary: Retrieving customers summary")
            response = self.api.v1_extranets_b2b_general_customers_summary_get(authorization=self.bearer_token)
            customers_count = len(response.customers) if response.customers else 0
            LOG.info("get_data_exchange_customers_summary: Successfully retrieved %s customers", customers_count)
            return response
        except ApiException as e:
            # Log the actual API endpoint URL for debugging
            api_url = f"{self.api.api_client.configuration.host}/v1/extranets-b2b-general/customers-summary"
            self._log_api_error(method_name="get_data_exchange_customers_summary", api_url=api_url, exception=e)
            raise e

    def get_data_exchange_customer_by_name(self, customer_name: str):
        """
        Get a specific Data Exchange customer by name.

        Args:
            customer_name (str): Name of the customer to retrieve

        Returns:
            dict: Customer details or None if not found
        """
        try:
            LOG.info("get_data_exchange_customer_by_name: Looking for customer '%s'", customer_name)
            customers_summary = self.get_data_exchange_customers_summary()

            # Handle case where customers list is None
            if not customers_summary.customers:
                LOG.info("get_data_exchange_customer_by_name: No customers found")
                return None

            for customer in customers_summary.customers:
                if customer.name == customer_name:
                    LOG.info(
                        "get_data_exchange_customer_by_name: Found customer '%s' with ID: %s",
                        customer_name,
                        customer.id,
                    )
                    return customer

            LOG.info("get_data_exchange_customer_by_name: Customer '%s' not found", customer_name)
            return None
        except Exception as e:
            LOG.error("get_data_exchange_customer_by_name: Error finding customer '%s': %s", customer_name, e)
            return None

    def get_matched_services_for_customer(self, customer_id: int):
        """
        Get list of services already matched to a specific customer.

        Args:
            customer_id (int): ID of the customer

        Returns:
            list: List of matched services with their details, or None if failed
        """
        try:
            LOG.info("get_matched_services_for_customer: Retrieving matched services for customer ID: %s", customer_id)
            response = self.api.v1_extranets_b2b_peering_match_services_summary_id_get(
                authorization=self.bearer_token, id=customer_id
            )

            services = getattr(response, "services", None) if response else None
            if services:
                LOG.info(
                    "get_matched_services_for_customer: Found %s matched services for customer %s",
                    len(services),
                    customer_id,
                )
                return services
            else:
                LOG.info("get_matched_services_for_customer: No matched services found for customer %s", customer_id)
                return []

        except ApiException as e:
            api_url = f"{self.api.api_client.configuration.host}/v1/extranets-b2b-peering/match/services/summary"
            self._log_api_error(
                method_name="get_matched_services_for_customer",
                api_url=api_url,
                query_params={"id": customer_id},
                exception=e,
            )
            return None
        except Exception as e:
            LOG.error("get_matched_services_for_customer: Unexpected error: %s", e)
            return None

    def get_matching_customers_for_service(self, service_id: int):
        """
        Get list of customers matched to a specific service (producer view).
        This API returns match_id for each customer-service match.

        Args:
            service_id (int): ID of the service

        Returns:
            list: List of matched customers with match_id, or None if failed
        """
        try:
            LOG.info("get_matching_customers_for_service: Retrieving matching customers for service ID: %s", service_id)
            response = self.api.v1_extranets_b2b_peering_producer_id_matching_customers_summary_get(
                authorization=self.bearer_token, id=service_id
            )

            if response and hasattr(response, "info") and response.info is not None:
                LOG.info(
                    "get_matching_customers_for_service: Found %s matching customers for service %s",
                    len(response.info),
                    service_id,
                )
                return response.info
            else:
                LOG.info("get_matching_customers_for_service: No matching customers found for service %s", service_id)
                return []

        except ApiException as e:
            host = self.api.api_client.configuration.host
            api_url = f"{host}/v1/extranets-b2b-peering/producer/{service_id}/matching-customers-summary"
            self._log_api_error(
                method_name="get_matching_customers_for_service",
                api_url=api_url,
                query_params={"id": service_id},
                exception=e,
            )
            return None
        except Exception as e:
            LOG.error("get_matching_customers_for_service: Unexpected error: %s", e)
            return None

    def delete_data_exchange_customer(self, customer_id: int):
        """
        Delete a Data Exchange customer.

        Args:
            customer_id (int): ID of the customer to delete

        Returns:
            dict: Delete response
        """
        if getattr(self, "check_mode", False):
            LOG.info("[check_mode] delete_data_exchange_customer would delete customer with ID: %s", customer_id)
            return type("MockResponse", (), {})()
        try:
            LOG.info("delete_data_exchange_customer: Deleting customer with ID: %s", customer_id)
            response = self.api.v1_extranets_b2b_peering_customer_id_delete(
                authorization=self.bearer_token, id=customer_id
            )
            LOG.info("delete_data_exchange_customer: Successfully deleted customer with ID: %s", customer_id)
            return response
        except ApiException as e:
            # Log the actual API endpoint URL for debugging
            api_url = f"{self.api.api_client.configuration.host}/v1/extranets-b2b-peering/customer/{customer_id}"
            self._log_api_error(
                method_name="delete_data_exchange_customer",
                api_url=api_url,
                path_params={"customer_id": customer_id},
                exception=e,
            )
            raise e

    def get_data_exchange_customer_details(self, customer_id: int) -> dict:
        """
        Get detailed information about a specific Data Exchange customer.

        GET /v1/extranets-b2b-peering/customer/{id}
        Returns: {customerName, type, emails, numSites}

        Args:
            customer_id (int): ID of the customer to retrieve

        Returns:
            dict: Customer details response
        """
        try:
            LOG.info("get_data_exchange_customer_details: Retrieving customer details for ID: %s", customer_id)
            api_client = self.api.api_client
            method, url, header_params, body, post_params = api_client.param_serialize(
                "GET",
                "/v1/extranets-b2b-peering/customer/{id}",
                path_params={"id": customer_id},
                header_params={
                    "Authorization": self.bearer_token,
                    "Accept": "application/json",
                },
                body=None,
            )
            response_data = api_client.call_api(method, url, header_params, body, post_params)
            response_data.read()
            LOG.info(
                "get_data_exchange_customer_details: Successfully retrieved customer details for ID: %s", customer_id
            )
            return json.loads(response_data.data)
        except ApiException as e:
            api_url = f"{self.api.api_client.configuration.host}/v1/extranets-b2b-peering/customer/{customer_id}"
            self._log_api_error(
                method_name="get_data_exchange_customer_details",
                api_url=api_url,
                path_params={"customer_id": customer_id},
                exception=e,
            )
            raise e

    def edit_data_exchange_customer(self, customer_id: int, update_payload: dict):
        """
        Edit an existing Data Exchange customer (update adminEmail list).

        PUT /v1/extranets-b2b-peering/customer/{id}

        Args:
            customer_id (int): ID of the customer to update
            update_payload (dict): Payload: {"id": id, "status": "",
                "invite": {"adminEmail": [...], "maximumNumberOfSites": n}}

        Returns:
            RESTResponse or MockResponse in check mode
        """
        if getattr(self, "check_mode", False):
            LOG.info(
                "[check_mode] edit_data_exchange_customer would update customer ID %s: %s",
                customer_id,
                json.dumps(update_payload, indent=2),
            )
            return type("MockResponse", (), {"id": customer_id})()
        try:
            LOG.info("edit_data_exchange_customer: Updating customer ID: %s", customer_id)
            api_client = self.api.api_client
            method, url, header_params, body, post_params = api_client.param_serialize(
                "PUT",
                "/v1/extranets-b2b-peering/customer/{id}",
                path_params={"id": customer_id},
                header_params={
                    "Authorization": self.bearer_token,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                body=update_payload,
            )
            response_data = api_client.call_api(method, url, header_params, body, post_params)
            response_data.read()
            LOG.info("edit_data_exchange_customer: Successfully updated customer ID: %s", customer_id)
            return response_data
        except ApiException as e:
            api_url = f"{self.api.api_client.configuration.host}/v1/extranets-b2b-peering/customer/{customer_id}"
            self._log_api_error(
                method_name="edit_data_exchange_customer",
                api_url=api_url,
                path_params={"customer_id": customer_id},
                request_body=update_payload,
                exception=e,
            )
            raise e

    def get_data_exchange_service_details(self, service_id: int, type: str = "peering_service") -> dict:
        """
        Get detailed information about a specific Data Exchange service.

        Uses a raw API call to avoid pydantic validation errors on optional fields
        (natPools, servicePrefixes) that the API may return as null.

        Args:
            service_id (int): ID of the service to retrieve
            type (str): Type of service to retrieve (default: "peering_service")

        Returns:
            dict: Service details response
        """
        try:
            LOG.info("get_data_exchange_service_details: Retrieving service details for ID: %s", service_id)
            api_client = self.api.api_client
            method, url, header_params, body, post_params = api_client.param_serialize(
                "GET",
                "/v1/extranets-b2b/{id}/producer",
                path_params={"id": service_id},
                query_params={"type": type},
                header_params={
                    "Authorization": self.bearer_token,
                    "Accept": "application/json",
                },
                body=None,
            )
            response_data = api_client.call_api(method, url, header_params, body, post_params)
            response_data.read()
            LOG.info("get_data_exchange_service_details: Successfully retrieved service details for ID: %s", service_id)
            return json.loads(response_data.data)
        except ApiException as e:
            api_url = f"{self.api.api_client.configuration.host}/v1/extranets-b2b/{service_id}/producer"
            self._log_api_error(
                method_name="get_data_exchange_service_details",
                api_url=api_url,
                path_params={"service_id": service_id},
                query_params={"type": type},
                exception=e,
            )
            raise e

    def edit_data_exchange_service(self, service_id: int, update_payload: dict):
        """
        Edit an existing Data Exchange peering service (e.g., update prefixTags).

        PUT /v1/extranets-b2b-peering/producer/{id}

        Args:
            service_id (int): ID of the service to update
            update_payload (dict): Update payload containing 'id' and 'policy' fields

        Returns:
            RESTResponse or MockResponse in check mode
        """
        if getattr(self, "check_mode", False):
            LOG.info(
                "[check_mode] edit_data_exchange_service would update service ID %s: %s",
                service_id,
                json.dumps(update_payload, indent=2),
            )
            return type("MockResponse", (), {"id": service_id})()
        try:
            LOG.info("edit_data_exchange_service: Updating service ID: %s", service_id)
            api_client = self.api.api_client
            method, url, header_params, body, post_params = api_client.param_serialize(
                "PUT",
                "/v1/extranets-b2b-peering/producer/{id}",
                path_params={"id": service_id},
                header_params={
                    "Authorization": self.bearer_token,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                body=update_payload,
            )
            response_data = api_client.call_api(method, url, header_params, body, post_params)
            response_data.read()
            LOG.info("edit_data_exchange_service: Successfully updated service ID: %s", service_id)
            return response_data
        except ApiException as e:
            api_url = f"{self.api.api_client.configuration.host}/v1/extranets-b2b-peering/producer/{service_id}"
            self._log_api_error(
                method_name="edit_data_exchange_service",
                api_url=api_url,
                path_params={"service_id": service_id},
                request_body=update_payload,
                exception=e,
            )
            raise e

    def match_service_to_customer(self, match_config: dict):
        """
        Match a service to a customer with specific prefix configurations.

        Args:
            match_config (dict): Match configuration containing:
                - id: Customer ID
                - service: Service configuration with prefixes and NAT settings

        Returns:
            dict: Match response with matchId
        """
        if getattr(self, "check_mode", False):
            LOG.info("[check_mode] match_service_to_customer would match: %s", json.dumps(match_config, indent=2))
            return type("MockResponse", (), {"match_id": 0, "timestamp": None})()
        try:
            LOG.info("match_service_to_customer: Matching service to customer")
            response = self.api.v1_extranets_b2b_peering_match_service_to_customer_post(
                authorization=self.bearer_token,
                v1_extranets_b2b_peering_match_service_to_customer_post_request=match_config,
            )
            LOG.info(
                "match_service_to_customer: Successfully matched service to customer with matchId: %s",
                response.match_id,
            )
            return response
        except ApiException as e:
            # Log the actual API endpoint URL and request body for debugging
            api_url = f"{self.api.api_client.configuration.host}/v1/extranets-b2b-peering/match/service-to-customer"
            self._log_api_error(
                method_name="match_service_to_customer", api_url=api_url, request_body=match_config, exception=e
            )
            raise e

    def delete_data_exchange_service(self, service_id: int):
        """
        Delete a Data Exchange service.

        Args:
            service_id (int): ID of the service to delete

        Returns:
            dict: Delete response
        """
        if getattr(self, "check_mode", False):
            LOG.info("[check_mode] delete_data_exchange_service would delete service with ID: %s", service_id)
            return type("MockResponse", (), {})()
        try:
            LOG.info("delete_data_exchange_service: Deleting service with ID: %s", service_id)
            response = self.api.v1_extranets_b2b_id_delete(authorization=self.bearer_token, id=service_id)
            LOG.info("delete_data_exchange_service: Successfully deleted service with ID: %s", service_id)
            return response
        except ApiException as e:
            # Log the actual API endpoint URL for debugging
            api_url = f"{self.api.api_client.configuration.host}/v1/extranets-b2b/{service_id}"
            self._log_api_error(
                method_name="delete_data_exchange_service",
                api_url=api_url,
                path_params={"service_id": service_id},
                exception=e,
            )
            raise e

    def accept_data_exchange_service(self, match_id, acceptance_payload):
        """
        Accept a Data Exchange service invitation.

        Args:
            match_id (int): The match ID to accept
            acceptance_payload (dict): The acceptance configuration payload

        Returns:
            API response object
        """
        try:
            sdk_request = graphiant_sdk.V1ExtranetsB2bPeeringConsumerMatchIdPostRequest(
                id=acceptance_payload.get("id"),
                customer_id=acceptance_payload.get("customerId"),
                site_information=acceptance_payload.get("siteInformation"),
                nat=acceptance_payload.get("nat"),
                policy=acceptance_payload.get("policy"),
                site_to_site_vpn=acceptance_payload.get("siteToSiteVpn"),
                global_object_ops=acceptance_payload.get("globalObjectOps"),
            )
            sdk_serialized = json.dumps(sdk_request.to_dict(), indent=2)
        except Exception as sdk_e:
            if getattr(self, "check_mode", False):
                raise ValidationError(
                    f"accept_data_exchange_service: Payload failed SDK schema validation "
                    f"for match_id={match_id}: {sdk_e}"
                ) from sdk_e
            LOG.error("accept_data_exchange_service: Could not construct SDK model for logging: %s", sdk_e)
            sdk_serialized = None

        if getattr(self, "check_mode", False):
            LOG.info(
                "[check_mode] accept_data_exchange_service would accept match_id=%s: %s",
                match_id,
                (
                    format_config_payload_for_log(json.loads(sdk_serialized))
                    if sdk_serialized is not None
                    else format_config_payload_for_log(acceptance_payload)
                ),
            )
            return type("MockResponse", (), {})()
        try:
            LOG.info("accept_data_exchange_service: Accepting match %s", match_id)
            if sdk_serialized is not None:
                LOG.info(
                    "accept_data_exchange_service: SDK-serialized payload for match %s:\n%s",
                    match_id,
                    format_config_payload_for_log(json.loads(sdk_serialized)),
                )
            # Use the correct method with match_id as path parameter
            response = self.api.v1_extranets_b2b_peering_consumer_match_id_post(
                authorization=self.bearer_token,
                match_id=match_id,  # Use match_id as the path parameter
                v1_extranets_b2b_peering_consumer_match_id_post_request=acceptance_payload,
            )
            LOG.info("accept_data_exchange_service: Successfully accepted match %s", match_id)
            return response
        except ApiException as e:
            api_url = f"{self.api.api_client.configuration.host}/v1/extranets-b2b-peering/consumer/{match_id}"
            self._log_api_error(
                method_name="accept_data_exchange_service",
                api_url=api_url,
                path_params={"match_id": match_id},
                request_body=acceptance_payload,
                exception=e,
            )
            raise e

    def get_ipsec_inside_subnet(self, region_id, lan_segment_id, address_family):
        """
        Get IPSec inside subnet for a specific region and LAN segment.

        Args:
            region_id (int): The region ID
            lan_segment_id (int): The LAN segment ID (VRF)
            address_family (str): Either 'ipv4' or 'ipv6'

        Returns:
            str or None: The inside subnet CIDR, or None if failed
        """
        try:
            LOG.info(
                "get_ipsec_inside_subnet: Getting %s subnet for region %s, LAN segment %s",
                address_family,
                region_id,
                lan_segment_id,
            )
            response = self.api.v1_gateways_ipsec_regions_region_id_vrfs_vrf_id_inside_subnet_get(
                authorization=self.bearer_token,
                region_id=region_id,
                vrf_id=lan_segment_id,
                address_family=address_family,
            )

            if address_family == "ipv4":
                subnet = getattr(response, "ipv4_subnet", None)
            else:  # ipv6
                subnet = getattr(response, "ipv6_subnet", None)

            LOG.info("get_ipsec_inside_subnet: Retrieved %s subnet: %s", address_family, subnet)
            return subnet
        except ApiException as e:
            api_url = (
                f"{self.api.api_client.configuration.host}/v1/gateways/ipsec/regions/"
                f"{region_id}/vrfs/{lan_segment_id}/inside-subnet"
            )
            self._log_api_error(
                method_name="get_ipsec_inside_subnet",
                api_url=api_url,
                query_params={"addressFamily": address_family},
                exception=e,
            )
            return None
        except Exception as e:
            LOG.error("get_ipsec_inside_subnet: Unexpected error: %s", e)
            return None

    def get_preshared_key(self):
        """
        Get a preshared key for IPSec tunnels.

        Returns:
            str or None: The preshared key, or None if failed
        """
        try:
            LOG.info("get_preshared_key: Getting preshared key")
            response = self.api.v1_presharedkey_get(authorization=self.bearer_token)
            psk = getattr(response, "presharedkey", None)
            LOG.info("get_preshared_key: Retrieved preshared key")
            return psk
        except ApiException as e:
            api_url = f"{self.api.api_client.configuration.host}/v1/presharedkey"
            self._log_api_error(method_name="get_preshared_key", api_url=api_url, exception=e)
            return None
        except Exception as e:
            LOG.error("get_preshared_key: Unexpected error: %s", e)
            return None

    def get_gateway_summary(self):
        """
        Get gateway summary information.

        Returns:
            API response object
        """
        try:
            LOG.info("get_gateway_summary: Retrieving gateway summary")
            response = self.api.v1_gateways_summary_get(authorization=self.bearer_token)
            LOG.info("get_gateway_summary: Successfully retrieved gateway summary")
            return response
        except ApiException as e:
            api_url = f"{self.api.api_client.configuration.host}/v1/gateways/summary"
            self._log_api_error(method_name="get_gateway_summary", api_url=api_url, exception=e)
            raise e

    def get_gateway_details(self, gateway_id):
        """
        Get detailed gateway information.

        Args:
            gateway_id (int): The gateway ID

        Returns:
            API response object
        """
        try:
            LOG.info("get_gateway_details: Retrieving details for gateway %s", gateway_id)
            response = self.api.v1_gateways_id_details_get(authorization=self.bearer_token, id=gateway_id)
            LOG.info("get_gateway_details: Successfully retrieved details for gateway %s", gateway_id)
            return response
        except ApiException as e:
            api_url = f"{self.api.api_client.configuration.host}/v1/gateways/{gateway_id}/details"
            self._log_api_error(
                method_name="get_gateway_details", api_url=api_url, path_params={"gateway_id": gateway_id}, exception=e
            )
            raise e

    def get_service_health(self, service_id, is_provider=False):
        """
        Get service health monitoring information.

        Args:
            service_id (int): The service ID
            is_provider (bool): Whether this is a provider view

        Returns:
            API response object
        """
        try:
            LOG.info("get_service_health: Retrieving health for service %s", service_id)
            # Create the proper request object
            health_request = graphiant_sdk.V1ExtranetB2bMonitoringPeeringServiceServiceHealthPostRequest(
                id=service_id, is_provider=is_provider
            )
            response = self.api.v1_extranet_b2b_monitoring_peering_service_service_health_post(
                authorization=self.bearer_token,
                v1_extranet_b2b_monitoring_peering_service_service_health_post_request=health_request,
            )
            LOG.info("get_service_health: Successfully retrieved health for service %s", service_id)
            return response
        except ApiException as e:
            api_url = (
                f"{self.api.api_client.configuration.host}/"
                f"v1/extranet-b2b-monitoring/peering-service/service-health"
            )
            self._log_api_error(
                method_name="get_service_health", api_url=api_url, path_params={"service_id": service_id}, exception=e
            )
            raise e

    def get_regions(self):
        """
        Get all available regions from the API.

        Returns:
            list: List of region objects with id and name
        """
        try:
            LOG.info("get_regions: Retrieving regions from API")
            response = self.api.v1_regions_get(authorization=self.bearer_token)
            LOG.info("get_regions: Successfully retrieved %s regions", len(response.regions))
            return response.regions
        except ApiException as e:
            api_url = f"{self.api.api_client.configuration.host}/v1/regions"
            self._log_api_error(method_name="get_regions", api_url=api_url, exception=e)
            return None

    def get_region_id_by_name(self, region_name):
        """
        Get region ID by region name using the API.

        Args:
            region_name (str): Region name to look up

        Returns:
            int: Region ID if found, None otherwise
        """
        try:
            regions = self.get_regions()
            if not regions:
                LOG.warning("get_region_id_by_name: No regions available")
                return None

            for region in regions:
                if region.name == region_name:
                    LOG.info("get_region_id_by_name: Found region '%s' with ID %s", region_name, region.id)
                    return region.id

            # Log available regions for debugging
            available_regions = [region.name for region in regions]
            LOG.warning(
                "get_region_id_by_name: Region '%s' not found. Available regions: %s", region_name, available_regions
            )
            return None
        except Exception as e:
            LOG.error("get_region_id_by_name: Failed to get region ID for '%s': %s", region_name, e)
            return None

    def get_global_ipsec_profiles(self):
        """
        Get all global IPsec (VPN) profiles from the portal.

        Returns:
            dict: Dictionary mapping VPN profile names to their configurations, or empty dict if failed
        """
        try:
            LOG.info("get_global_ipsec_profiles: Retrieving all global IPsec profiles")
            response = self.api.v1_global_ipsec_profile_get(authorization=self.bearer_token)
            profiles = {}
            ipsec_profiles = None
            if hasattr(response, "ipsec_profiles"):
                ipsec_profiles = response.ipsec_profiles

            if ipsec_profiles:
                for profile_entry in ipsec_profiles:
                    profile_name = None
                    if hasattr(profile_entry, "ipsec_profile_name"):
                        profile_name = profile_entry.ipsec_profile_name
                    if profile_name:
                        profiles[profile_name] = profile_entry
                        LOG.debug("get_global_ipsec_profiles: Found VPN profile '%s'", profile_name)

                LOG.info("get_global_ipsec_profiles: Successfully retrieved %s VPN profiles", len(profiles))
                return profiles
            else:
                LOG.info("get_global_ipsec_profiles: No VPN profiles found in response")
                return {}
        except ApiException as e:
            api_url = f"{self.api.api_client.configuration.host}/v1/global/ipsec-profile"
            self._log_api_error(method_name="get_global_ipsec_profiles", api_url=api_url, exception=e)
            return {}
        except Exception as e:
            LOG.error("get_global_ipsec_profiles: Unexpected error: %s", e)
            return {}

    def get_device_info(self, device_id: int):
        """
        Get device information.

        Args:
            device_id (int): The device ID

        Returns:
            API response object
        """
        try:
            LOG.info("get_device_info: Retrieving information for device ID %s", device_id)
            response = self.api.v1_devices_device_id_get(authorization=self.bearer_token, device_id=device_id)
            LOG.info("get_device_info: Successfully retrieved information for device ID %s", device_id)
            return response
        except ApiException as e:
            api_url = f"{self.api.api_client.configuration.host}/v1/devices/{device_id}"
            self._log_api_error(
                method_name="get_device_info", api_url=api_url, path_params={"device_id": device_id}, exception=e
            )
            return None

    def get_macsec_status(self, device_id: int):
        """
        Get MACsec monitoring status for a device.

        GET /v2/monitoring/macsec/{device_id}/status

        Args:
            device_id (int): The device ID

        Returns:
            dict or SDK response object with macsecStatuses list
        """
        api_url = f"{self.api.api_client.configuration.host}/v2/monitoring/macsec/{device_id}/status"
        try:
            LOG.info("get_macsec_status: Retrieving MACsec status for device ID %s", device_id)
            method = getattr(self.api, "v2_monitoring_macsec_device_id_status_get", None)
            if callable(method):
                response = method(authorization=self.bearer_token, device_id=device_id)
                LOG.info("get_macsec_status: Successfully retrieved MACsec status for device ID %s", device_id)
                return response
            response_data = self.api.api_client.call_api(
                resource_path="/v2/monitoring/macsec/{device_id}/status",
                method="GET",
                path_params={"device_id": device_id},
                header_params={"Authorization": self.bearer_token},
                response_types_map={200: "dict"},
                _request_timeout=None,
            )
            LOG.info("get_macsec_status: Successfully retrieved MACsec status for device ID %s", device_id)
            return response_data
        except ApiException as e:
            self._log_api_error(
                method_name="get_macsec_status",
                api_url=api_url,
                path_params={"device_id": device_id},
                exception=e,
            )
            raise APIError(
                f"get_macsec_status: Failed to retrieve MACsec status for device_id={device_id}. Exception: {e}"
            )
