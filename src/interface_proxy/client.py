"""Client part of the interface-proxy.

This module provides Proxy classes that transparently behave like the module on the server side, and a
convenience class to start and terminate the server process, if it is running on the same machine.
"""

from __future__ import annotations

import abc
import asyncio
import builtins
import contextlib
import json
import logging
import os
import subprocess
import sys
import time
from abc import ABC
from pathlib import Path
from typing import Any, ClassVar, cast

import pywintypes
import win32pipe
import winerror
from six import reraise
from tblib import Traceback

logger = logging.getLogger("InterfaceProxyClient")


class RemoteError(Exception):
    """A generic exception that is raised when the server-side code encountered an exception.

    As there is no universal specification on how an exception (in particular custom exception)
    looks like and can be created, we have to use a generic one
    and print the original traceback and exception type as the message.
    """


class RemoteVar:
    """A class that represents an object stored on the server side application, referenced by its name."""

    def __init__(self, variable_reference_name: str) -> None:
        """Create a Reference to an object on the remote side.

        Args:
            variable_reference_name: The name of the variable on the server.
        """
        self.variable_reference_name = variable_reference_name


class RunServer:
    """A helper class that simplifies starting and terminating the server process.

    For one server (specified by exe or py script), always the same RunServer instance is returned.
    At the end, the user must call the release() method to signal that it's safe to kill the server process.
    """

    _instances: ClassVar[dict[str, RunServer]] = {}
    _server_py = None
    _server_exe = None
    _process: subprocess.Popen[bytes] | None = None
    _references: set[int]

    def __new__(cls, _: object | int, server_exe: Path | None = None, server_py: Path | None = None) -> RunServer:
        """Lookup if an instance was already created for the give exe or py path and return it, or create a new one.

        This class is something like a per-path singleton.

        Args:
            _:
            server_exe: Path to the server as an executable.
            server_py: Path to the server as a python script.
        """
        obj = cls._instances.get(str(server_exe), None) or cls._instances.get(str(server_py), None)
        if not obj:
            obj = super().__new__(cls)
            obj._references = set()  # noqa: SLF001
        if cls._instances.get(str(server_exe), obj) != cls._instances.get(str(server_py), obj):
            msg = (
                "Mismatch between exe and py version. Either the exe does not belong to the py version, or"
                "RunServer was previously called with different arguments."
            )
            raise ValueError(msg)

        if server_exe:
            cls._instances[str(server_exe)] = obj
        if server_py:
            cls._instances[str(server_py)] = obj

        return obj

    def __init__(self, caller: object | int, server_exe: Path | None = None, server_py: Path | None = None) -> None:
        """Start up a server if it is not running already.

        The calling instance needs to pass a reference to itself as the caller. At the end, the caller needs to call
        the release() method with it own reference again. If all callers have called the release() method, the
        server will be terminated.

        Args:
            caller: The instance that was requesting the RunServer.
            server_exe: Path to the server as an executable.
            server_py: Path to the server as a python script.
        """
        self.check_server_path(self._server_exe, server_exe)
        self.check_server_path(self._server_py, server_py)
        if server_exe:
            self._server_exe = server_exe
        if server_py:
            self._server_py = server_py

        if not self._process or self._process.poll() is not None:
            # process was never started or it crashed
            self.run_server()

        self._references.add(self.get_id(caller))

    def get_id(self, caller: object | int) -> int:
        """Make the caller an integer.

        If it already was an integer, the integer itself is returned. Otherwise the id of the object is used.
        This could lead to conflicts, but is unlikely and ignored here.

        Args:
            caller: Instance that was calling the RunServer, or a unique integer.

        Returns:
            An almost unique integer for each caller.
        """
        if isinstance(caller, object):
            return id(caller)
        return caller

    def check_server_path(self, previous: Path | None, new: Path | None) -> None:
        """Verify that exe and py version do not change over the lifetime of the RunServer instance.

        Args:
            previous: The current (previous) path.
            new: The new path.
        """
        if not previous or not new:
            return
        if previous != new:
            msg = (
                f"The server has previously been called with path {previous}, but was now called "
                f"with path {new}. One instance can only manage a single server."
            )
            raise ValueError(msg)

    def get_exe_command(self) -> list[os.PathLike[str] | str]:
        """Assemble the run command for the subprocess call in case of an exe server.

        Returns:
            The run command that can be passed to the first argument of the subprocess call.
        """
        if not self._server_exe:
            msg = "The server executable path has not been initialized properly. This should not have happened."
            raise RuntimeError(msg)
        return [self._server_exe]

    def get_python_interpreter(self) -> Path | None:
        """Get the path to the interpreter of the current process.

        Returns:
            Path to the python interpreter of the current process, or None if the current interpreter is not python.
        """
        interpreter = Path(sys.executable)
        if interpreter.name.lower() == "python.exe":
            return interpreter
        return None

    def get_py_command(self) -> list[os.PathLike[str] | str]:
        """Assemble the run command for the subprocess call in case of an py script server.

        Returns:
            The run command that can be passed to the first argument of the subprocess call.
        """
        if not self._server_py:
            msg = "The server script path has not been initialized properly. This should not have happened."
            raise RuntimeError(msg)
        interpreter = self.get_python_interpreter()
        if not interpreter:
            msg = "No interpreter could be found. Unable to start python script server."
            raise RuntimeError(msg)
        return [interpreter, str(self._server_py.resolve())]

    def terminate_server(self) -> None:
        """Terminate the server process, if it is still running."""
        if self._process and self._process.poll() is None:
            try:
                logger.info("Terminating server")
                self._references = set()
                self._process.terminate()
            except Exception:
                logger.exception("Failed to terminate running server process. You may need to restart your PC.")

    def run_server(self) -> None:
        """Start the server."""
        self.terminate_server()
        if self._server_exe and self._server_exe.is_file():
            cmd = self.get_exe_command()
            cwd = self._server_exe.parent
            flags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
            logger.info("Starting exe server")
        elif not self.get_python_interpreter():
            # exe could not be found, and there is no python interpreter to run the py version
            msg = f"Could not find the server to run, as {self._server_exe} does not exist."
            raise FileNotFoundError(msg)
        elif self._server_py and self._server_py.is_file():
            cmd = self.get_py_command()
            cwd = self._server_py.parent
            flags = subprocess.CREATE_NEW_CONSOLE
            logger.info("Starting py server")
        else:
            msg = f"Could not find the server to run, as neither {self._server_exe} nor {self._server_py} exist."
            raise FileNotFoundError(msg)
        # cmd was constructed from path objects that were valid files
        self._process = subprocess.Popen(cmd, cwd=cwd, creationflags=flags)  # noqa: S603

    def release(self, caller: object | int) -> None:
        """Notify the RunServer that the caller no longer needs the server.

        The server process will be terminated when the last caller notified the RunServer about the release.

        Args:
            caller: The instance that previously called RunServer().
        """
        with contextlib.suppress(KeyError):
            self._references.remove(self.get_id(caller))
        if not self._references:
            self.terminate_server()

    def __del__(self) -> None:
        """Terminate the associated server process when the RunServer instance is destroyed."""
        self.terminate_server()


class Proxy(ABC):
    """A class that forwards all attribute and function calls to a server."""

    _target_class: str

    def __init__(self, target_class: str) -> None:
        """Create a proxy object for the specified object.

        Args:
            target_class: The name by which the server knows the object or module.
        """
        self._target_class = target_class

    def _convert_argument_from_json(self, arg: Any) -> object:  # noqa: ANN401  # JSON can be complicated
        """Convert a json (loaded) object to an actual python object.

        Supports lists, tuples (also treated as lists), dicts, builtin primitives.
        Objects that were referenced previously, are retrieved by their reference.

        Args:
            arg: The object after loaded from json.

        Returns:
            The actual python object.
        """
        if isinstance(arg, list):
            return [self._convert_argument_from_json(element) for element in arg]
        arg_type = arg["type"]
        arg_value = arg["value"]
        if arg_type == "RemoteVar":
            return RemoteVar(arg_value)
        if arg_type == "NoneType":
            return None
        return getattr(builtins, arg_type)(arg_value)

    def _convert_argument_to_json(self, arg: object) -> Any:  # noqa: ANN401  # JSON can be complicated
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
            return [self._convert_argument_to_json(element) for element in arg]
        arg_type = type(arg).__name__
        # complex types are not transferred but saved locally and only a reference is sent back
        if arg_type == "RemoteVar":
            arg = cast(RemoteVar, arg)
            arg = arg.variable_reference_name
        return {
            "type": arg_type,
            "value": arg,
        }

    def _send_to_server(self, command: str) -> str:
        return self._send_to_server_binary(command.encode("utf-8")).decode("utf-8")

    @abc.abstractmethod
    def _send_to_server_binary(self, command: bytes) -> bytes: ...

    def unpack_result(self, response: str) -> Any:  # noqa: ANN401  # JSON can be complicated.
        """Convert a string from the server to a JSON object.

        If there was an exception on the server, a RemoteError is raised with the details of the remote exception.

        Args:
            response: String retrieved from the server.

        Returns:
            An JSON object representing the response from the server.
        """
        result = json.loads(response)
        status = result.get("status", "invalid")
        if status == "success":
            return result
        if status == "exception":
            message = result["message"]

            tb = Traceback.from_dict(result["traceback"]).as_traceback()

            reraise(
                RemoteError,
                RemoteError(f"Server-side processing failed with {message}"),
                tb,
            )

        msg = "Error decoding the response from the server"
        raise RuntimeError(msg)

    def __getattr__(self, function: str) -> Any:  # noqa: ANN401
        """Forward all requests to get an attribute to the server.

        Attributes that start with an underscore are ignored by this function. Private members should not be accessed
        from the outside, and furthermore this breaks debugging of the Proxy class.

        Args:
            function: The name of the attribute to get.

        Returns:
            The value of the requested attribute, or a callable that behaves like the function on the server if
            the attribute is callable on the server.
        """

        def handle_call(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
            args = args or ()
            kwargs = kwargs or {}
            command_json = {
                "class": self._target_class,
                "function": function,
                "args": [self._convert_argument_to_json(arg) for arg in args],
                "kwargs": {k: self._convert_argument_to_json(v) for k, v in kwargs.items()},
            }
            command = json.dumps(command_json)
            logger.debug(f"Request: {command}")
            result = self._send_to_server(command)
            logger.debug(f"Response: {result}")
            result_json = self.unpack_result(result)
            return self._convert_argument_from_json(result_json["return"])

        if function[0] != "_":
            # try to determine if it is an attribute and not a function
            command_json = {
                "class": self._target_class,
                "attribute": function,
            }
            command = json.dumps(command_json)
            result = self._send_to_server(command)
            result_json = self.unpack_result(result)
            if result_json["return"]["type"] == "callable":
                return handle_call
            logger.debug(f"Request: {command}")
            logger.debug(f"Response: {result}")
            return self._convert_argument_from_json(result_json["return"])
        return None


class TCPProxy(Proxy):
    """Proxy that communicates with a server via TCP sockets."""

    def __init__(self, target_class: str, address: str, port: int) -> None:
        """Create a proxy object for the specified object.

        Args:
            target_class: The name by which the server knows the object or module.
            address: The IP address of the server.
            port: The port number where the server can be reached.
        """
        super().__init__(target_class)
        self.loop = asyncio.new_event_loop()
        self._target_class = target_class
        self.address = address
        self.port = port

    def __del__(self) -> None:
        """Clean up the asyncio loop that was used for communicating with the server asynchronously."""
        self.loop.close()

    async def _async_send_to_server(self, command: bytes) -> bytes:
        reader, writer = await asyncio.open_connection(self.address, self.port)

        writer.write(command + b"\n")
        await writer.drain()

        data = await reader.readline()

        writer.close()
        return data

    def _send_to_server_binary(self, command: bytes) -> bytes:
        return self.loop.run_until_complete(self._async_send_to_server(command))


class PipeProxy(Proxy):
    """Proxy that communicates with a server via TCP sockets."""

    MAX_TIMEOUT = 2.0

    def __init__(self, target_class: str, pipe_name: str) -> None:
        """Create a proxy object for the specified object.

        Args:
            target_class: The name by which the server knows the object or module.
            pipe_name: The name of the pipe to communicate with the server.
        """
        super().__init__(target_class)
        self._target_class = target_class
        self.pipe_name = rf"\\.\PIPE\{pipe_name}"

    def _send_to_server_binary(self, command: bytes) -> bytes:
        delay = 0.03
        while True:
            try:
                return win32pipe.CallNamedPipe(self.pipe_name, command + b"\n", 2**16, 5000)  # type: ignore

            except pywintypes.error as e:
                if e.winerror != winerror.ERROR_FILE_NOT_FOUND:
                    raise
                if delay > self.MAX_TIMEOUT:
                    raise
                time.sleep(delay)
                delay *= 1.5
