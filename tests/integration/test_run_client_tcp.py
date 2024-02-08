"""Test that starts a server for different protocols and initializes the proxies, where the tests are run."""

import logging
import sys
from pathlib import Path
from typing import Any

from interface_proxy.client import PipeProxy, RunServer, TCPProxy

logging.basicConfig(stream=sys.stdout)
# remove for production use:
logging.getLogger("InterfaceProxyClient").setLevel(logging.INFO)


class BaseTestClientServerCommunication:
    """Base class defining test cases independent of communication protocol."""

    t: Any
    p: Any
    rs: RunServer

    def test_call(self) -> None:
        """Just call a method that executes something on the server."""
        self.t.do_something("wonder")

    def test_doubling(self) -> None:
        """Call a function on the server that takes an argument, transforms it, and returns the result."""
        assert self.t.get_double(21) == 42

    def test_two_objects(self) -> None:
        """Create objects on the server, and work with them without interference."""
        obj1 = self.t.create_complicated_object()
        obj2 = self.t.create_complicated_object()
        self.t.set_co(obj1, 42)
        self.t.set_co(obj2, self.p.PARAM1)
        assert self.t.get_co(obj1) == 42
        assert self.t.get_co(obj2) == 4  # PARAM1

    def teardown_class(self) -> None:
        """Let the RunServer know that the server process can be terminated."""
        self.rs.release(self)


class TestClientServerCommunicationPipe(BaseTestClientServerCommunication):
    """Test implementation for Pipe Proxy."""

    def setup_class(self) -> None:
        """Start the Pipe server and create Proxy objects for the tests."""
        self.rs = RunServer(self, server_py=Path(__file__).parent / "server_app_pipe.py")
        self.t = PipeProxy("TargetClass", "interface-proxy-test-pipe")
        self.p = PipeProxy("Param", "interface-proxy-test-pipe")


class TestClientServerCommunicationTCP(BaseTestClientServerCommunication):
    """Test implementation for TCP Proxy."""

    def setup_class(self) -> None:
        """Start the TCP server and create Proxy objects for the tests."""
        self.rs = RunServer(self, server_py=Path(__file__).parent / "server_app_tcp.py")
        self.t = TCPProxy("TargetClass", "127.0.0.1", 8888)
        self.p = TCPProxy("Param", "127.0.0.1", 8888)
