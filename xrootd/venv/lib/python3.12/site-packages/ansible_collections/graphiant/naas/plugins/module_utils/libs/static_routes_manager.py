"""
Static Routes Manager for Graphiant Playbooks.

This module handles static routes configuration management for Graphiant Playbooks.

Routes are configured under:
  edge.segments.<segment>.staticRoutes

Idempotency: configure uses get_device_info to compare intended static routes to the
device's current state (per segment + prefix). If the desired state already matches,
it skips the config push for that device.

Deconfigure deletes only the prefixes listed (per segment)
and skips pushing when those routes are already absent.
"""

import json
from typing import Any, Dict, Iterator, List, Optional, Tuple

from .base_manager import BaseManager
from .device_config_common import new_apply_result
from .logger import setup_logger
from .exceptions import ConfigurationError, DeviceNotFoundError

LOG = setup_logger()


class StaticRoutesManager(BaseManager):
    """
    Manage static routes for a given device via raw device-config payload generation.
    """

    def _payload_differs_from_existing(self, desired_payload: Dict[str, Any], device_info_dict: Any) -> bool:
        """
        Return True if the desired payload would change current device state.

        This checks only the segments/prefixes present in the desired payload.
        """
        desired_edge = (desired_payload or {}).get("edge") or {}
        desired_segments = desired_edge.get("segments") or {}
        if not desired_segments:
            return False

        # Device info may be nested under 'device' or may already be the device dict.
        # Some API calls return a bare list of segments; handle that too.
        device_dict = device_info_dict.get("device") if isinstance(device_info_dict, dict) else None
        if device_dict is None:
            if isinstance(device_info_dict, dict):
                device_dict = device_info_dict
            elif isinstance(device_info_dict, list):
                # Treat list as a segments list
                device_dict = {"segments": device_info_dict}
            else:
                device_dict = {}

        for seg_name, seg_cfg in desired_segments.items():
            desired_static_routes = (seg_cfg or {}).get("staticRoutes") or {}
            if not desired_static_routes:
                continue

            existing_static_routes = self._get_existing_static_routes_for_segment(device_dict, seg_name) or {}

            for prefix, desired_entry in desired_static_routes.items():
                desired_route = (desired_entry or {}).get("route")
                existing_entry = (
                    existing_static_routes.get(prefix) if isinstance(existing_static_routes, dict) else None
                )
                existing_route = (existing_entry or {}).get("route") if isinstance(existing_entry, dict) else None

                # Deconfigure semantics: route=null should be a no-op if missing/already-null
                if desired_route is None:
                    if existing_route is None:
                        continue
                    return True

                # Configure semantics: compare normalized route objects
                if self._normalize_route(desired_route) != self._normalize_route(existing_route):
                    return True

        return False

    @staticmethod
    def _get_existing_static_routes_for_segment(device_dict: Dict[str, Any], seg_name: str) -> Optional[Dict[str, Any]]:
        """
        Extract existing staticRoutes map for a specific segment from the device GET response dict.
        """
        if not isinstance(device_dict, dict):
            return None

        edge = device_dict.get("edge") or {}
        segments = None
        if isinstance(edge, dict):
            segments = edge.get("segments")
        if segments is None:
            segments = device_dict.get("segments")
        if segments is None:
            segments = device_dict.get("lanSegments")

        seg_obj = None
        if isinstance(segments, dict):
            # Common case: segments is a dict keyed by segment name
            seg_obj = segments.get(seg_name)
            if seg_obj is None:
                # Fallback: dict keyed by IDs; try to match by name fields in values
                for seg_value in segments.values():
                    if not isinstance(seg_value, dict):
                        continue
                    candidate = (
                        seg_value.get("name")
                        or seg_value.get("lanSegment")
                        or seg_value.get("lan_segment")
                        or seg_value.get("segment")
                    )
                    if candidate == seg_name:
                        seg_obj = seg_value
                        break
        elif isinstance(segments, list):
            for item in segments:
                if not isinstance(item, dict):
                    continue
                if (
                    item.get("name") == seg_name
                    or item.get("lanSegment") == seg_name
                    or item.get("lan_segment") == seg_name
                    or item.get("segment") == seg_name
                ):
                    seg_obj = item
                    break

        if not isinstance(seg_obj, dict):
            return {}

        static_routes = seg_obj.get("staticRoutes")
        if static_routes is None:
            static_routes = seg_obj.get("static_routes")

        if static_routes is None:
            return {}
        # Newer/alternate shapes: some APIs return staticRoutes as a list of routes
        # with fields like { prefix, administrativeDistance, nextHops:[{outgoingInterface,...}] }.
        if isinstance(static_routes, list):
            out: Dict[str, Any] = {}
            for r in static_routes:
                if not isinstance(r, dict):
                    continue
                prefix = r.get("prefix") or r.get("destinationPrefix")
                if not prefix:
                    continue
                route_obj: Dict[str, Any] = {"destinationPrefix": prefix}
                if r.get("description") is not None:
                    route_obj["description"] = r.get("description")
                if r.get("administrativeDistance") is not None:
                    # API may return int here; normalizer handles int or dict
                    route_obj["administrativeDistance"] = r.get("administrativeDistance")

                nhs = r.get("nextHops") or []
                norm_nhs: List[Dict[str, Any]] = []
                if isinstance(nhs, list):
                    for nh in nhs:
                        if not isinstance(nh, dict):
                            continue
                        nh_obj: Dict[str, Any] = {}
                        if nh.get("outgoingInterface") is not None:
                            nh_obj["outgoingInterface"] = nh.get("outgoingInterface")
                        if nh.get("nextHopAddress") is not None:
                            nh_obj["nextHopAddress"] = nh.get("nextHopAddress")
                        if nh_obj:
                            norm_nhs.append(nh_obj)
                route_obj["nextHops"] = norm_nhs

                out[prefix] = {"route": route_obj}
            return out

        if isinstance(static_routes, dict):
            return static_routes
        return {}

    @staticmethod
    def _normalize_route(route: Any) -> Optional[Dict[str, Any]]:
        """
        Normalize a route object for stable comparisons.

        - Ignores unknown keys
        - Normalizes key casing
        - Normalizes administrativeDistance.distance to string
        - Sorts nextHops (order-insensitive compare)
        """
        if route is None:
            return None
        if not isinstance(route, dict):
            return None

        dest = route.get("destinationPrefix") or route.get("destination_prefix") or route.get("prefix")

        # Administrative distance
        ad = route.get("administrativeDistance") or route.get("administrative_distance") or {}
        dist = None
        if isinstance(ad, dict):
            dist = ad.get("distance")
        elif isinstance(ad, (int, float, str)):
            dist = ad
        if dist is not None:
            dist = str(dist)

        # Next hops
        nhs = route.get("nextHops") or route.get("next_hops") or []
        if nhs is None:
            nhs = []
        norm_nhs: List[Dict[str, Any]] = []
        if isinstance(nhs, list):
            for nh in nhs:
                if not isinstance(nh, dict):
                    continue
                norm_nh: Dict[str, Any] = {}
                # Canonicalize "outgoing interface" regardless of how it is expressed
                outgoing = (
                    nh.get("outgoingInterface")
                    or nh.get("thirdPartyIpsecTunnel")
                    or nh.get("third_party_ipsec_tunnel")
                    or nh.get("circuit")
                    or nh.get("interface")
                )
                if outgoing is not None:
                    norm_nh["outgoingInterface"] = outgoing

                if nh.get("nextHopAddress") is not None or nh.get("next_hop_address") is not None:
                    norm_nh["nextHopAddress"] = nh.get("nextHopAddress") or nh.get("next_hop_address")
                if norm_nh:
                    norm_nhs.append(norm_nh)

        norm_nhs = sorted(norm_nhs, key=lambda x: json.dumps(x, sort_keys=True))

        out: Dict[str, Any] = {"destinationPrefix": dest, "nextHops": norm_nhs}
        if route.get("description") is not None:
            out["description"] = route.get("description")
        if dist is not None:
            out["administrativeDistance"] = {"distance": dist}
        return out

    @staticmethod
    def _build_next_hop(nh: Any) -> Dict[str, Any]:
        if not isinstance(nh, dict):
            raise ConfigurationError("Each next_hop must be a dict")

        # YAML schema: camelCase keys only
        if nh.get("thirdPartyIpsecTunnel") is not None:
            return {"thirdPartyIpsecTunnel": nh.get("thirdPartyIpsecTunnel")}

        if nh.get("circuit") is not None:
            return {"circuit": nh["circuit"]}

        if nh.get("interface") is not None:
            hop: Dict[str, Any] = {"interface": nh["interface"]}
            if nh.get("nextHopAddress") is not None:
                hop["nextHopAddress"] = nh.get("nextHopAddress")
            return hop

        if nh.get("nextHopAddress") is not None:
            return {"nextHopAddress": nh.get("nextHopAddress")}

        raise ConfigurationError(
            "Invalid nextHop: expected one of thirdPartyIpsecTunnel, circuit, interface, nextHopAddress"
        )

    @staticmethod
    def _build_static_routes(static_routes_cfg: Any, operation: str) -> Dict[str, Any]:
        """
        Convert a list (or dict) of static route configs into the API payload shape.
        """
        routes: List[Dict[str, Any]]
        if static_routes_cfg is None:
            routes = []
        elif isinstance(static_routes_cfg, list):
            routes = static_routes_cfg
        elif isinstance(static_routes_cfg, dict):
            # Allow dict keyed by prefix -> route_config
            routes = []
            for pfx, rc in static_routes_cfg.items():
                if rc is None:
                    rc = {}
                if not isinstance(rc, dict):
                    raise ConfigurationError("static_routes dict values must be dicts")
                merged = {"destinationPrefix": pfx}
                merged.update(rc)
                routes.append(merged)
        else:
            raise ConfigurationError("'staticRoutes' must be a list or dict")

        static_routes_payload: Dict[str, Any] = {}
        for r in routes:
            if not isinstance(r, dict):
                raise ConfigurationError("Each static route must be a dict")

            prefix = r.get("destinationPrefix")
            if not prefix:
                raise ConfigurationError("Static route missing 'destinationPrefix'")

            if operation == "deconfigure":
                static_routes_payload[prefix] = {"route": None}
                continue

            route_obj: Dict[str, Any] = {"destinationPrefix": prefix}

            if r.get("description") is not None:
                route_obj["description"] = r.get("description")

            # Allow either an int distance (recommended in YAML) or API-shaped dict
            ad_val = r.get("administrativeDistance")
            if ad_val is not None:
                if isinstance(ad_val, dict):
                    # Accept: administrativeDistance: { distance: 10 }
                    dist = ad_val.get("distance")
                    if dist is None:
                        raise ConfigurationError(f"Route {prefix}: 'administrativeDistance' missing 'distance'")
                    route_obj["administrativeDistance"] = {"distance": dist}
                else:
                    # Accept: administrativeDistance: 10
                    route_obj["administrativeDistance"] = {"distance": ad_val}

            next_hops_cfg = r.get("nextHops") or []
            if next_hops_cfg is None:
                next_hops_cfg = []
            if not isinstance(next_hops_cfg, list):
                raise ConfigurationError(f"Route {prefix}: 'nextHops' must be a list")

            route_obj["nextHops"] = [StaticRoutesManager._build_next_hop(nh) for nh in next_hops_cfg]

            static_routes_payload[prefix] = {"route": route_obj}

        return static_routes_payload

    def _iter_device_payloads(self, config_yaml_file: str, operation: str) -> Iterator[Tuple[int, str, Dict[str, Any]]]:
        """
        Iterate through the YAML and yield per-device payloads.

        Yields:
            (device_id, device_name, payload)
        """
        if operation not in ("configure", "deconfigure"):
            raise ConfigurationError(f"Unsupported operation '{operation}'")

        cfg = self.render_config_file(config_yaml_file) or {}
        device_list = cfg.get("staticRoutes") or []
        if not device_list:
            LOG.info("[static-routes] No 'staticRoutes' section found in %s", config_yaml_file)
            return

        for device_entry in device_list:
            if not isinstance(device_entry, dict):
                raise ConfigurationError("Each entry in 'staticRoutes' must be a dict keyed by device name")

            for device_name, device_cfg in device_entry.items():
                if not isinstance(device_cfg, dict):
                    raise ConfigurationError(f"Device '{device_name}' config must be a dict")

                device_id = self.gsdk.get_device_id(device_name)
                if device_id is None:
                    raise DeviceNotFoundError(
                        f"Device '{device_name}' is not found in the current enterprise: "
                        f"{self.gsdk.enterprise_info['company_name']}. Please check device name."
                    )

                segments_cfg = device_cfg.get("segments") or device_cfg.get("lanSegments") or []
                if not isinstance(segments_cfg, list):
                    raise ConfigurationError(f"Device '{device_name}': 'segments' must be a list")

                segments_payload: Dict[str, Any] = {}
                for seg in segments_cfg:
                    if not isinstance(seg, dict):
                        raise ConfigurationError(f"Device '{device_name}': each segment must be a dict")

                    seg_name = seg.get("lanSegment") or seg.get("name")
                    if not seg_name:
                        raise ConfigurationError(f"Device '{device_name}': segment missing 'lanSegment'")

                    static_routes_cfg = seg.get("staticRoutes") or []
                    static_routes_payload = StaticRoutesManager._build_static_routes(
                        static_routes_cfg, operation=operation
                    )
                    segments_payload[seg_name] = {"staticRoutes": static_routes_payload}

                payload: Dict[str, Any] = {"edge": {"segments": segments_payload}}

                yield device_id, device_name, payload

    def apply_static_routes(self, config_yaml_file: str, operation: str) -> dict:
        result = new_apply_result()
        output_config: Dict[int, Dict[str, Any]] = {}

        for device_id, device_name, payload in self._iter_device_payloads(config_yaml_file, operation=operation):
            gcs_device_info = self.gsdk.get_device_info(device_id)
            if gcs_device_info is None:
                raise ConfigurationError(f"Failed to retrieve device info for device_id={device_id}")

            try:
                device_info_dict = gcs_device_info.to_dict()
            except Exception:
                device_info_dict = gcs_device_info
            if not self._payload_differs_from_existing(payload, device_info_dict):
                LOG.info("[static-routes] ✓ No changes needed for %s (ID: %s), skipping", device_name, device_id)
                result["skipped_devices"].append(device_name)
                continue

            device_dict = device_info_dict.get("device") if isinstance(device_info_dict, dict) else None
            if device_dict is None:
                device_dict = device_info_dict if isinstance(device_info_dict, dict) else {}
            desired_segments = payload.get("edge", {}).get("segments", {})
            before_segments: Dict[str, Any] = {}
            for seg_name in desired_segments:
                before_segments[seg_name] = {
                    "staticRoutes": self._get_existing_static_routes_for_segment(device_dict, seg_name) or {}
                }
            result["diff_plan"].append(
                {
                    "device": device_name,
                    "branch": "edge.segments",
                    "before": {"segments": before_segments},
                    "after": {"segments": desired_segments},
                }
            )

            output_config[device_id] = {"device_id": device_id, "payload": payload}
            result["configured_devices"].append(device_name)

        if not output_config:
            return result

        LOG.info("[static-routes] Pushing payload for %d device(s)...", len(output_config))
        self.execute_concurrent_tasks(self.gsdk.put_device_config_raw, output_config)

        result["changed"] = True
        return result

    def configure(self, config_yaml_file: str) -> dict:
        return self.apply_static_routes(config_yaml_file, operation="configure")

    def deconfigure(self, config_yaml_file: str) -> dict:
        return self.apply_static_routes(config_yaml_file, operation="deconfigure")
