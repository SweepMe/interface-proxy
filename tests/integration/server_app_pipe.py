"""Run the server listening on a named pipe."""

from server_app import served_objects

from interface_proxy.server import run_server

run_server(served_objects, pipe_name="interface-proxy-test-pipe")
