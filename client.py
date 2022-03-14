import socket


class TestSocket:

    def __init__(self) -> None:
        print("INIT TEST CLIENT")

    def test_msg(self):
        sock = socket.socket()
        sock.connect(('localhost', 9090))
        sock.send('hello, world!'.encode())
        data = sock.recv(1024)
        sock.close()
        print(data.decode())


if __name__ == "__main__":
    client = TestSocket()
    client.test_msg()