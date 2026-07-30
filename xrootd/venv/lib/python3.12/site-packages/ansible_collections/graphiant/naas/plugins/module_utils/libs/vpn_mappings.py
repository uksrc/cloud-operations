"""
VPN Algorithm Mappings

This module provides mappings between simplified algorithm names used in configurations
and the full format names expected by the Graphiant system.
"""

# IPSec encryption algorithm mappings (System Format -> User Friendly)
IPSEC_ENCRYPTION_MAPPINGS = {
    "AES 256 CBC": "aes256",
    "AES 128 CBC": "aes128",
    "AES 256 GCM": "aes256gcm128",
    "AES 128 GCM": "aes128gcm128",
    "None": "encryption_none",
}

# IPSec integrity algorithm mappings (System Format -> User Friendly)
IPSEC_INTEGRITY_MAPPINGS = {"SHA256": "sha256", "SHA384": "sha384", "SHA512": "sha512", "None": "integrity_none"}

# DH Group mappings (System Format -> User Friendly)
DH_GROUP_MAPPINGS = {
    "Group 19": "ecp256",
    "Group 20": "ecp384",
    "Group 21": "ecp521",
    "Group 14": "modp2048",
    "Group 24": "modp2048s256",
    "None": "pfs_none",
}


def map_ike_encryption(algorithm):
    """
    Map IKE encryption algorithm from system format to user-friendly format.

    Args:
        algorithm (str): System format algorithm name (e.g., 'AES 256 CBC')

    Returns:
        str: User-friendly format algorithm name (e.g., 'aes256')
    """
    return IPSEC_ENCRYPTION_MAPPINGS.get(algorithm, algorithm)


def map_ike_integrity(algorithm):
    """
    Map IKE integrity algorithm from system format to user-friendly format.

    Args:
        algorithm (str): System format algorithm name (e.g., 'SHA256')

    Returns:
        str: User-friendly format algorithm name (e.g., 'sha256')
    """
    return IPSEC_INTEGRITY_MAPPINGS.get(algorithm, algorithm)


def map_ike_dh_group(group):
    """
    Map IKE DH group from system format to user-friendly format.

    Args:
        group (str): System format group name (e.g., 'Group 20')

    Returns:
        str: User-friendly format group name (e.g., 'ecp384')
    """
    return DH_GROUP_MAPPINGS.get(group, group)


def map_ipsec_encryption(algorithm):
    """
    Map IPSec encryption algorithm from system format to user-friendly format.

    Args:
        algorithm (str): System format algorithm name (e.g., 'AES 256 CBC')

    Returns:
        str: User-friendly format algorithm name (e.g., 'aes256')
    """
    return IPSEC_ENCRYPTION_MAPPINGS.get(algorithm, algorithm)


def map_ipsec_integrity(algorithm):
    """
    Map IPSec integrity algorithm from system format to user-friendly format.

    Args:
        algorithm (str): System format algorithm name (e.g., 'SHA256')

    Returns:
        str: User-friendly format algorithm name (e.g., 'sha256')
    """
    return IPSEC_INTEGRITY_MAPPINGS.get(algorithm, algorithm)


def map_perfect_forward_secrecy(group):
    """
    Map perfect forward secrecy group from system format to user-friendly format.

    Args:
        group (str): System format group name (e.g., 'Group 20')

    Returns:
        str: User-friendly format group name (e.g., 'ecp384')
    """
    return DH_GROUP_MAPPINGS.get(group, group)


def map_vpn_profile(vpn_profile):
    """
    Map an entire VPN profile from system format to user-friendly format.

    Args:
        vpn_profile (dict): VPN profile with system format algorithm names

    Returns:
        dict: VPN profile with user-friendly format algorithm names
    """
    mapped_profile = vpn_profile.copy()

    if "vpnProfile" in mapped_profile:
        profile = mapped_profile["vpnProfile"]

        # Map IKE algorithms
        if "ikeEncryptionAlg" in profile:
            profile["ikeEncryptionAlg"] = map_ike_encryption(profile["ikeEncryptionAlg"])

        if "ikeIntegrity" in profile:
            profile["ikeIntegrity"] = map_ike_integrity(profile["ikeIntegrity"])

        if "ikeDhGroup" in profile:
            profile["ikeDhGroup"] = map_ike_dh_group(profile["ikeDhGroup"])

        # Map IPSec algorithms
        if "ipsecEncryptionAlg" in profile:
            profile["ipsecEncryptionAlg"] = map_ipsec_encryption(profile["ipsecEncryptionAlg"])

        if "ipsecIntegrity" in profile:
            profile["ipsecIntegrity"] = map_ipsec_integrity(profile["ipsecIntegrity"])

        if "perfectForwardSecrecy" in profile:
            profile["perfectForwardSecrecy"] = map_perfect_forward_secrecy(profile["perfectForwardSecrecy"])

    return mapped_profile


def map_vpn_profiles(vpn_profiles):
    """
    Map a list of VPN profiles from system format to user-friendly format.

    Args:
        vpn_profiles (list): List of VPN profiles with system format algorithm names

    Returns:
        list: List of VPN profiles with user-friendly format algorithm names
    """
    return [map_vpn_profile(profile) for profile in vpn_profiles]
