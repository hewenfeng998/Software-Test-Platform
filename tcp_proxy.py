import socket
import threading

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
    start_proxy(5902, 'localhost', 5900)