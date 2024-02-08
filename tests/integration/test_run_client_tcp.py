import logging, sys
from pathlib import Path
from typing import Any

from interface_proxy.client import TCPProxy, PipeProxy, RunServer

logging.basicConfig(stream=sys.stdout)
# remove for production use:
logging.getLogger("InterfaceProxyClient").setLevel(logging.DEBUG)


class BaseTestClientServerCommunication:
    t: Any
    p: Any
    def test_call(self):
        self.t.do_something("wonder")

    def test_doubling(self):
        assert self.t.get_double(21) == 42

    def test_two_objects(self):
        obj1 = self.t.create_complicated_object()
        obj2 = self.t.create_complicated_object()
        self.t.set_co(obj1, 42)
        self.t.set_co(obj2, self.p.PARAM1)
        assert self.t.get_co(obj1) == 42
        assert self.t.get_co(obj2) == 4  # PARAM1


class TestClientServerCommunicationPipe(BaseTestClientServerCommunication):
    def setup_class(self) -> None:
        self.rs = RunServer(self, server_py=Path(__file__).parent / "server_app_pipe.py")
        self.t = PipeProxy("TargetClass", "interface-proxy-test-pipe")
        self.p = PipeProxy("Param", "interface-proxy-test-pipe")

    def teardown_class(self) -> None:
        self.rs.release(self)


class TestClientServerCommunicationTCP(BaseTestClientServerCommunication):
    def setup_class(self) -> None:
        self.rs = RunServer(self, server_py=Path(__file__).parent / "server_app_tcp.py")
        self.t = TCPProxy("TargetClass", "127.0.0.1", 8888)
        self.p = TCPProxy("Param", "127.0.0.1", 8888)

    def teardown_class(self) -> None:
        self.rs.release(self)
