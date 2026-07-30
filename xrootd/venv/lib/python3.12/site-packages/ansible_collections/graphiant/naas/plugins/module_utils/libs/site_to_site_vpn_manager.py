"""
Site-to-Site VPN Manager for Graphiant Playbooks.

This module handles Site-to-Site VPN configuration management for Graphiant Playbooks.

Idempotency: create uses get_device_info (device.ipsecTunnels) to get existing S2S VPN;
skips push when intended config matches existing. Delete uses get_device_info to only delete
VPNs that exist on the device; skips push when none to delete (second delete is no-op).
"""

from typing import Any, Dict, List, Optional
from .base_manager import BaseManager
from .logger import setup_logger
from .exceptions import ConfigurationError, DeviceNotFoundError

LOG = setup_logger()


class SiteToSiteVpnManager(BaseManager):
    """
    Manages Site-to-Site VPN configurations.

    Handles the creation and deletion of Site-to-Site VPN connections,
    supporting both static and BGP routing.
    """

    @staticmethod
    def _drop_secrets(o: Any) -> Any:
        """Recursively remove presharedKey and md5Password from a dict/list structure."""
        if o is None:
            return None
        if isinstance(o, dict):
            return {
                k: SiteToSiteVpnManager._drop_secrets(v)
                for k, v in o.items()
                if k not in ("presharedKey", "md5Password")
            }
        if isinstance(o, list):
            return [SiteToSiteVpnManager._drop_secrets(x) for x in o]
        return o

    @staticmethod
    def _get_existing_site_to_site_vpn(gcs_device_info) -> Dict[str, Any]:
        """
        Get existing Site-to-Site VPN (ipsecTunnels) from device info.

        Same pattern as interfaces/VRRP: takes device info object from gsdk.get_device_info().
        ipsecTunnels is the S2S VPN list on the device.

        Args:
            gcs_device_info: Device info object from gsdk.get_device_info()

        Returns:
            dict: VPN name -> config (camelCase dict). Empty if none or on error.
        """
        if not hasattr(gcs_device_info, "device"):
            LOG.debug("_get_existing_site_to_site_vpn: No 'device' attribute in gcs_device_info")
            return {}
        device = gcs_device_info.device
        tunnels = getattr(device, "ipsec_tunnels", None) or getattr(device, "ipsecTunnels", None)
        if not tunnels:
            return {}
        result = {}
        for t in tunnels:
            name = getattr(t, "name", None)
            if not name:
                continue
            if hasattr(t, "model_dump"):
                d = t.model_dump(by_alias=True, exclude_none=True)
            elif hasattr(t, "to_dict") and callable(t.to_dict):
                d = t.to_dict()
            else:
                d = dict(t) if isinstance(t, dict) else {}
            result[str(name)] = d
        return result

    def configure(self, config_yaml_file: str) -> Dict[str, Any]:
        """
        Create Site-to-Site VPN (implements abstract method from BaseManager).

        Args:
            config_yaml_file: Path to the YAML file containing Site-to-Site VPN configurations
        """
        return self.create_site_to_site_vpn(config_yaml_file)

    def deconfigure(self, config_yaml_file: str) -> Dict[str, Any]:
        """
        Delete Site-to-Site VPN (implements abstract method from BaseManager).

        Args:
            config_yaml_file: Path to the YAML file containing Site-to-Site VPN configurations
        """
        return self.delete_site_to_site_vpn(config_yaml_file)

    def _inject_vault_secrets(
        self, vpn_config: Dict[str, Any], vault_keys: Dict[str, Any], vault_md5_passwords: Dict[str, Any]
    ) -> None:
        """
        Inject presharedKey and md5Password using unified precedence:
        YAML non-null wins; vault fills null/absent; error (presharedKey) or None (md5Password) if both missing.
        Lookup key = VPN name field.
        """
        vpn_name = vpn_config.get("name")
        if not vpn_name:
            return
        # presharedKey: YAML wins if non-null, else vault, else error (required)
        if vpn_config.get("presharedKey") is None:
            vault_psk = vault_keys.get(vpn_name)
            if vault_psk:
                vpn_config["presharedKey"] = vault_psk
                LOG.debug("Injected presharedKey for VPN '%s' from vault", vpn_name)
            else:
                raise ConfigurationError(
                    f"presharedKey is required but missing for VPN '{vpn_name}'. "
                    "Set presharedKey in the YAML config or pass it via vault_site_to_site_vpn_keys "
                    "(see configs/vault_secrets.yml.example)."
                )
        else:
            LOG.debug("Using presharedKey from YAML config for VPN '%s'", vpn_name)
        # BGP md5Password: YAML wins if non-null, else vault, else None (optional)
        routing = vpn_config.get("routing")
        if isinstance(routing, dict) and isinstance(routing.get("bgp"), dict):
            bgp = routing["bgp"]
            if bgp.get("md5Password") is None:
                vault_md5 = vault_md5_passwords.get(vpn_name)
                bgp["md5Password"] = {"md5_password": str(vault_md5).strip()} if vault_md5 else None
                if vault_md5:
                    LOG.debug("Injected md5Password for VPN '%s' from vault", vpn_name)
            else:
                LOG.debug("Using md5Password from YAML config for VPN '%s'", vpn_name)

    def _normalize_bgp_md5_password(self, vpn_config: Dict[str, Any]) -> None:
        """
        Normalize BGP md5Password to the ManaV2NullableMd5Password dict form.

        Accepts plain string or dict forms and normalizes to {"md5_password": value}
        so the SDK model validates correctly on PUT /v1/devices/{device_id}/config.
        """
        routing = vpn_config.get("routing")
        if not isinstance(routing, dict) or "bgp" not in routing:
            return
        bgp = routing["bgp"]
        if not isinstance(bgp, dict):
            return
        md5_val = bgp.get("md5Password")
        if md5_val is None:
            return
        if isinstance(md5_val, str):
            bgp["md5Password"] = {"md5_password": md5_val}
        elif isinstance(md5_val, dict):
            # Normalize camelCase key to snake_case expected by ManaV2NullableMd5Password
            plain = md5_val.get("md5_password") or md5_val.get("md5Password")
            bgp["md5Password"] = {"md5_password": plain}

    def _normalize_policy_field(self, val: Any) -> Any:
        """Ensure policy is API shape: { policy: str or None }. Accepts string or dict."""
        if val is None:
            return {"policy": None}
        if isinstance(val, str):
            return {"policy": val}
        if isinstance(val, dict):
            if "policy" in val:
                return val
            return {"policy": val.get("policy")}
        return {"policy": None}

    def _normalize_bgp_address_families_for_api(self, vpn_config: Dict[str, Any]) -> None:
        """
        Normalize BGP addressFamilies for API: wrap in 'family' and ensure
        inboundPolicy/outboundPolicy are { policy: str or None }.
        Also set inboundFilter/outboundFilter from the same policy so the device
        shows "Inbound Filters" / "Outbound Filters" (Graphiant UI terminology).
        """
        routing = vpn_config.get("routing") or vpn_config.get("routingPolicy")
        if not isinstance(routing, dict) or "bgp" not in routing:
            return
        bgp = routing["bgp"]
        if not isinstance(bgp, dict):
            return
        af = bgp.get("addressFamilies")
        if not isinstance(af, dict):
            return
        normalized = {}
        for af_name, af_val in af.items():
            if not isinstance(af_val, dict):
                normalized[af_name] = af_val
                continue
            if "family" in af_val:
                family = af_val["family"]
            else:
                family = dict(af_val)
            if not isinstance(family, dict):
                normalized[af_name] = {"family": family}
                continue
            for key in ("inboundPolicy", "outboundPolicy"):
                if key in family:
                    family[key] = self._normalize_policy_field(family[key])
            # Mirror policy to filter keys so device/API "Inbound Filters"/"Outbound Filters" are set
            for policy_key, filter_key in (("inboundPolicy", "inboundFilter"), ("outboundPolicy", "outboundFilter")):
                if policy_key in family:
                    policy_val = family[policy_key]
                    if isinstance(policy_val, dict) and "policy" in policy_val:
                        family[filter_key] = {"policy": policy_val["policy"]}
                    else:
                        family[filter_key] = {"policy": None}
            if "family" in af_val:
                normalized[af_name] = af_val
            else:
                normalized[af_name] = {"family": family}
        bgp["addressFamilies"] = normalized

    def create_site_to_site_vpn(
        self,
        vpn_config_file: str,
        vault_site_to_site_vpn_keys: Optional[Dict[str, Any]] = None,
        vault_bgp_md5_passwords: Optional[Dict[str, Any]] = None,
    ) -> dict:
        """
        Create Site-to-Site VPN for multiple devices concurrently.

        Args:
            vpn_config_file: Path to the YAML file containing Site-to-Site VPN configurations.
            vault_site_to_site_vpn_keys: Dict of VPN name -> preshared key (pass from Ansible
                Vault; never written to disk).
            vault_bgp_md5_passwords: Dict of VPN name -> BGP MD5 password (pass from Ansible
                Vault; never written to disk).

        Returns:
            dict: Result with 'changed' status and list of created devices

        Raises:
            ConfigurationError: If configuration processing fails
            DeviceNotFoundError: If any device cannot be found
        """
        result: Dict[str, Any] = {"changed": False, "created_devices": []}

        try:
            vault_keys = (vault_site_to_site_vpn_keys if vault_site_to_site_vpn_keys is not None else {}) or {}
            vault_md5 = (vault_bgp_md5_passwords if vault_bgp_md5_passwords is not None else {}) or {}
            if not isinstance(vault_keys, dict):
                vault_keys = {}
            if not isinstance(vault_md5, dict):
                vault_md5 = {}

            # Load Site-to-Site VPN configurations
            vpn_config_data = self.render_config_file(vpn_config_file)
            output_config = {}
            device_name_by_id: Dict[int, str] = {}

            # Config format: siteToSiteVpn is a list of { device_name: [ vpn_config, ... ] }
            site_to_site_vpn_list = vpn_config_data.get("siteToSiteVpn", [])
            if not site_to_site_vpn_list:
                LOG.warning("No siteToSiteVpn configuration found in %s", vpn_config_file)
                return result

            for device_entry in site_to_site_vpn_list:
                if not isinstance(device_entry, dict):
                    LOG.warning("Skipping invalid device entry (expected dict): %s", type(device_entry))
                    continue
                for device_name, vpn_configs in device_entry.items():
                    try:
                        device_id = self.gsdk.get_device_id(device_name)
                        if device_id is None:
                            raise DeviceNotFoundError(
                                f"Device '{device_name}' is not found in the current enterprise: "
                                f"{self.gsdk.enterprise_info['company_name']}. "
                                "Please check device name and enterprise credentials."
                            )

                        device_name_by_id[device_id] = device_name
                        if device_id not in output_config:
                            output_config[device_id] = {"device_id": device_id, "edge": {"siteToSiteVpn": {}}}

                        LOG.info("[create] Processing device: %s (ID: %s)", device_name, device_id)

                        if not isinstance(vpn_configs, list):
                            vpn_configs = [vpn_configs]

                        for vpn_config in vpn_configs:
                            vpn_name = vpn_config.get("name")
                            if not vpn_name:
                                LOG.warning("Skipping VPN config - missing 'name' field")
                                continue

                            LOG.info("Processing Site-to-Site VPN: %s", vpn_name)

                            # Build API payload: inject vault, normalize BGP md5 + addressFamilies (family + policy)
                            inner = dict(vpn_config)
                            inner.setdefault("name", vpn_name)
                            self._inject_vault_secrets(inner, vault_keys, vault_md5)
                            self._normalize_bgp_md5_password(inner)
                            self._normalize_bgp_address_families_for_api(inner)
                            output_config[device_id]["edge"]["siteToSiteVpn"][vpn_name] = {"siteToSiteVpn": inner}
                            LOG.info(" ✓ Added Site-to-Site VPN: %s", vpn_name)

                    except DeviceNotFoundError:
                        raise
                    except Exception as e:
                        LOG.error("Error creating Site-to-Site VPN for device %s: %s", device_name, str(e))
                        raise ConfigurationError(f"Create failed for {device_name}: {str(e)}") from e

            # Idempotency: get device info (same as interfaces/VRRP), compare intended vs existing ipsecTunnels
            configs_to_push = {}
            diff_plan: List[Dict[str, Any]] = []
            if output_config:

                def _for_compare(cfg: Dict[str, Any], from_intended: bool) -> Dict[str, Any]:
                    out = dict(cfg)
                    if from_intended:
                        # API has top-level bgp and static; intended has routing.bgp and routing.static
                        routing = out.get("routing") or out.get("routingPolicy")
                        if isinstance(routing, dict):
                            if "bgp" in routing and "bgp" not in out:
                                out["bgp"] = routing["bgp"]
                            if "static" in routing and "static" not in out:
                                out["static"] = routing["static"]
                            out.pop("routing", None)
                            out.pop("routingPolicy", None)

                    result = SiteToSiteVpnManager._drop_secrets(out)
                    if (
                        not from_intended
                        and isinstance(result, dict)
                        and "bgp" in result
                        and isinstance(result["bgp"], dict)
                    ):
                        # API returns bgp.addressFamilies as list; intended uses dict with 'family'
                        # wrapper. Normalize existing.
                        af = result["bgp"].get("addressFamilies")
                        if isinstance(af, list):
                            by_name = {}
                            for item in af:
                                if isinstance(item, dict) and "addressFamily" in item:
                                    by_name[item["addressFamily"]] = item
                                else:
                                    by_name[str(len(by_name))] = item
                            result = dict(result)
                            result["bgp"] = dict(result["bgp"])
                            result["bgp"]["addressFamilies"] = by_name
                        # Ensure each address family has 'family' wrapper and policy as { policy }
                        # for comparison with intended.
                        af = result["bgp"].get("addressFamilies")
                        if isinstance(af, dict):
                            for k, v in list(af.items()):
                                if isinstance(v, dict) and "family" not in v:
                                    af[k] = {"family": v}
                                elif isinstance(v, dict) and "family" in v:
                                    fam = v["family"]
                                    if isinstance(fam, dict):
                                        for pk in ("inboundPolicy", "outboundPolicy"):
                                            if pk in fam and isinstance(fam[pk], str):
                                                fam[pk] = {"policy": fam[pk]}
                                        # Mirror filter <-> policy for comparison (API may return either naming)
                                        for fk, pk in (
                                            ("inboundFilter", "inboundPolicy"),
                                            ("outboundFilter", "outboundPolicy"),
                                        ):
                                            if fk in fam and isinstance(fam[fk], dict) and pk not in fam:
                                                fam[pk] = {"policy": fam[fk].get("policy")}
                                            elif pk in fam and isinstance(fam[pk], dict) and fk not in fam:
                                                fam[fk] = {"policy": fam[pk].get("policy")}
                    return result

                def _intended_matches_existing(
                    intended_compare: Dict[str, Any], existing_compare: Dict[str, Any]
                ) -> bool:
                    """True if every intended VPN is present and keys we set match existing.

                    Extra keys on the device are ignored.
                    """
                    for name, i_cfg in intended_compare.items():
                        if name not in existing_compare:
                            return False
                        if not _subset_equal(i_cfg, existing_compare[name]):
                            return False
                    return True

                def _subset_equal(intended: Any, existing: Any) -> bool:
                    """True if intended equals existing for all keys in intended; existing may have extra keys."""
                    if intended is None:
                        return existing is None
                    if not isinstance(intended, dict):
                        return intended == existing
                    if not isinstance(existing, dict):
                        return False
                    for k, v in intended.items():
                        if k not in existing:
                            return False
                        if not _subset_equal(v, existing[k]):
                            return False
                    return True

                for device_id, pl in output_config.items():
                    gcs_device_info = self.gsdk.get_device_info(device_id)
                    edge = pl.get("edge") or {}
                    intended_s2s_raw = edge.get("siteToSiteVpn") or edge.get("site_to_site_vpn") or {}
                    intended_s2s = {}
                    for vpn_name, wrapped in intended_s2s_raw.items():
                        if isinstance(wrapped, dict) and "siteToSiteVpn" in wrapped:
                            intended_s2s[vpn_name] = wrapped["siteToSiteVpn"]
                        else:
                            intended_s2s[vpn_name] = wrapped
                    existing_s2s = self._get_existing_site_to_site_vpn(gcs_device_info)
                    intended_compare = {n: _for_compare(d, from_intended=True) for n, d in intended_s2s.items()}
                    existing_compare = {n: _for_compare(d, from_intended=False) for n, d in existing_s2s.items()}
                    if _intended_matches_existing(intended_compare, existing_compare):
                        LOG.info("Site-to-Site VPN for device %s unchanged, Nothing to push", device_id)
                        continue
                    configs_to_push[device_id] = pl
                    dname = device_name_by_id.get(device_id, str(device_id))
                    diff_plan.append(
                        {
                            "device": dname,
                            "branch": "edge.siteToSiteVpn",
                            "before": {"siteToSiteVpn": existing_compare},
                            "after": {"siteToSiteVpn": intended_compare},
                        }
                    )

            if configs_to_push:
                validation_config = {
                    did: {"device_id": did, "payload": {"edge": pl.get("edge"), "core": pl.get("core")}}
                    for did, pl in configs_to_push.items()
                }
                LOG.info("Validating Site-to-Site VPN creation for %d device(s)...", len(configs_to_push))
                try:
                    self.execute_concurrent_tasks(self.gsdk.show_validated_payload, validation_config)
                except Exception as e:
                    LOG.error("SDK validation failed (e.g. ManaV2NullableIPsecTunnelConfig): %s", str(e))
                    raise ConfigurationError(
                        f"Site-to-Site VPN creation validation failed: {str(e)}. "
                        "Check IPsec tunnel and BGP fields against the API schema."
                    ) from e
                LOG.info("Pushing Site-to-Site VPN creation to %d device(s)...", len(configs_to_push))
                self.execute_concurrent_tasks(self.gsdk.put_device_config, configs_to_push)
                result["changed"] = True
                result["created_devices"] = list(configs_to_push)
                LOG.info("Successfully created Site-to-Site VPN for %s devices", len(configs_to_push))
            elif output_config:
                LOG.info("Site-to-Site VPN unchanged for all %d device(s), Nothing to push", len(output_config))
            else:
                LOG.warning("No valid device configurations found")

            result["diff_plan"] = diff_plan
            return result

        except Exception as e:
            LOG.error("Error in Site-to-Site VPN creation: %s", str(e))
            raise ConfigurationError(f"Site-to-Site VPN creation failed: {str(e)}")

    def delete_site_to_site_vpn(self, vpn_config_file: str) -> dict:
        """
        Delete Site-to-Site VPN for multiple devices concurrently.

        Args:
            vpn_config_file: Path to the YAML file containing Site-to-Site VPN configurations

        Returns:
            dict: Result with 'changed' status and list of deleted devices

        Raises:
            ConfigurationError: If configuration processing fails
            DeviceNotFoundError: If any device cannot be found
        """
        result: Dict[str, Any] = {"changed": False, "deleted_devices": []}

        try:
            # Load Site-to-Site VPN configurations
            vpn_config_data = self.render_config_file(vpn_config_file)
            output_config = {}
            device_name_by_id: Dict[int, str] = {}

            # Config format: siteToSiteVpn is a list of { device_name: [ vpn_config, ... ] }
            site_to_site_vpn_list = vpn_config_data.get("siteToSiteVpn", [])
            if not site_to_site_vpn_list:
                LOG.warning("No siteToSiteVpn configuration found in %s", vpn_config_file)
                return result

            for device_entry in site_to_site_vpn_list:
                if not isinstance(device_entry, dict):
                    LOG.warning("Skipping invalid device entry (expected dict): %s", type(device_entry))
                    continue
                for device_name, vpn_configs in device_entry.items():
                    try:
                        device_id = self.gsdk.get_device_id(device_name)
                        if device_id is None:
                            raise DeviceNotFoundError(
                                f"Device '{device_name}' is not found in the current enterprise: "
                                f"{self.gsdk.enterprise_info['company_name']}. "
                                "Please check device name and enterprise credentials."
                            )

                        device_name_by_id[device_id] = device_name
                        if device_id not in output_config:
                            output_config[device_id] = {"device_id": device_id, "edge": {"siteToSiteVpn": {}}}

                        LOG.info("[delete] Processing device: %s (ID: %s)", device_name, device_id)

                        if not isinstance(vpn_configs, list):
                            vpn_configs = [vpn_configs]

                        for vpn_config in vpn_configs:
                            vpn_name = vpn_config.get("name")
                            if not vpn_name:
                                LOG.warning("Skipping VPN config - missing 'name' field")
                                continue

                            LOG.info("Deleting Site-to-Site VPN: %s", vpn_name)

                            # Build delete payload directly (no template)
                            output_config[device_id]["edge"]["siteToSiteVpn"][vpn_name] = {"siteToSiteVpn": None}
                            LOG.info(" ✓ Removed Site-to-Site VPN: %s", vpn_name)

                    except DeviceNotFoundError:
                        raise
                    except Exception as e:
                        LOG.error("Error deleting Site-to-Site VPN for device %s: %s", device_name, str(e))
                        raise ConfigurationError(f"Delete failed for {device_name}: {str(e)}") from e

            # Idempotency: only delete VPNs that exist on the device (skip already-absent)
            diff_plan: List[Dict[str, Any]] = []
            if output_config:
                configs_to_delete = {}
                for device_id, pl in output_config.items():
                    gcs_device_info = self.gsdk.get_device_info(device_id)
                    existing_s2s = self._get_existing_site_to_site_vpn(gcs_device_info)
                    requested_deletes = list((pl.get("edge") or {}).get("siteToSiteVpn") or {})
                    to_delete = {
                        k: v for k, v in (pl.get("edge") or {}).get("siteToSiteVpn", {}).items() if k in existing_s2s
                    }
                    if not to_delete:
                        LOG.info("Device %s: no VPNs to delete (already absent), skipping", device_id)
                        continue
                    for name in requested_deletes:
                        if name not in existing_s2s:
                            LOG.info("Site-to-Site VPN '%s' not present on device %s, skipping delete", name, device_id)
                    configs_to_delete[device_id] = {
                        "device_id": device_id,
                        "edge": {"siteToSiteVpn": to_delete},
                        "core": pl.get("core"),
                    }
                    dname = device_name_by_id.get(device_id, str(device_id))
                    diff_plan.append(
                        {
                            "device": dname,
                            "branch": "edge.siteToSiteVpn",
                            "before": {
                                "siteToSiteVpn": {
                                    n: SiteToSiteVpnManager._drop_secrets(existing_s2s.get(n)) for n in to_delete
                                }
                            },
                            "after": {"siteToSiteVpn": {n: None for n in to_delete}},
                        }
                    )
                output_config = configs_to_delete

            # Validate payload with SDK before push
            if output_config:
                validation_config = {
                    did: {"device_id": did, "payload": {"edge": pl.get("edge"), "core": pl.get("core")}}
                    for did, pl in output_config.items()
                }
                LOG.info("Validating Site-to-Site VPN deletion for %d device(s)...", len(output_config))
                try:
                    self.execute_concurrent_tasks(self.gsdk.show_validated_payload, validation_config)
                except Exception as e:
                    LOG.error("SDK validation failed: %s", str(e))
                    raise ConfigurationError(f"Site-to-Site VPN deletion validation failed: {str(e)}.") from e
                LOG.info("Pushing Site-to-Site VPN deletion to %d device(s)...", len(output_config))
                self.execute_concurrent_tasks(self.gsdk.put_device_config, output_config)
                result["changed"] = True
                result["deleted_devices"] = list(output_config)
                LOG.info("Successfully deleted Site-to-Site VPN for %s devices", len(output_config))
            else:
                LOG.warning("No valid device configurations found")

            result["diff_plan"] = diff_plan
            return result

        except Exception as e:
            LOG.error("Error in Site-to-Site VPN deletion: %s", str(e))
            raise ConfigurationError(f"Site-to-Site VPN deletion failed: {str(e)}")
