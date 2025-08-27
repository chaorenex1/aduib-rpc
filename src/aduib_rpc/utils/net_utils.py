import socket
from lib2to3.fixer_util import find_root


class NetUtils:
    @classmethod
    def get_local_ip(cls):
        """
        获取本地IP地址（适用于大部分场景）
        """
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # 连接外部地址（不实际发包），以此确定本地IP
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        finally:
            s.close()
        return ip

    @classmethod
    def find_free_port(cls,start_port=5002, max_port=6000):
        """
        从 start_port 开始查找可用端口
        """
        if start_port >= max_port:
            raise RuntimeError("没有找到可用端口")
        for port in range(start_port, max_port+1):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.bind(("", port))  # 绑定测试
                    return port
                except OSError:
                    find_root(start_port+1, max_port)
        raise RuntimeError("没有找到可用端口")

    @classmethod
    def get_ip_and_free_port(cls, start_port=5002, max_port=6000)-> tuple[str, int]:
        """
        获取本地IP地址和可用端口
        :param start_port:
        :param max_port:
        :return:
        """
        ip = cls.get_local_ip()
        port = cls.find_free_port(start_port, max_port)
        return ip, port


if __name__ == "__main__":
    ip = NetUtils.get_local_ip()
    port = NetUtils.find_free_port(5002, 5100)
    print(f"本地IP: {ip}, 可用端口: {port}")
