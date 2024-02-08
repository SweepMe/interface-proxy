from interface_proxy.server import run_server

from server_app import served_objects

run_server(served_objects, pipe_name="interface-proxy-test-pipe")
