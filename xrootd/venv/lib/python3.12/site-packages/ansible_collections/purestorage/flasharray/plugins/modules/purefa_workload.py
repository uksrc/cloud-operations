#!/usr/bin/python
# -*- coding: utf-8 -*-

# (c) 2025, Simon Dodsley (simon@purestorage.com)
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import absolute_import, division, print_function

__metaclass__ = type

ANSIBLE_METADATA = {
    "metadata_version": "1.1",
    "status": ["preview"],
    "supported_by": "community",
}

DOCUMENTATION = r"""
---
module: purefa_workload
version_added: '1.33.0'
short_description: Manage Fusion Fleet Workloads
description:
- Apply/Rename/Delete Fusion fleet workloads
author:
- Everpure Ansible Team (@sdodsley) <pure-ansible-team@purestorage.com>
options:
  context:
    description:
    - Name of fleet member on which to perform the workload operation.
    - This requires the array receiving the request is a member of a fleet
      and the context name to be a member of the same fleet.
    type: str
    default: ""
  host:
    type: str
    description:
    - Host to connect to the workload after provisioning
    default: ""
  name:
    description:
    - Name of the workload.
    type: str
    required: true
  state:
    description:
    - Define whether to create or delete a fleet workload.
    - Using the expand option will add volume(s) to the workload.
    - If absent is specified together with a host, rather than deleting the workload, the host will be disconnected from the workload
    default: present
    choices: [ absent, present, expand]
    type: str
  preset:
    description:
    - name of existing preset to use as the basis of the workload
    type: str
  rename:
    description:
    - new name for a workload
    type: str
  eradicate:
    description:
    - whether to eradicate a workload
    type: bool
    default: false
  placement:
    description:
    - name of target on which the workload will be deployed
    type: str
  recommendation:
    description:
    - whether to use the Fusion placement recommendation based
      on the workload preset definitions.
    - This will use the first recommended placement if more than
      one is available
    default: false
    type: bool
  parameters:
    description:
    - Parameter values to apply when creating a workload from the preset.
    - Parameters are only applied on the create path and are not applied
      when recovering an existing destroyed workload.
    type: list
    elements: dict
    suboptions:
      name:
        description:
        - Name of the preset parameter to set.
        type: str
        required: true
      value:
        description:
        - Value for the preset parameter.
        - Exactly one of C(string), C(integer), C(boolean), or
          C(resource_reference) must be provided.
        type: dict
        required: true
        suboptions:
          string:
            description:
            - String parameter value.
            type: str
          integer:
            description:
            - Integer parameter value.
            type: int
          boolean:
            description:
            - Boolean parameter value.
            type: bool
          resource_reference:
            description:
            - Reference to another resource.
            type: dict
            suboptions:
              id:
                description:
                - ID of the referenced resource.
                type: str
              name:
                description:
                - Name of the referenced resource.
                type: str
              resource_type:
                description:
                - Optional resource type for the reference.
                type: str
  volume_count:
    description:
    - Number of additional volumes to add to an existing workload
    type: int
  volume_configuration:
    description:
    - Name of the volume configuration to use for adding volumes
      to a workload
    type: str
extends_documentation_fragment:
- purestorage.flasharray.purestorage.fa
"""

EXAMPLES = r"""
- name: Create a workload using an existing preset on a specific placement target and connect to host myhost
  purestorage.flasharray.purefa_workload:
    name: foo
    preset: bar
    host: myhost
    placement: arrayB
    fa_url: 10.10.10.2
    api_token: e31060a7-21fc-e277-6240-25983c6c4592

- name: Create a workload using an existing preset using the recommended target and connect to host myhost
  purestorage.flasharray.purefa_workload:
    name: foo
    preset: bar
    host: myhost
    recommendation: true
    fa_url: 10.10.10.2
    api_token: e31060a7-21fc-e277-6240-25983c6c4592

- name: Create a workload using preset parameters
  purestorage.flasharray.purefa_workload:
    name: foo
    preset: bar
    context: arr1
    parameters:
      - name: replication_target
        value:
          resource_reference:
            name: arr2
    fa_url: 10.10.10.2
    api_token: e31060a7-21fc-e277-6240-25983c6c4592

- name: Add volumes to workload foo based on volume configuration fin and connect to host myhost
  purestorage.flasharray.purefa_workload:
    name: foo
    preset: bar
    volume_configuration: fin
    volume_count: 3
    host: myhost
    state: expand
    fa_url: 10.10.10.2
    api_token: e31060a7-21fc-e277-6240-25983c6c4592

- name: Rename an existing workload
  purestorage.flasharray.purefa_workload:
    name: foo
    rename: bar
    state: rename
    fa_url: 10.10.10.2
    api_token: e31060a7-21fc-e277-6240-25983c6c4592

- name: Disconnect an existing workload from host
  purestorage.flasharray.purefa_workload:
    name: foo
    host: myhost
    state: absent
    fa_url: 10.10.10.2
    api_token: e31060a7-21fc-e277-6240-25983c6c4592

- name: Delete an existing workload
  purestorage.flasharray.purefa_workload:
    name: foo
    state: absent
    fa_url: 10.10.10.2
    api_token: e31060a7-21fc-e277-6240-25983c6c4592

- name: Eradicate an existing workload
  purestorage.flasharray.purefa_workload:
    name: foo
    state: absent
    eradicate: true
    fa_url: 10.10.10.2
    api_token: e31060a7-21fc-e277-6240-25983c6c4592

- name: Recover a deleted workload
  purestorage.flasharray.purefa_workload:
    name: foo
    state: present
    fa_url: 10.10.10.2
    api_token: e31060a7-21fc-e277-6240-25983c6c4592

- name: Reconnect an existing workload to a host
  purestorage.flasharray.purefa_workload:
    name: foo
    host: myhost
    fa_url: 10.10.10.2
    api_token: e31060a7-21fc-e277-6240-25983c6c4592
"""

RETURN = r"""
"""

HAS_PURESTORAGE = True
try:
    from pypureclient.flasharray import (
        WorkloadConfigurationReference,
        WorkloadParameter,
        WorkloadParameterValue,
        WorkloadParameterValueResourceReference,
        WorkloadPatch,
        WorkloadPost,
        WorkloadPlacementRecommendation,
        VolumePost,
        ConnectionPost,
    )
except ImportError:
    HAS_PURESTORAGE = False

import time
from ansible.module_utils.basic import AnsibleModule
from ansible_collections.purestorage.flasharray.plugins.module_utils.purefa import (
    get_array,
    purefa_argument_spec,
)
from ansible_collections.purestorage.flasharray.plugins.module_utils.version import (
    LooseVersion,
)
from ansible_collections.purestorage.flasharray.plugins.module_utils.api_helpers import (
    check_response,
)

VERSION = 1.5
USER_AGENT_BASE = "Ansible"
MIN_REQUIRED_API_VERSION = "2.40"
SUPPORTED_PARAMETER_VALUE_TYPES = (
    "string",
    "integer",
    "boolean",
    "resource_reference",
)


def _parameter_fail(module, parameter_name, message):
    module.fail_json(msg=f"Invalid workload parameter '{parameter_name}': {message}")


def _coerce_parameter_list(parameter_items):
    if parameter_items is None:
        return []
    try:
        return list(parameter_items)
    except TypeError:
        return []


def _supplied_option_keys(value_definition, allowed_keys):
    return [
        key
        for key in allowed_keys
        if key in value_definition and value_definition[key] is not None
    ]


def _build_resource_reference(module, parameter_name, resource_reference):
    if not isinstance(resource_reference, dict):
        _parameter_fail(
            module,
            parameter_name,
            "resource_reference must be a dictionary",
        )
    unknown_keys = set(resource_reference) - {"id", "name", "resource_type"}
    if unknown_keys:
        _parameter_fail(
            module,
            parameter_name,
            "resource_reference contains unsupported keys: {0}".format(
                ", ".join(sorted(unknown_keys))
            ),
        )
    identifier_keys = _supplied_option_keys(resource_reference, ("id", "name"))
    if len(identifier_keys) != 1:
        _parameter_fail(
            module,
            parameter_name,
            "resource_reference must include exactly one of id or name",
        )
    return WorkloadParameterValueResourceReference(
        **{
            key: resource_reference[key]
            for key in resource_reference
            if resource_reference[key] is not None
        }
    )


def _build_parameter_value(module, parameter_name, value_definition):
    if not isinstance(value_definition, dict):
        _parameter_fail(module, parameter_name, "value must be a dictionary")
    unknown_keys = set(value_definition) - set(SUPPORTED_PARAMETER_VALUE_TYPES)
    if unknown_keys:
        _parameter_fail(
            module,
            parameter_name,
            "value contains unsupported keys: {0}".format(
                ", ".join(sorted(unknown_keys))
            ),
        )
    supplied_value_types = _supplied_option_keys(
        value_definition, SUPPORTED_PARAMETER_VALUE_TYPES
    )
    if len(supplied_value_types) != 1:
        _parameter_fail(
            module,
            parameter_name,
            "value must include exactly one of {0}".format(
                ", ".join(SUPPORTED_PARAMETER_VALUE_TYPES)
            ),
        )

    value_type = supplied_value_types[0]
    normalized_value = value_definition[value_type]
    if value_type == "string":
        if not isinstance(normalized_value, str):
            _parameter_fail(module, parameter_name, "string value must be a string")
    elif value_type == "integer":
        if isinstance(normalized_value, bool) or not isinstance(normalized_value, int):
            _parameter_fail(module, parameter_name, "integer value must be an integer")
    elif value_type == "boolean":
        if not isinstance(normalized_value, bool):
            _parameter_fail(
                module, parameter_name, "boolean value must be true or false"
            )
    elif value_type == "resource_reference":
        normalized_value = _build_resource_reference(
            module, parameter_name, normalized_value
        )

    return value_type, WorkloadParameterValue(**{value_type: normalized_value})


def _build_workload_parameters(module, preset_config):
    raw_parameters = module.params.get("parameters") or []
    if not raw_parameters:
        return None

    preset_parameters = {}
    for preset_parameter in _coerce_parameter_list(
        getattr(preset_config, "parameters", [])
    ):
        if getattr(preset_parameter, "name", None):
            preset_parameters[preset_parameter.name] = preset_parameter

    normalized_parameters = []
    seen_parameters = set()
    for raw_parameter in raw_parameters:
        if not isinstance(raw_parameter, dict):
            module.fail_json(msg="Each workload parameter must be a dictionary")
        parameter_name = raw_parameter.get("name")
        if not parameter_name:
            module.fail_json(msg="Each workload parameter requires a name")
        if parameter_name in seen_parameters:
            _parameter_fail(module, parameter_name, "parameter names must be unique")
        if parameter_name not in preset_parameters:
            _parameter_fail(
                module,
                parameter_name,
                "parameter is not defined by preset {0}".format(
                    module.params["preset"]
                ),
            )
        if "value" not in raw_parameter:
            _parameter_fail(module, parameter_name, "parameter requires a value")

        value_type, parameter_value = _build_parameter_value(
            module, parameter_name, raw_parameter["value"]
        )
        preset_type = getattr(preset_parameters[parameter_name], "type", None)
        if preset_type and preset_type != value_type:
            _parameter_fail(
                module,
                parameter_name,
                "expected type {0}, got {1}".format(preset_type, value_type),
            )

        normalized_parameters.append(
            WorkloadParameter(name=parameter_name, value=parameter_value)
        )
        seen_parameters.add(parameter_name)
    return normalized_parameters


def _create_volume(module, array):
    """Create an actual volume in a workload"""
    res = array.post_volumes(
        volume=VolumePost(
            workload=WorkloadConfigurationReference(
                name=module.params["name"],
                configuration=module.params["volume_configuration"],
            ),
        ),
        context_names=[module.params["context"]],
    )
    check_response(res, module, "Workload volume creation failed")


def _disconnect_volumes(module, array):
    """Disconnect host from volumes in the workload"""
    volumes = list(
        array.get_volumes(
            filter="workload.name='{0}'".format(module.params["name"]),
            context_names=[module.params["context"]],
        ).items
    )
    volNames = [vol.name for vol in volumes]

    res = array.delete_connections(
        host_names=[module.params["host"]],
        context_names=[module.params["context"]],
        volume_names=volNames,
    )
    check_response(res, module, "Failed to disconnect volumes from host")


def _connect_volumes(module, array):
    """Connect host to volumes in the workload"""
    volumes = list(
        array.get_volumes(
            filter="workload.name='{0}'".format(module.params["name"]),
            context_names=[module.params["context"]],
        ).items
    )
    volNames = [vol.name for vol in volumes]

    res = array.post_connections(
        host_names=[module.params["host"]],
        context_names=[module.params["context"]],
        volume_names=volNames,
        connection=ConnectionPost(),
    )
    check_response(res, module, "Failed to connect volumes to host")


def create_workload(module, array, fleet, preset_config):
    """Create fleet workload using existing preset"""
    changed = True
    workload_parameters = _build_workload_parameters(module, preset_config)
    if module.params["recommendation"]:
        # Start the workload calculation for the preset being used
        res = array.post_workloads_placement_recommendations(
            inputs=WorkloadPlacementRecommendation(parameters=workload_parameters),
            preset_names=[module.params["preset"]],
            context_names=[module.params["context"]],
        )
        check_response(res, module, "Recommendation calculation failure")
        workload_calc = list(res.items)[0].name
        # Wait for the workload calculation to complete
        result = list(
            array.get_workloads_placement_recommendations(
                names=[workload_calc], context_names=[module.params["context"]]
            ).items
        )[0]
        while result.status != "completed":
            time.sleep(1)
            result = list(
                array.get_workloads_placement_recommendations(
                    names=[workload_calc], context_names=[module.params["context"]]
                ).items
            )[0]
        # Replace any defined placement with the result from the recommendation
        module.params["placement"] = result.results[0].placements[0].targets[0].name
        module.params["context"] = module.params["placement"]
    if not module.check_mode:
        res = array.post_workloads(
            names=[module.params["name"]],
            preset_names=[module.params["preset"]],
            workload=WorkloadPost(parameters=workload_parameters),
            context_names=[module.params["context"]],
        )
        check_response(
            res, module, f"Failed to create workload {module.params['name']}"
        )
        if module.params["host"] != "":
            _connect_volumes(module, array)

    module.exit_json(changed=changed)


def expand_workload(module, array, fleet, volume_configs):
    """Add new volumes to workload"""
    changed = False
    for vol_config in volume_configs:
        if vol_config.name == module.params["volume_configuration"]:
            for x in range(module.params["volume_count"]):
                changed = True
                _create_volume(module, array)
    if changed:
        if module.params["host"] != "":
            _connect_volumes(module, array)
    else:
        module.fail_json(
            msg="Volume Configuration {0} does not exist for preset {1}.".format(
                module.params["volume_configuration"], module.params["preset"]
            )
        )

    module.exit_json(changed=changed)


def delete_workload(module, array):
    """Delete the workload"""
    changed = True
    if not module.check_mode:
        res = array.patch_workloads(
            names=[module.params["name"]],
            workload=WorkloadPatch(destroyed=True),
            context_names=[module.params["context"]],
        )
        check_response(res, module, "Workload deletion failed")
        if module.params["eradicate"]:
            eradicate_workload(module, array)
    module.exit_json(changed=changed)


def eradicate_workload(module, array):
    """Eradicate the workload"""
    changed = True
    if not module.check_mode:
        res = array.delete_workloads(
            names=[module.params["name"]],
            context_names=[module.params["context"]],
        )
        check_response(res, module, "Workload eradication failed")
    module.exit_json(changed=changed)


def recover_workload(module, array):
    """Recover the workload and optionally reconnect to host"""
    changed = True
    if not module.check_mode:
        res = array.patch_workloads(
            names=[module.params["name"]],
            workload=WorkloadPatch(destroyed=False),
            context_names=[module.params["context"]],
        )
        check_response(res, module, "Workload recovery failed")
        if module.params["host"] != "":
            _connect_volumes(module, array)

    module.exit_json(changed=changed)


def rename_workload(module, array):
    """Rename the workload"""
    changed = True
    if not module.check_mode:
        res = array.patch_workloads(
            names=[module.params["name"]],
            workload=WorkloadPatch(name=module.params["rename"]),
            context_names=[module.params["context"]],
        )
        check_response(res, module, "Workload rename failed")
    module.exit_json(changed=changed)


def connect_or_disconnect_volumes(module, array, mode):
    """Connect or disconnect volumes in the workload to a host"""
    changed = False

    res = array.get_connections(
        host_names=[module.params["host"]],
        context_names=[module.params["context"]],
    )
    check_response(
        res, module, f"Failed to get volume connection for host {module.params['host']}"
    )
    volume_connections = [conn.volume.name for conn in list(res.items)]

    res = array.get_volumes(
        filter="workload.name='{0}'".format(module.params["name"]),
        context_names=[module.params["context"]],
    )
    check_response(
        res, module, f"Failed to get volumes for workload {module.params['name']}"
    )
    volumes = list(res.items)

    if mode == "connect":
        for volume in volumes:
            if volume.name not in volume_connections:
                changed = True
    elif mode == "disconnect":
        for volume in volumes:
            if volume.name in volume_connections:
                changed = True

    if not module.check_mode and changed:
        if mode == "connect":
            _connect_volumes(module, array)
        elif mode == "disconnect":
            _disconnect_volumes(module, array)

    module.exit_json(changed=changed)


def main():
    argument_spec = purefa_argument_spec()
    argument_spec.update(
        dict(
            name=dict(type="str", required=True),
            state=dict(
                type="str",
                default="present",
                choices=["absent", "present", "expand"],
            ),
            preset=dict(type="str"),
            rename=dict(type="str"),
            eradicate=dict(type="bool", default=False),
            placement=dict(type="str"),
            parameters=dict(
                type="list",
                elements="dict",
                options=dict(
                    name=dict(type="str", required=True),
                    value=dict(
                        type="dict",
                        required=True,
                        options=dict(
                            string=dict(type="str"),
                            integer=dict(type="int"),
                            boolean=dict(type="bool"),
                            resource_reference=dict(
                                type="dict",
                                options=dict(
                                    id=dict(type="str"),
                                    name=dict(type="str"),
                                    resource_type=dict(type="str"),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
            volume_count=dict(type="int"),
            volume_configuration=dict(type="str"),
            recommendation=dict(type="bool", default=False),
            context=dict(type="str", default=""),
            host=dict(type="str", default=""),
        )
    )

    required_if = [["state", "expand", ["volume_count", "volume_configuration"]]]

    module = AnsibleModule(
        argument_spec, supports_check_mode=True, required_if=required_if
    )

    if not HAS_PURESTORAGE:
        module.fail_json(msg="py-pure-client sdk is required for this module")

    array = get_array(module)
    api_version = array.get_rest_version()
    if LooseVersion(MIN_REQUIRED_API_VERSION) > LooseVersion(api_version):
        module.fail_json(
            msg="FlashArray REST version not supported. "
            "Minimum version required: {0}".format(MIN_REQUIRED_API_VERSION)
        )
    state = module.params["state"]
    if module.params["volume_count"] and module.params["volume_count"] <= 0:
        module.fail_json(msg="volume_count must be a positive integer.")
    fleet_res = array.get_fleets()
    fleet_items = list(fleet_res.items) if fleet_res.status_code == 200 else []
    if not fleet_items:
        module.fail_json(
            msg="purefa_workload requires a Fusion fleet environment, but this "
            "array is not a member of a fleet."
        )
    fleet = fleet_items[0].name

    workload_destroyed = False
    workload_exists = False
    preset_config = {}
    # Update preset name with fleet prefix
    module.params["preset"] = fleet + ":" + module.params["preset"]
    res = array.get_workloads(
        names=[module.params["name"]], context_names=[module.params["context"]]
    )
    if res.status_code == 200:
        workload_exists = True
        workload_destroyed = list(res.items)[0].destroyed

    if (state == "present" and not workload_destroyed and not workload_exists) or (
        state == "expand" and not workload_destroyed
    ):
        res = array.get_presets_workload(
            names=[module.params["preset"]],
        )
        check_response(
            res,
            module,
            f"Preset {module.params['preset']} does not exist in fleet {fleet}",
        )
        preset_config = list(res.items)[0]
    if (
        state == "present"
        and workload_exists
        and module.params["rename"]
        and not workload_destroyed
    ):
        rename_workload(module, array)
    elif state == "present" and not workload_exists:
        create_workload(module, array, fleet, preset_config)
    elif state == "expand" and workload_exists and not workload_destroyed:
        expand_workload(module, array, fleet, preset_config.volume_configurations)
    elif state == "present" and workload_exists and workload_destroyed:
        recover_workload(module, array)
    elif (
        state == "present"
        and workload_exists
        and not workload_destroyed
        and module.params["host"] != ""
    ):
        connect_or_disconnect_volumes(module, array, "connect")
    elif (
        state == "absent"
        and workload_exists
        and not workload_destroyed
        and module.params["host"] != ""
    ):
        connect_or_disconnect_volumes(module, array, "disconnect")
    elif state == "absent" and workload_exists and not workload_destroyed:
        delete_workload(module, array)
    elif state == "absent" and workload_destroyed and module.params["eradicate"]:
        eradicate_workload(module, array)
    else:
        module.exit_json(changed=False)


if __name__ == "__main__":
    main()
