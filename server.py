import socket
from threading import Thread
import main as imageRecognize


def client_handler(conn, startClass: imageRecognize.Start):
    while True:
        data = conn.recv(1024)
        if not data:
            break
        params = str(data.decode(encoding='utf-16')).split("$$") #example: 0$$images/road-1.png$$0.98$$car
        print(params)
        res = startClass.start_main(int(params[0]), params[1], float(params[2]), params[3])
        print(res)
        conn.send(res.encode(encoding='utf-8'))
    conn.close()


class ServerSocket:
    startClass = imageRecognize.Start()
    PORT: int = 9090
    MAX_QUEUE: int = 1

    def __init__(self) -> None:
        print("INIT SERVER")

    def start_listen(self):
        sock = socket.socket()
        sock.bind(('', self.PORT))
        sock.listen()
        print("SERVER IS START")
        while True:
            conn, addr = sock.accept()
            th = Thread(target=client_handler, args=(conn, self.startClass,))
            th.start()
        print("SERVER CLOSE")


if __name__ == "__main__":
    serv = ServerSocket()
    th = Thread(target=serv.start_listen())
    th.start()