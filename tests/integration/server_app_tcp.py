"""Run the server listening on a local port."""

from server_app import served_objects

from interface_proxy.server import run_server

run_server(served_objects, local_ip="127.0.0.1", local_port=8888)
