"""Server part of the interface-proxy library that listens for commands, executes them, and returns the results."""

from __future__ import annotations

import asyncio
import builtins
import json
import logging
import sys
import traceback
from typing import Any, cast

from tblib import Traceback


class Server:
    """This class parses commands, runs them on the target modules, and returns the results.

    Commands and results are communicated in a json structure. Objects will not be transferred, but
    instead stored locally and only a reference is transferred, which from there on can be used in
    function arguments.
    """

    _target_classes: dict[str, object]
    _local_variables: dict[str, Any]
    _local_variable_count: int

    def __init__(self, served_objects: dict[str, Any]) -> None:
        """Initialize the server and specify the objects that shall be available in commands.

        Args:
            served_objects: Dictionary mapping from names to objects that shall be available over the proxy.
        """
        self._target_classes = served_objects
        self._local_variable_count = 0
        self._local_variables = {}

    def return_target(self, target_class: str) -> object:
        """Obtain the target class from the name.

        Args:
            target_class: The object to retrieve by their name.

        Returns:
            The requested object or module.
        """
        return self._target_classes[target_class]

    def convert_argument_from_json(self, arg: Any) -> object:  # noqa: ANN401  # JSON can be complicated
        """Convert a json (loaded) object to an actual python object.

        Supports lists, tuples (also treated as lists), dicts, builtin primitives.
        Objects that were referenced previously, are retrieved by their reference.

        Args:
            arg: The object after loaded from json.

        Returns:
            The actual python object.
        """
        if isinstance(arg, list):
            return [self.convert_argument_from_json(element) for element in arg]
        arg_type = arg["type"]
        arg_value = arg["value"]
        if arg_type == "RemoteVar":
            return self._local_variables[str(arg_value)]
        if arg_type == "NoneType":
            return None
        return getattr(builtins, arg_type)(arg_value)

    def convert_argument_to_json(self, arg: object) -> Any:  # noqa: ANN401  # JSON can be complicated
        """Convert a python object to a json-serializable object.

        Supports lists, tuples (also treated as lists), dicts, builtin primitives.
        Objects are stored locally and given a reference for future use.

        Args:
            arg: The python object to serialize.

        Returns:
            A json-serializable object.
        """
        # tuples become lists in json anyway, so treat them the same here
        if isinstance(arg, (list, tuple)):
            return [self.convert_argument_to_json(element) for element in arg]
        arg_type = type(arg).__name__
        # complex types are not transferred but saved locally and only a reference is sent back
        if not hasattr(builtins, arg_type) and arg_type != "NoneType":
            self._local_variable_count += 1
            self._local_variables[str(self._local_variable_count)] = arg
            arg_type = "RemoteVar"
            arg = str(self._local_variable_count)
        return {
            "type": arg_type,
            "value": arg,
        }

    def run_command(self, command: str) -> str:
        """Run a command that is encoded in a JSON format.

        If the command does not reference a function, the attribute value is returned instead.

        Args:
            command: JSON representation of the command.

        Returns:
            Return value of the executed command.
        """
        command_json = json.loads(command)
        if "function" not in command_json:
            return self.get_attribute(command)
        target_class = command_json["class"]
        function = command_json["function"]
        args_raw = command_json.get("args", [])
        args = [self.convert_argument_from_json(arg) for arg in args_raw]
        kwargs_raw = command_json.get("kwargs", {})
        kwargs = {k: self.convert_argument_from_json(v) for k, v in kwargs_raw.items()}
        target_function = getattr(self.return_target(target_class), function)
        result = target_function(*args, **kwargs)
        ret = self.convert_argument_to_json(result)
        return json.dumps(
            {
                "status": "success",
                "return": ret,
            },
        )

    def get_attribute(self, command: str) -> str:
        """Get the value of attribute specified in the command.

        If the attribute specifies a callable, the function returns that the object is an callable, allowing
        the client to send another request with the desired arguments.

        Args:
            command: JSON representation of the class and attribute to retrieve.

        Returns:
            The value of the attribute in a JSON string.
        """
        command_json = json.loads(command)
        target_class = command_json["class"]
        attribute = command_json["attribute"]
        target_attribute = getattr(self.return_target(target_class), attribute)
        if callable(target_attribute):
            ret = {
                "type": "callable",
                "value": None,
            }
        else:
            ret = self.convert_argument_to_json(target_attribute)
        return json.dumps(
            {
                "status": "success",
                "return": ret,
            },
        )


server: Server | None = None


async def handle_request(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    """Read the command from the client, run it, and return the server response.

    Args:
        reader: Input Buffer.
        writer: Output Buffer.

    Returns:
        Response from the server.
    """
    if server is None:
        msg = "Server object was not initialized properly."
        raise RuntimeError(msg)
    try:
        data = await reader.readline()
        if not data:
            # for pipes handle_request can get called even on a connect, then the string is empty
            # and nothing should be done
            return
        command = data.decode("utf-8")
        result_string = server.run_command(command)
        result = result_string.encode("utf-8")
    except Exception:  # noqa: BLE001  # no matter what, server should forward all kinds of exceptions to the client
        traceback.print_exc()
        et, ev, tb = sys.exc_info()
        message = repr(ev)
        tb = Traceback(tb).to_dict()
        result = json.dumps(
            {
                "status": "exception",
                "message": message,
                "traceback": tb,
            },
        ).encode("utf-8")
    writer.write(result + b"\n")
    await writer.drain()

    writer.close()


async def main_tcp(local_ip: str, local_port: int) -> None:
    """Start a TCP server to handle requests from the client.

    Args:
        local_ip: IP-Address of the interface to listen on.
        local_port: Port number to listen on.
    """
    tcp_server = await asyncio.start_server(handle_request, local_ip, local_port)

    addr = tcp_server.sockets[0].getsockname()
    logging.info(f"Serving on {addr}")

    async with tcp_server:
        await tcp_server.serve_forever()


async def main_pipe(pipe_name: str) -> None:
    """Start a local server that is listening on a named pipe.

    The named pipe itself will also be created in a duplex mode.

    Args:
        pipe_name: The name of the pipe to create and listen on.
    """
    # ProactorEventLoop is required for pipes and was set in run_server()
    loop = cast(asyncio.ProactorEventLoop, asyncio.get_event_loop())

    def factory() -> asyncio.StreamReaderProtocol:
        return asyncio.StreamReaderProtocol(asyncio.StreamReader(), handle_request)

    await loop.start_serving_pipe(factory, rf"\\.\PIPE\{pipe_name}")
    logging.info(f"Serving on pipe {pipe_name}")

    _serving_forever_fut = loop.create_future()
    await _serving_forever_fut


def run_server(
    served_objects: dict[str, Any],
    *,
    local_ip: str = "",
    local_port: int = -1,
    pipe_name: str = "",
) -> None:
    """Start serving the passed objects via TCP or named pipes.

    Args:
        served_objects: Dictionary of the names and objects to serve.
        local_ip: IP address of the interface to listen on. Required for TCP Server.
        local_port: Port number to listen on. Required for TCP Server.
        pipe_name: Name of the named pipe to communicate with the client. Required for Pipe Server.
    """
    global server  # noqa: PLW0603
    if server is not None:
        msg = "The server cannot be run more than once."
        raise RuntimeError(msg)
    server = Server(served_objects)
    if local_ip:
        coro = main_tcp(local_ip, local_port)
    elif pipe_name:
        loop = asyncio.ProactorEventLoop()
        asyncio.set_event_loop(loop)
        coro = main_pipe(pipe_name)
    else:
        msg = "Did not specify any address on which to listen."
        raise ValueError(msg)
    asyncio.run(coro)
