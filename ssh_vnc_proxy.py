import paramiko
import socket
import threading
import sys
import os

ssh_tunnels = {}

def create_ssh_tunnel(machine_id, host, port, ssh_username, ssh_password, vnc_port=5900):
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(host, port=port, username=ssh_username, password=ssh_password, timeout=10)
        
        transport = ssh.get_transport()
        
        local_port = 6000 + machine_id
        
        channel = transport.open_channel('direct-tcpip', (host, vnc_port), ('localhost', local_port))
        
        ssh_tunnels[machine_id] = {
            'ssh': ssh,
            'channel': channel,
            'local_port': local_port
        }
        
        print(f"SSH tunnel created for machine {machine_id}: localhost:{local_port} -> {host}:{vnc_port}")
        return local_port
        
    except Exception as e:
        print(f"Failed to create SSH tunnel: {e}")
        return None

def close_ssh_tunnel(machine_id):
    if machine_id in ssh_tunnels:
        tunnel = ssh_tunnels[machine_id]
        try:
            tunnel['channel'].close()
            tunnel['ssh'].close()
        except:
            pass
        del ssh_tunnels[machine_id]
        print(f"SSH tunnel closed for machine {machine_id}")

def handle_client(client_socket, target_host, target_port):
    try:
        target_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        target_socket.connect((target_host, target_port))
        
        def forward(source, destination):
            while True:
                try:
                    data = source.recv(4096)
                    if not data:
                        break
                    destination.sendall(data)
                except Exception as e:
                    break
        
        thread1 = threading.Thread(target=forward, args=(client_socket, target_socket))
        thread2 = threading.Thread(target=forward, args=(target_socket, client_socket))
        
        thread1.start()
        thread2.start()
        
        thread1.join()
        thread2.join()
    finally:
        client_socket.close()
        target_socket.close()

def start_proxy(listen_port, target_host, target_port):
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(('0.0.0.0', listen_port))
    server_socket.listen(5)
    
    print(f"TCP proxy listening on port {listen_port}")
    print(f"Forwarding to {target_host}:{target_port}")
    
    while True:
        client_socket, addr = server_socket.accept()
        print(f"Accepted connection from {addr}")
        
        handler_thread = threading.Thread(
            target=handle_client,
            args=(client_socket, target_host, target_port)
        )
        handler_thread.start()

if __name__ == "__main__":
    if len(sys.argv) < 7:
        print("Usage: python ssh_vnc_proxy.py <machine_id> <ssh_host> <ssh_port> <ssh_username> <ssh_password> <vnc_port>")
        sys.exit(1)
    
    machine_id = int(sys.argv[1])
    ssh_host = sys.argv[2]
    ssh_port = int(sys.argv[3])
    ssh_username = sys.argv[4]
    ssh_password = sys.argv[5]
    vnc_port = int(sys.argv[6]) if len(sys.argv) > 6 else 5900
    
    local_port = create_ssh_tunnel(machine_id, ssh_host, ssh_port, ssh_username, ssh_password, vnc_port)
    
    if local_port:
        try:
            start_proxy(local_port + 100, 'localhost', local_port)
        finally:
            close_ssh_tunnel(machine_id)