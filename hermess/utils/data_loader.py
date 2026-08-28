# © 2024-2026 ETH Zurich
# Original author: Milos Katanic
# Simulation-only fork & maintainer: Maitraya Avadhut Desai
#
# Licensed under the GNU General Public License v3.0 or later;
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at:
#
#     https://www.gnu.org/licenses/gpl-3.0.en.html
#
# This software is distributed "AS IS", WITHOUT WARRANTY OF ANY KIND,
# express or implied. See the License for specific language governing
# permissions and limitations under the License.
#
# Simulation-only fork of PowerDynamicEstimator
# (https://doi.org/10.5905/ethz-1007-842); dynamic state estimation removed.
# For inquiries, contact: mdesai@ethz.ch
"""Parsing of the system files (``sim_param.txt``, ``sim_dist.txt``) into
device instances; internal.
"""

import importlib
import os
import pkgutil
import re
from hermess import system
import logging


def class_to_instance_name(
    class_name,
    typ,
    avr_type=None,
    governor_type=None,
    pss_type=None,
    shaft_type=None,
    filter_type=None,
    angle_type=None,
    voltage_type=None,
    inner_type=None,
    pll_type=None,
):
    # Add underscores before uppercase letters and convert to lowercase
    instance_name = (
        re.sub(r"(?<!^)(?=[A-Z])", "_", class_name).lower() + "_" + typ.lower()
    )
    if avr_type and avr_type != "IEEEDC1A":
        instance_name += "_" + avr_type.lower()
    if governor_type and governor_type != "TGOV1":
        instance_name += "_" + governor_type.lower()
    if pss_type:
        instance_name += "_" + pss_type.lower()
    if shaft_type and shaft_type != "SingleMass":
        instance_name += "_" + shaft_type.lower()
    # Encode inverter strategy selectors in the instance name so that two
    # inverter rows differing only by strategy map to distinct instances.
    if filter_type:
        instance_name += "_" + filter_type.lower()
    if angle_type:
        instance_name += "_" + angle_type.lower()
    if voltage_type:
        instance_name += "_" + voltage_type.lower()
    if inner_type:
        instance_name += "_" + inner_type.lower()
    if pll_type:
        instance_name += "_" + pll_type.lower()
    return instance_name


def _strategy_instances(
    avr_type=None,
    governor_type=None,
    pss_type=None,
    shaft_type=None,
    filter_type=None,
    angle_type=None,
    voltage_type=None,
    inner_type=None,
    pll_type=None,
) -> dict:
    """Instantiate the strategies selected on a system-file line.

    Returns constructor keyword arguments ({"avr": <AVR instance>, ...}) for the
    strategy keywords that were given; the others are omitted, so device classes
    without that strategy axis are unaffected. Names resolve through the same
    registries that :func:`hermess.register` extends, so user-registered
    strategies are found here like shipped ones.
    """
    kwargs = {}
    if avr_type is not None:
        from hermess.devices.avr import AVR_REGISTRY

        kwargs["avr"] = AVR_REGISTRY[avr_type]()
    if governor_type is not None:
        from hermess.devices.governor import GOVERNOR_REGISTRY

        kwargs["governor"] = GOVERNOR_REGISTRY[governor_type]()
    if pss_type is not None:
        from hermess.devices.pss import PSS_REGISTRY

        kwargs["pss"] = PSS_REGISTRY[pss_type]()
    if shaft_type is not None:
        from hermess.devices.shaft import SHAFT_REGISTRY

        kwargs["shaft"] = SHAFT_REGISTRY[shaft_type]()
    # Inverter strategy selectors (ignored by other device types).
    if filter_type is not None:
        from hermess.devices.inverter_filter import FILTER_REGISTRY

        kwargs["filter"] = FILTER_REGISTRY[filter_type]()
    if angle_type is not None:
        from hermess.devices.inverter_angle import ANGLE_REGISTRY

        kwargs["angle"] = ANGLE_REGISTRY[angle_type]()
    if voltage_type is not None:
        from hermess.devices.inverter_voltage import VOLTAGE_REGISTRY

        kwargs["voltage"] = VOLTAGE_REGISTRY[voltage_type]()
    if inner_type is not None:
        from hermess.devices.inverter_inner import INNER_REGISTRY

        kwargs["inner"] = INNER_REGISTRY[inner_type]()
    if pll_type is not None:
        from hermess.devices.inverter_pll import PLL_REGISTRY

        kwargs["pll"] = PLL_REGISTRY[pll_type]()
    return kwargs


def create_device_instance(
    class_name,
    instance_name,
    typ,
    avr_type=None,
    governor_type=None,
    pss_type=None,
    shaft_type=None,
    filter_type=None,
    angle_type=None,
    voltage_type=None,
    inner_type=None,
    pll_type=None,
):
    """
    Ensures an instance with a specific name exists in globals().
    If not, searches through all scripts in the specified subpackage to find and load the class.

    :param class_name: Name of the class as a string.
    :param instance_name: Desired instance name in snake_case.
    :param typ: Device-list suffix (always 'sim').
    :param avr_type: Optional AVR type string for synchronous machines.
    :return: The instance, or raises an ImportError if not found.
    """
    found_class = False

    # User-registered devices (hermess.register) take precedence over the package
    # scan below, so a device class defined in a script or notebook is selectable
    # from a system file by its class name like any shipped device.
    from hermess.registry import DEVICE_REGISTRY

    if class_name in DEVICE_REGISTRY:
        instance = DEVICE_REGISTRY[class_name](
            **_strategy_instances(
                avr_type,
                governor_type,
                pss_type,
                shaft_type,
                filter_type,
                angle_type,
                voltage_type,
                inner_type,
                pll_type,
            )
        )
        setattr(system, instance_name, instance)
        logging.info(f"Created {instance_name} of registered class {class_name}().")
        exec(f"system.device_list_{typ}.append(system.{instance_name})")
        return instance

    for folder in ["hermess.devices"]:
        package = importlib.import_module(folder)
        # Get the directory of the subpackage
        package_dir = os.path.dirname(package.__file__)

        # Iterate through all modules in the subpackage
        for _, module_name, is_pkg in pkgutil.iter_modules([package_dir]):

            full_module_name = f"{folder}.{module_name}"

            try:
                # Dynamically import the module
                module = importlib.import_module(full_module_name)

                # Check if the class exists in the module
                if hasattr(module, class_name):
                    # Get the class
                    cls = getattr(module, class_name)

                    # Pass any specified strategies to the constructor;
                    # synchronous-machine and inverter strategies are ignored by
                    # other device types.
                    cls_kwargs = _strategy_instances(
                        avr_type,
                        governor_type,
                        pss_type,
                        shaft_type,
                        filter_type,
                        angle_type,
                        voltage_type,
                        inner_type,
                        pll_type,
                    )
                    instance = cls(**cls_kwargs)
                    setattr(system, instance_name, instance)
                    logging.info(f"Created {instance_name} of class {class_name}().")
                    # Append the instance to the system's device list.
                    exec(f"system.device_list_{typ}.append(system.{instance_name})")
                    found_class = True  # Mark as found
                    break  # Stop checking further modules in this folder

            except Exception as e:
                # Log or handle individual module import errors gracefully
                logging.info(f"Error while trying to create {instance_name}: {e}")

        if found_class:
            break  # If the class was found, exit the outer loop as well

    if not found_class:
        # If the class wasn't found in any module
        raise ImportError(
            f"Class {class_name} not found in any script within devices."
        )


def read(file, typ: str):
    """Read the contents from .txt files"""
    # Define regular expressions and constants for parsing
    comment_pattern = re.compile(r"^#\s*")
    arithmetic_pattern = re.compile(r"[*/+-]")
    number_pattern = re.compile(r"[+-]? *(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")
    split_pattern = re.compile(r"\s*,\s*")
    assignment_pattern = re.compile(r"\s*=\s*")

    # Process file content line by line
    while True:
        line = file.readline()
        if not line:
            break
        line = line.strip().replace("\n", "")  # Clean up the line

        if not line or comment_pattern.search(line):
            continue  # Skip empty lines or comments

        # Handle multi-line data entries (when lines end with ',' or ';')
        while line.endswith((",", ";")):
            next_line = file.readline().strip()
            if not next_line:
                break
            if not next_line or comment_pattern.search(next_line):
                continue  # Skip empty lines or comments
            line += " " + next_line  # Concatenate multi-line data

        parts = split_pattern.split(line)  # Split line by commas
        class_name = parts.pop(0).strip()  # The first part is the class name

        params = {}
        for part in parts:

            try:
                key, value = map(
                    str.strip, assignment_pattern.split(part.strip())
                )  # extract key value pairs
            except ValueError:
                logging.warning(
                    f"Some parameters could not be loaded: {part}! Correct the input! Miss-placed comma? Ignoring this part."
                )
                continue

            key = key.strip()
            value = value.strip()

            # Handle different types of values (strings, arrays, numbers, booleans)
            if value.startswith('"'):
                value = value[1:-1]  # String without quotes
            elif value.startswith("["):  # Array processing
                array_values = value[1:-1].split(";")
                if arithmetic_pattern.search(value):  # If it contains arithmetic
                    value = list(map(lambda x: eval(x), array_values))
                else:
                    value = list(
                        map(lambda x: float(x), array_values)
                    )  # Convert strings to floats
            elif number_pattern.search(
                value
            ):  # Check if it's a number (could be an arithmetic expression)
                if arithmetic_pattern.search(value):  # If it contains arithmetic
                    value = eval(value)
                else:
                    value = float(value)  # Convert to float
            elif value == "True":
                value = True
            elif value == "False":
                value = False
            else:
                value = int(value)  # Default to integer if no other matches

            params[key] = value  # Add parsed value to the parameters dictionary

        name = params.pop("name", None)
        idx = params.pop("idx", None)
        # Synchronous-machine strategy selectors (ignored by other devices).
        avr_type = params.pop("avr", None)
        governor_type = params.pop("governor", None)
        pss_type = params.pop("pss", None)
        shaft_type = params.pop("shaft", None)
        # Inverter strategy selectors (ignored by other devices).
        filter_type = params.pop("filter", None)
        angle_type = params.pop("angle", None)
        voltage_type = params.pop("voltage", None)
        inner_type = params.pop("inner", None)
        pll_type = params.pop("pll", None)

        instance_name = class_to_instance_name(
            class_name,
            typ,
            avr_type,
            governor_type,
            pss_type,
            shaft_type,
            filter_type,
            angle_type,
            voltage_type,
            inner_type,
            pll_type,
        )
        if hasattr(system, instance_name):
            try:
                getattr(system, instance_name).add(idx=idx, name=name, **params)

            except KeyError as e:
                logging.warning(
                    f"Failed to add element {class_name} due to missing key: {e}"
                )
        else:
            create_device_instance(
                class_name,
                instance_name,
                typ,
                avr_type,
                governor_type,
                pss_type,
                shaft_type,
                filter_type,
                angle_type,
                voltage_type,
                inner_type,
                pll_type,
            )
            try:
                getattr(system, instance_name).add(idx=idx, name=name, **params)
            except KeyError as e:
                logging.warning(
                    f"Failed to add element {class_name} due to missing key: {e}"
                )

    return True
