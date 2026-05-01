"""
vpn.py — QR generation, peer management helpers.
"""
import base64
import io
import re
import logging

logger = logging.getLogger(__name__)


def get_ip_from_conf(conf_text: str) -> str:
    """Extract client IP from WireGuard .conf text."""
    match = re.search(r'Address\s*=\s*([\d.]+)', conf_text)
    return match.group(1) if match else "N/A"


def get_pubkey_from_conf(conf_text: str) -> str | None:
    """Derive WireGuard public key from private key in .conf text."""
    match = re.search(r'PrivateKey\s*=\s*(\S+)', conf_text)
    if not match:
        logger.warning("PrivateKey not found in conf")
        return None
    try:
        from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
        raw = base64.b64decode(match.group(1))
        priv = X25519PrivateKey.from_private_bytes(raw)
        pub_raw = priv.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        return base64.b64encode(pub_raw).decode()
    except Exception as e:
        logger.error(f"Failed to derive pubkey: {e}")
        return None


def disconnect_peer(conf_text: str) -> bool:
    """Remove a WireGuard peer from AmneziaWG container when key is revoked.

    Uses Python Docker SDK to exec into the AWG container and run:
      awg set <interface> peer <pubkey> remove
    Returns True on success, False on any error (non-fatal).
    """
    from config import AWG_CONTAINER, AWG_INTERFACE

    pubkey = get_pubkey_from_conf(conf_text)
    if not pubkey:
        logger.warning("disconnect_peer: could not derive pubkey, skipping")
        return False

    ip = get_ip_from_conf(conf_text)

    try:
        import docker
        client = docker.DockerClient(base_url="unix://var/run/docker.sock")
        container = client.containers.get(AWG_CONTAINER)

        # 1. Мгновенная блокировка — дропаем трафик по IP клиента
        if ip and ip != "N/A":
            for chain in ("FORWARD", "INPUT"):
                container.exec_run(
                    ["iptables", "-I", chain, "-s", ip, "-j", "DROP"],
                    user="root", privileged=True
                )
            logger.info(f"iptables DROP added for ip={ip}")

        # 2. Удаляем пира из WireGuard — запрет на новые handshake
        result = container.exec_run(
            ["wg", "set", AWG_INTERFACE, "peer", pubkey, "remove"],
            user="root",
            privileged=True
        )
        if result.exit_code == 0:
            logger.info(f"Peer disconnected: pubkey={pubkey[:12]}… ip={ip}")
            return True
        else:
            logger.warning(
                f"awg set peer remove failed (exit={result.exit_code}): "
                f"{result.output.decode().strip()}"
            )
            return False
    except Exception as e:
        logger.error(f"disconnect_peer error: {e}")
        return False


def generate_qr(data: str) -> bytes:
    """Generate PNG QR-code bytes for the given string."""
    import qrcode
    qr = qrcode.make(data)
    buf = io.BytesIO()
    qr.save(buf, format='PNG')
    return buf.getvalue()
