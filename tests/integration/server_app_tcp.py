from interface_proxy.server import run_server

from server_app import served_objects

run_server(served_objects, local_ip="127.0.0.1", local_port=8888)
