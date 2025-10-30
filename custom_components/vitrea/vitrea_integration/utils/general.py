# TODO - Get Controllers on network.
import socket
import struct
import binascii
import netifaces


def get_interface_addresses():
    interface_addresses = []
    interfaces = netifaces.interfaces()
    for interface in interfaces:
        addrs = netifaces.ifaddresses(interface)
        if netifaces.AF_INET in addrs:
            for link in addrs[netifaces.AF_INET]:
                if "addr" in link and "broadcast" in link:
                    interface_addresses.append((link["addr"], link["broadcast"]))
    return interface_addresses


def discover_vitrea_devices(message):
    UDP_PORT = 11505
    interface_addresses = get_interface_addresses()
    result = []
    for local_addr, broadcast_addr in interface_addresses:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.settimeout(5)
            sock.bind((local_addr, 0))
            sock.sendto(message.encode(), (broadcast_addr, UDP_PORT))

            while True:
                try:
                    data, addr = sock.recvfrom(1024)
                    print(f"Response from {addr}: {data.hex()}")
                    result.append(addr)
                except socket.timeout:
                    break

        except Exception as e:
            print(f"Error on interface {local_addr}: {e}")
        finally:
            sock.close()
    return result

def scale_to_100(value: int) -> int:
    # Ensure the value is within the expected range
    if value < 1:
        value = 1
    elif value > 255:
        value = 255

    # Map from 1-255 scale to 1-100 scale
    # Subtract 1 from the value and the range start to start from 0, scale, then add 1 to return to 1-100 range
    return int(((value - 1) / (255 - 1)) * (100 - 1) + 1)


def scale_to_255(value: int) -> int:
    # Ensure the value is within the expected range
    if value < 1:
        value = 1
    elif value > 100:
        value = 100

    # Map from 1-100 scale back to 1-255 scale
    return int(((value - 1) / (100 - 1)) * (255 - 1) + 1)


# Example usage

# Repeat for other messages as needed

if __name__ == "__main__":
    discover_vitrea_devices("VITREA-APP")
